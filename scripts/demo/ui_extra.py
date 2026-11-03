"""Ayudantes de mapa para las secciones por concepto (grilla, red, DES, agentes)."""
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from scripts.demo import datos as D


def plain_layout(fig, view, height=620, bg='#eef1f4'):
    """Mapa en metros UTM, sin imagen de fondo, escala 1:1 y sin franjas sobrantes."""
    fig.update_layout(
        xaxis=dict(range=view[0], visible=False, constrain='domain'),
        yaxis=dict(range=view[1], visible=False, scaleanchor='x', scaleratio=1, constrain='domain'),
        margin=dict(l=0, r=0, t=0, b=50), height=height, uirevision=str(view), plot_bgcolor=bg,
        legend=dict(orientation='h', yanchor='top', y=-0.01, x=0, bgcolor='rgba(0,0,0,0)'))
    return fig


def seg_xy(S, ids):
    """Coordenadas (con separadores NaN) de un conjunto de aristas para dibujarlas como líneas."""
    ids = np.asarray(ids, dtype=int)
    n = len(ids)
    xs = np.stack([S['xy'][S['u'][ids], 0], S['xy'][S['v'][ids], 0], np.full(n, np.nan)], 1).ravel()
    ys = np.stack([S['xy'][S['u'][ids], 1], S['xy'][S['v'][ids], 1], np.full(n, np.nan)], 1).ravel()
    return xs.astype(np.float32), ys.astype(np.float32)


def roads_trace(S, color='#222', width=1.2, name='Carreteras (vectorial, TIGER)', mask=None):
    """Todas las carreteras como una sola traza de líneas (un tramo por segmento geométrico)."""
    keep = S['u'] < S['v']
    if mask is not None:
        keep = keep & mask
    xs, ys = seg_xy(S, np.flatnonzero(keep))
    return go.Scattergl(x=xs, y=ys, mode='lines', line=dict(color=color, width=width), name=name, hoverinfo='skip')


@st.cache_resource(show_spinner='Cargando metadatos del grafo…')
def net_extra():
    return D.load_net_extra()


@st.cache_resource(show_spinner=False)
def fire_model():
    M = D.fuego_modulos()
    return M, M.cargar_parametros(), M.cargar_entradas()


def town_center_cell(name):
    x, y = D.town_xy()[name]
    r, c = D.xy_to_cell(np.array([x]), np.array([y]))
    return int(r[0]), int(c[0])


def lazy_tabs(labels, key, color='#888'):
    """Selector tipo pestañas que ejecuta solo la vista elegida (st.tabs ejecuta y monta todas)."""
    st.markdown(f"<style>div[data-testid='stRadio'][aria-label='{key}'] label{{font-weight:600}}</style>", unsafe_allow_html=True)
    cur = st.session_state.get(f'lz_{key}')
    if isinstance(cur, str) and cur.startswith('__sub__'):      # enlace directo ?sub=n
        st.session_state[f'lz_{key}'] = labels[min(int(cur[7:]), len(labels) - 1)]
    sel = st.radio(key, labels, horizontal=True, key=f'lz_{key}', label_visibility='collapsed')
    st.markdown(f"<hr style='margin:4px 0 14px 0;border:0;border-top:3px solid {color}'>", unsafe_allow_html=True)
    return labels.index(sel)
