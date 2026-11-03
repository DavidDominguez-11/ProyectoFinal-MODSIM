"""Demo visual: incendio (Camp Fire) + evacuación por la red vial.

    .venv/Scripts/streamlit run scripts/demo/app.py
"""
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.demo import datos as D  # noqa: E402

st.set_page_config(page_title='Camp Fire — Fuego y evacuación', page_icon='🔥', layout='wide')

XC = D.X0 + (np.arange(D.SHAPE[1]) + .5) * D.RES
YC = D.Y0 - (np.arange(D.SHAPE[0]) + .5) * D.RES
EXTENT = (D.X0, D.X0 + D.SHAPE[1] * D.RES, D.Y0 - D.SHAPE[0] * D.RES, D.Y0)
ROAD_W = {'S1100': 2.2, 'S1200': 1.6, 'S1400': .6, 'S1500': .5, 'S1740': .5}


# ----------------------------------------------------------------- carga con caché
@st.cache_resource(show_spinner='Cargando red vial, fuego y población…')
def static():
    return D.load_static()


@st.cache_resource(show_spinner='Cargando trayectorias…')
def traj(path):
    return D.load_traj(path)


@st.cache_resource(show_spinner='Dibujando mapa base…')
def base_image():
    """Relieve sombreado + población + red vial como imagen de fondo (rápida de repintar)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    from PIL import Image
    S = static()
    g = S['grid']
    ls = LightSource(azdeg=315, altdeg=40)
    hs = ls.hillshade(g['elevacion_m'], vert_exag=4)
    shade = np.dstack([0.80 + 0.2 * hs, 0.80 + 0.19 * hs, 0.74 + 0.2 * hs]).clip(0, 1)
    fig = plt.figure(figsize=(13.9, 10.25), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(shade, extent=EXTENT, interpolation='bilinear')
    pop = np.ma.masked_less_equal(g['poblacion'], 0.5)
    ax.imshow(pop, extent=EXTENT, cmap='Purples', alpha=.45, vmin=0, vmax=np.percentile(g['poblacion'][g['poblacion'] > 0], 98))
    xy, u, v = S['xy'], S['u'], S['v']
    seen = u < v
    keep = seen | True
    for cls, w, c in (('S1400', .5, '#6b6b6b'), ('S1740', .5, '#777'), ('S1500', .5, '#777'),
                      ('S1200', 1.4, '#2b2b2b'), ('S1100', 2.2, '#000')):
        m = (S['edge_mtfcc'] == cls) & seen
        segs = np.stack([xy[u[m]], xy[v[m]]], 1)
        from matplotlib.collections import LineCollection
        ax.add_collection(LineCollection(segs, colors=c, linewidths=w, alpha=.8))
    ax.set_xlim(EXTENT[0], EXTENT[1])
    ax.set_ylim(EXTENT[2], EXTENT[3])
    ax.axis('off')
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert('RGB')


def base_layout(fig, view, height=640):
    fig.update_layout(
        images=[dict(source=base_image(), xref='x', yref='y', x=EXTENT[0], y=EXTENT[3],
                     sizex=EXTENT[1] - EXTENT[0], sizey=EXTENT[3] - EXTENT[2], sizing='stretch',
                     layer='below', opacity=1)],
        xaxis=dict(range=view[0], visible=False, constrain='domain'),
        yaxis=dict(range=view[1], visible=False, scaleanchor='x', scaleratio=1),
        margin=dict(l=0, r=0, t=0, b=0), height=height, uirevision=str(view),
        legend=dict(orientation='h', y=-0.02, bgcolor='rgba(255,255,255,.7)'),
        plot_bgcolor='#dfe6ec')
    return fig


def view_for(name, radius_km=7):
    full = ([EXTENT[0], EXTENT[1]], [EXTENT[2], EXTENT[3]])
    if name == 'Todo el dominio':
        return full
    x, y = D.town_xy()[name]
    r = radius_km * 1000
    return ([x - r * 1.35, x + r * 1.35], [y - r, y + r])


def fire_trace(arrival, t, opacity=.8):
    age = np.where((arrival >= 0) & (arrival <= t), t - arrival, np.nan).astype(float)
    return go.Heatmap(z=age, x=XC, y=YC, colorscale=[[0, '#fff3a0'], [.12, '#ff9d00'], [.35, '#d62800'],
                                                   [.7, '#5a0b00'], [1, '#1a1a1a']],
                      zmin=0, zmax=240, opacity=opacity, showscale=True, hoverinfo='skip',
                      colorbar=dict(title='min desde<br>que arde', len=.35, y=.2, thickness=12),
                      name='Fuego', showlegend=False)


# ----------------------------------------------------------------- barra lateral
S = static()
runs = D.available_runs()
st.sidebar.title('🔥 Camp Fire\nFuego + evacuación')
st.sidebar.caption('Modelación y Simulación — demo de la rama `test`. Todo el escenario de evacuación '
                   'usa **supuestos hipotéticos**; no es una validación histórica.')
page = st.sidebar.radio('Vista', ['🚨 Simulación animada', '🛣️ Rutas y congestión',
                                   '🔥 Solo el incendio', '📊 Comparación de escenarios', 'ℹ️ Modelo y supuestos'])

with st.sidebar.expander('➕ Calcular otra réplica / escenario'):
    st.caption('Ejecuta el motor completo (≈10–15 min por corrida) y guarda las trayectorias.')
    sc_new = st.selectbox('Escenario', list(D.SCENARIO_LABELS), format_func=D.SCENARIO_LABELS.get, key='sc_new')
    rep_new = st.number_input('Réplica de fuego (0–29)', 0, 29, 0, key='rep_new')
    if st.button('Calcular'):
        with st.spinner('Simulando… (puedes seguir mirando otras réplicas en otra pestaña del navegador)'):
            subprocess.run([sys.executable, str(Path(D.ROOT, 'scripts/demo/precomputar.py')),
                            '--scenario', sc_new, '--replica', str(int(rep_new))], check=True)
        st.rerun()


def pick_run(key):
    if not runs:
        st.warning('No hay réplicas precalculadas en `salidas/demo/`. Usa la barra lateral o ejecuta '
                   '`python scripts/demo/precomputar.py --scenario all --replica 0`.')
        st.stop()
    c1, c2 = st.columns(2)
    scs = sorted({s for s, _ in runs}, key=list(D.SCENARIO_LABELS).index)
    sc = c1.selectbox('Escenario', scs, format_func=D.SCENARIO_LABELS.get, key=key + 's')
    reps = sorted(r for s, r in runs if s == sc)
    rep = c2.selectbox('Réplica de fuego', reps, key=key + 'r')
    return sc, rep, traj(runs[(sc, rep)])


# ================================================================= 1) animación
if page.startswith('🚨'):
    st.header('Simulación animada: el fuego avanza y las familias evacúan')
    sc, rep, T = pick_run('anim')
    fire_rep = S['fire'][rep]
    c1, c2, c3 = st.columns([2, 2, 3])
    zone = c1.selectbox('Zona del mapa', ['Todo el dominio'] + list(D.TOWNS))
    show_fire = c2.checkbox('Fuego', True)
    show_closed = c2.checkbox('Tramos cerrados por política', True)
    step = c3.select_slider('Velocidad de reproducción (min simulados por cuadro)', [2, 5, 10, 15, 30], 10)
    frac = c3.slider('Grupos dibujados (%)', 10, 100, 50, help='Menos puntos = más fluido')
    if 't_anim' not in st.session_state:
        st.session_state.t_anim = 0
    t = st.slider('Minuto desde la ignición (06:25 hora local)', 0, 480, key='t_anim')
    play = st.button('▶ Reproducir desde aquí')
    holder_map, holder_k = st.empty(), st.empty()
    sel = np.random.default_rng(3).random(len(T['g_people'])) < frac / 100

    def draw(t):
        px, py, st_ = D.positions_at(S, T, fire_rep, t)
        fig = go.Figure()
        if show_fire:
            fig.add_trace(fire_trace(fire_rep, t))
        if show_closed and len(T['closed_edges']):
            ce = T['closed_edges']
            xs = np.stack([S['xy'][S['u'][ce], 0], S['xy'][S['v'][ce], 0], np.full(len(ce), np.nan)], 1).ravel()
            ys = np.stack([S['xy'][S['u'][ce], 1], S['xy'][S['v'][ce], 1], np.full(len(ce), np.nan)], 1).ravel()
            fig.add_trace(go.Scattergl(x=xs, y=ys, mode='lines', line=dict(color='#00e5ff', width=4),
                                       name='Cerrado (Skyway)', hoverinfo='skip'))
        for k in (D.PREP, D.WAIT, D.MOVE, D.FIRE, D.SAFE):
            m = (st_ == k) & sel
            fig.add_trace(go.Scattergl(x=px[m], y=py[m], mode='markers', name=D.STATE_NAMES[k],
                                       marker=dict(size=4 if k != D.MOVE else 5, color=D.STATE_COLORS[k],
                                                   opacity=.8 if k != D.MOVE else 1),
                                       hoverinfo='skip'))
        ex = S['xy'][S['exits']]
        fig.add_trace(go.Scatter(x=ex[:, 0], y=ex[:, 1], mode='markers+text', text=['Salida'] * len(ex),
                                 textposition='top center', name='Salidas del dominio',
                                 marker=dict(symbol='star', size=14, color='#ffd400', line=dict(width=1, color='black'))))
        fig.update_layout(title=None)
        base_layout(fig, view_for(zone))
        holder_map.plotly_chart(fig, width='stretch', key=f'm{time.time_ns()}')
        w = T['g_people']
        tot = w.sum()
        cols = holder_k.columns(6)
        cols[0].metric('Hora', f'{(6 * 60 + 25 + t) // 60:02d}:{(6 * 60 + 25 + t) % 60:02d}')
        for c_, k in zip(cols[1:], (D.PREP, D.WAIT, D.MOVE, D.SAFE, D.FIRE)):
            n = w[st_ == k].sum()
            c_.metric(D.STATE_NAMES[k], f'{n:,.0f}', f'{100 * n / tot:.1f}%', delta_color='off')

    draw(t)
    if play:
        for tt in range(t, 481, step):
            draw(tt)
            time.sleep(.05)
        st.session_state.t_anim = 480

    h = go.Figure()
    h.add_trace(go.Scatter(x=T['hist_t'], y=T['hist_safe'], name='Personas a salvo (acumulado)', line=dict(color='#1db954')))
    h.add_trace(go.Scatter(x=T['hist_t'], y=T['hist_exposed'], name='Personas expuestas (acumulado)', line=dict(color='#e5134b')))
    h.add_trace(go.Scatter(x=T['hist_t'], y=T['hist_qpeople'], name='Personas en cola', line=dict(color='#7b2cbf')))
    h.add_vline(x=t, line_dash='dash')
    h.update_layout(height=300, margin=dict(t=10, b=30), xaxis_title='min desde la ignición',
                    yaxis_title='personas ponderadas', legend=dict(orientation='h'))
    st.plotly_chart(h, width='stretch')
    m = T['meta']['metrics']
    st.caption(f"Resultado final de esta corrida: {m['people_safe']:,.0f} de {m['people_total']:,.0f} personas llegaron a una salida "
               f"({100 * m['people_safe_before_fire'] / m['people_total']:.1f}% antes del fuego); "
               f"{m['people_exposed']:,.0f} tuvieron exposición potencial; {T['meta']['traversals']:,} tramos recorridos. "
               f"Semilla de fuego {T['meta']['fire_seed']}, semilla de preparación {T['meta']['preparation_seed']}.")

# ================================================================= 2) rutas y congestión
elif page.startswith('🛣️'):
    st.header('Rutas de evacuación y congestión')
    sc, rep, T = pick_run('rut')
    tab_a, tab_b = st.tabs(['Recorridos de grupos concretos', 'Mapa de uso y congestión de la red'])
    with tab_a:
        c1, c2, c3 = st.columns(3)
        town = c1.selectbox('Origen cercano a', list(D.TOWNS), key='rt')
        n_show = c2.slider('Cuántos grupos dibujar', 1, 60, 25)
        radius = c3.slider('Radio de selección (km)', 1, 8, 3)
        seed = c3.number_input('Semilla de muestreo', 0, 999, 1)
        tx, ty = D.town_xy()[town]
        gx, gy = S['xy'][T['g_node'], 0], S['xy'][T['g_node'], 1]
        near = np.flatnonzero((np.hypot(gx - tx, gy - ty) < radius * 1000))
        has = np.isin(near, np.unique(T['tr_group']))
        pool = near[has]
        if len(pool) == 0:
            st.info('Ningún grupo de esta zona se movió en esta corrida.')
            st.stop()
        pick = np.random.default_rng(int(seed)).choice(pool, min(n_show, len(pool)), replace=False)
        fig = go.Figure()
        if len(T['closed_edges']):
            ce = T['closed_edges']
            fig.add_trace(go.Scattergl(
                x=np.stack([S['xy'][S['u'][ce], 0], S['xy'][S['v'][ce], 0], np.full(len(ce), np.nan)], 1).ravel(),
                y=np.stack([S['xy'][S['u'][ce], 1], S['xy'][S['v'][ce], 1], np.full(len(ce), np.nan)], 1).ravel(),
                mode='lines', line=dict(color='#00e5ff', width=4), name='Cerrado por política', hoverinfo='skip'))
        rows = []
        palette = ['#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4', '#008080', '#9a6324', '#800000',
                   '#808000', '#000075', '#f032e6', '#469990']
        for i, gi in enumerate(pick):
            e, s_, en, oc = D.group_path(S, T, gi)
            xs, ys = [], []
            for k, ed in enumerate(e):
                xs += [S['xy'][S['u'][ed], 0], S['xy'][S['v'][ed], 0]]
                ys += [S['xy'][S['u'][ed], 1], S['xy'][S['v'][ed], 1]]
                xs.append(None); ys.append(None)
            fin = T['g_finish'][gi]
            status = 'llegó a salida' if fin >= 0 else ('alcanzado por fuego' if T['g_state'][gi] == 2 else 'sin llegar en 480 min')
            waits = float(np.sum(np.maximum(0, s_[1:] - en[:-1]))) + max(0, float(s_[0] - T['g_ready'][gi]))
            fig.add_trace(go.Scattergl(x=xs, y=ys, mode='lines', line=dict(width=3, color=palette[i % len(palette)]),
                                       name=f'g{gi} · {status}', opacity=.9))
            fig.add_trace(go.Scatter(x=[S['xy'][T['g_node'][gi], 0]], y=[S['xy'][T['g_node'][gi], 1]], mode='markers',
                                     marker=dict(size=9, color=palette[i % len(palette)], line=dict(width=1.5, color='white')),
                                     showlegend=False, hovertext=f'Grupo {gi}: {T["g_people"][gi]:.1f} personas'))
            rows.append(dict(grupo=int(gi), personas=round(float(T['g_people'][gi]), 2), sale_a_min=round(float(T['g_ready'][gi]), 1),
                             tramos=len(e), min_en_cola=round(waits, 1),
                             llega_min=round(float(fin), 1) if fin >= 0 else None, resultado=status,
                             expuesto=bool(T['g_exposed'][gi])))
        ex = S['xy'][S['exits']]
        fig.add_trace(go.Scatter(x=ex[:, 0], y=ex[:, 1], mode='markers', name='Salidas del dominio',
                                 marker=dict(symbol='star', size=15, color='#ffd400', line=dict(width=1, color='black'))))
        fig.add_trace(fire_trace(S['fire'][rep], 480, opacity=.35))
        fig = base_layout(fig, view_for(town, radius_km=max(radius + 2, 6)), height=760)
        fig.update_layout(legend=dict(orientation='v', x=1.0, y=1, font=dict(size=10)))
        st.plotly_chart(fig, width='stretch')
        df = pd.DataFrame(rows)
        st.dataframe(df, width='stretch', hide_index=True)
        st.caption('El mapa muestra el fuego acumulado al minuto 480 (tenue) y el camino real de cada grupo: los puntos son el origen, '
                   'las estrellas las salidas del dominio. Algunos grupos hacen ida y vuelta cuando un cierre o el fuego los obliga a recalcular la ruta.')
        if len(df):
            gsel = st.selectbox('Línea de tiempo detallada de un grupo', df['grupo'])
            e, s_, en, oc = D.group_path(S, T, gsel)
            tl = go.Figure()
            ready = float(T['g_ready'][gsel])
            tl.add_trace(go.Bar(y=['Preparación'], x=[ready], base=[0], orientation='h', marker_color='#8e9aaf', name='Preparación'))
            prev = ready
            for k, ed in enumerate(e):
                if s_[k] > prev + 1e-6:
                    tl.add_trace(go.Bar(y=['Espera en cola'], x=[s_[k] - prev], base=[prev], orientation='h',
                                        marker_color='#7b2cbf', showlegend=False))
                label = S['edge_name'][ed] or f'tramo {ed}'
                tl.add_trace(go.Bar(y=['Recorrido'], x=[max(en[k] - s_[k], .05)], base=[s_[k]], orientation='h', hovertext=label,
                                    marker_color='#1f77ff' if oc[k] == 0 else '#e5134b', showlegend=False))
                prev = en[k]
            tl.update_layout(barmode='overlay', height=230, xaxis_title='min desde la ignición', margin=dict(t=10, b=30), showlegend=False)
            st.plotly_chart(tl, width='stretch')
            names = [S['edge_name'][ed] for ed in e if S['edge_name'][ed]]
            if names:
                seq = [names[0]] + [n for a, n in zip(names, names[1:]) if n != a]
                st.write('**Calles recorridas:** ' + ' → '.join(seq))
    with tab_b:
        w = T['g_people'][T['tr_group']]
        use = np.bincount(T['tr_edge'], weights=w, minlength=len(S['u']))
        peak = T['edge_peak'] / np.maximum(S['edge_cap'], 1)
        metric = st.radio('Colorear por', ['Personas que transitaron', 'Ocupación máxima / capacidad'], horizontal=True)
        val = use if metric.startswith('Pers') else peak
        used = np.flatnonzero(use > 0)
        seen = used[S['u'][used] != S['v'][used]]
        if metric.startswith('Pers'):
            edges = [0, 1, 50, 200, 800, 2500, 8000, 1e9]
            cols = ['#cfd8dc', '#ffe08a', '#ffb703', '#fb8500', '#e5383b', '#9d0208', '#370617']
        else:
            edges = [0, .25, .5, .75, .999, 1e9]
            cols = ['#b2dfdb', '#ffe08a', '#fb8500', '#e5383b', '#6a040f']
        fig = go.Figure(fire_trace(S['fire'][rep], 480, .3))
        for lo, hi, c in zip(edges[:-1], edges[1:], cols):
            m = seen[(val[seen] >= lo) & (val[seen] < hi)]
            if not len(m):
                continue
            fig.add_trace(go.Scattergl(
                x=np.stack([S['xy'][S['u'][m], 0], S['xy'][S['v'][m], 0], np.full(len(m), np.nan)], 1).ravel(),
                y=np.stack([S['xy'][S['u'][m], 1], S['xy'][S['v'][m], 1], np.full(len(m), np.nan)], 1).ravel(),
                mode='lines', line=dict(color=c, width=1 + 3 * cols.index(c) / len(cols)), hoverinfo='skip',
                name=(f'{lo:g}–{hi:g}' if hi < 1e8 else f'≥ {lo:g}') + (' pers.' if metric.startswith('Pers') else '× cap.')))
        zone = st.selectbox('Zona', ['Todo el dominio'] + list(D.TOWNS), key='zc')
        fig = base_layout(fig, view_for(zone))
        st.plotly_chart(fig, width='stretch')
        top = pd.DataFrame({'calle': S['edge_name'], 'personas': use, 'ocupación máx./cap.': peak})
        top = top[top.calle != ''].groupby('calle').agg(personas=('personas', 'sum'),
                                                       sat=('ocupación máx./cap.', 'max')).sort_values('personas', ascending=False).head(12)
        top.columns = ['Personas·tramo transitadas', 'Máx. ocupación/capacidad']
        st.write('**Calles más usadas (suma sobre sus tramos)**')
        st.dataframe(top.round(2), width='stretch')

# ================================================================= 3) incendio
elif page.startswith('🔥'):
    st.header('El incendio: autómata celular estocástico (30 réplicas)')
    fire = S['fire']
    c1, c2 = st.columns(2)
    rep = c1.slider('Réplica de fuego', 0, 29, 0)
    mode = c2.radio('Mapa', ['Avance en el tiempo', 'Probabilidad de quema (30 réplicas)', 'Minuto de llegada'], horizontal=True)
    zone = st.selectbox('Zona', ['Todo el dominio'] + list(D.TOWNS), key='zf')
    obs = pd.read_csv(D.ROOT / 'data/procesado/observaciones_nist.csv')
    fig = go.Figure()
    if mode.startswith('Avance'):
        t = st.slider('Minuto desde la ignición', 0, 480, 240, key='tf')
        fig.add_trace(fire_trace(fire[rep], t, .85))
        if st.checkbox('Superponer observaciones de NIST (llegadas reales)', True):
            seen_ = obs[obs.minuto <= t]
            fig.add_trace(go.Scatter(x=seen_.x, y=seen_.y, mode='markers', name='Observado ≤ t (NIST)',
                                     marker=dict(size=6, color='#00e5ff', line=dict(width=1, color='black')),
                                     hovertext=seen_.hora_local))
            later = obs[obs.minuto > t]
            fig.add_trace(go.Scatter(x=later.x, y=later.y, mode='markers', name='Observado > t (aún no)',
                                     marker=dict(size=5, color='white', line=dict(width=1, color='gray'), opacity=.7)))
    elif mode.startswith('Prob'):
        p = (fire >= 0).mean(0)
        fig.add_trace(go.Heatmap(z=np.where(p > 0, p, np.nan), x=XC, y=YC, colorscale='YlOrRd', zmin=0, zmax=1,
                                 opacity=.8, colorbar=dict(title='P(arde)', thickness=12, len=.4)))
    else:
        a = np.where(fire[rep] >= 0, fire[rep], np.nan).astype(float)
        fig.add_trace(go.Heatmap(z=a, x=XC, y=YC, colorscale='Turbo', zmin=0, zmax=480, opacity=.8,
                                 colorbar=dict(title='min', thickness=12, len=.4)))
        fig.add_trace(go.Scatter(x=obs.x, y=obs.y, mode='markers', name='Observaciones NIST',
                                 marker=dict(size=7, color=obs.minuto, colorscale='Turbo', cmin=0, cmax=480,
                                             line=dict(width=1.5, color='black')),
                                 hovertext=obs.hora_local + ' (min ' + obs.minuto.astype(str) + ')'))
    base_layout(fig, view_for(zone))
    st.plotly_chart(fig, width='stretch')
    area = np.stack([((f >= 0)[None] & (f[None] <= np.arange(481)[:, None, None])).sum((1, 2)) for f in fire])
    band = go.Figure()
    for r_ in range(30):
        band.add_trace(go.Scatter(x=np.arange(481), y=area[r_], mode='lines', line=dict(width=1, color='rgba(229,19,75,.25)'), showlegend=False, hoverinfo='skip'))
    band.add_trace(go.Scatter(x=np.arange(481), y=area[rep], mode='lines', line=dict(width=3, color='#e5134b'), name=f'Réplica {rep}'))
    band.add_trace(go.Scatter(x=np.arange(481), y=np.median(area, 0), mode='lines', line=dict(width=3, dash='dash', color='black'), name='Mediana'))
    band.update_layout(height=320, xaxis_title='min desde la ignición', yaxis_title='área quemada (ha, celdas de 1 ha)',
                       margin=dict(t=10), legend=dict(orientation='h'))
    st.plotly_chart(band, width='stretch')
    st.caption('Cada línea gris es una de las 30 réplicas del autómata celular; la variabilidad refleja la estocasticidad de la propagación.')
    v = json.loads((D.ROOT / 'salidas/fuego/validacion.json').read_text())['validacion']
    k = st.columns(4)
    k[0].metric('Error absoluto medio (validación)', f"{v['mae_min']['media']:.0f} min")
    k[1].metric('Sesgo', f"{v['sesgo_min']['media']:.0f} min", 'el modelo llega antes', delta_color='off')
    k[2].metric('Dentro de tolerancia', f"{100 * v['frac_dentro_tolerancia']['media']:.0f}%")
    k[3].metric('Fuera del perímetro real', f"{100 * v['frac_fuera_perimetro_quemada']['media']:.0f}%")
    with st.expander('Figuras de calibración y validación del módulo de fuego'):
        for f in ('fig_validacion.png', 'fig_sensibilidad.png', 'fig_capas.png'):
            st.image(str(D.ROOT / 'salidas/fuego' / f))

# ================================================================= 4) escenarios
elif page.startswith('📊'):
    st.header('Comparación de escenarios (Monte Carlo: 30 réplicas pareadas × 4 escenarios)')
    rep = pd.read_csv(D.FINAL / 'replicas.csv')
    summ = json.loads((D.FINAL / 'summary.json').read_text())
    rep['pct_seguro'] = 100 * rep.fraction_safe_before_fire
    lab = D.SCENARIO_LABELS
    col = {'base': '#6c757d', 'early_alert': '#1db954', 'skyway_closed': '#e5134b', 'exit_capacity': '#1f77ff'}
    metric = st.selectbox('Métrica', {
        'pct_seguro': '% de personas seguras antes del fuego', 'people_exposed': 'Personas con exposición potencial',
        'evacuation_mean_min': 'Tiempo medio de llegada (min, condicionado a llegar)', 'max_queue_people': 'Cola máxima (personas)',
        'queue_person_minutes': 'Integral de la cola (personas·min)', 'people_remaining': 'Personas que no llegaron en 480 min'}.items(),
        format_func=lambda kv: kv[1])[0]
    fig = go.Figure()
    for s in D.SCENARIO_LABELS:
        d = rep[rep.scenario == s]
        fig.add_trace(go.Box(y=d[metric], name=lab[s], marker_color=col[s], boxpoints='all', jitter=.4, pointpos=0, boxmean=True))
    fig.update_layout(height=450, showlegend=False, margin=dict(t=10))
    st.plotly_chart(fig, width='stretch')
    st.subheader('Efecto de cada intervención respecto de la base (diferencias pareadas, IC 95%)')
    pdv = summ['paired_differences_vs_base']
    rows = []
    for s, d in pdv.items():
        a = d['fraction_safe_before_fire'] if 'fraction_safe_before_fire' in d else None
        rows.append((s, d))
    fig2 = go.Figure()
    names, means, lo, hi = [], [], [], []
    key = 'fraction_safe_before_fire' if 'fraction_safe_before_fire' in next(iter(pdv.values())) else None
    for s, d in pdv.items():
        names.append(lab[s])
        if key:
            m = d[key]
            means.append(100 * m['mean']); lo.append(100 * m['ci95'][0]); hi.append(100 * m['ci95'][1])
        else:
            base = rep[rep.scenario == 'base'].sort_values('replica').pct_seguro.values
            alt = rep[rep.scenario == s].sort_values('replica').pct_seguro.values
            diff = alt - base
            sem = diff.std(ddof=1) / np.sqrt(len(diff))
            means.append(diff.mean()); lo.append(diff.mean() - 2.045 * sem); hi.append(diff.mean() + 2.045 * sem)
    fig2.add_trace(go.Bar(x=names, y=means, marker_color=[col[s] for s in pdv],
                          error_y=dict(type='data', symmetric=False, array=np.array(hi) - np.array(means), arrayminus=np.array(means) - np.array(lo)),
                          text=[f'{m:+.2f} pp' for m in means], textposition='outside'))
    fig2.update_layout(height=380, yaxis_title='Δ puntos porcentuales de personas seguras antes del fuego', margin=dict(t=10))
    st.plotly_chart(fig2, width='stretch')
    st.warning('El aumento de capacidad en una salida **reduce** la fracción segura (~−1.6 pp). El repositorio documenta que no se aisló '
               'el mecanismo; no debe leerse como que más capacidad perjudica en general. Todos los parámetros de evacuación son hipotéticos.')
    tab = rep.groupby('scenario').agg(pct_seguro=('pct_seguro', 'mean'), expuestos=('people_exposed', 'mean'),
                                      llegada_media=('evacuation_mean_min', 'mean'), cola_max=('max_queue_people', 'mean')).reindex(list(lab))
    tab.index = [lab[s] for s in tab.index]
    st.dataframe(tab.round(2), width='stretch')
    c = st.columns(3)
    for ci, f in zip(c, ('metrics.png', 'cdf.png', 'queues.png')):
        ci.image(str(D.FINAL / f), caption=f)

# ================================================================= 5) modelo
else:
    st.header('Qué se modela')
    st.markdown("""
**Caso:** Camp Fire, 8 de noviembre de 2018, 06:25–14:25 (480 min). Dominio de 27,8 × 20,5 km, celdas de 100 m, que incluye Pulga, Concow, Paradise y Magalia.

**1. Fuego (autómata celular estocástico).** Cada celda pasa de *sin quemar* a *ardiendo* según su combustible (LANDFIRE), pendiente (3DEP), viento (ERA5) y vecinos. Calibrado y validado con observaciones de NIST. Produce **30 réplicas** con el minuto en que arde cada celda.

**2. Evacuación (simulación por eventos).**
- Población WorldPop reescalada → **50 314 grupos** de hasta 3 personas ponderadas (42 389 personas).
- Cada grupo sale a `alerta + preparación` (alerta a los 85 min; preparación Gamma(2, 10 min)).
- Se mueven por la red vial TIGER 2018 (64 098 tramos dirigidos) con tiempo de viaje fijo y **capacidad** por tramo (grupos simultáneos). Si el tramo está lleno, **esperan en cola**.
- Cuando el fuego alcanza un tramo se cierra, y los grupos recalculan su ruta; si el fuego alcanza el nodo donde están, quedan *expuestos*.
- Destinos: 6 salidas del dominio (Skyway, Clark, Pentz, Neal…) con capacidad finita.

**3. Escenarios (se cambia un solo factor)**: base · alerta 30 min antes · cierre de Skyway · más capacidad en una salida. Monte Carlo pareado: la réplica *r* usa el fuego *r* en los cuatro escenarios.

**Límites que conviene decir en voz alta:** la evacuación **no está validada** contra datos históricos (avisos, cierres, capacidades y velocidades son supuestos), la población es residencial (no la presente ese día), no hay brigadistas ni refugios temporales, y el fuego tiende a llegar antes de lo observado (sesgo ≈ −58 min).
""")
    st.json(json.loads((D.ROOT / 'config/escenarios_evacuacion.json').read_text())['assumptions'], expanded=False)
