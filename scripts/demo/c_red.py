"""Concepto 2 · Redes: grafo vial dirigido, conectividad, destinos y selección de rutas."""
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.demo import datos as D
from scripts.demo.ui import banner, fire_trace, view_for
from scripts.demo.ui_extra import lazy_tabs, net_extra, plain_layout, seg_xy

EXIT_COLORS = ['#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4', '#00b3b3']
CLASS_INFO = {'S1200': ('Calle secundaria', '#d62728'), 'S1400': ('Calle local', '#555555'),
              'S1500': ('Camino 4x4', '#9467bd'), 'S1740': ('Camino privado', '#8c564b')}


@st.cache_data(show_spinner=False, max_entries=24)
def _tree(_S, blocked_bytes, exits_key):
    """Árbol de rutas más cortas hacia las salidas (cacheado por conjunto de cierres)."""
    blocked = np.unpackbits(np.frombuffer(blocked_bytes, np.uint8))[:len(_S['u'])].astype(bool)
    return D.route_tree(_S, blocked, np.array(exits_key))


def tree_for(S, blocked, exits_ok):
    return _tree(S, np.packbits(blocked).tobytes(), tuple(int(e) for e in exits_ok))


def render(S):
    X = net_extra()
    banner('net', '2', 'Redes: grafo vial dirigido, conectividad, destinos y selección de rutas',
           'La red vial es un <b>grafo dirigido G = (V, E)</b>: los <b>nodos</b> son intersecciones y las <b>aristas</b> son '
           'tramos con sentido, longitud, tiempo de viaje y capacidad. Sobre el grafo se estudia la '
           '<b>conectividad</b> (componentes), los <b>destinos</b> (salidas del dominio) y la <b>selección de rutas</b> '
           'de costo mínimo (Dijkstra), que cambia cuando el fuego cierra tramos.',
           '<code>scripts/evacuacion/red_vial.py</code> (construcción del grafo desde TIGER) y '
           '<code>scripts/evacuacion/motor.py</code> función <code>route()</code> (Dijkstra con cierres)',
           ['<b>Grafo dirigido:</b> cada calle genera dos aristas opuestas; el peso es el tiempo de viaje (min).',
            '<b>Conectividad:</b> componentes conexas; los nodos sin camino a una salida no pueden evacuar.',
            '<b>Destinos:</b> 6 salidas absorbentes (Skyway, Clark, Pentz, Neal…), cada una con capacidad finita.',
            '<b>Rutas:</b> cada grupo toma el camino de menor tiempo hacia la salida alcanzable más cercana.'])
    _sel = lazy_tabs(['🕸️ A · Estructura del grafo dirigido', '🧩 B · Conectividad y destinos',
                                    '🧭 C · Selección de rutas (Dijkstra)'], 'net', '#1f6feb')
    N, E = len(S['xy']), len(S['u'])
    summ = json.loads((D.FINAL / 'summary.json').read_text())['metadata']['attachment']

    # ------------------------------------------------------------ A) estructura
    if _sel == 0:
        m = st.columns(3)
        m[0].metric('Nodos (intersecciones)', f'{N:,}')
        m[1].metric('Aristas dirigidas', f'{E:,}', 'dos por cada calle (una por sentido)', delta_color='off')
        m[2].metric('Longitud de la red', f"{S['edge_len'].sum() / 2000:,.0f} km")
        outdeg = np.bincount(S['u'], minlength=N)
        c1, c2, c3, c4 = st.columns(4)
        zone = c1.selectbox('Zona a observar', list(D.TOWNS) + ['Todo el dominio'], index=1, key='ra')
        radius = c2.slider('Radio de la vista (km)', 0.3, 2.0, 0.45, 0.05, key='rrad') if zone != 'Todo el dominio' else 7
        show_nodes = c3.checkbox('Mostrar nodos', True)
        show_arrows = c4.checkbox('Mostrar sentido (flechas)', True,
                                  help='Cada arista dirigida se dibuja desplazada a la derecha de su sentido de marcha; '
                                       'se activa solo si hay pocas aristas en la vista')
        view = view_for(zone, radius)
        fig = go.Figure()
        vis = ((S['xy'][S['u'], 0] > view[0][0]) & (S['xy'][S['u'], 0] < view[0][1]) &
               (S['xy'][S['u'], 1] > view[1][0]) & (S['xy'][S['u'], 1] < view[1][1]))
        off = 0.007 * (view[0][1] - view[0][0])      # desplazamiento lateral proporcional al zoom
        arrows = zone != 'Todo el dominio' and show_arrows and vis.sum() <= 400
        if zone != 'Todo el dominio' and show_arrows and not arrows:
            st.info(f'Hay {int(vis.sum())} aristas en la vista: reduce el radio (≤ 400 aristas) para ver las flechas de sentido.')
        for cls, (label, col) in CLASS_INFO.items():
            ids = np.flatnonzero(vis & (S['edge_mtfcc'] == cls) & ((S['u'] < S['v']) | (not arrows)))
            if not len(ids):
                continue
            if arrows:   # ambos sentidos, cada uno desplazado a la derecha
                ids = np.flatnonzero(vis & (S['edge_mtfcc'] == cls))
                xs, ys = [], []
                for i in ids:
                    a, b = S['xy'][S['u'][i]], S['xy'][S['v'][i]]
                    d = b - a
                    n = np.array([d[1], -d[0]]) / max(np.hypot(*d), 1e-9) * off
                    xs += [a[0] + n[0], b[0] + n[0], None]
                    ys += [a[1] + n[1], b[1] + n[1], None]
                fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', line=dict(color=col, width=2.2), name=f'{label} ({cls})'))
                ax_, ay_, ang = [], [], []
                for i in ids:
                    a, b = S['xy'][S['u'][i]], S['xy'][S['v'][i]]
                    d = b - a
                    L = np.hypot(*d)
                    if L < 12:
                        continue
                    n = np.array([d[1], -d[0]]) / L * off
                    mid = a + n + d * .6
                    ax_.append(mid[0]); ay_.append(mid[1]); ang.append(float(np.degrees(np.arctan2(d[0], d[1]))))
                fig.add_trace(go.Scatter(x=ax_, y=ay_, mode='markers', showlegend=False, hoverinfo='skip',
                                         marker=dict(symbol='arrow', size=14, angle=ang, color=col, line=dict(width=0))))
            else:
                xs, ys = seg_xy(S, ids)
                fig.add_trace(go.Scattergl(x=xs, y=ys, mode='lines', line=dict(color=col, width=1.6), name=f'{label} ({cls})'))
        if show_nodes:
            nv = np.flatnonzero((S['xy'][:, 0] > view[0][0]) & (S['xy'][:, 0] < view[0][1]) &
                                (S['xy'][:, 1] > view[1][0]) & (S['xy'][:, 1] < view[1][1]))
            Node = go.Scatter if len(nv) <= 1500 else go.Scattergl
            fig.add_trace(Node(x=S['xy'][nv, 0].astype(np.float32), y=S['xy'][nv, 1].astype(np.float32), mode='markers',
                               name='Nodos (intersecciones)', marker=dict(size=8 if zone != 'Todo el dominio' else 2,
                                                                           color='#111', line=dict(width=1, color='white')),
                               hovertext=[f'nodo n{i} · grado de salida {outdeg[i]}' for i in nv] if len(nv) <= 1500 else None))
        ex = S['xy'][S['exits']]
        fig.add_trace(go.Scatter(x=ex[:, 0], y=ex[:, 1], mode='markers', name='Destinos (salidas)',
                                 marker=dict(symbol='star', size=18, color='#ffd400', line=dict(width=1.5, color='black'))))
        plain_layout(fig, view, height=640)
        st.plotly_chart(fig, width='stretch')
        st.caption('Cada tramo es **dos aristas opuestas** (una por sentido), cada una con su propia capacidad. Con '
                   '"flechas" activadas se ven los dos sentidos separados; en esta red la bidireccionalidad es un supuesto.')
        rp = X['road_params']
        tab = pd.DataFrame([{
            'Clase MTFCC': k, 'Tipo': CLASS_INFO[k][0], 'Aristas': int((S['edge_mtfcc'] == k).sum()),
            'Velocidad (km/h)': rp.get(k, {}).get('speed_kmh', '—'),
            'Capacidad (grupos simultáneos)': rp.get(k, {}).get('capacity_groups', '—'),
            'Longitud media (m)': round(float(S['edge_len'][S['edge_mtfcc'] == k].mean()), 1)} for k in CLASS_INFO])
        st.markdown('**Atributos de las aristas por jerarquía vial** (supuestos hipotéticos)')
        st.dataframe(tab, hide_index=True, width='stretch')

    # ------------------------------------------------------------ B) conectividad y destinos
    if _sel == 1:
        comp = X['node_comp']
        no_exit = np.array([not c['tiene_salida'] for c in X['comps']])[comp]
        m = st.columns(4)
        m[0].metric('Componentes conexas', len(X['comps']))
        m[1].metric('Nodos sin camino a una salida', f"{int(no_exit.sum()):,}", f'{100 * no_exit.mean():.1f} % de los nodos', delta_color='off')
        m[2].metric('Personas en esos nodos', f"{summ['people_no_exit']:.0f}", f"{100 * summ['fraction_people_no_exit']:.2f} % de la población", delta_color='off')
        m[3].metric('Destinos', len(X['dest']))
        fig = go.Figure()
        fig.add_trace(go.Scattergl(x=S['xy'][~no_exit, 0].astype(np.float32), y=S['xy'][~no_exit, 1].astype(np.float32), mode='markers',
                                   name='Componente principal (con salida)', marker=dict(size=2, color='#1f6feb'), hoverinfo='skip'))
        fig.add_trace(go.Scattergl(x=S['xy'][no_exit, 0].astype(np.float32), y=S['xy'][no_exit, 1].astype(np.float32), mode='markers',
                                   name='Componentes aisladas (sin salida)', marker=dict(size=7, color='#e5134b', line=dict(width=1, color='white')),
                                   hovertext=[f'componente {c["id"]}' for c in np.array(X['comps'])[comp[no_exit]]]))
        ex = S['xy'][S['exits']]
        fig.add_trace(go.Scatter(x=ex[:, 0], y=ex[:, 1], mode='markers+text', text=[f'D{i + 1}' for i in range(len(ex))],
                                 textposition='top center', name='Destinos', marker=dict(symbol='star', size=18, color='#ffd400',
                                                                                         line=dict(width=1.5, color='black'))))
        plain_layout(fig, view_for('Todo el dominio'), height=600)
        a, b = st.columns([2, 1])
        a.plotly_chart(fig, width='stretch')
        b.markdown('**Componentes conexas**')
        b.dataframe(pd.DataFrame(X['comps']).rename(columns={'id': 'Componente', 'nodos': 'Nodos', 'tiene_salida': '¿Tiene salida?'}),
                    hide_index=True, width='stretch', height=290)
        b.caption('Una componente es un conjunto de nodos mutuamente alcanzables. Sin salida en su componente, los '
                  'grupos ubicados ahí **no pueden evacuar** (el modelo no inventa puentes).')
        st.markdown('**Destinos (salidas del dominio)**')
        rows = []
        for i, d in enumerate(X['dest']):
            inc = np.flatnonzero((S['u'] == d['idx']) | (S['v'] == d['idx']))
            names = sorted({S['edge_name'][j] for j in inc if S['edge_name'][j]})
            rows.append({'Destino': f'D{i + 1}', 'Nodo': d['nodo'], 'Tipo': 'Seguro (absorbente, hipotético)',
                         'Capacidad base (personas)': 5000, 'Vía(s) de acceso': ', '.join(names) or '—'})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        st.caption('Los destinos son un supuesto de escenario: salidas absorbentes fuera del dominio con capacidad finita '
                   '(5 000 personas; 10 000 en el escenario de mayor capacidad en una salida).')

    # ------------------------------------------------------------ C) selección de rutas
    if _sel == 2:
        st.markdown('**Selección de rutas:** para cada nodo se calcula el camino de menor tiempo hacia la salida más cercana '
                    '(Dijkstra multi-fuente sobre el grafo invertido). Cuando una arista se cierra —por política o porque '
                    'el fuego la alcanza— se recalcula y la ruta cambia (o desaparece).')
        c1, c2, c3 = st.columns(3)
        scen = c1.radio('Estado de la red', ['Red completa', 'Skyway cerrada (política)', 'Cierre por fuego'], key='rs')
        town = c2.selectbox('Origen: nodo cercano a', list(D.TOWNS), key='rt')
        k = c3.slider('Nodo candidato (0 = el más cercano)', 0, 80, 12, key='rk')
        rep, t = 0, 240
        also_sky = False
        if scen == 'Cierre por fuego':
            f1, f2, f3 = st.columns(3)
            rep = f1.slider('Réplica de fuego', 0, 29, 0, key='rrep')
            t = f2.slider('Minuto del incendio', 0, 480, 200, key='rt2')
            also_sky = f3.checkbox('Además Skyway cerrada', False)
        fire = S['fire'][rep]
        ef = D.edge_fire_times(X, E, fire)
        nf = D.node_fire_times(S, fire)
        blocked = np.zeros(E, bool)
        if scen.startswith('Skyway') or also_sky:
            blocked |= D.skyway_mask(S)
        if scen == 'Cierre por fuego':
            blocked |= (ef <= t) | (nf[S['u']] <= t)
        exits_ok = np.array([e for e in S['exits'] if scen != 'Cierre por fuego' or nf[e] > t])
        base_tree = tree_for(S, np.zeros(E, bool), S['exits'])
        tree = tree_for(S, blocked, exits_ok)
        tx, ty = D.town_xy()[town]
        order = np.argsort(np.hypot(S['xy'][:, 0] - tx, S['xy'][:, 1] - ty))
        origin = int(order[k])
        p0 = D.route_path(S, base_tree, origin)
        p1 = D.route_path(S, tree, origin)
        exit_idx = {int(e): i for i, e in enumerate(S['exits'])}

        def info(path, tr):
            if path is None:
                return None
            nodes, edges = path
            return dict(min=float(tr[0][origin]), km=float(S['edge_len'][edges].sum() / 1000),
                        exit=exit_idx[int(tr[2][origin])] + 1, n=len(edges))
        i0, i1 = info(p0, base_tree), info(p1, tree)
        m = st.columns(5)
        m[0].metric('Nodo origen', f'n{origin}')
        m[1].metric('Ruta con red completa', f"{i0['min']:.1f} min" if i0 else 'sin ruta',
                    f"{i0['km']:.1f} km → salida D{i0['exit']}" if i0 else None, delta_color='off')
        if i1:
            extra = f"{i1['min'] - i0['min']:+.1f} min · " if i0 else ''
            m[2].metric('Ruta en este estado', f"{i1['min']:.1f} min", f"{extra}{i1['km']:.1f} km → D{i1['exit']}", delta_color='off')
        else:
            m[2].metric('Ruta en este estado', '❌ sin ruta a ninguna salida')
        reach0, reach1 = np.isfinite(base_tree[0]), np.isfinite(tree[0])
        changed = int(((base_tree[2] != tree[2]) & reach0 & reach1).sum())
        m[3].metric('Nodos que cambian de salida', f'{changed:,}')
        m[4].metric('Nodos sin salida (nuevos)', f'{int((reach0 & ~reach1).sum()):,}')
        fig = go.Figure()
        if scen == 'Cierre por fuego':
            fig.add_trace(fire_trace(fire, t, .35, colorbar=False))
        # cuencas de atracción: a qué salida llega cada nodo
        src = tree[2]
        for i, e in enumerate(S['exits']):
            sel = np.flatnonzero(reach1 & (src == e))
            fig.add_trace(go.Scattergl(x=S['xy'][sel, 0].astype(np.float32), y=S['xy'][sel, 1].astype(np.float32), mode='markers',
                                       name=f'Nodos → D{i + 1}', marker=dict(size=3, color=EXIT_COLORS[i]), hoverinfo='skip'))
        lost = np.flatnonzero(~reach1)
        fig.add_trace(go.Scattergl(x=S['xy'][lost, 0].astype(np.float32), y=S['xy'][lost, 1].astype(np.float32), mode='markers',
                                   name='Sin ruta a salida', marker=dict(size=4, color='#222222'), hoverinfo='skip'))
        if blocked.any():
            xs, ys = seg_xy(S, np.flatnonzero(blocked & (S['u'] < S['v'])))
            fig.add_trace(go.Scattergl(x=xs, y=ys, mode='lines', name='Tramos cerrados', line=dict(color='#00e5ff', width=3), hoverinfo='skip'))
        if p0:
            xs, ys = seg_xy(S, p0[1])
            fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', name='Ruta con red completa', line=dict(color='#ffffff', width=9), hoverinfo='skip'))
            fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', name='Ruta con red completa ', showlegend=False,
                                     line=dict(color='#777777', width=4, dash='dot'), hoverinfo='skip'))
        if p1:
            xs, ys = seg_xy(S, p1[1])
            fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', name='Ruta elegida', line=dict(color='#000000', width=8), hoverinfo='skip'))
            fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', name='Ruta elegida ', showlegend=False,
                                     line=dict(color='#ffe600', width=4), hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=[S['xy'][origin, 0]], y=[S['xy'][origin, 1]], mode='markers', name='Origen',
                                 marker=dict(size=16, color='white', line=dict(width=4, color='black'))))
        ex = S['xy'][S['exits']]
        fig.add_trace(go.Scatter(x=ex[:, 0], y=ex[:, 1], mode='markers+text', text=[f'D{i + 1}' for i in range(len(ex))],
                                 textposition='top center', name='Destinos',
                                 marker=dict(symbol='star', size=18, color='#ffd400', line=dict(width=1.5, color='black'))))
        view = view_for('Todo el dominio') if st.checkbox('Ver todo el dominio', False, key='rfull') else view_for(town, 6)
        plain_layout(fig, view, height=680)
        a, b = st.columns([2.4, 1])
        a.plotly_chart(fig, width='stretch')
        b.markdown('**Itinerario de la ruta elegida**')
        if p1:
            nodes, edges = p1
            rows, cum = [], 0.0
            for e in edges:
                cum += float(S['edge_min'][e])
                nm = S['edge_name'][e] or '(sin nombre)'
                if rows and rows[-1]['Calle'] == nm:
                    rows[-1]['Tramos'] += 1
                    rows[-1]['Min acum.'] = round(cum, 1)
                    rows[-1]['m'] += round(float(S['edge_len'][e]))
                else:
                    rows.append({'Calle': nm, 'Tramos': 1, 'm': round(float(S['edge_len'][e])), 'Min acum.': round(cum, 1)})
            b.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        else:
            b.error('Este nodo no tiene camino a ninguna salida en el estado elegido.')
        b.caption('Cada color es la salida a la que llegaría cada nodo (su "cuenca"). Línea punteada gris = ruta con la red '
                  'completa; línea amarilla = ruta tras los cierres.')
