"""Carga de datos y utilidades de posición para el demo visual (sin Streamlit)."""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / 'salidas' / 'demo'
FINAL = ROOT / 'salidas' / 'evacuacion_final'
X0, Y0, RES = 609500.0, 4413500.0, 100.0
SHAPE = (205, 278)
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


def group_path(static, traj, gidx):
    """Tramos recorridos por un grupo: lista de (edge, start, end, outcome)."""
    lo = np.searchsorted(traj['tr_group'], gidx, 'left')
    hi = np.searchsorted(traj['tr_group'], gidx, 'right')
    return (traj['tr_edge'][lo:hi], traj['tr_start'][lo:hi], traj['tr_end'][lo:hi],
            traj['tr_outcome'][lo:hi])


# ===================================================================== extras de red (grafo)
CLASES_COMB = {-1: 'no combustible', 0: 'urbano', 1: 'pasto (GR)', 2: 'pasto-arbusto (GS)',
               3: 'arbustal (SH)', 4: 'sotobosque (TU)', 5: 'hojarasca (TL)', 6: 'restos de corta (SB)'}
COLORES_COMB = {-1: '#bdbdbd', 0: '#4d4d4d', 1: '#f1e05a', 2: '#b5d96b', 3: '#d98e3f',
                4: '#1f7a3d', 5: '#7b5a35', 6: '#a14fa1'}
VECINAS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
VECINAS_NOMBRE = {(-1, -1): 'NO', (-1, 0): 'N', (-1, 1): 'NE', (0, -1): 'O', (0, 1): 'E',
                  (1, -1): 'SO', (1, 0): 'S', (1, 1): 'SE'}


def load_net_extra():
    """Metadatos del grafo: celdas por tramo, componentes conexas, parámetros viales y destinos."""
    net = json.loads((ROOT / 'data/procesado/red_vial.json').read_text())
    nid = {n['id']: i for i, n in enumerate(net['nodes'])}
    ec_edge, ec_r, ec_c = [], [], []
    for i, e in enumerate(net['edges']):
        for r, c in e['cells']:
            ec_edge.append(i); ec_r.append(r); ec_c.append(c)
    meta = net['metadata']
    node_comp = np.full(len(net['nodes']), -1, np.int32)
    comps = []
    for k, comp in enumerate(meta['connectivity']['components']):
        node_comp[[nid[n] for n in comp['nodes']]] = k
        comps.append({'id': comp['id'], 'nodos': len(comp['nodes']), 'tiene_salida': bool(comp['has_exit'])})
    return dict(ec_edge=np.array(ec_edge), ec_r=np.array(ec_r), ec_c=np.array(ec_c),
                node_comp=node_comp, comps=comps, road_params=meta['road_parameters'],
                nodes_without_exit=meta['connectivity']['nodes_without_exit'],
                dest=[{'nodo': d['node'], 'idx': nid[d['node']], 'capacidad': d['capacity']}
                      for d in net['destinations']])


def edge_fire_times(extra, n_edges, fire_rep):
    """Minuto en que el fuego alcanza el primer tramo-celda de cada arista (inf si nunca)."""
    v = fire_rep[extra['ec_r'], extra['ec_c']].astype(np.float64)
    v[v < 0] = np.inf
    out = np.full(n_edges, np.inf)
    np.minimum.at(out, extra['ec_edge'], v)
    return out


def node_fire_times(static, fire_rep):
    v = fire_rep[static['node_cell'][:, 0], static['node_cell'][:, 1]].astype(np.float64)
    v[v < 0] = np.inf
    return v


def skyway_mask(static):
    import re
    pat = re.compile(r'\bSkyway\b', re.IGNORECASE)
    return np.array([bool(pat.search(n)) for n in static['edge_name']])


def route_tree(static, blocked, exits_ok):
    """Dijkstra inverso multi-fuente desde las salidas, sobre las aristas no cerradas.

    Devuelve (dist, pred, fuente, claves, ids): pred[n] es el siguiente nodo hacia la salida.
    """
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    N = len(static['xy'])
    ok = np.flatnonzero(~blocked)
    u, v, w = static['u'][ok], static['v'][ok], static['edge_min'][ok]
    key = v.astype(np.int64) * N + u            # grafo invertido: fila=v, columna=u
    order = np.lexsort((w, key))
    key_s = key[order]
    first = np.r_[True, key_s[1:] != key_s[:-1]]
    sel = order[first]                           # arista más rápida entre cada par (v,u)
    G = csr_matrix((w[sel], (v[sel], u[sel])), shape=(N, N))
    dist, pred, src = dijkstra(G, directed=True, indices=exits_ok, return_predecessors=True, min_only=True)
    return dist, pred, src, key_s[first], ok[sel]


def route_path(static, tree, origin):
    """Lista de (nodo, arista) desde origin hasta su salida; None si no hay ruta."""
    dist, pred, src, keys, ids = tree
    if not np.isfinite(dist[origin]):
        return None
    N = len(static['xy'])
    nodes, edges = [origin], []
    cur = origin
    while pred[cur] >= 0 and src[cur] != cur:
        nxt = int(pred[cur])
        edges.append(int(ids[np.searchsorted(keys, nxt * N + cur)]))
        nodes.append(nxt)
        cur = nxt
    return nodes, edges


# ===================================================================== autómata (fuego)
def fuego_modulos():
    import sys
    sys.path.insert(0, str(ROOT / 'scripts' / 'fuego'))
    import modelo_fuego as M
    return M


def viento_en(minuto):
    import csv
    rows = list(csv.DictReader(open(ROOT / 'data/procesado/viento_era5.csv')))
    m = np.array([float(r['minuto']) for r in rows])
    return (float(np.interp(minuto, m, [float(r['velocidad_ms']) for r in rows])),
            float(np.interp(minuto, m, [float(r['direccion_desde_grados']) for r in rows])))


def moore_probabilidades(clase, elev, r, c, params, vel_ms, desde_deg, res=100.0):
    """Probabilidad por minuto con que cada vecina ardiendo enciende a la celda central (r, c)."""
    V = params.factor_viento * vel_ms
    desde = np.radians(desde_deg)
    hacia = np.array([-np.sin(desde), -np.cos(desde)])
    filas = []
    for df, dc in VECINAS:
        d = np.array([-dc, df], float)
        d /= np.hypot(*d)
        cos_t = float(d @ hacia)
        dist = res * np.hypot(df, dc)
        theta_s = float(np.degrees(np.arctan((elev[r, c] - elev[r + df, c + dc]) / dist)))
        p_w = float(np.exp(params.c1 * V) * np.exp(V * params.c2 * (cos_t - 1)))
        p_s = float(np.exp(params.a_pendiente * theta_s))
        k = int(clase[r, c])
        p_veg = params.p_veg[k] if k >= 0 else None
        p_h = params.p_h
        base = 0.0 if p_veg is None else p_h * (1 + p_veg) * p_s
        p = 1.0 - (1.0 - min(max(base * p_w, 0.0), 1.0)) ** params.paso_min
        filas.append(dict(vecina=(df, dc), nombre=VECINAS_NOMBRE[(df, dc)], clase_vecina=int(clase[r + df, c + dc]),
                          elev_vecina=float(elev[r + df, c + dc]), theta_s=theta_s, cos_theta=cos_t,
                          p_w=p_w, p_s=p_s, p_veg=p_veg, p_h=p_h, p=p))
    return filas
