"""Motor determinista por eventos; capacidades viales en grupos simultáneos."""
from collections import defaultdict, deque
import heapq
import math


def _number(value, name, minimum=0, positive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not math.isfinite(value) or value < minimum or (positive and value == 0)):
        raise ValueError(f'{name}: número finito inválido')
    return value


def _identifier(value):
    if not isinstance(value, str) or not value:
        raise ValueError('Los identificadores deben ser cadenas no vacías')
    return value


def _validate(network, groups, fire, horizon, closed_edges):
    """Validar todo antes de construir el estado privado de la simulación."""
    _number(horizon, 'horizon')
    if not isinstance(fire, list) or not fire or not isinstance(fire[0], list) or not fire[0]:
        raise ValueError('fire debe ser una matriz rectangular no vacía')
    width = len(fire[0])
    for row in fire:
        if not isinstance(row, list) or len(row) != width:
            raise ValueError('fire debe ser rectangular')
        for value in row:
            if value != -1:
                _number(value, 'fire')

    def cell_time(cell):
        if (not isinstance(cell, (list, tuple)) or len(cell) != 2 or
                any(isinstance(x, bool) or not isinstance(x, int) for x in cell)):
            raise ValueError('cell debe contener dos índices enteros')
        r, c = cell
        if not (0 <= r < len(fire) and 0 <= c < width):
            raise ValueError('cell fuera de fire')
        return math.inf if fire[r][c] == -1 else fire[r][c]

    nodes, edges, destinations = {}, {}, {}
    transform = network.get('metadata', {}).get('transform_gdal')
    if transform is not None:
        if len(transform) != 6:
            raise ValueError('transform_gdal debe tener seis coeficientes')
        for value in transform:
            _number(value, 'transform_gdal', minimum=-math.inf)
        determinant = transform[1] * transform[5] - transform[2] * transform[4]
        if determinant == 0:
            raise ValueError('transform_gdal singular')
    node_fire = {}
    for node in network['nodes']:
        identifier = _identifier(node['id'])
        if identifier in nodes:
            raise ValueError('Nodo duplicado')
        _number(node['x'], 'x', minimum=-math.inf)
        _number(node['y'], 'y', minimum=-math.inf)
        nodes[identifier] = node
        cell = node.get('cell')
        if cell is None and transform is not None:
            dx, dy = node['x'] - transform[0], node['y'] - transform[3]
            cell = [math.floor((dy * transform[1] - dx * transform[4]) / determinant),
                    math.floor((dx * transform[5] - dy * transform[2]) / determinant)]
            # Los nodos fuera de la grilla no tienen fuego observado.
            if not (0 <= cell[0] < len(fire) and 0 <= cell[1] < width):
                cell = None
        node_fire[identifier] = cell_time(cell) if cell is not None else math.inf
    edge_fire = {}
    for edge in network['edges']:
        identifier = _identifier(edge['id'])
        if identifier in edges or edge['u'] not in nodes or edge['v'] not in nodes:
            raise ValueError('Tramo duplicado o extremo desconocido')
        _number(edge['length_m'], 'length_m', positive=True)
        _number(edge['travel_min'], 'travel_min', positive=True)
        cap = _number(edge['capacity'], 'capacity', positive=True)
        if int(cap) != cap:
            raise ValueError('capacity vial debe ser un número entero de grupos')
        edges[identifier] = edge
        edge_fire[identifier] = min((cell_time(c) for c in edge['cells']), default=math.inf)
    for destination in network['destinations']:
        node = destination['node']
        if node not in nodes or node in destinations or destination['kind'] not in ('safe', 'temporary'):
            raise ValueError('Destino inválido o duplicado')
        _number(destination['capacity'], 'destination capacity')
        destinations[node] = destination
    identifiers = set()
    origin_fire = []
    for group in groups:
        identifier = _identifier(group['id'])
        if identifier in identifiers or group['node'] not in nodes:
            raise ValueError('Grupo duplicado o nodo desconocido')
        identifiers.add(identifier)
        _number(group['people'], 'people', positive=True)
        _number(group['ready_min'], 'ready_min')
        origin_fire.append(cell_time(group['origin_cell']))
    _number(math.fsum(group['people'] for group in groups), 'people_total')
    if any(edge not in edges for edge in closed_edges):
        raise ValueError('closed_edges contiene un tramo desconocido')
    return nodes, edges, destinations, node_fire, edge_fire, origin_fire


def simulate(network, groups, fire, horizon=480, closed_edges=None, *, progress=None):
    """Simular sin mutar entradas; ver docs/motor_evacuacion.md para el contrato."""
    try:
        nodes, edges, destinations, node_fire, edge_fire, origin_fire = _validate(
            network, groups, fire, horizon, closed_edges or [])
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError(f'Entrada incompleta o inválida: {error}') from error
    states = [dict(g, state='preparing', destination=None, finish_min=None,
                   exposed=False, edge=None, queue_since=None, ticket=None,
                   traversal=None, blocked_edge=None, blocked_version=0) for g in groups]
    total = math.fsum(g['people'] for g in groups)
    incoming = defaultdict(list)
    for identifier in sorted(edges):
        incoming[edges[identifier]['v']].append(identifier)
    closed = set(closed_edges or [])
    occupancy = {e: set() for e in edges}
    peak = {e: 0 for e in edges}
    reserved = {n: 0.0 for n in destinations}
    arrived = {n: 0.0 for n in destinations}
    waiting = defaultdict(deque)
    blocked = defaultdict(deque)
    destination_waiters = defaultdict(list)
    residents = defaultdict(set)
    for index, g in enumerate(states):
        g['_index'] = index
        residents[g['node']].add(index)
    holders = set()
    processing_events = False
    reservations_released = False
    safe_people = temporary_people = exposed_people = 0.0
    dirty = set()
    events, history, traversals, evacuation_times = [], [], [], []
    sequence = 0
    ticket = 0
    time = 0
    queue_groups = 0
    queue_people = 0.0
    queue_group_minutes = 0.0
    queue_person_minutes = 0.0
    max_queue_groups = 0
    max_queue_people = 0.0
    route_cache = {}
    event_batches = 0
    last_progress_min = None

    def event(when, priority, kind, payload):
        nonlocal sequence
        if when <= horizon:
            sequence += 1
            heapq.heappush(events, (when, priority, sequence, kind, payload))

    def expose(g):
        nonlocal exposed_people
        if not g['exposed']:
            exposed_people += g['people']
            g['exposed'] = True

    def wake_edge(identifier, all_groups=False):
        count = len(blocked[identifier]) if all_groups else max(
            0, int(edges[identifier]['capacity']) - len(occupancy[identifier]))
        awakened = 0
        while blocked[identifier] and awakened < count:
            index, version = blocked[identifier].popleft()
            g = states[index]
            if (g['state'] == 'waiting' and g['blocked_edge'] == identifier and
                    g['blocked_version'] == version):
                g['blocked_edge'] = None
                waiting[g['node']].append(index)
                dirty.add(g['node'])
                awakened += 1

    def wake_all():
        for identifier in list(blocked):
            wake_edge(identifier, all_groups=True)
        dirty.update(waiting)

    def queue_add(index):
        nonlocal ticket, queue_groups, queue_people
        g = states[index]
        if g['queue_since'] is not None:
            return
        ticket += 1
        g.update(state='waiting', queue_since=time, ticket=ticket)
        waiting[g['node']].append(index)
        queue_groups += 1
        queue_people += g['people']
        dirty.add(g['node'])

    def queue_remove(g):
        nonlocal queue_groups, queue_people
        if g['queue_since'] is not None:
            queue_groups -= 1
            queue_people -= g['people']
            g['queue_since'] = None

    def release(g):
        nonlocal reservations_released
        destination = g['destination']
        if destination is not None:
            reserved[destination] -= g['people']
            g['destination'] = None
            holders.discard(g['_index'])
            if processing_events:
                reservations_released = True
            else:
                wake_all()

    def reserve(g, destination):
        g['destination'] = destination
        holders.add(g['_index'])
        reserved[destination] += g['people']
        available = destinations[destination]['capacity'] - reserved[destination] - arrived[destination]
        heap = destination_waiters[destination]
        # Despertar solo grupos cuya factibilidad cambia al reservar personas.
        while heap and -heap[0][0] > available + 1e-10:
            _, index, version = heapq.heappop(heap)
            other = states[index]
            if (other['state'] == 'waiting' and other['blocked_edge'] is not None and
                    other['blocked_version'] == version):
                other['blocked_edge'] = None
                waiting[other['node']].append(index)
                dirty.add(other['node'])

    def finish(g):
        nonlocal safe_people, temporary_people
        destination = g['destination']
        reserved[destination] -= g['people']
        arrived[destination] += g['people']
        holders.discard(g['_index'])
        g['state'] = destinations[destination]['kind']
        g['finish_min'] = time
        if g['state'] == 'safe':
            safe_people += g['people']
            evacuation_times.append({'time_min': time, 'people': g['people']})
        else:
            temporary_people += g['people']

    def route(g):
        if g['destination'] is not None:
            choices = (g['destination'],)
        else:
            choices = tuple(sorted(n for n, d in destinations.items()
                                   if node_fire[n] > time and
                                   d['capacity'] - reserved[n] - arrived[n] >= g['people'] - 1e-10))
        # La clave agrupa hogares por el conjunto de destinos factibles, no por hogar.
        if choices not in route_cache:
            tables = []
            for kind in ('safe', 'temporary'):
                best, heap = {}, []
                for n in choices:
                    if destinations[n]['kind'] == kind and node_fire[n] > time:
                        best[n] = (0, n, '')
                        heapq.heappush(heap, (0, n, '', n))
                while heap:
                    distance, destination, first, node = heapq.heappop(heap)
                    if best.get(node) != (distance, destination, first):
                        continue
                    for identifier in incoming[node]:
                        edge = edges[identifier]
                        if identifier in closed or node_fire[edge['u']] <= time:
                            continue
                        candidate = (distance + edge['travel_min'], destination, identifier)
                        if edge['u'] not in best or candidate < best[edge['u']]:
                            best[edge['u']] = candidate
                            heapq.heappush(heap, (*candidate, edge['u']))
                tables.append(best)
            route_cache[choices] = tables
        for table in route_cache[choices]:
            if g['node'] in table:
                return table[g['node']]
        return None

    def dispatch():
        # FIFO global entre cabeceras de colas; un tramo lleno no bloquea otros tramos.
        candidates = []
        for node in sorted(dirty):
            for index in waiting.pop(node, ()):
                g = states[index]
                if g['state'] == 'waiting':
                    heapq.heappush(candidates, (g['ticket'], index))
        dirty.clear()
        while candidates:
            _, index = heapq.heappop(candidates)
            g = states[index]
            if node_fire[g['node']] <= time:
                expose(g)
                queue_remove(g)
                release(g)
                g['state'] = 'stranded'
                continue
            path = route(g)
            if path is None and g['destination'] is not None:
                release(g)
                path = route(g)
            if path is None:
                waiting[g['node']].append(index)
                continue
            _, destination, identifier = path
            if not identifier:
                if g['destination'] is None:
                    reserve(g, destination)
                queue_remove(g)
                finish(g)
                continue
            edge = edges[identifier]
            if len(occupancy[identifier]) >= edge['capacity']:
                g['blocked_edge'] = identifier
                g['blocked_version'] += 1
                version = g['blocked_version']
                blocked[identifier].append((index, version))
                if g['destination'] is None:
                    heapq.heappush(destination_waiters[destination], (-g['people'], index, version))
                continue
            if g['destination'] is None:
                reserve(g, destination)
            queue_remove(g)
            residents[g['node']].discard(index)
            occupancy[identifier].add(index)
            peak[identifier] = max(peak[identifier], len(occupancy[identifier]))
            record = {'group': g['id'], 'edge': identifier, 'start_min': time,
                      'end_min': None, 'outcome': 'active'}
            traversals.append(record)
            g.update(state='traveling', edge=identifier, traversal=record)
            event(time + edge['travel_min'], 2, 'arrival', (index, record))
        if dirty:
            dispatch()

    def snapshot():
        sample = {'time_min': time, 'people_safe': safe_people, 'people_temporary': temporary_people,
                  'people_remaining': total - safe_people - temporary_people,
                  'people_exposed': exposed_people,
                  'queue_groups': queue_groups, 'queue_people': max(0.0, queue_people)}
        if history and history[-1]['time_min'] == time:
            history[-1] = sample
        else:
            history.append(sample)

    for identifier, when in edge_fire.items():
        event(when, 0, 'closure', identifier)
    for node, when in node_fire.items():
        event(when, 1, 'node_fire', node)
    for index, g in enumerate(states):
        event(origin_fire[index], 1, 'origin_fire', index)
        event(g['ready_min'], 3, 'ready', index)
    event(0, 4, 'sample', None)
    event(horizon, 4, 'sample', None)
    while events:
        next_time = events[0][0]
        queue_group_minutes += queue_groups * (next_time - time)
        queue_person_minutes += max(0.0, queue_people) * (next_time - time)
        time = next_time
        processing_events = True
        reservations_released = False
        topology_changed = False
        closures_changed = False
        while events and events[0][0] == time:
            _, _, _, kind, payload = heapq.heappop(events)
            if kind == 'closure':
                identifier = payload
                closed.add(identifier)
                topology_changed = closures_changed = True
                for index in sorted(occupancy[identifier]):
                    g = states[index]
                    expose(g)
                    g['traversal'].update(end_min=time, outcome='interrupted')
                    g['edge'] = None
                    residents[g['node']].add(index)
                    release(g)
                    queue_add(index)
                occupancy[identifier].clear()
            elif kind == 'node_fire':
                node = payload
                topology_changed = True
                for index in residents[node]:
                    g = states[index]
                    if g['state'] in ('preparing', 'waiting', 'temporary', 'stranded'):
                        expose(g)
                        if g['state'] == 'temporary':
                            temporary_people -= g['people']
                            arrived[node] -= g['people']
                        queue_remove(g)
                        release(g)
                        g['state'] = 'stranded'
                if node in destinations:
                    for index in list(holders):
                        g = states[index]
                        if g['destination'] == node:
                            release(g)
            elif kind == 'origin_fire':
                g = states[payload]
                if g['state'] == 'preparing':
                    expose(g)
            elif kind == 'ready':
                if states[payload]['state'] == 'preparing':
                    queue_add(payload)
            elif kind == 'arrival':
                index, record = payload
                g = states[index]
                if g['state'] != 'traveling' or g['traversal'] is not record:
                    continue
                identifier = g['edge']
                edge = edges[identifier]
                occupancy[identifier].remove(index)
                wake_edge(identifier)
                dirty.add(edge['u'])
                record.update(end_min=time, outcome='arrived')
                g.update(node=edge['v'], edge=None)
                residents[g['node']].add(index)
                if node_fire[g['node']] <= time:
                    expose(g)
                    release(g)
                    g['state'] = 'stranded'
                elif g['destination'] == g['node']:
                    finish(g)
                else:
                    queue_add(index)
        if closures_changed:
            # Una sola pasada por reservas activas para todo el lote de cierres.
            for index in list(holders):
                if states[index]['state'] == 'waiting':
                    release(states[index])
        processing_events = False
        if topology_changed:
            route_cache.clear()
        if topology_changed or reservations_released:
            wake_all()
        dispatch()
        max_queue_groups = max(max_queue_groups, queue_groups)
        max_queue_people = max(max_queue_people, max(0.0, queue_people))
        snapshot()
        if progress is not None:
            event_batches += 1
            if last_progress_min is None or time - last_progress_min >= 30 or time == horizon:
                progress({'time_min': time, 'horizon': horizon, 'event_batches': event_batches,
                          'people_safe': safe_people, 'people_temporary': temporary_people,
                          'people_remaining': total - safe_people - temporary_people})
                last_progress_min = time
    # El horizonte trunca recorridos activos sin inventar una llegada.
    for g in states:
        if g['state'] == 'traveling':
            g['traversal'].update(end_min=horizon, outcome='horizon')
    result = dict(history[-1])
    result.pop('time_min')
    result.pop('queue_groups')
    result.pop('queue_people')
    result.update(people_total=total,
                  people_safe_before_fire=math.fsum(g['people'] for g in states
                                                   if g['state'] == 'safe' and not g['exposed']),
                  queue_group_minutes=queue_group_minutes, queue_person_minutes=queue_person_minutes,
                  max_queue_groups=max_queue_groups, max_queue_people=max_queue_people,
                  edge_max_occupancy=peak,
                  capacity_invariant=all(peak[e] <= edges[e]['capacity'] for e in edges),
                  no_closed_edge_traversal=all(t['end_min'] <= edge_fire[t['edge']] and
                                               t['edge'] not in (closed_edges or []) for t in traversals),
                  destination_people=arrived, history=history, traversals=traversals,
                  evacuation_times=evacuation_times,
                  groups=[{key: g[key] for key in ('id', 'people', 'node', 'state', 'edge',
                                                  'destination', 'finish_min', 'exposed')}
                          for g in states])
    return result
