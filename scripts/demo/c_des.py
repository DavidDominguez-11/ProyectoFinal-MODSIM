"""Concepto 3 · Simulación de eventos discretos (DES): entidades, recursos y colas."""
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.demo import datos as D
from scripts.demo.ui import banner, base_layout, fire_trace, pick_run, view_for
from scripts.demo.ui_extra import lazy_tabs, net_extra, seg_xy

ORANGE = '#f08a00'
PRIORITY = {'closure': 0, 'node_fire': 1, 'arrival': 2, 'ready': 3}
STATE_LABEL = {0: 'a salvo', 1: 'refugio temporal', 2: 'alcanzado por el fuego', 3: 'preparándose',
               4: 'esperando en cola', 5: 'en ruta'}


def wquantile(x, w, q):
    o = np.argsort(x)
    cw = np.cumsum(w[o])
    return float(x[o][np.searchsorted(cw, q * cw[-1])])


@st.cache_resource(show_spinner='Indexando los recorridos por arista (recurso)…')
def edge_index(_T, key, n_edges):
    order = np.argsort(_T['tr_edge'], kind='stable')
    starts = np.searchsorted(_T['tr_edge'][order], np.arange(n_edges + 1))
    return order, starts


def occupancy(T, order, starts, e, horizon=480.0):
    sel = order[starts[e]:starts[e + 1]]
    s, en = T['tr_start'][sel], T['tr_end'][sel].copy()
    en[en < 0] = horizon
    times = np.concatenate([s, en]).astype(np.float64)
    delta = np.concatenate([np.ones(len(s)), -np.ones(len(en))])
    o = np.lexsort((delta, times))            # a igual tiempo, primero salen y luego entran
    return times[o], np.cumsum(delta[o]), len(s)


@st.cache_data(show_spinner='Calculando saturación de las aristas más usadas…')
def resource_table(_T, key, _S, _idx):
    order, starts = _idx
    counts = np.diff(starts)
    top = np.argsort(-counts)[:80]
    rows = []
    for e in top:
        if counts[e] == 0:
            continue
        t, occ, n = occupancy(_T, order, starts, int(e))
        cap = int(_S['edge_cap'][e])
        dt = np.diff(np.r_[t, 480.0])
        sat = float(dt[occ >= cap].sum())
        rows.append(dict(arista=int(e), calle=_S['edge_name'][e] or f'tramo {e}', capacidad=cap, grupos=n,
                         ocupacion_max=int(occ.max()), saturada_min=round(sat, 1),
                         utilizacion=round(float((dt * occ).sum() / 480.0 / cap), 3)))
    return pd.DataFrame(rows).sort_values('saturada_min', ascending=False).reset_index(drop=True)


@st.cache_data(show_spinner='Calculando tiempos de espera de los 50 mil grupos…')
def wait_stats(_T, key):
    T = _T
    tg, ts, te = T['tr_group'], T['tr_start'], T['tr_end']
    G = len(T['g_ready'])
    first = np.r_[True, tg[1:] != tg[:-1]]
    last = np.r_[first[1:], True]
    same = ~first[1:]
    wait = np.zeros(G)
    gaps = ts[1:][same] - te[:-1][same]
    wait += np.bincount(tg[1:][same], weights=np.maximum(gaps, 0), minlength=G)
    fi = np.flatnonzero(first)
    wait[tg[fi]] += np.maximum(ts[fi] - T['g_ready'][tg[fi]], 0)
    travel = np.bincount(tg, weights=np.maximum(te - ts, 0), minlength=G)
    li = np.flatnonzero(last)
    g_last = tg[li]
    pend = (T['g_finish'][g_last] < 0) & (T['g_state'][g_last] == 4)
    wait[g_last[pend]] += np.maximum(480 - te[li][pend], 0)
    never = ~T['moved'] & (T['g_ready'] < 480)
    wait[never] = 480 - T['g_ready'][never]
    return wait, travel, never


@st.cache_data(show_spinner=False)
def event_histogram(_T, key, _S, _X, rep):
    bins = np.arange(0, 491, 10)
    ef = D.edge_fire_times(_X, len(_S['u']), _S['fire'][rep])
    nf = D.node_fire_times(_S, _S['fire'][rep])
    return dict(bins=bins,
                ready=np.histogram(_T['g_ready'], bins)[0],
                arrival=np.histogram(_T['tr_end'][_T['tr_outcome'] == 0], bins)[0],
                interrupt=np.histogram(_T['tr_end'][_T['tr_outcome'] == 1], bins)[0],
                closure=np.histogram(ef[np.isfinite(ef)], bins)[0],
                node_fire=np.histogram(nf[np.isfinite(nf)], bins)[0])


def render(S, runs):
    X = net_extra()
    banner('des', '3', 'DES: simulación de eventos discretos (entidades, recursos y colas)',
           'El sistema cambia de estado solo en instantes discretos (<b>eventos</b>) que se procesan en orden de tiempo. '
           'Las <b>entidades</b> (aquí, grupos de evacuados) fluyen por el sistema, compiten por <b>recursos</b> de '
           'capacidad limitada (aquí, las aristas viales) y cuando el recurso está lleno esperan en una <b>cola</b>.',
           '<code>scripts/evacuacion/motor.py</code> → <code>simulate()</code>: cola de eventos con <code>heapq</code>, '
           'estados de cada grupo, ocupación por arista y despacho FIFO',
           ['<b>Entidades:</b> 50 314 grupos con peso (personas), nodo de origen, hora de salida y estado.',
            '<b>Recursos:</b> 64 098 aristas dirigidas, cada una con capacidad de <i>c</i> grupos simultáneos (servidores); '
            'los destinos tienen capacidad en personas.',
            '<b>Eventos ordenados:</b> <code>closure</code> (0) → <code>node_fire</code> (1) → <code>arrival</code> (2) → '
            '<code>ready</code> (3), desempatados por orden de llegada.',
            '<b>Métricas de espera:</b> longitud de cola, tiempo en cola por grupo, saturación de cada recurso.'])
    sc, rep, T = pick_run(runs, 'des')
    key = f'{sc}_{rep}'
    _sel = lazy_tabs(['🧱 A · Anatomía: entidades, recursos, eventos', '📅 B · Agenda de eventos ordenada',
                                          '🚦 C · Recursos con capacidad', '⏳ D · Colas y métricas de espera'], 'des', '#f08a00')
    E = len(S['u'])
    G = len(T['g_ready'])
    w = T['g_people']
    ef = D.edge_fire_times(X, E, S['fire'][rep])

    # ------------------------------------------------------------ A) anatomía
    if _sel == 0:
        n_end = int((T['tr_outcome'] == 0).sum())
        m = st.columns(4)
        m[0].metric('Entidades (grupos)', f'{G:,}', f'{w.sum():,.0f} personas', delta_color='off')
        m[1].metric('Recursos (aristas)', f'{E:,}', 'capacidad 5–25 grupos', delta_color='off')
        m[2].metric('Eventos "arrival" procesados', f'{n_end:,}')
        m[3].metric('Eventos de fuego (cierres)', f'{int(np.isfinite(ef).sum()):,}')
        dot = '''digraph G { rankdir=LR; bgcolor="transparent"; fontname="Helvetica";
        node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=14, color="#444444", fontcolor="#111111"];
        edge [fontname="Helvetica", fontsize=13, fontcolor="#e8e8e8", color="#b0b5ba"]; ranksep=0.9; nodesep=0.5;
        prep [label="PREPARÁNDOSE\\n(entidad aún en su hogar)", fillcolor="#e3e6ea"];
        wait [label="EN COLA (FIFO)\\nespera ruta o capacidad", fillcolor="#e9d5f5"];
        move [label="EN ARISTA\\nocupa 1 de c servidores", fillcolor="#fde0b3"];
        safe [label="A SALVO\\n(destino con capacidad)", fillcolor="#c8e6c9"];
        hit  [label="ALCANZADO\\npor el fuego", fillcolor="#ffcdd2"];
        prep -> wait [label="ready\\n(alerta + preparación)", color="#f08a00"];
        wait -> move [label="arista libre\\n(despacho)"];
        move -> wait [label="arrival en nodo\\nintermedio", color="#f08a00"];
        move -> safe [label="arrival en destino", color="#f08a00"];
        move -> wait [label="closure:\\ninterrumpe y re-rutea", color="#d62800", style=dashed];
        wait -> hit [label="node_fire", color="#d62800"];
        prep -> hit [label="node_fire /\\norigin_fire", color="#d62800"];
        }'''
        st.graphviz_chart(dot, width='stretch')
        st.markdown('**Mapa de conceptos DES → código del proyecto**')
        st.dataframe(pd.DataFrame([
            ('Entidad', 'Grupo de personas (hasta 3 ponderadas)', 'id, people, node, ready_min, state', 'lista `states` en simulate()'),
            ('Recurso', 'Arista vial dirigida', 'capacity = servidores simultáneos', 'diccionario `occupancy[arista]`'),
            ('Recurso (destino)', 'Salida segura', 'capacity en personas', '`reserved` / `arrived`'),
            ('Cola', 'Espera FIFO global por ticket', 'grupos listos sin arista libre o sin ruta', '`waiting`, `blocked`, `queue_since`'),
            ('Evento', 'closure · node_fire · arrival · ready · sample', 'tiempo, prioridad, secuencia', 'montículo `events` (heapq)'),
            ('Reloj', 'Avanza al siguiente evento (no por pasos fijos)', 'time = events[0][0]', 'bucle `while events`'),
            ('Métricas', 'Cola máx., persona·min en cola, saturación', 'queue_person_minutes, max_queue_people', 'resultado de simulate()'),
        ], columns=['Concepto DES', 'En este modelo', 'Atributos', 'Dónde en motor.py']), hide_index=True, width='stretch')
        st.caption('El reloj **salta** de evento en evento: entre dos eventos no ocurre nada que simular. Por eso 22,8 millones de '
                   'llegadas a aristas se procesan en minutos y no en 480 pasos de 1 minuto × 50 mil grupos.')

    # ------------------------------------------------------------ B) agenda de eventos
    if _sel == 1:
        st.markdown('**Agenda de eventos:** se procesan siempre por **(tiempo, prioridad, orden de inserción)**. Elige una ventana '
                    'de tiempo para ver los eventos reales de esta corrida en el orden exacto en que el motor los atiende.')
        c1, c2 = st.columns(2)
        t0 = c1.slider('Inicio de la ventana (min)', 0.0, 479.0, 100.0, 0.5, key='dt0')
        width = c2.slider('Ancho de la ventana (min)', 0.05, 5.0, 0.5, 0.05, key='dtw')
        t1 = t0 + width
        nf = D.node_fire_times(S, S['fire'][rep])
        ev = []
        ids = np.flatnonzero((T['g_ready'] >= t0) & (T['g_ready'] < t1))
        n_ready = len(ids)
        mask_all = (T['tr_end'] >= t0) & (T['tr_end'] < t1) & (T['tr_outcome'] <= 1)
        n_arr = int(np.count_nonzero(mask_all & (T['tr_outcome'] == 0)))
        n_int = int(np.count_nonzero(mask_all & (T['tr_outcome'] == 1)))
        n_clo = int(np.count_nonzero((ef >= t0) & (ef < t1)))
        n_nf = int(np.count_nonzero((nf >= t0) & (nf < t1)))
        ev += [(float(T['g_ready'][i]), 3, 'ready', f'g{i:07d}', f"nodo n{T['g_node'][i]}", f"{w[i]:.2f} personas listas para salir") for i in ids[:400]]
        mask = (T['tr_end'] >= t0) & (T['tr_end'] < t1) & (T['tr_outcome'] <= 1)
        for j in np.flatnonzero(mask)[:600]:
            g, e, oc = int(T['tr_group'][j]), int(T['tr_edge'][j]), int(T['tr_outcome'][j])
            nm = S['edge_name'][e] or f'tramo {e}'
            if oc == 0:
                fin = T['g_finish'][g] >= 0 and abs(T['g_finish'][g] - T['tr_end'][j]) < 1e-4
                ev.append((float(T['tr_end'][j]), 2, 'arrival', f'g{g:07d}', f'arista e{e} · {nm}',
                           'llega a destino seguro' if fin else 'llega al nodo siguiente y vuelve a la cola'))
            else:
                ev.append((float(T['tr_end'][j]), 0, 'closure', f'g{g:07d}', f'arista e{e} · {nm}', 'tramo cerrado por el fuego: grupo interrumpido y expuesto'))
        for e in np.flatnonzero((ef >= t0) & (ef < t1))[:200]:
            ev.append((float(ef[e]), 0, 'closure', '—', f'arista e{e} · {S["edge_name"][e] or "sin nombre"}', 'el fuego alcanza el tramo: se cierra'))
        for n in np.flatnonzero((nf >= t0) & (nf < t1))[:200]:
            ev.append((float(nf[n]), 1, 'node_fire', '—', f'nodo n{n}', 'el fuego alcanza el nodo'))
        ev.sort(key=lambda r: (r[0], r[1]))
        df = pd.DataFrame(ev, columns=['Tiempo (min)', 'Prioridad', 'Tipo de evento', 'Entidad', 'Recurso / lugar', 'Qué ocurre'])
        df.insert(0, '#', np.arange(1, len(df) + 1))
        m = st.columns(5)
        m[0].metric('closure (prioridad 0)', f'{n_clo + n_int:,}', f'{n_clo} tramos + {n_int} interrupciones', delta_color='off')
        m[1].metric('node_fire (prioridad 1)', f'{n_nf:,}')
        m[2].metric('arrival (prioridad 2)', f'{n_arr:,}')
        m[3].metric('ready (prioridad 3)', f'{n_ready:,}')
        m[4].metric('Eventos en la ventana', f'{n_clo + n_int + n_nf + n_arr + n_ready:,}', f'la tabla lista hasta {len(df):,}', delta_color='off')
        st.dataframe(df.round({'Tiempo (min)': 3}), hide_index=True, width='stretch', height=380)
        h = event_histogram(T, key, S, X, rep)
        ctr = h['bins'][:-1] + 5
        fig = go.Figure()
        for k, nm, col in [('ready', 'ready (salen del hogar)', '#8e9aaf'), ('arrival', 'arrival (llegan a un nodo)', '#1f6feb'),
                           ('interrupt', 'interrupción por cierre', '#e5134b'), ('closure', 'closure (tramo se quema)', '#f08a00'),
                           ('node_fire', 'node_fire (nodo se quema)', '#7b2cbf')]:
            fig.add_trace(go.Bar(x=ctr, y=h[k], name=nm, marker_color=col))
        fig.add_vrect(x0=t0, x1=t1, fillcolor='#f08a00', opacity=.25, line_width=0)
        fig.update_layout(barmode='stack', height=380, margin=dict(t=30, b=30), title='Eventos por tipo cada 10 min (banda naranja = ventana elegida)',
                          xaxis_title='min desde la ignición', yaxis_title='eventos (escala log)', yaxis_type='log', legend=dict(orientation='h', y=-0.3))
        st.plotly_chart(fig, width='stretch')

    # ------------------------------------------------------------ C) recursos
    if _sel == 2:
        idx = edge_index(T, key, E)
        order, starts = idx
        peak = T['edge_peak'].astype(float)
        used = np.diff(starts) > 0
        sat = used & (peak >= S['edge_cap'])
        m = st.columns(4)
        m[0].metric('Aristas usadas', f'{int(used.sum()):,}', f'de {E:,}', delta_color='off')
        m[1].metric('Aristas que llegaron a su capacidad', f'{int(sat.sum()):,}', f'{100 * sat.sum() / max(used.sum(), 1):.1f} % de las usadas', delta_color='off')
        m[2].metric('Ocupación máx. / capacidad', f'{float((peak / np.maximum(S["edge_cap"], 1))[used].max()):.2f}', 'nunca > 1: capacidad respetada', delta_color='off')
        m[3].metric('Invariante de capacidad', 'cumple' if T['meta']['metrics'].get('capacity_invariant', True) else 'VIOLADA')
        tab = resource_table(T, key, S, idx)
        st.markdown('**Cuellos de botella:** los recursos (aristas) que pasaron más tiempo con todos sus servidores ocupados')
        view_tab = tab.rename(columns={'calle': 'Calle', 'capacidad': 'Capacidad c', 'grupos': 'Grupos que la usaron',
                                       'ocupacion_max': 'Ocupación máx.', 'saturada_min': 'Min saturada', 'utilizacion': 'Utilización media'})
        st.dataframe(view_tab.rename(columns={'arista': 'Arista (id)'}).head(25), hide_index=True, width='stretch', height=260)
        choice = st.selectbox('Examinar un recurso', tab.index, format_func=lambda i: f"{tab.calle[i]} (arista e{tab.arista[i]}) · c = {tab.capacidad[i]} · saturada {tab.saturada_min[i]} min")
        e = int(tab.arista[choice])
        cap = int(S['edge_cap'][e])
        t, occ, n = occupancy(T, order, starts, e)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t, y=occ, mode='lines', line=dict(shape='hv', color='#1f6feb', width=2), name='Grupos en la arista', fill='tozeroy', fillcolor='rgba(31,111,235,.2)'))
        fig.add_hline(y=cap, line=dict(color='#d62800', width=3, dash='dash'), annotation_text=f'capacidad c = {cap}', annotation_position='top left')
        satmask = occ >= cap
        dt = np.diff(np.r_[t, 480.0])
        fig.add_trace(go.Scatter(x=t, y=np.where(satmask, occ, np.nan), mode='lines', line=dict(shape='hv', color='#d62800', width=5),
                                 name='Saturado (todos los servidores ocupados)'))
        fig.update_layout(height=360, margin=dict(t=30, b=30), title=f'Ocupación del recurso en el tiempo — {S["edge_name"][e] or e}',
                          xaxis_title='min desde la ignición', yaxis_title='grupos simultáneos', xaxis_range=[0, 480],
                          legend=dict(orientation='h', y=-0.3))
        a, b = st.columns([2, 1])
        a.plotly_chart(fig, width='stretch')
        mid = (S['xy'][S['u'][e]] + S['xy'][S['v'][e]]) / 2
        mf = go.Figure(fire_trace(S['fire'][rep], 480, .35, colorbar=False))
        xs, ys = seg_xy(S, [e])
        mf.add_trace(go.Scatter(x=xs, y=ys, mode='lines', line=dict(color='#000', width=12), showlegend=False, hoverinfo='skip'))
        mf.add_trace(go.Scatter(x=xs, y=ys, mode='lines', line=dict(color='#f08a00', width=6), name='Recurso elegido'))
        v = ([mid[0] - 2500, mid[0] + 2500], [mid[1] - 1850, mid[1] + 1850])
        base_layout(mf, v, height=360)
        b.plotly_chart(mf, width='stretch')
        sat_min = float(dt[satmask].sum())
        m = st.columns(4)
        m[0].metric('Capacidad (servidores)', cap)
        m[1].metric('Ocupación máxima', int(occ.max()))
        m[2].metric('Min con servidores llenos', f'{sat_min:.0f} min')
        m[3].metric('Utilización media', f'{100 * float((dt * occ).sum() / 480 / cap):.0f} %')
        st.caption('Franjas rojas = el recurso estuvo saturado: cualquier grupo que llegara tenía que **esperar en cola** a que otro saliera.')

    # ------------------------------------------------------------ D) colas y espera
    if _sel == 3:
        wait, travel, never = wait_stats(T, key)
        mv = T['moved']
        m = st.columns(5)
        m[0].metric('Espera media (ponderada)', f'{np.average(wait, weights=w):.0f} min')
        m[1].metric('Mediana', f'{wquantile(wait, w, .5):.0f} min')
        m[2].metric('Percentil 90', f'{wquantile(wait, w, .9):.0f} min')
        m[3].metric('Personas con espera > 60 min', f'{100 * w[wait > 60].sum() / w.sum():.0f} %')
        m[4].metric('Nunca salieron del nodo', f'{100 * w[never].sum() / w.sum():.1f} %', 'sin ruta ni capacidad', delta_color='off')
        a, b = st.columns(2)
        fq = go.Figure()
        fq.add_trace(go.Scatter(x=T['hist_t'], y=T['hist_qpeople'], name='Personas en cola', line=dict(color='#7b2cbf', width=3), fill='tozeroy'))
        fq.add_trace(go.Scatter(x=T['hist_t'], y=T['hist_qgroups'], name='Grupos en cola', line=dict(color='#f08a00', width=2, dash='dot')))
        fq.update_layout(height=340, margin=dict(t=30, b=30), title='Longitud de la cola en el tiempo', xaxis_title='min desde la ignición',
                         yaxis_title='personas / grupos', legend=dict(orientation='h', y=-0.3))
        a.plotly_chart(fq, width='stretch')
        fh = go.Figure(go.Histogram(x=wait, y=w, histfunc='sum', nbinsx=48, marker_color='#7b2cbf'))
        fh.update_layout(height=340, margin=dict(t=30, b=30), title='Distribución del tiempo de espera (personas)',
                         xaxis_title='min esperando en cola', yaxis_title='personas')
        b.plotly_chart(fh, width='stretch')
        cfg = json.loads((D.ROOT / 'config/escenarios_evacuacion.json').read_text())
        alert = cfg['base_alert_min'] + (cfg['early_alert_delta_min'] if sc == 'early_alert' else 0)
        safe = T['g_finish'] >= 0
        fb = go.Figure()
        for nm, mask in [('Llegaron a una salida', safe), ('No llegaron', ~safe)]:
            if mask.sum() == 0:
                continue
            ww = w[mask]
            vals = [float(np.average(np.maximum(T['g_ready'][mask] - alert, 0), weights=ww)), float(np.average(wait[mask], weights=ww)),
                    float(np.average(travel[mask], weights=ww))]
            fb.add_trace(go.Bar(name=nm, x=['Preparación (demora)', 'Espera en cola', 'Viaje por aristas'], y=vals, text=[f'{v:.0f}' for v in vals], textposition='outside'))
        fb.update_layout(barmode='group', height=330, margin=dict(t=30, b=30), title='¿En qué se va el tiempo? (promedio ponderado, min)', yaxis_title='min')
        a, b = st.columns(2)
        a.plotly_chart(fb, width='stretch')
        towns = D.town_xy()
        gx, gy = S['xy'][T['g_node'], 0], S['xy'][T['g_node'], 1]
        zone = np.full(G, 'Resto del dominio', dtype=object)
        for tname, (tx, ty) in towns.items():
            zone[np.hypot(gx - tx, gy - ty) < 3000] = tname
        zs = pd.DataFrame({'zona': zone, 'w': w, 'wait': wait, 'wxw': wait * w}).groupby('zona').agg(w=('w', 'sum'), wxw=('wxw', 'sum'))
        zs['espera'] = zs.wxw / zs.w
        fz = go.Figure(go.Bar(x=zs.index, y=zs.espera, marker_color='#f08a00', text=[f'{v:.0f}' for v in zs.espera], textposition='outside'))
        fz.update_layout(height=330, margin=dict(t=30, b=30), title='Espera media por zona de origen (min)', yaxis_title='min')
        b.plotly_chart(fz, width='stretch')
        st.markdown('**¿Dónde se forman las colas?** Mapa de calor de las personas que esperan en un instante dado')
        tq = st.slider('Minuto', 0, 480, 150, key='dq')
        px, py, stt = D.positions_at(S, T, S['fire'][rep], tq)
        wm = stt == D.WAIT
        H, xe, ye = np.histogram2d(px[wm], py[wm], bins=[np.arange(D.X0, D.X0 + D.SHAPE[1] * D.RES + 1, 300),
                                                         np.arange(D.Y0 - D.SHAPE[0] * D.RES, D.Y0 + 1, 300)], weights=w[wm])
        fm = go.Figure(fire_trace(S['fire'][rep], tq, .5, colorbar=False))
        fm.add_trace(go.Heatmap(z=np.where(H.T > 0, H.T, np.nan), x=(xe[:-1] + xe[1:]) / 2, y=(ye[:-1] + ye[1:]) / 2, colorscale='Purples',
                                zmin=0, zmax=float(np.percentile(H[H > 0], 98)) if (H > 0).any() else 1, opacity=.9,
                                colorbar=dict(title='personas<br>en cola', thickness=12, len=.5), hovertemplate='%{z:.0f} personas esperando<extra></extra>'))
        base_layout(fm, view_for('Todo el dominio'), height=640)
        st.plotly_chart(fm, width='stretch')
        st.caption(f'En el minuto {tq} hay **{w[wm].sum():,.0f} personas** esperando en cola. Cada celda de 300 m acumula a '
                   'quienes aguardan ahí una arista libre; el fuego (naranja) las va encerrando.')
