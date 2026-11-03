"""Carga de datos y utilidades de posición para el demo visual (sin Streamlit)."""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / 'salidas' / 'demo'
FINAL = ROOT / 'salidas' / 'evacuacion_final'
X0, Y0, RES = 609500.0, 4413500.0, 100.0
SHAPE = (205, 278)
# Estados de visualización
PREP, WAIT, MOVE, SAFE, FIRE = 0, 1, 2, 3, 4
STATE_NAMES = {PREP: 'Preparándose', WAIT: 'En cola / esperando ruta', MOVE: 'En movimiento',
               SAFE: 'A salvo (salió del dominio)', FIRE: 'Alcanzado por el fuego'}
STATE_COLORS = {PREP: '#8e9aaf', WAIT: '#7b2cbf', MOVE: '#1f77ff', SAFE: '#1db954', FIRE: '#e5134b'}
SCENARIO_LABELS = {'base': 'Base', 'early_alert': 'Alerta 30 min antes',
                   'skyway_closed': 'Cierre de Skyway', 'exit_capacity': 'Más capacidad en una salida'}
# Ubicaciones aproximadas (lat, lon) para enfocar el mapa; no son datos del modelo.
TOWNS = {'Paradise': (39.7596, -121.6219), 'Magalia': (39.8120, -121.5780),
         'Concow': (39.7650, -121.5090), 'Pulga': (39.7918, -121.4783)}


def xy_to_cell(x, y):
    return (np.clip(((Y0 - np.asarray(y)) // RES).astype(int), 0, SHAPE[0] - 1),
            np.clip(((np.asarray(x) - X0) // RES).astype(int), 0, SHAPE[1] - 1))


def town_xy():
    from pyproj import Transformer
    tr = Transformer.from_crs('EPSG:4326', 'EPSG:32610', always_xy=True)
    return {k: tuple(map(float, tr.transform(lon, lat))) for k, (lat, lon) in TOWNS.items()}


def load_static():
    net = json.loads((ROOT / 'data/procesado/red_vial.json').read_text())
    nid = {n['id']: i for i, n in enumerate(net['nodes'])}
    xy = np.array([[n['x'], n['y']] for n in net['nodes']])
    u = np.array([nid[e['u']] for e in net['edges']])
    v = np.array([nid[e['v']] for e in net['edges']])
    with np.load(ROOT / 'data/procesado/grilla_fuego.npz') as d:
        grid = {k: d[k] for k in d.files}
    with np.load(ROOT / 'salidas/fuego/llegada_replicas.npz') as d:
        fire, seeds = d['llegada_min'].astype(np.int16), d['semillas']
    r, c = xy_to_cell(xy[:, 0], xy[:, 1])
    return dict(
        xy=xy, u=u, v=v, node_cell=np.stack([r, c], 1),
        edge_cap=np.array([e['capacity'] for e in net['edges']]),
        edge_len=np.array([e['length_m'] for e in net['edges']]),
        edge_min=np.array([e['travel_min'] for e in net['edges']]),
        edge_name=[e.get('name') or '' for e in net['edges']],
        edge_mtfcc=np.array([e.get('mtfcc') or '' for e in net['edges']]),
        exits=np.array([nid[d['node']] for d in net['destinations']]),
        exit_names=[d['node'] for d in net['destinations']],
        grid=grid, fire=fire, seeds=seeds)


def available_runs():
    """Réplicas precalculadas: {(escenario, réplica): ruta}."""
    out = {}
    for p in sorted(DEMO.glob('*_r*.npz')):
        if '.cache' in p.name:
            continue
        s, _, r = p.stem.rpartition('_r')
        out[(s, int(r))] = p
    return out


def load_traj(path):
    """Carga una réplica; la primera vez guarda una caché ordenada y sin comprimir (carga ~10x más rápida)."""
    path = Path(path)
    cache = path.with_suffix('.cache2.npz')
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        with np.load(cache) as d:
            t = {k: d[k] for k in d.files}
    else:
        with np.load(path) as d:
            t = {k: d[k] for k in d.files}
        order = np.argsort(t['tr_group'], kind='stable')  # cada grupo conserva su orden temporal
        for k in ('tr_group', 'tr_edge', 'tr_start', 'tr_end', 'tr_outcome'):
            t[k] = t[k][order]
        # La historia trae un punto por evento (millones): se reduce a ~1000 puntos para graficar.
        n_hist = len(t['hist_t'])
        keep = np.unique(np.linspace(0, n_hist - 1, 1000).astype(int))
        for k in [k for k in t if k.startswith('hist_')]:
            t[k] = t[k][keep]
        t['moved'] = np.zeros(len(t['g_people']), bool)
        t['moved'][t['tr_group']] = True
        t['edge_people'] = np.bincount(t['tr_edge'], weights=t['g_people'][t['tr_group']],
                                       minlength=int(t['tr_edge'].max()) + 1).astype(np.float32)
        np.savez(cache, **t)
    t['meta'] = json.loads(str(t['meta']))
    t['jitter'] = np.random.default_rng(7).normal(0, 35, (len(t['g_people']), 2)).astype(np.float32)
    return t


def positions_at(static, traj, fire_rep, t):
    """Posición (x, y) y estado de cada grupo en el minuto t."""
    G = len(traj['g_people'])
    xy = static['xy']
    tg, te = traj['tr_group'], traj['tr_edge']
    state = np.where(t < traj['g_ready'], PREP, WAIT).astype(np.int8)
    node = traj['g_node'].copy()
    px = xy[node, 0].astype(np.float64)
    py = xy[node, 1].astype(np.float64)
    started = np.flatnonzero(traj['tr_start'] <= t)
    if started.size:
        g = tg[started]
        last = started[np.r_[g[1:] != g[:-1], True]]
        lg, le = tg[last], te[last]
        s, e, oc = traj['tr_start'][last], traj['tr_end'][last], traj['tr_outcome'][last]
        u, v = static['u'][le], static['v'][le]
        moving = (t < e) | (e < 0)
        frac = np.clip((t - s) / np.maximum(e - s, 1e-6), 0, 1)
        # Recorridos truncados por cierre/horizonte: la fracción real usa el tiempo nominal del tramo.
        nominal = np.minimum(frac, (t - s) / np.maximum(static['edge_min'][le], 1e-6))
        f = np.where(moving, np.clip(nominal, 0, 1), 1.0)
        at_v = ~moving & (oc == 0)
        end_node = np.where(at_v, v, u)
        tx = np.where(moving, xy[u, 0] + (xy[v, 0] - xy[u, 0]) * f, xy[end_node, 0])
        ty = np.where(moving, xy[u, 1] + (xy[v, 1] - xy[u, 1]) * f, xy[end_node, 1])
        px[lg], py[lg] = tx, ty
        node[lg] = np.where(moving, u, end_node)
        state[lg] = np.where(moving, MOVE, WAIT)
        # Si todavía no llegó la hora de salir (no ocurre tras un recorrido) se mantiene WAIT.
    safe = (traj['g_finish'] >= 0) & (traj['g_finish'] <= t)
    state[safe] = SAFE
    # Alcanzado: el nodo donde está ya ardió y no está a salvo ni en movimiento.
    rc = static['node_cell'][node]
    burnt = fire_rep[rc[:, 0], rc[:, 1]]
    hit = (burnt >= 0) & (burnt <= t) & ~safe & (state != MOVE)
    state[hit] = FIRE
    still = state != MOVE
    px = px + np.where(still, traj['jitter'][:, 0], 0)
    py = py + np.where(still, traj['jitter'][:, 1], 0)
    return px, py, state


def group_path(static, traj, gidx):
    """Tramos recorridos por un grupo: lista de (edge, start, end, outcome)."""
    lo = np.searchsorted(traj['tr_group'], gidx, 'left')
    hi = np.searchsorted(traj['tr_group'], gidx, 'right')
    return (traj['tr_edge'][lo:hi], traj['tr_start'][lo:hi], traj['tr_end'][lo:hi],
            traj['tr_outcome'][lo:hi])
