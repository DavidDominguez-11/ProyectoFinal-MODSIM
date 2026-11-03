"""Ayudantes compartidos del demo: carga con caché, mapa base, capas y banners por concepto."""
import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.demo import datos as D  # noqa: E402

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
    """Relieve + población + red vial como JPEG (data URI, cacheado en disco) para el fondo del mapa."""
    import base64
    cache = D.DEMO / 'base_map.jpg'
    if cache.exists():
        return 'data:image/jpeg;base64,' + base64.b64encode(cache.read_bytes()).decode()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
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
    for cls, w, c in (('S1400', .5, '#6b6b6b'), ('S1740', .5, '#777'), ('S1500', .5, '#777'),
                      ('S1200', 1.4, '#2b2b2b'), ('S1100', 2.2, '#000')):
        m = (S['edge_mtfcc'] == cls) & seen
        segs = np.stack([xy[u[m]], xy[v[m]]], 1)
        from matplotlib.collections import LineCollection
        ax.add_collection(LineCollection(segs, colors=c, linewidths=w, alpha=.8))
    ax.set_xlim(EXTENT[0], EXTENT[1])
    ax.set_ylim(EXTENT[2], EXTENT[3])
    ax.axis('off')
    D.DEMO.mkdir(parents=True, exist_ok=True)
    fig.savefig(cache, format='jpg', pil_kwargs={'quality': 82})
    plt.close(fig)
    return 'data:image/jpeg;base64,' + base64.b64encode(cache.read_bytes()).decode()


def base_layout(fig, view, height=660):
    fig.update_layout(
        images=[dict(source=base_image(), xref='x', yref='y', x=EXTENT[0], y=EXTENT[3],
                     sizex=EXTENT[1] - EXTENT[0], sizey=EXTENT[3] - EXTENT[2], sizing='stretch',
                     layer='below', opacity=1)],
        xaxis=dict(range=view[0], visible=False, constrain='domain'),
        yaxis=dict(range=view[1], visible=False, scaleanchor='x', scaleratio=1, constrain='domain'),
        margin=dict(l=0, r=70, t=0, b=64), height=height, uirevision=str(view),
        legend=dict(orientation='h', yanchor='top', y=-0.01, x=0, bgcolor='rgba(0,0,0,0)'),
        plot_bgcolor='#dfe6ec')
    return fig


def view_for(name, radius_km=7):
    full = ([EXTENT[0], EXTENT[1]], [EXTENT[2], EXTENT[3]])
    if name == 'Todo el dominio':
        return full
    x, y = D.town_xy()[name]
    r = radius_km * 1000
    return ([x - r * 1.35, x + r * 1.35], [y - r, y + r])


def fire_trace(arrival, t, opacity=.8, colorbar=True):
    age = np.where((arrival >= 0) & (arrival <= t), t - arrival, np.nan).astype(np.float32)
    return go.Heatmap(z=age, x=XC, y=YC, colorscale=[[0, '#fff3a0'], [.12, '#ff9d00'], [.35, '#d62800'],
                                                   [.7, '#5a0b00'], [1, '#1a1a1a']],
                      zmin=0, zmax=240, opacity=opacity, showscale=colorbar, hoverinfo='skip',
                      colorbar=dict(title='min desde<br>que arde', len=.4, y=.25, x=1.0, xanchor='left', thickness=12),
                      name='Fuego', showlegend=False)


def pick_run(runs, key):
    """Elige escenario y réplica; si solo hay una corrida disponible no muestra selectores."""
    if not runs:
        st.warning('No hay réplicas precalculadas en `salidas/demo/`. Ejecuta '
                   '`python scripts/demo/precomputar.py --scenario base --replica 0`.')
        st.stop()
    scs = sorted({s for s, _ in runs}, key=list(D.SCENARIO_LABELS).index)
    if len(runs) == 1:
        sc, rep = next(iter(runs))
        st.caption(f'Corrida analizada: **{D.SCENARIO_LABELS[sc]}**, fuego réplica {rep} (semilla {1000 + rep}).')
        return sc, rep, traj(runs[(sc, rep)])
    c1, c2 = st.columns(2)
    sc = c1.selectbox('Escenario', scs, format_func=D.SCENARIO_LABELS.get, key=key + 's')
    reps = sorted(r for s, r in runs if s == sc)
    rep = c2.selectbox('Réplica de fuego', reps, key=key + 'r')
    return sc, rep, traj(runs[(sc, rep)])
