"""Precalcula una réplica completa (con trayectorias) para el demo visual.

Usa el mismo motor y las mismas entradas que el Monte Carlo, pero conserva el
detalle de cada recorrido (retain_details=True) y lo guarda en un .npz compacto.

    .venv/Scripts/python scripts/demo/precomputar.py --scenario base --replica 0
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.evacuacion.experimentos import (DEFAULTS, SCENARIOS, load_inputs, make_groups,
                                             scenario_inputs)
from scripts.evacuacion.motor import simulate

OUT = ROOT / 'salidas' / 'demo'
OUTCOMES = {'arrived': 0, 'interrupted': 1, 'horizon': 2, 'active': 3}
STATES = {'safe': 0, 'temporary': 1, 'stranded': 2, 'preparing': 3, 'waiting': 4, 'traveling': 5}


def run(scenario, replica, inputs):
    network, population, fire, seeds, contract, config, details, hashes = inputs
    groups, _ = make_groups(population, network, contract, config,
                            config['preparation_seed_start'] + replica)
    adapted, prepared, closed, intervention = scenario_inputs(network, groups, config, scenario)
    t0 = time.perf_counter()
    result = simulate(adapted, prepared, fire[replica].tolist(),
                      horizon=contract['horizonte_min'], closed_edges=closed,
                      retain_details=True,
                      progress=lambda s: print(f"  t={s['time_min']:.0f} min  seguras={s['people_safe']:.0f}", flush=True))
    print(f'  simulación: {time.perf_counter() - t0:.1f} s')
    edge_index = {e['id']: i for i, e in enumerate(network['edges'])}
    group_index = {g['id']: i for i, g in enumerate(prepared)}
    tr = result['traversals']
    n = len(tr)
    arr = {
        'tr_group': np.fromiter((group_index[r['group']] for r in tr), np.int32, n),
        'tr_edge': np.fromiter((edge_index[r['edge']] for r in tr), np.int32, n),
        'tr_start': np.fromiter((r['start_min'] for r in tr), np.float32, n),
        'tr_end': np.fromiter((r['end_min'] if r['end_min'] is not None else -1 for r in tr), np.float32, n),
        'tr_outcome': np.fromiter((OUTCOMES[r['outcome']] for r in tr), np.int8, n),
    }
    fg = result['groups']
    node_index = {nd['id']: i for i, nd in enumerate(network['nodes'])}
    arr.update(
        g_people=np.array([g['people'] for g in prepared], np.float32),
        g_node=np.array([node_index[g['node']] for g in prepared], np.int32),
        g_ready=np.array([g['ready_min'] for g in prepared], np.float32),
        g_cell=np.array([g['origin_cell'] for g in prepared], np.int16),
        g_state=np.array([STATES[g['state']] for g in fg], np.int8),
        g_finish=np.array([g['finish_min'] if g['finish_min'] is not None else -1 for g in fg], np.float32),
        g_exposed=np.array([g['exposed'] for g in fg], bool),
        g_dest=np.array([node_index[g['destination']] if g['destination'] in node_index else -1 for g in fg], np.int32),
        closed_edges=np.array([edge_index[e] for e in closed], np.int32),
        hist_t=np.array([h['time_min'] for h in result['history']], np.float32),
        hist_safe=np.array([h['people_safe'] for h in result['history']], np.float32),
        hist_exposed=np.array([h['people_exposed'] for h in result['history']], np.float32),
        hist_qpeople=np.array([h['queue_people'] for h in result['history']], np.float32),
        hist_qgroups=np.array([h['queue_groups'] for h in result['history']], np.float32),
        edge_peak=np.array([result['edge_max_occupancy'][e['id']] for e in network['edges']], np.int16),
    )
    scalars = {k: v for k, v in result.items() if isinstance(v, (int, float, bool))}
    meta = {'scenario': scenario, 'replica': replica, 'fire_seed': int(seeds[replica]),
            'preparation_seed': config['preparation_seed_start'] + replica,
            'traversals': n, 'groups': len(prepared), 'metrics': scalars, **intervention}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f'{scenario}_r{replica}.npz'
    np.savez_compressed(path, meta=np.array(json.dumps(meta)), **arr)
    print(f'  guardado {path.name}: {n} recorridos, {path.stat().st_size / 1e6:.1f} MB')


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--scenario', nargs='+', default=['base'], choices=SCENARIOS + ('all',))
    p.add_argument('--replica', type=int, nargs='+', default=[0])
    a = p.parse_args()
    scenarios = SCENARIOS if 'all' in a.scenario else a.scenario
    paths = {k: ROOT / v for k, v in DEFAULTS.items()}
    inputs = load_inputs(paths, 30, False)
    for r in a.replica:
        for s in scenarios:
            print(f'== {s} réplica {r}')
            run(s, r, inputs)


if __name__ == '__main__':
    main()
