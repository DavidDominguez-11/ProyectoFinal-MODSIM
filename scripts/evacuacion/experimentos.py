"""Adaptador reproducible y Monte Carlo pareado; no descarga datos ni duplica el motor."""
import argparse
import copy
import csv
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import t
from scipy import __version__ as scipy_version

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.evacuacion.motor import simulate

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ('base', 'early_alert', 'skyway_closed', 'exit_capacity')
DEFAULTS = {'network': 'data/procesado/red_vial.json',
            'grid': 'data/procesado/grilla_fuego.npz',
            'fire': 'salidas/fuego/llegada_replicas.npz',
            'contract': 'salidas/fuego/contrato.json',
            'config': 'config/escenarios_evacuacion.json',
            'output': 'salidas/evacuacion'}
PEOPLE_METRICS = ('people_total', 'people_safe', 'people_safe_before_fire',
                  'people_exposed', 'people_temporary', 'people_remaining')
QUEUE_METRICS = ('queue_group_minutes', 'queue_person_minutes',
                 'max_queue_groups', 'max_queue_people')


def _finite(value, name, minimum=0, positive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not math.isfinite(value) or value < minimum or (positive and value == 0)):
        raise ValueError(f'{name}: número finito inválido')
    return value


def validate_config(config):
    """Rechazar supuestos incompletos o valores imposibles antes de escribir."""
    for key in ('group_max_people', 'preparation_gamma_shape', 'preparation_gamma_scale_min'):
        _finite(config[key], key, positive=True)
    for key in ('base_alert_min', 'base_exit_capacity_people', 'increased_exit_capacity_people'):
        _finite(config[key], key)
    delta = _finite(config['early_alert_delta_min'], 'early_alert_delta_min', minimum=-math.inf)
    if delta >= 0 or config['base_alert_min'] + delta < 0:
        raise ValueError('La alerta temprana debe ser anterior y no negativa')
    if config['increased_exit_capacity_people'] <= config['base_exit_capacity_people']:
        raise ValueError('La alternativa debe aumentar capacidad')
    bins = config['distribution_bins']
    if isinstance(bins, bool) or not isinstance(bins, int) or not 1 <= bins <= 10000:
        raise ValueError('distribution_bins debe ser entero entre 1 y 10000')
    seed = config['preparation_seed_start']
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError('preparation_seed_start debe ser entero no negativo')
    if not isinstance(config['closed_corridor'], str) or not config['closed_corridor'].strip():
        raise ValueError('closed_corridor vacío')
    target = config['capacity_target_node']
    if target is not None and (not isinstance(target, str) or not target):
        raise ValueError('capacity_target_node inválido')
    assumptions = config['assumptions']
    required = ('status', 'clock', 'preparation', 'groups', 'attachment', 'boundary',
                'destinations', 'route', 'pairing', 'population', 'road')
    if not isinstance(assumptions, dict) or any(
            not isinstance(assumptions.get(k), str) or not assumptions[k] for k in required):
        raise ValueError('Faltan supuestos explícitos')


def _transform(contract):
    transform = np.asarray(contract['transform_gdal'], dtype=np.float64)
    if transform.shape != (6,) or not np.isfinite(transform).all():
        raise ValueError('transform_gdal inválida')
    matrix = np.array([[transform[1], transform[2]], [transform[4], transform[5]]])
    if np.linalg.det(matrix) == 0:
        raise ValueError('transform_gdal singular')
    return transform, matrix


def prepare_network(network, contract):
    """Copiar la red completa y asignar celdas, incluso en el borde cerrado."""
    result = copy.deepcopy(network)
    transform, matrix = _transform(contract)
    shape = contract['forma_filas_columnas']
    if (len(shape) != 2 or any(isinstance(x, bool) or not isinstance(x, int) or x <= 0
                               for x in shape)):
        raise ValueError('Forma de contrato inválida')
    _finite(contract['horizonte_min'], 'horizonte_min', positive=True)
    if contract.get('crs') != 'EPSG:32610':
        raise ValueError('El contrato requiere coordenadas UTM EPSG:32610')
    if result.get('metadata', {}).get('crs', 'EPSG:32610') != contract['crs']:
        raise ValueError('CRS de red y contrato incompatibles')
    if not result['nodes']:
        raise ValueError('Red vacía')
    for node in result['nodes']:
        xy = np.array([node['x'], node['y']], dtype=np.float64)
        if not np.isfinite(xy).all():
            raise ValueError('Coordenadas no finitas')
        col, row = np.linalg.solve(matrix, xy - transform[[0, 3]])
        # Tolerancia solo para error de inversión afín en el límite, en celdas.
        if not (-1e-8 <= row <= shape[0] + 1e-8 and -1e-8 <= col <= shape[1] + 1e-8):
            raise ValueError('Nodo fuera del dominio del contrato')
        node['cell'] = [max(0, min(shape[0] - 1, math.floor(row))),
                        max(0, min(shape[1] - 1, math.floor(col)))]
    result.setdefault('metadata', {})['transform_gdal'] = transform.tolist()
    return result


def _reachable(network):
    """Alcanzabilidad dirigida inversa; no depende de metadatos opcionales."""
    incoming = {n['id']: [] for n in network['nodes']}
    for edge in network['edges']:
        incoming[edge['v']].append(edge['u'])
    reached = {d['node'] for d in network['destinations'] if d['kind'] == 'safe'}
    stack = list(reached)
    while stack:
        for node in incoming[stack.pop()]:
            if node not in reached:
                reached.add(node)
                stack.append(node)
    return reached


def make_groups(population, network, contract, config, seed):
    """Dividir cada celda sin redondear; preparación RNG local PCG64 registrada."""
    population = np.asarray(population, dtype=np.float64)
    if (population.shape != tuple(contract['forma_filas_columnas']) or
            not np.isfinite(population).all() or (population < 0).any()):
        raise ValueError('Población/forma inválida')
    validate_config(config)
    total = math.fsum(float(x) for x in population.flat)
    if not math.isfinite(total) or total <= 0:
        raise ValueError('Masa poblacional debe ser positiva y finita')
    nodes = sorted(network['nodes'], key=lambda n: n['id'])
    coords = np.array([[n['x'], n['y']] for n in nodes], dtype=np.float64)
    tree = cKDTree(coords)
    cells = np.argwhere(population > 0)
    transform, matrix = _transform(contract)
    xy = (cells[:, [1, 0]] + .5) @ matrix.T + transform[[0, 3]]
    distances, indices = tree.query(xy, k=min(2, len(nodes)))
    if len(nodes) == 1:
        distances, indices = distances[:, None], indices[:, None]
    reachable = _reachable(network)
    rng = np.random.default_rng(seed)
    groups, no_exit_cells, no_exit_weights = [], 0, []
    weights = []
    maximum = config['group_max_people']
    for i, (row, col) in enumerate(cells):
        index = int(indices[i, 0])
        if len(nodes) > 1 and distances[i, 0] == distances[i, 1]:
            candidates = tree.query_ball_point(xy[i], np.nextafter(distances[i, 0], math.inf))
            index = min(candidates, key=lambda j: (float(np.sum((coords[j] - xy[i]) ** 2)),
                                                    nodes[j]['id']))
        node = nodes[index]['id']
        weight = float(population[row, col])
        weights.append(weight)
        if node not in reachable:
            no_exit_cells += 1
            no_exit_weights.append(weight)
        count = math.floor(weight / maximum)
        # Evitar que la división redondee hacia un múltiplo superior.
        if count * maximum > weight:
            count -= 1
        remainder = weight - count * maximum
        portions = [maximum] * count
        if remainder > 0:
            portions.append(remainder)
        for portion in portions:
            preparation = float(rng.gamma(config['preparation_gamma_shape'],
                                          config['preparation_gamma_scale_min']))
            alert = config['base_alert_min']
            ready = alert + preparation
            if not math.isfinite(ready):
                raise ValueError('Preparación no finita')
            groups.append({'id': f'g{len(groups):07d}', 'people': portion, 'node': node,
                           'origin_cell': [int(row), int(col)], 'alert_min': alert,
                           'preparation_min': preparation, 'ready_min': ready})
    group_mass = math.fsum(g['people'] for g in groups)
    if not math.isclose(total, group_mass, rel_tol=1e-14, abs_tol=0):
        raise ValueError('No se conserva masa al crear grupos')
    nearest_distances = distances[:, 0]
    details = {'people_total': total, 'group_people_total': group_mass,
               'group_count': len(groups), 'positive_cells': len(cells),
               'no_exit_origins': no_exit_cells, 'people_no_exit': math.fsum(no_exit_weights),
               'fraction_people_no_exit': math.fsum(no_exit_weights) / total,
               'nodes_without_exit': len(nodes) - len(reachable),
               'attachment_distance_m': {
                   'min': float(nearest_distances.min()), 'max': float(nearest_distances.max()),
                   'mean_origins': float(nearest_distances.mean()),
                   'p50_origins': float(np.quantile(nearest_distances, .5)),
                   'p90_origins': float(np.quantile(nearest_distances, .9)),
                   'mean_people': math.fsum(float(d) * w for d, w in zip(nearest_distances, weights)) / total}}
    return groups, details


def scenario_inputs(network, groups, config, scenario):
    """Una única intervención respecto de base; no mutar red ni grupos pareados."""
    if scenario not in SCENARIOS:
        raise ValueError('Escenario desconocido')
    result, prepared = copy.deepcopy(network), copy.deepcopy(groups)
    exits = sorted(d['node'] for d in result['destinations'] if d['kind'] == 'safe')
    if not exits:
        raise ValueError('Se requiere al menos una salida segura')
    target = config['capacity_target_node'] or exits[0]
    if target not in exits:
        raise ValueError('La salida seleccionada no existe')
    pattern = re.compile(r'\b' + re.escape(config['closed_corridor']) + r'\b', re.IGNORECASE)
    corridor = sorted(e['id'] for e in result['edges'] if pattern.search(e.get('name') or ''))
    if not corridor:
        raise ValueError('El corredor de cierre no contiene aristas')
    for destination in result['destinations']:
        if destination['kind'] == 'safe':
            destination['capacity'] = (config['increased_exit_capacity_people']
                                       if scenario == 'exit_capacity' and destination['node'] == target
                                       else config['base_exit_capacity_people'])
    if scenario == 'early_alert':
        for group in prepared:
            group['alert_min'] += config['early_alert_delta_min']
            group['ready_min'] = group['alert_min'] + group['preparation_min']
    closed = corridor if scenario == 'skyway_closed' else []
    return result, prepared, closed, {'capacity_target_node': target,
                                     'closure_edge_count': len(closed),
                                     'skyway_edge_count': len(corridor)}


def confidence_interval(values):
    """Student-t bilateral 95% sobre estadísticas independientes de réplicas."""
    values = [float(x) for x in values if x is not None]
    n = len(values)
    if not n:
        return {'n': 0, 'mean': None, 'ci95': None}
    mean = math.fsum(values) / n
    if n < 2:
        return {'n': n, 'mean': mean, 'ci95': None}
    variance = math.fsum((x - mean) ** 2 for x in values) / (n - 1)
    margin = float(t.ppf(.975, n - 1)) * math.sqrt(variance / n)
    return {'n': n, 'mean': mean, 'ci95': [mean - margin, mean + margin]}


def evacuation_statistics(arrivals):
    ordered = sorted(arrivals, key=lambda a: a['time_min'])
    mass = math.fsum(a['people'] for a in ordered)
    result = {'safe_arrival_count': len(ordered), 'safe_arrival_people': mass,
              'evacuation_mean_min': None, 'evacuation_p50_min': None,
              'evacuation_p90_min': None}
    if not mass:
        return result
    result['evacuation_mean_min'] = math.fsum(a['time_min'] * a['people'] for a in ordered) / mass
    cumulative = 0.
    for arrival in ordered:
        cumulative += arrival['people']
        for quantile, name in ((.5, 'evacuation_p50_min'), (.9, 'evacuation_p90_min')):
            if result[name] is None and cumulative >= quantile * mass:
                result[name] = arrival['time_min']
    return result


def queue_duration(history):
    """Minutos con alguna cola: integral del indicador, no recuento de eventos."""
    return math.fsum(b['time_min'] - a['time_min'] for a, b in zip(history, history[1:])
                     if a['queue_groups'] > 0)


def summarize_replica(result):
    if not result['capacity_invariant'] or not result['no_closed_edge_traversal']:
        raise ValueError('Invariante del motor violada')
    total = result['people_total']
    if not math.isclose(total, math.fsum(result[k] for k in
                       ('people_safe', 'people_temporary', 'people_remaining')), rel_tol=1e-9):
        raise ValueError('Masa no conservada por motor')
    metrics = {k: result[k] for k in PEOPLE_METRICS + QUEUE_METRICS}
    metrics['fraction_safe_before_fire'] = result['people_safe_before_fire'] / total
    metrics['queue_duration_min'] = queue_duration(result['history'])
    metrics.update(evacuation_statistics(result['evacuation_times']))
    return metrics


def representative_example(run, groups, result, metrics):
    """Proyección acotada: nunca entregar el resultado completo a json.dump."""
    history = result['history']
    count = min(481, len(history))
    indices = ([i * (len(history) - 1) // (count - 1) for i in range(count)]
               if count > 1 else [0])
    sampled = {key: value for key, value in result.items()
               if isinstance(value, (int, float, bool, str)) or value is None}
    sampled.update(groups=result['groups'][:100], traversals=result['traversals'][:100],
                   history=[history[i] for i in indices])
    records = {'input_groups': groups, **{key: result[key] for key in
               ('groups', 'traversals', 'history', 'evacuation_times',
                'edge_max_occupancy', 'destination_people')}}
    counts = {key: len(value) for key, value in records.items()}
    exported = {'input_groups': min(100, len(groups)),
                **{key: len(sampled.get(key, [])) for key in counts if key != 'input_groups'}}
    return {'schema': 'evacuation_representative_example', 'version': 1,
            'representative': True,
            'description': 'Representative illustrative samples, not a full trajectory; metrics use the full run.',
            'run': run, 'metrics': metrics, 'record_counts': counts,
            'exported_counts': exported,
            'truncated': {key: exported[key] < counts[key] for key in counts},
            'selection': {'input_groups': 'first 100', 'groups': 'first 100',
                          'traversals': 'first 100',
                          'history': 'at most 481 uniformly spaced record indices, including first/last',
                          'evacuation_times': 'omitted; exact distribution.csv',
                          'edge_max_occupancy': 'omitted; scalar capacity_invariant retained',
                          'destination_people': 'omitted; scalar population totals retained'},
            'input_groups': groups[:100], 'result': sampled}


def _read_json(path):
    with Path(path).open(encoding='utf-8') as stream:
        return json.load(stream)


def _write_json(path, data):
    with Path(path).open('w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_inputs(paths, replicas, smoke):
    """Preflight completo, sin crear directorios, figuras ni contadores de salida."""
    if isinstance(replicas, bool) or not isinstance(replicas, int) or replicas <= 0:
        raise ValueError('replicas debe ser entero positivo')
    if replicas < 30 and not smoke:
        raise ValueError('Menos de 30 réplicas requiere --smoke (provisional)')
    config, contract = _read_json(paths['config']), _read_json(paths['contract'])
    validate_config(config)
    network = prepare_network(_read_json(paths['network']), contract)
    with np.load(paths['grid'], allow_pickle=False) as data:
        population = np.asarray(data['poblacion'], dtype=np.float64)
    with np.load(paths['fire'], allow_pickle=False) as data:
        fire = np.array(data['llegada_min'], dtype=np.float64)
        seeds = np.array(data['semillas'])
    shape = tuple(contract['forma_filas_columnas'])
    if (fire.ndim != 3 or fire.shape[1:] != shape or fire.shape[0] < replicas or
            not np.isfinite(fire).all() or ((fire < 0) & (fire != -1)).any()):
        raise ValueError('Forma, valores o número de fuegos distintos inválidos')
    if (seeds.shape != (len(fire),) or seeds.dtype.kind not in 'iu' or
            (seeds < 0).any() or len(set(int(s) for s in seeds)) != len(seeds)):
        raise ValueError('Semillas de fuego deben ser enteras, únicas y corresponder a réplicas')
    # El motor público valida toda la red sin grupos ni eventos de evacuación.
    simulate(network, [], np.full(shape, -1).tolist(), horizon=0)
    groups, details = make_groups(population, network, contract, config,
                                  config['preparation_seed_start'])
    for scenario in SCENARIOS:
        scenario_inputs(network, groups, config, scenario)
    hashes = {key: _sha256(paths[key]) for key in ('network', 'grid', 'fire', 'contract', 'config')}
    return network, population, fire, seeds, contract, config, details, hashes


def _plot_outputs(output, summaries, distributions, bin_edges, provisional):
    # Importación diferida: entradas rechazadas no crean caché de Matplotlib.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    names = list(summaries)
    title = 'PROVISIONAL — smoke' if provisional else 'Monte Carlo hipotético'

    def bars(ax, metric, label):
        stats = [summaries[s][metric] for s in names]
        means = [s['mean'] if s['mean'] is not None else float('nan') for s in stats]
        errors = [0 if s['ci95'] is None else (s['ci95'][1] - s['ci95'][0]) / 2 for s in stats]
        ax.bar(names, means, yerr=errors, capsize=4)
        ax.set_ylabel(label)
        ax.tick_params(axis='x', rotation=20)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    bars(axes[0], 'fraction_safe_before_fire', 'Fracción segura antes del fuego')
    bars(axes[1], 'people_exposed', 'Personas con exposición potencial')
    fig.suptitle(title + ' — medias e IC t 95% (si n ≥ 2)')
    fig.tight_layout()
    fig.savefig(output / 'metrics.png')
    plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, metric, label in zip(axes.flat,
            (*QUEUE_METRICS, 'queue_duration_min', 'evacuation_mean_min'),
            ('Grupos·min', 'Personas·min', 'Máximo grupos', 'Máximo personas',
             'Minutos con cola', 'Llegada segura media (min)')):
        bars(ax, metric, label)
    fig.suptitle(title + ' — medias e IC t 95%')
    fig.tight_layout()
    fig.savefig(output / 'queues.png')
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5))
    for scenario in names:
        counts = distributions[scenario]
        mass = math.fsum(counts)
        if mass:
            ax.step(bin_edges, np.r_[0., np.cumsum(counts) / mass],
                    where='post', label=scenario)
    ax.set(xlabel='Minutos desde ignición (intervalos de visualización)',
           ylabel='CDF ponderada condicional a llegada segura',
           title=title + ' — masa agrupada por intervalos, no IC; CSV exacto')
    if ax.lines:
        ax.legend()
    fig.tight_layout()
    fig.savefig(output / 'cdf.png')
    plt.close(fig)


def run_experiments(paths, replicas=30, smoke=False, scenarios=None):
    """Ejecutar secuencialmente; solo una historia completa reside en memoria."""
    scenarios = tuple(SCENARIOS if scenarios is None else scenarios)
    if not scenarios or len(set(scenarios)) != len(scenarios) or any(s not in SCENARIOS for s in scenarios):
        raise ValueError('Selección de escenarios inválida')
    print('phase=preflight start', flush=True)
    network, population, fire, seeds, contract, config, attachment, hashes = load_inputs(
        paths, replicas, smoke)
    print('phase=preflight done', flush=True)
    output = Path(paths['output'])
    # Evitar mezclar una corrida con archivos viejos o sobrescribir evidencia.
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('output debe ser nuevo o un directorio vacío')
    output.mkdir(parents=True, exist_ok=True)
    metadata = {'provisional': bool(smoke), 'classification': 'provisional' if smoke else 'hypothetical_mc',
                'replicas_per_scenario': replicas, 'input_sha256': hashes,
                'config': config, 'contract': contract, 'attachment': attachment,
                'rng': 'numpy.default_rng / PCG64', 'numpy_version': np.__version__,
                'scipy_version': scipy_version, 'python_version': sys.version.split()[0],
                'units': {'people': 'personas ponderadas', 'times': 'min desde ignición',
                          'queue_group_minutes': 'grupos·min', 'queue_person_minutes': 'personas·min',
                          'queue_duration_min': 'min con cola no vacía',
                          'safe_arrival_count': 'grupos con llegada segura'},
                'ci_method': 'Student-t bilateral 95%; estadística por réplica independiente; n excluye null',
                'distribution': 'CSV exacto por réplica; CDF gráfica por intervalos uniformes, conserva masa segura. No es IC.',
                'distribution_bins': config['distribution_bins'],
                'runs': []}
    rows = {scenario: [] for scenario in scenarios}
    bin_edges = np.linspace(0, contract['horizonte_min'], config['distribution_bins'] + 1)
    distributions = {scenario: np.zeros(config['distribution_bins'], dtype=np.float64)
                     for scenario in scenarios}
    started = time.perf_counter()
    with ExitStack() as stack:
        stream = stack.enter_context((output / 'replicas.csv').open('w', newline='', encoding='utf-8'))
        distribution_stream = stack.enter_context((output / 'distribution.csv').open('w', newline='', encoding='utf-8'))
        distribution_writer = csv.writer(distribution_stream)
        distribution_writer.writerow(['scenario', 'replica', 'time_min', 'people',
                                      'cumulative_people', 'conditional_cdf', 'provisional'])
        writer = None
        # Réplica externa: generar preparación una vez y copiar para cada escenario.
        for r in range(replicas):
            preparation_seed = config['preparation_seed_start'] + r
            groups, _ = make_groups(population, network, contract, config, preparation_seed)
            replica_fire = fire[r].tolist()
            for scenario in scenarios:
                adapted, prepared, closed, intervention = scenario_inputs(network, groups, config, scenario)
                print(f'{scenario} r={r + 1}/{replicas} start elapsed={time.perf_counter() - started:.3f}s', flush=True)
                simulation_started = time.perf_counter()
                print(f'phase=simulate start scenario={scenario} replica={r}', flush=True)

                def report_progress(sample):
                    print(f'phase=simulate progress scenario={scenario} replica={r} '
                          f'modeled_min={sample["time_min"]:.3f} horizon={sample["horizon"]} '
                          f'batches={sample["event_batches"]} safe={sample["people_safe"]} '
                          f'remaining={sample["people_remaining"]} '
                          f'wall={time.perf_counter() - simulation_started:.3f}s', flush=True)

                result = simulate(adapted, prepared, replica_fire,
                                  horizon=contract['horizonte_min'], closed_edges=closed,
                                  progress=report_progress)
                print(f'phase=simulate done scenario={scenario} replica={r} '
                      f'wall={time.perf_counter() - simulation_started:.3f}s', flush=True)
                metrics = summarize_replica(result)
                run = {'scenario': scenario, 'replica': r, 'fire_index': r,
                       'fire_seed': int(seeds[r]), 'preparation_seed': preparation_seed,
                       'provisional': bool(smoke), **intervention}
                row = {**run, **metrics}
                if writer is None:
                    writer = csv.DictWriter(stream, fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
                stream.flush()
                metadata['runs'].append(run)
                rows[scenario].append(metrics)
                # Distribución exacta se transmite a disco; solo el histograma gráfico
                # acotado queda entre réplicas (no millones de tiempos únicos en RAM).
                arrivals = sorted(result['evacuation_times'], key=lambda a: a['time_min'])
                arrival_mass = math.fsum(a['people'] for a in arrivals)
                cumulative = 0.
                for arrival in arrivals:
                    cumulative += arrival['people']
                    distribution_writer.writerow([scenario, r, arrival['time_min'], arrival['people'],
                                                  cumulative, cumulative / arrival_mass, bool(smoke)])
                if arrivals:
                    counts, _ = np.histogram([a['time_min'] for a in arrivals], bins=bin_edges,
                                             weights=[a['people'] for a in arrivals])
                    distributions[scenario] += counts
                distribution_stream.flush()
                del arrivals
                print(f'phase=distribution done scenario={scenario} replica={r}', flush=True)
                if r == 0 and scenario == scenarios[0]:
                    _write_json(output / 'example_replica.json',
                                representative_example(run, prepared, result, metrics))
                    print(f'phase=example done scenario={scenario} replica={r}', flush=True)
                del result, adapted, prepared
                print(f'{scenario} r={r + 1}/{replicas} done elapsed={time.perf_counter() - started:.3f}s', flush=True)
    summaries = {s: {metric: confidence_interval(row[metric] for row in rows[s])
                     for metric in rows[s][0]} for s in scenarios}
    paired = {}
    if 'base' in scenarios:
        for scenario in scenarios:
            if scenario != 'base':
                paired[scenario] = {
                    metric: confidence_interval(a[metric] - b[metric]
                                                for a, b in zip(rows[scenario], rows['base'])
                                                if a[metric] is not None and b[metric] is not None)
                    for metric in rows['base'][0]}
    summary = {'metadata': metadata, 'scenarios': summaries, 'paired_differences_vs_base': paired}
    _write_json(output / 'summary.json', summary)
    print('phase=plots start', flush=True)
    _plot_outputs(output, summaries, distributions, bin_edges, bool(smoke))
    print('phase=plots done', flush=True)
    print(f'phase=experiment complete elapsed={time.perf_counter() - started:.3f}s', flush=True)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description='Monte Carlo de evacuación hipotético, sin descargas.')
    for key, default in DEFAULTS.items():
        parser.add_argument('--' + key, type=Path, default=ROOT / default,
                            help=f'Ruta {key}; predeterminada relativa a raíz: {default}')
    parser.add_argument('--replicas', type=int, default=30, help='Réplicas distintas por escenario (predeterminado: 30)')
    parser.add_argument('--smoke', action='store_true', help='Permitir <30 réplicas; TODAS las salidas son provisionales')
    parser.add_argument('--scenario', choices=SCENARIOS, help='Solo este escenario; predeterminado: los cuatro')
    args = parser.parse_args(argv)
    try:
        run_experiments({key: getattr(args, key) for key in DEFAULTS}, args.replicas, args.smoke,
                        [args.scenario] if args.scenario else None)
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
