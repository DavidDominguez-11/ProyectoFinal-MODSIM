"""Pruebas de comportamiento del motor independiente, sin datos históricos."""
import copy
import json
import unittest

from scripts.evacuacion.motor import simulate


def network(capacity=1, destination_capacity=100, travel=2):
    return {
        'nodes': [{'id': 'a', 'x': 0, 'y': 0, 'cell': [0, 0]},
                  {'id': 'b', 'x': 1, 'y': 0, 'cell': [0, 1]}],
        'edges': [{'id': 'ab', 'u': 'a', 'v': 'b', 'length_m': 10,
                   'travel_min': travel, 'capacity': capacity, 'cells': [[0, 1]]}],
        'destinations': [{'node': 'b', 'kind': 'safe', 'capacity': destination_capacity}],
        'metadata': {},
    }


def group(identifier='g', people=2.5, ready=0):
    return {'id': identifier, 'people': people, 'node': 'a',
            'ready_min': ready, 'origin_cell': [0, 0]}


class MotorTests(unittest.TestCase):
    def run_model(self, net=None, groups=None, fire=None, **kwargs):
        return simulate(net or network(), groups if groups is not None else [group()],
                        fire if fire is not None else [[-1, -1]], **kwargs)

    def assert_mass(self, result):
        total = result['people_total']
        self.assertAlmostEqual(total, result['people_safe'] + result['people_temporary'] +
                               result['people_remaining'])
        for sample in result['history']:
            self.assertAlmostEqual(total, sample['people_safe'] + sample['people_temporary'] +
                                   sample['people_remaining'])

    def test_fractional_mass_finish_and_json(self):
        result = self.run_model(groups=[group('one', .25), group('two', 1.75)])
        self.assert_mass(result)
        self.assertEqual(result['people_safe_before_fire'], 2)
        self.assertEqual(result['evacuation_times'], [{'time_min': 2, 'people': .25},
                                                     {'time_min': 4, 'people': 1.75}])
        json.dumps(result, allow_nan=False)

    def test_fifo_capacity_and_queue_integrals(self):
        result = self.run_model(groups=[group('first'), group('second'), group('third')])
        self.assertEqual([g['finish_min'] for g in result['groups']], [2, 4, 6])
        self.assertEqual(result['queue_group_minutes'], 6)
        self.assertEqual(result['queue_person_minutes'], 15)
        self.assertEqual(result['max_queue_groups'], 2)
        self.assertEqual(result['max_queue_people'], 5)
        self.assertTrue(result['capacity_invariant'])
        self.assertEqual(result['edge_max_occupancy']['ab'], 1)

    def test_initial_closure_and_no_input_mutation(self):
        args = [network(), [group()], [[-1, -1]], ['ab']]
        before = copy.deepcopy(args)
        result = simulate(*args[:3], closed_edges=args[3])
        self.assertEqual(result['people_safe'], 0)
        self.assertEqual(result['traversals'], [])
        self.assertEqual(args, before)

    def test_mid_transit_and_equal_arrival_closures(self):
        for closure in (1, 2):
            with self.subTest(closure=closure):
                result = self.run_model(fire=[[-1, closure]])
                self.assertEqual(result['people_safe'], 0)
                self.assertEqual(result['people_exposed'], 2.5)
                self.assertEqual(result['groups'][0]['node'], 'a')
                self.assertEqual(result['traversals'][0]['end_min'], closure)
                self.assertEqual(result['traversals'][0]['outcome'], 'interrupted')
                self.assertTrue(result['no_closed_edge_traversal'])

    def test_reroute_after_interruption_and_exposure_persists(self):
        net = network(travel=4)
        net['nodes'].append({'id': 'c', 'x': 2, 'y': 0, 'cell': [0, 2]})
        net['edges'].append(dict(net['edges'][0], id='ac', v='c', travel_min=6, cells=[[0, 2]]))
        net['destinations'].append({'node': 'c', 'kind': 'safe', 'capacity': 100})
        result = self.run_model(net, fire=[[-1, 1, -1]])
        self.assertEqual(result['people_safe'], 2.5)
        self.assertEqual(result['people_safe_before_fire'], 0)
        self.assertEqual(result['groups'][0]['finish_min'], 7)
        self.assertEqual([t['edge'] for t in result['traversals']], ['ab', 'ac'])

    def test_origin_exposure_before_ready_with_displaced_node(self):
        g = group(ready=5)
        g['origin_cell'] = [0, 2]
        result = self.run_model(groups=[g], fire=[[-1, -1, 1]])
        self.assertEqual(result['people_safe'], 2.5)
        self.assertEqual(result['people_exposed'], 2.5)
        self.assertEqual(result['people_safe_before_fire'], 0)

    def test_node_fire_while_waiting(self):
        result = self.run_model(groups=[group('first'), group('waiting')], fire=[[1, -1]])
        self.assertEqual(result['people_exposed'], 2.5)
        self.assertEqual(result['people_safe'], 2.5)
        self.assertEqual(result['groups'][1]['state'], 'stranded')

    def test_temporary_is_not_safe(self):
        net = network()
        net['destinations'][0]['kind'] = 'temporary'
        result = self.run_model(net)
        self.assertEqual(result['people_temporary'], 2.5)
        self.assertEqual(result['people_safe_before_fire'], 0)
        self.assert_mass(result)

    def test_full_destination_routes_elsewhere_and_respects_full_group(self):
        net = network(destination_capacity=2.5)
        net['nodes'].append({'id': 'c', 'x': 2, 'y': 0})
        net['edges'].append(dict(net['edges'][0], id='ac', v='c', travel_min=3, cells=[]))
        net['destinations'].append({'node': 'c', 'kind': 'safe', 'capacity': 2.5})
        result = self.run_model(net, [group('one'), group('two'), group('three')])
        self.assertEqual(result['people_safe'], 5)
        self.assertEqual([g['destination'] for g in result['groups']], ['b', 'c', None])
        self.assertEqual(result['destination_people'], {'b': 2.5, 'c': 2.5})
        self.assert_mass(result)
        self.assertEqual(self.run_model(network(destination_capacity=2))['people_safe'], 0)

    def test_reservation_released_on_interrupted_route(self):
        net = network(destination_capacity=2.5, travel=4)
        net['nodes'].append({'id': 'c', 'x': 2, 'y': 0})
        net['edges'].append(dict(net['edges'][0], id='cb', u='c', travel_min=2, cells=[]))
        late = dict(group('late', ready=2), node='c')
        # Solo arde el primer tramo; el nodo destino permanece sin fuego.
        net['edges'][0]['cells'] = [[0, 2]]
        result = self.run_model(net, [group(), late], fire=[[-1, -1, 1]])
        self.assertEqual(result['people_safe'], 2.5)
        self.assertEqual(result['groups'][1]['finish_min'], 4)

    def test_transform_fallback_and_horizon(self):
        net = network()
        for node in net['nodes']:
            node.pop('cell')
        net['metadata']['transform_gdal'] = [0, 1, 0, 0, 0, 1]
        result = self.run_model(net, groups=[group(ready=5)], fire=[[1, -1]], horizon=3)
        self.assertEqual(result['people_exposed'], 2.5)
        self.assertEqual(result['people_remaining'], 2.5)
        self.assertEqual(result['history'][-1]['time_min'], 3)

    def test_determinism_tie_break_and_no_randomness(self):
        net = network()
        net['edges'].append(dict(net['edges'][0], id='aa'))
        first = self.run_model(net)
        self.assertEqual(first, self.run_model(net))
        self.assertEqual(first['traversals'][0]['edge'], 'aa')

    def test_large_shared_queue_retains_disconnected_fractional_groups(self):
        net = network(capacity=4, travel=1, destination_capacity=10000)
        net['nodes'].append({'id': 'isolated', 'x': 2, 'y': 0})
        groups = [group(str(i), .125) for i in range(50000)]
        groups.append(dict(group('isolated', .375), node='isolated'))
        result = self.run_model(net, groups, horizon=13000)
        self.assertEqual(result['people_safe'], 6250)
        self.assertEqual(result['people_remaining'], .375)
        self.assertEqual(result['groups'][-1]['state'], 'waiting')
        self.assertEqual(result['edge_max_occupancy']['ab'], 4)
        self.assertEqual(result['groups'][-2]['finish_min'], 12500)
        self.assert_mass(result)

    def test_queue_truncated_at_horizon_and_empty_population(self):
        result = self.run_model(groups=[group('one'), group('two')], horizon=1)
        self.assertEqual(result['queue_group_minutes'], 1)
        self.assertEqual(result['queue_person_minutes'], 2.5)
        self.assertEqual(result['traversals'][0]['outcome'], 'horizon')
        self.assert_mass(result)
        empty = self.run_model(groups=[])
        self.assertEqual(empty['people_total'], 0)
        self.assertEqual(empty['groups'], [])

    def test_multihop_and_safe_priority_over_nearby_temporary(self):
        net = network()
        net['nodes'].append({'id': 'c', 'x': 2, 'y': 0})
        net['edges'].append(dict(net['edges'][0], id='bc', u='b', v='c', cells=[]))
        net['destinations'] = [{'node': 'b', 'kind': 'temporary', 'capacity': 10},
                               {'node': 'c', 'kind': 'safe', 'capacity': 10}]
        result = self.run_model(net)
        self.assertEqual(result['groups'][0]['finish_min'], 4)
        self.assertEqual(result['people_safe'], 2.5)
        self.assertEqual(result['people_temporary'], 0)
        self.assertEqual([t['edge'] for t in result['traversals']], ['ab', 'bc'])

    def test_temporary_refuge_can_become_exposed(self):
        net = network()
        net['edges'][0]['cells'] = []
        net['destinations'][0]['kind'] = 'temporary'
        result = self.run_model(net, fire=[[-1, 3]])
        self.assertEqual(result['people_temporary'], 0)
        self.assertEqual(result['people_exposed'], 2.5)
        self.assertEqual(result['people_remaining'], 2.5)
        self.assert_mass(result)

    def test_full_destination_wakes_blocked_routes(self):
        net = network(destination_capacity=5.5)
        net['nodes'].append({'id': 'c', 'x': 2, 'y': 0})
        net['edges'].append(dict(net['edges'][0], id='ac', v='c', travel_min=5, cells=[]))
        net['destinations'].append({'node': 'c', 'kind': 'safe', 'capacity': 10})
        result = self.run_model(net, [group('one'), group('two'), group('three')])
        self.assertEqual([g['finish_min'] for g in result['groups']], [2, 4, 7])
        self.assertEqual(result['people_safe'], 7.5)

    def test_downstream_closure_releases_reservation_on_arrival_and_reroutes(self):
        net = network(travel=2)
        net['nodes'] += [{'id': 'c', 'x': 2, 'y': 0},
                         {'id': 'd', 'x': 3, 'y': 0}]
        net['edges'] += [dict(net['edges'][0], id='bc', u='b', v='c', cells=[[0, 2]]),
                         dict(net['edges'][0], id='bd', u='b', v='d', cells=[], travel_min=3)]
        net['destinations'] = [{'node': 'c', 'kind': 'safe', 'capacity': 2.5},
                               {'node': 'd', 'kind': 'safe', 'capacity': 2.5}]
        result = self.run_model(net, fire=[[-1, -1, 1]])
        self.assertEqual(result['people_safe'], 2.5)
        self.assertEqual(result['groups'][0]['destination'], 'd')
        self.assertEqual(result['groups'][0]['finish_min'], 5)
        self.assertEqual(result['people_exposed'], 0)

    def test_invalid_inputs_are_rejected_without_mutation(self):
        cases = []
        for field, value in [('people', 0), ('people', -1), ('people', float('nan')),
                             ('ready_min', -1), ('ready_min', float('inf'))]:
            g = group()
            g[field] = value
            cases.append((network(), [g], [[-1, -1]], {}))
        for field, value in [('capacity', 0), ('capacity', 1.5), ('travel_min', 0),
                             ('travel_min', float('inf'))]:
            net = network()
            net['edges'][0][field] = value
            cases.append((net, [group()], [[-1, -1]], {}))
        net = network(destination_capacity=float('inf'))
        cases += [(net, [group()], [[-1, -1]], {}),
                  (network(), [group(), group()], [[-1, -1]], {}),
                  (network(), [group()], [[-2, -1]], {}),
                  (network(), [group()], [[-1], [-1, -1]], {}),
                  (network(), [group()], [[-1, -1]], {'closed_edges': ['missing']}),
                  (network(), [group()], [[-1, -1]], {'horizon': -1})]
        for net, groups, fire, kwargs in cases:
            with self.subTest(case=repr((net, groups, fire, kwargs))):
                before = repr((net, groups, fire, kwargs))
                with self.assertRaises(ValueError):
                    simulate(net, groups, fire, **kwargs)
                self.assertEqual(before, repr((net, groups, fire, kwargs)))


if __name__ == '__main__':
    unittest.main()
