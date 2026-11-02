"""Contrato de integración con datos sintéticos, sin ejecutar la red real."""
import copy
import csv
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import numpy as np
from scipy.stats import t

from scripts.evacuacion import experimentos as exp

ROOT = Path(__file__).resolve().parents[1]


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'config/escenarios_evacuacion.json').read_text())
        self.contract = {'transform_gdal': [0, 1, 0, 2, 0, -1],
                         'forma_filas_columnas': [2, 2], 'horizonte_min': 480,
                         'crs': 'EPSG:32610'}
        self.network = {
            'nodes': [{'id': 'a', 'x': .5, 'y': 1.5},
                      {'id': 'b', 'x': 2, 'y': 1.5},
                      {'id': 'z', 'x': .5, 'y': .5}],
            'edges': [{'id': 'ab', 'u': 'a', 'v': 'b', 'length_m': 1,
                       'travel_min': 2, 'capacity': 1, 'cells': [[0, 1]], 'name': 'Skyway'},
                      {'id': 'ba', 'u': 'b', 'v': 'a', 'length_m': 1,
                       'travel_min': 2, 'capacity': 1, 'cells': [[0, 1]], 'name': 'SKYWAY Rd'}],
            'destinations': [{'node': 'b', 'kind': 'safe', 'capacity': 100000}],
            'metadata': {}}
        self.population = np.array([[6.25, 0], [1.e-12, 0]], dtype=np.float64)
        self.fire = np.full((30, 2, 2), -1, dtype=np.int16)
        self.seeds = np.arange(1000, 1030)

    def fixtures(self, folder):
        paths = {}
        for key, data in [('network', self.network), ('contract', self.contract),
                          ('config', self.config)]:
            paths[key] = folder / (key + '.json')
            paths[key].write_text(json.dumps(data))
        paths['grid'] = folder / 'grid.npz'
        np.savez(paths['grid'], poblacion=self.population)
        paths['fire'] = folder / 'fire.npz'
        np.savez(paths['fire'], llegada_min=self.fire, semillas=self.seeds)
        return paths

    def cli(self, paths, output, *extra):
        command = [sys.executable, str(ROOT / 'scripts/evacuacion/experimentos.py')]
        for key, path in paths.items():
            command += ['--' + key, str(path)]
        command += ['--output', str(output), *extra]
        return subprocess.run(command, text=True, capture_output=True, cwd=output.parent,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=60)

    def test_adapter_mass_remainders_connectivity_and_repeatability(self):
        original = copy.deepcopy(self.network)
        network = exp.prepare_network(self.network, self.contract)
        self.assertEqual(network['nodes'][1]['cell'], [0, 1])
        self.assertEqual(network['metadata']['transform_gdal'], self.contract['transform_gdal'])
        self.assertEqual(self.network, original)
        groups, details = exp.make_groups(self.population, network, self.contract, self.config, 2000)
        again, _ = exp.make_groups(self.population, network, self.contract, self.config, 2000)
        self.assertEqual(groups, again)
        self.assertEqual([g['people'] for g in groups], [3, 3, .25, 1.e-12])
        self.assertEqual(math.fsum(g['people'] for g in groups), math.fsum(self.population.flat))
        self.assertEqual(details['no_exit_origins'], 1)
        self.assertEqual(details['people_no_exit'], 1.e-12)
        for g in groups:
            self.assertEqual(g['ready_min'], g['alert_min'] + g['preparation_min'])
        self.assertEqual(groups[-1]['origin_cell'], [1, 0])
        self.assertIn('attachment_distance_m', details)

    def test_deterministic_tie_and_rotated_transform(self):
        network = copy.deepcopy(self.network)
        network['nodes'][0]['x'] = 0
        network['nodes'][1]['x'] = 1
        prepared = exp.prepare_network(network, self.contract)
        groups, _ = exp.make_groups(self.population, prepared, self.contract, self.config, 1)
        self.assertEqual(groups[0]['node'], 'a')
        contract = dict(self.contract, transform_gdal=[0, 1, .25, 2, .1, -1])
        prepared = exp.prepare_network(self.network, contract)
        self.assertEqual(prepared['nodes'][0]['cell'], [0, 0])

    def test_boundary_corners_single_node_and_tiny_only_mass(self):
        network = copy.deepcopy(self.network)
        network['nodes'] = [{'id': str(i), 'x': x, 'y': y}
                            for i, (x, y) in enumerate([(0, 0), (0, 2), (2, 0), (2, 2)])]
        prepared = exp.prepare_network(network, self.contract)
        self.assertEqual([n['cell'] for n in prepared['nodes']],
                         [[1, 0], [0, 0], [1, 1], [0, 1]])
        singleton = {'nodes': [self.network['nodes'][0]], 'edges': [],
                     'destinations': [{'node': 'a', 'kind': 'safe', 'capacity': 1}], 'metadata': {}}
        singleton = exp.prepare_network(singleton, self.contract)
        population = np.zeros((2, 2), dtype=np.float64)
        population[1, 1] = np.nextafter(0., 1.)
        groups, details = exp.make_groups(population, singleton, self.contract, self.config, 2000)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['people'], population[1, 1])
        self.assertEqual(groups[0]['node'], 'a')
        self.assertEqual(details['no_exit_origins'], 0)
        self.assertEqual(details['group_people_total'], population[1, 1])

    def test_one_factor_and_paired_groups(self):
        network = exp.prepare_network(self.network, self.contract)
        groups, _ = exp.make_groups(self.population, network, self.contract, self.config, 2000)
        base, bg, bc, meta = exp.scenario_inputs(network, groups, self.config, 'base')
        early, eg, ec, _ = exp.scenario_inputs(network, groups, self.config, 'early_alert')
        closed, cg, cc, cm = exp.scenario_inputs(network, groups, self.config, 'skyway_closed')
        capacity, capg, capc, capm = exp.scenario_inputs(network, groups, self.config, 'exit_capacity')
        self.assertEqual(base, early)
        self.assertEqual(base, closed)
        self.assertEqual(bg, cg)
        self.assertEqual(bg, capg)
        self.assertEqual(bc, ec)
        self.assertEqual(capc, [])
        self.assertEqual(cc, ['ab', 'ba'])
        self.assertEqual(cm['closure_edge_count'], 2)
        self.assertEqual(capm['capacity_target_node'], 'b')
        self.assertEqual(base['destinations'][0]['capacity'], 5000)
        self.assertEqual(capacity['destinations'][0]['capacity'], 10000)
        capacity['destinations'][0]['capacity'] = 5000
        self.assertEqual(base, capacity)
        for b, e in zip(bg, eg):
            self.assertAlmostEqual(b['ready_min'] - e['ready_min'], 30)
            self.assertEqual(b['preparation_min'], e['preparation_min'])
            e['ready_min'] = b['ready_min']
            e['alert_min'] = b['alert_min']
            self.assertEqual(b, e)

    def test_multiple_exits_only_one_capacity_and_only_named_corridor(self):
        network = copy.deepcopy(self.network)
        network['destinations'].append({'node': 'a', 'kind': 'safe', 'capacity': 100000})
        extra = dict(network['edges'][0], id='clark', name='Clark Rd')
        network['edges'].append(extra)
        network = exp.prepare_network(network, self.contract)
        groups, _ = exp.make_groups(self.population, network, self.contract, self.config, 2000)
        base, _, _, _ = exp.scenario_inputs(network, groups, self.config, 'base')
        alternative, _, _, meta = exp.scenario_inputs(network, groups, self.config, 'exit_capacity')
        self.assertEqual(meta['capacity_target_node'], 'a')
        differences = [(a['node'], a['capacity'], b['capacity']) for a, b in
                       zip(base['destinations'], alternative['destinations']) if a != b]
        self.assertEqual(differences, [('a', 5000, 10000)])
        _, _, closed, _ = exp.scenario_inputs(network, groups, self.config, 'skyway_closed')
        self.assertEqual(closed, ['ab', 'ba'])
        self.config['capacity_target_node'] = 'b'
        _, _, _, meta = exp.scenario_inputs(network, groups, self.config, 'exit_capacity')
        self.assertEqual(meta['capacity_target_node'], 'b')

    def test_engine_summary_invariants_queue_units_and_empty_safe(self):
        from scripts.evacuacion.motor import simulate
        network = exp.prepare_network(self.network, self.contract)
        groups, _ = exp.make_groups(self.population, network, self.contract, self.config, 2000)
        # Preparación externa anulada solo en esta prueba determinista de integrales.
        for group in groups:
            group['ready_min'] = 0
        result = simulate(network, groups, self.fire[0].tolist(), horizon=10)
        metrics = exp.summarize_replica(result)
        self.assertTrue(result['capacity_invariant'])
        self.assertTrue(result['no_closed_edge_traversal'])
        self.assertAlmostEqual(metrics['queue_group_minutes'], 16)
        self.assertAlmostEqual(metrics['queue_person_minutes'], 7 + 1.e-11)
        self.assertEqual(metrics['queue_duration_min'], 10)
        self.assertAlmostEqual(math.fsum(metrics[k] for k in
                               ('people_safe', 'people_temporary', 'people_remaining')),
                               metrics['people_total'])
        closed = simulate(network, groups, self.fire[0].tolist(), horizon=10, closed_edges=['ab', 'ba'])
        self.assertEqual(closed['traversals'], [])
        empty = exp.summarize_replica(closed)
        self.assertEqual(empty['safe_arrival_count'], 0)
        self.assertIsNone(empty['evacuation_mean_min'])
        self.assertIsNone(empty['evacuation_p50_min'])
        self.assertIsNone(empty['evacuation_p90_min'])

    def test_statistics_weighting_null_and_queue_intervals(self):
        stat = exp.confidence_interval([1, 2, 3])
        margin = float(t.ppf(.975, 2)) / math.sqrt(3)
        self.assertAlmostEqual(stat['ci95'][0], 2 - margin)
        self.assertEqual(stat['n'], 3)
        self.assertIsNone(exp.confidence_interval([1])['ci95'])
        self.assertEqual(exp.evacuation_statistics([]),
                         {'safe_arrival_count': 0, 'safe_arrival_people': 0.,
                          'evacuation_mean_min': None, 'evacuation_p50_min': None,
                          'evacuation_p90_min': None})
        weighted = exp.evacuation_statistics([{'time_min': 2, 'people': 9},
                                              {'time_min': 10, 'people': 1}])
        self.assertAlmostEqual(weighted['evacuation_mean_min'], 2.8)
        self.assertEqual(weighted['evacuation_p90_min'], 2)
        history = [{'time_min': 0, 'queue_groups': 1},
                   {'time_min': 2, 'queue_groups': 2},
                   {'time_min': 5, 'queue_groups': 0},
                   {'time_min': 10, 'queue_groups': 0}]
        self.assertEqual(exp.queue_duration(history), 5)

    def test_cli_rejects_before_output_and_preserves_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            paths = self.fixtures(folder)
            output = folder / 'absent'
            for args in [[], ['--replicas', '31'], ['--replicas', '0', '--smoke']]:
                if not args:
                    args = ['--replicas', '1']
                result = self.cli(paths, output, *args)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse(output.exists())
            output.mkdir()
            sentinel = output / 'keep.txt'
            sentinel.write_text('unchanged')
            self.seeds[1] = self.seeds[0]
            np.savez(paths['fire'], llegada_min=self.fire, semillas=self.seeds)
            result = self.cli(paths, output, '--smoke', '--replicas', '1')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(output.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_text(), 'unchanged')

    def test_invalid_inputs_preflight(self):
        mutations = [lambda: self.population.__setitem__((0, 0), -1),
                     lambda: self.fire.__setitem__((29, 0, 0), -2),
                     lambda: self.config.__setitem__('group_max_people', 0),
                     lambda: self.contract.__setitem__('forma_filas_columnas', [1, 2]),
                     lambda: self.network['edges'][0].__setitem__('capacity', 0),
                     lambda: self.network['nodes'][0].__setitem__('x', 100)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.setUp()
                mutate()
                with tempfile.TemporaryDirectory() as tmp:
                    paths = self.fixtures(Path(tmp))
                    output = Path(tmp) / 'absent'
                    result = self.cli(paths, output, '--smoke', '--replicas', '1')
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())

    def test_cli_smoke_schema_plots_reproducibility_and_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            paths = self.fixtures(folder)
            outputs = [folder / 'one', folder / 'two']
            for output in outputs:
                started = time.perf_counter()
                result = self.cli(paths, output, '--smoke', '--replicas', '1')
                elapsed = time.perf_counter() - started
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('elapsed', result.stdout)
                if output == outputs[0]:
                    print(f'SYNTHETIC_SMOKE wall={elapsed:.3f}s; ' +
                          result.stdout.strip().splitlines()[-1], flush=True)
                summary = json.loads((output / 'summary.json').read_text())
                self.assertTrue(summary['metadata']['provisional'])
                self.assertEqual(len(summary['scenarios']), 4)
                self.assertEqual(summary['metadata']['runs'][0]['fire_seed'], 1000)
                self.assertEqual(summary['metadata']['runs'][0]['preparation_seed'], 2000)
                self.assertEqual(len(summary['metadata']['input_sha256']), 5)
                for name in ['replicas.csv', 'distribution.csv', 'cdf.png', 'metrics.png', 'queues.png']:
                    self.assertGreater((output / name).stat().st_size, 0)
                self.assertEqual(len(list(output.glob('example_*.json'))), 1)
                with (output / 'distribution.csv').open() as stream:
                    distribution = list(csv.DictReader(stream))
                with (output / 'replicas.csv').open() as stream:
                    replicas = list(csv.DictReader(stream))
                for row in replicas:
                    mass = math.fsum(float(d['people']) for d in distribution
                                     if d['scenario'] == row['scenario'])
                    self.assertAlmostEqual(mass, float(row['people_safe']))
                for name in ['evacuation_mean_min', 'evacuation_p50_min', 'evacuation_p90_min']:
                    self.assertIsNone(summary['scenarios']['skyway_closed'][name]['mean'])
                    self.assertEqual(summary['scenarios']['skyway_closed'][name]['n'], 0)
            self.assertEqual((outputs[0] / 'replicas.csv').read_bytes(),
                             (outputs[1] / 'replicas.csv').read_bytes())
            self.assertEqual((outputs[0] / 'summary.json').read_bytes(),
                             (outputs[1] / 'summary.json').read_bytes())
            output = folder / 'base'
            # Config predeterminada relativa a raíz, aun con cwd temporal.
            without_config = {key: value for key, value in paths.items() if key != 'config'}
            result = self.cli(without_config, output, '--smoke', '--replicas', '1', '--scenario', 'base')
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((output / 'summary.json').read_text())
            self.assertEqual(list(summary['scenarios']), ['base'])

    def test_cli_example_is_bounded_but_full_run_products_are_exact(self):
        self.population[0, 0] = 1800.25
        self.network['edges'][0]['travel_min'] = .1
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            paths = self.fixtures(folder)
            output = folder / 'bounded'
            completed = self.cli(paths, output, '--smoke', '--replicas', '1', '--scenario', 'base')
            self.assertEqual(completed.returncode, 0, completed.stderr)
            example = json.loads((output / 'example_replica.json').read_text())
            self.assertLessEqual(len(example['input_groups']), 100)
            self.assertEqual(example['schema'], 'evacuation_representative_example')
            self.assertEqual(example['version'], 1)
            self.assertTrue(example['representative'])
            network = exp.prepare_network(self.network, self.contract)
            groups, _ = exp.make_groups(self.population, network, self.contract, self.config, 2000)
            adapted, prepared, closed, _ = exp.scenario_inputs(network, groups, self.config, 'base')
            full = exp.simulate(adapted, prepared, self.fire[0].tolist(), 480, closed)
            metrics = exp.summarize_replica(full)
            self.assertEqual(example['metrics'], metrics)
            self.assertEqual(example['input_groups'], prepared[:100])
            for key in ('groups', 'traversals'):
                self.assertGreater(len(full[key]), 100)
                self.assertEqual(example['result'][key], full[key][:100])
            self.assertGreater(len(full['history']), 481)
            history = example['result']['history']
            indices = [i * (len(full['history']) - 1) // 480 for i in range(481)]
            self.assertEqual(history, [full['history'][i] for i in indices])
            self.assertEqual(history[0], full['history'][0])
            self.assertEqual(history[-1], full['history'][-1])
            records = {'input_groups': prepared, **{k: full[k] for k in
                       ('groups', 'traversals', 'history', 'evacuation_times',
                        'edge_max_occupancy', 'destination_people')}}
            for key, records_full in records.items():
                exported = example['input_groups'] if key == 'input_groups' else example['result'].get(key, [])
                self.assertEqual(example['record_counts'][key], len(records_full))
                self.assertEqual(example['truncated'][key], len(exported) < len(records_full))
            for key, value in full.items():
                if not isinstance(value, (dict, list)):
                    self.assertEqual(example['result'][key], value)
            for key in ('evacuation_times', 'edge_max_occupancy', 'destination_people'):
                self.assertNotIn(key, example['result'])
            self.assertLess((output / 'example_replica.json').stat().st_size, 300000)
            with (output / 'replicas.csv').open() as stream:
                row = next(csv.DictReader(stream))
            summary = json.loads((output / 'summary.json').read_text())
            for key, value in metrics.items():
                self.assertEqual(float(row[key]), value)
                self.assertEqual(summary['scenarios']['base'][key]['mean'], value)
            with (output / 'distribution.csv').open() as stream:
                arrivals = list(csv.DictReader(stream))
            self.assertEqual([(float(a['time_min']), float(a['people'])) for a in arrivals],
                             [(a['time_min'], a['people']) for a in
                              sorted(full['evacuation_times'], key=lambda a: a['time_min'])])
            phases = ['phase=preflight start', 'phase=preflight done', 'phase=simulate start',
                      'phase=simulate progress', 'phase=simulate done', 'phase=distribution done',
                      'phase=example done', 'phase=plots start', 'phase=plots done',
                      'phase=experiment complete']
            positions = [completed.stdout.index(phase) for phase in phases]
            self.assertEqual(positions, sorted(positions))

    def test_config_validation_boundaries(self):
        invalid = [('group_max_people', 0), ('preparation_gamma_shape', -1),
                   ('preparation_gamma_scale_min', math.inf), ('base_alert_min', -1),
                   ('early_alert_delta_min', 0), ('early_alert_delta_min', -100),
                   ('base_exit_capacity_people', math.nan),
                   ('increased_exit_capacity_people', 5000),
                   ('preparation_seed_start', True), ('preparation_seed_start', -1),
                   ('preparation_seed_start', 1.5), ('capacity_target_node', ''),
                   ('closed_corridor', ' '), ('assumptions', {}),
                   ('distribution_bins', 0), ('distribution_bins', 10001)]
        for key, value in invalid:
            with self.subTest(key=key, value=value):
                config = dict(self.config, **{key: value})
                with self.assertRaises(ValueError):
                    exp.validate_config(config)
        network = exp.prepare_network(self.network, self.contract)
        groups, _ = exp.make_groups(self.population, network, self.contract, self.config, 2000)
        for config in [dict(self.config, capacity_target_node='missing'),
                       dict(self.config, closed_corridor='missing')]:
            with self.assertRaises(ValueError):
                exp.scenario_inputs(network, groups, config, 'base')
        with self.assertRaises(ValueError):
            exp.scenario_inputs(network, groups, self.config, 'unknown')
        with self.assertRaises(ValueError):
            exp.prepare_network(self.network, dict(self.contract, transform_gdal=[0] * 6))
        with self.assertRaises(ValueError):
            exp.prepare_network(self.network, dict(self.contract, crs='EPSG:4326'))

    def test_help_all_flags_and_preflight_more_boundaries(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/evacuacion/experimentos.py'), '--help'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        for flag in (*exp.DEFAULTS, 'replicas', 'smoke', 'scenario'):
            self.assertIn('--' + flag, result.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            paths = self.fixtures(folder)
            for bad in [np.nan, np.inf]:
                self.population[0, 0] = bad
                np.savez(paths['grid'], poblacion=self.population)
                with self.assertRaises(ValueError):
                    exp.load_inputs(paths, 1, True)
            self.population[:] = 0
            np.savez(paths['grid'], poblacion=self.population)
            with self.assertRaises(ValueError):
                exp.load_inputs(paths, 1, True)
            self.population[0, 0] = .125
            np.savez(paths['grid'], poblacion=self.population)
            self.fire = self.fire[:, :1, :]
            np.savez(paths['fire'], llegada_min=self.fire, semillas=self.seeds)
            with self.assertRaises(ValueError):
                exp.load_inputs(paths, 1, True)

    def test_thirty_distinct_replicates_and_paired_ci(self):
        from scripts.evacuacion.motor import simulate
        # Fuegos realmente distintos: comprobar métricas contra el motor público,
        # no solamente confiar en índices registrados en metadata.
        self.fire[:, 0, 1] = np.arange(30) + 90
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.fixtures(Path(tmp))
            output = Path(tmp) / 'batch'
            result = self.cli(paths, output, '--replicas', '30')
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((output / 'summary.json').read_text())
            self.assertFalse(summary['metadata']['provisional'])
            runs = summary['metadata']['runs']
            for scenario in exp.SCENARIOS:
                selected = [r for r in runs if r['scenario'] == scenario]
                self.assertEqual([r['fire_index'] for r in selected], list(range(30)))
                self.assertEqual([r['preparation_seed'] for r in selected], list(range(2000, 2030)))
            self.assertIn('early_alert', summary['paired_differences_vs_base'])
            self.assertEqual(summary['scenarios']['base']['people_total']['n'], 30)
            self.assertEqual(summary['scenarios']['base']['queue_duration_min']['n'], 30)
            with (output / 'replicas.csv').open() as stream:
                actual_rows = list(csv.DictReader(stream))
            network = exp.prepare_network(self.network, self.contract)
            expected_differences = []
            for r in range(30):
                groups, _ = exp.make_groups(self.population, network, self.contract, self.config, 2000 + r)
                expected = {}
                for scenario in exp.SCENARIOS:
                    adapted, prepared, closed, _ = exp.scenario_inputs(network, groups, self.config, scenario)
                    result = simulate(adapted, prepared, self.fire[r].tolist(), 480, closed)
                    metrics = exp.summarize_replica(result)
                    expected[scenario] = metrics
                    actual = next(row for row in actual_rows
                                  if row['scenario'] == scenario and int(row['replica']) == r)
                    for key, value in metrics.items():
                        if value is None:
                            self.assertEqual(actual[key], '')
                        else:
                            self.assertAlmostEqual(float(actual[key]), value)
                expected_differences.append(expected['early_alert']['people_safe'] - expected['base']['people_safe'])
            self.assertEqual(summary['paired_differences_vs_base']['early_alert']['people_safe'],
                             exp.confidence_interval(expected_differences))
            self.assertGreater(len({row['people_safe'] for row in actual_rows if row['scenario'] == 'base'}), 1)


if __name__ == '__main__':
    unittest.main()
