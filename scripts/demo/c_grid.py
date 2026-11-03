"""Concepto 1 · Grillas, autómatas celulares y SIG."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scripts.demo import datos as D
from scripts.demo.ui import XC, YC, banner, view_for
from scripts.demo.ui_extra import lazy_tabs, fire_model, plain_layout, roads_trace, town_center_cell


def _discrete_scale(keys, colors):
    n = len(keys)
    scale = []
    for i, k in enumerate(keys):
        scale += [[i / n, colors[k]], [(i + 1) / n, colors[k]]]
    return scale


def render(S):
    banner('grid', '1', 'Grillas, autómatas celulares y SIG',
           'El territorio se discretiza en una <b>grilla regular de celdas de 100 m</b>; cada celda guarda atributos '
           '(capas ráster) y el fuego se propaga celda a celda con una regla local sobre la <b>vecindad de Moore</b> '
           '(las 8 celdas que rodean a una celda). Las carreteras entran como capa <b>vectorial</b> (líneas) y se '
           'cruzan espacialmente con la grilla.',
           '<code>scripts/fuego/f1…f2</code> (capas ráster), <code>scripts/fuego/modelo_fuego.py</code> (autómata), '
           '<code>scripts/evacuacion/red_vial.py</code> (capa vectorial)',
           ['<b>SIG:</b> combustible (LANDFIRE), elevación y pendiente (USGS 3DEP), población (WorldPop) = ráster; '
            'perímetro final (CAL FIRE) y carreteras (TIGER) = vectorial; todo en <b>EPSG:32610 (UTM 10N)</b>.',
            '<b>Autómata:</b> 4 estados (no combustible, susceptible, ardiendo, consumida) con paso de 1 min.',
            '<b>Regla:</b> p = p<sub>h</sub>·(1+p<sub>veg</sub>)·p<sub>w</sub>·p<sub>s</sub> (combustible, viento, pendiente).'])
    _sel = lazy_tabs(['🗺️ A · Capas SIG: ráster + vectorial', '🔲 B · Vecindad de Moore (la regla)',
                                    '🔥 C · Autómata celular en vivo'], 'grid', '#2e9e5b')
    g = S['grid']
    M, P, E = fire_model()

    # ------------------------------------------------------------ A) capas SIG
    if _sel == 0:
        c1, c2, c3 = st.columns(3)
        c1.metric('Sistema de coordenadas', 'EPSG:32610', 'UTM zona 10N', delta_color='off')
        c2.metric('Grilla ráster', '205 × 278 celdas', '100 m = 1 ha por celda', delta_color='off')
        c3.metric('Extensión', '27,8 × 20,5 km', f'{205 * 278:,} celdas', delta_color='off')
        layer = st.radio('Capa ráster', ['Combustible (clase FBFM40)', 'Elevación (m)', 'Pendiente (°)',
                                         'Población (personas por celda)', 'Perímetro final del incendio'],
                         horizontal=True)
        o1, o2, o3 = st.columns(3)
        roads = o1.checkbox('Superponer carreteras (vectorial)', True)
        grid_lines = o2.checkbox('Mostrar bordes de celda', False, help='Se aprecia al acercarse a un pueblo')
        zone = o3.selectbox('Zona', ['Todo el dominio'] + list(D.TOWNS), index=1, key='gz')
        radius = 4 if zone != 'Todo el dominio' else 7
        rows_, cols_ = np.meshgrid(np.arange(D.SHAPE[0]), np.arange(D.SHAPE[1]), indexing='ij')
        cust = np.stack([rows_, cols_], -1).astype(np.int16)
        fig = go.Figure()
        hm = dict(x=XC, y=YC, customdata=cust, xgap=1 if grid_lines else 0, ygap=1 if grid_lines else 0,
                  hovertemplate='fila %{customdata[0]} · columna %{customdata[1]}<br>valor %{z:.1f}<extra></extra>')
        if layer.startswith('Comb'):
            fig.add_trace(go.Heatmap(z=g['clase'], zmin=-1.5, zmax=6.5,
                                     colorscale=_discrete_scale(list(D.CLASES_COMB), D.COLORES_COMB),
                                     showscale=False, **hm))
        elif layer.startswith('Elev'):
            fig.add_trace(go.Heatmap(z=g['elevacion_m'], colorscale='Earth', colorbar=dict(title='m', thickness=12), **hm))
        elif layer.startswith('Pend'):
            fig.add_trace(go.Heatmap(z=g['pendiente_grados'], colorscale='YlOrRd', zmin=0, zmax=40,
                                     colorbar=dict(title='°', thickness=12), **hm))
        elif layer.startswith('Pobl'):
            z = np.where(g['poblacion'] > 0, g['poblacion'], np.nan)
            fig.add_trace(go.Heatmap(z=z, colorscale='Purples', zmin=0, zmax=float(np.nanpercentile(z, 98)),
                                     colorbar=dict(title='pers.', thickness=12), **hm))
        else:
            fig.add_trace(go.Heatmap(z=g['dentro_perimetro'].astype(float), colorscale=[[0, '#eef1f4'], [1, '#d6452d']],
                                     showscale=False, **hm))
        if roads:
            fig.add_trace(roads_trace(S, '#111', 1.1))
        plain_layout(fig, view_for(zone, radius))
        left, right = st.columns([3, 1.2])
        left.plotly_chart(fig, width='stretch')
        if layer.startswith('Comb'):
            cnt = np.bincount((g['clase'] + 1).ravel(), minlength=8)
            rows = ''.join(
                f"<tr><td><span style='background:{D.COLORES_COMB[k]};padding:2px 14px;border:1px solid #666'>&nbsp;</span></td>"
                f"<td>{D.CLASES_COMB[k]}</td><td align=right>{cnt[k + 1]:,}</td>"
                f"<td align=right>{(f'{P.p_veg[k]:+.1f}' if k >= 0 else '—')}</td></tr>" for k in D.CLASES_COMB)
            right.markdown(f"<table style='width:100%;font-size:.85rem'><tr><th></th><th>Clase</th><th>Celdas</th>"
                           f"<th>p<sub>veg</sub></th></tr>{rows}</table>", unsafe_allow_html=True)
            right.caption('p_veg es el efecto de cada combustible en la probabilidad de ignición (calibrado).')
        elif layer.startswith('Pobl'):
            right.metric('Población total en la grilla', f"{float(g['poblacion'].sum()):,.0f}")
            right.metric('Celdas con población', f"{int((g['poblacion'] > 0).sum()):,}")
            right.caption('WorldPop 2018 reescalada para que Paradise sume 26 581 habitantes.')
        elif layer.startswith('Perí'):
            right.metric('Celdas dentro del perímetro final', f"{int(g['dentro_perimetro'].sum()):,}")
        else:
            arr = g['elevacion_m'] if layer.startswith('Elev') else g['pendiente_grados']
            right.metric('Mínimo – máximo', f'{float(arr.min()):.0f} – {float(arr.max()):.0f}')
            right.metric('Promedio', f'{float(arr.mean()):.1f}')
        st.markdown('**Cómo se organiza la información geográfica (SIG)**')
        st.dataframe(pd.DataFrame([
            ('Combustible', 'Ráster (grilla)', 'LANDFIRE 2016 FBFM40 → 7 clases Scott & Burgan', 'Entra a p_veg del autómata'),
            ('Elevación', 'Ráster (grilla)', 'USGS 3DEP', 'Pendiente θs entre celdas vecinas → p_s'),
            ('Pendiente', 'Ráster derivado', 'Diferencias finitas de la elevación', 'Fuego más rápido cuesta arriba'),
            ('Población', 'Ráster (grilla)', 'WorldPop 2018, 100 m', 'Se convierte en 50 314 grupos evacuantes'),
            ('Perímetro final', 'Vector (polígono) → rasterizado', 'CAL FIRE / NIFC', 'Calibración y validación del fuego'),
            ('Carreteras', 'Vector (líneas)', 'TIGER/Line 2018, Butte County', 'Grafo vial dirigido; cada tramo cruza celdas'),
            ('Observaciones NIST', 'Vector (puntos)', 'NIST TN 2135, Apéndice F', 'Llegada observada del fuego'),
        ], columns=['Capa', 'Tipo de dato', 'Fuente', 'Uso en el modelo']), hide_index=True, width='stretch')

    # ------------------------------------------------------------ B) vecindad de Moore
    if _sel == 1:
        st.markdown('**Vecindad de Moore:** cada celda tiene 8 vecinas. Si una vecina está ardiendo, enciende a la celda '
                    'central con una probabilidad por minuto que depende del **combustible** de la celda central, de la '
                    '**pendiente** entre ambas y del **viento** respecto a la dirección de propagación.')
        st.latex(r'p=p_h\,(1+p_{veg})\,p_w\,p_s,\quad p_w=e^{c_1V}\,e^{Vc_2(\cos\theta-1)},\quad p_s=e^{a\,\theta_s}'
                 r'\;\Rightarrow\;P_{\text{ignición}}=1-\prod_i(1-p_i)')
        c1, c2, c3 = st.columns(3)
        town = c1.selectbox('Centrar en', list(D.TOWNS), index=2, key='mt')
        r0, c0 = town_center_cell(town)
        dr = c2.slider('Mover la celda: filas (↓ sur)', -30, 30, 0, key='mdr')
        dc = c3.slider('Mover la celda: columnas (→ este)', -30, 30, 0, key='mdc')
        r = int(np.clip(r0 + dr, 2, D.SHAPE[0] - 3))
        c = int(np.clip(c0 + dc, 2, D.SHAPE[1] - 3))
        w1, w2 = st.columns(2)
        minuto = w1.slider('Minuto del incendio (fija el viento ERA5)', 0, 480, 240, key='mm')
        vel, desde = D.viento_en(minuto)
        w2.metric('Viento ERA5', f'{vel:.1f} m/s desde {desde:.0f}°',
                  f'×{P.factor_viento:.2f} (factor calibrado) = {vel * P.factor_viento:.1f} m/s efectivo', delta_color='off')
        rows = D.moore_probabilidades(g['clase'], g['elevacion_m'], r, c, P, vel, desde)
        burning = st.multiselect('¿Qué vecinas están ardiendo?', [x['nombre'] for x in rows], default=['O', 'SO'],
                                 help='La probabilidad total combina todas las vecinas que arden')
        p_tot = 1.0 - float(np.prod([1 - x['p'] for x in rows if x['nombre'] in burning]))
        k = int(g['clase'][r, c])
        fig = go.Figure()
        for x in rows:
            df, dc_ = x['vecina']
            on = x['nombre'] in burning
            fig.add_shape(type='rect', x0=dc_ - .5, x1=dc_ + .5, y0=-df - .5, y1=-df + .5,
                          fillcolor=D.COLORES_COMB[x['clase_vecina']],
                          line=dict(color='#d62800' if on else '#ffffff', width=6 if on else 2), layer='below')
            fig.add_annotation(x=dc_, y=-df + .22, text=f"<b>{x['nombre']}</b>", showarrow=False,
                               font=dict(color='white', size=15), bgcolor='rgba(0,0,0,.5)')
            fig.add_annotation(x=dc_, y=-df - .2, showarrow=False, font=dict(color='white', size=12), bgcolor='rgba(0,0,0,.5)',
                               text=f"p = {100 * x['p']:.1f} %<br>Δz {g['elevacion_m'][r, c] - x['elev_vecina']:+.0f} m")
            fig.add_annotation(ax=dc_ * .66, ay=-df * .66, x=dc_ * .4, y=-df * .4, xref='x', yref='y', axref='x', ayref='y',
                               showarrow=True, arrowhead=2, arrowwidth=1 + 14 * x['p'],
                               arrowcolor='#d62800' if on else '#666666', text='')
        fig.add_shape(type='rect', x0=-.5, x1=.5, y0=-.5, y1=.5, fillcolor=D.COLORES_COMB[k], line=dict(color='black', width=6))
        fig.add_annotation(x=0, y=.2, text='<b>CELDA<br>CENTRAL</b>', showarrow=False, font=dict(color='white', size=13),
                           bgcolor='rgba(0,0,0,.55)')
        fig.add_annotation(x=0, y=-.22, text=f"{D.CLASES_COMB[k]}<br>{g['elevacion_m'][r, c]:.0f} m", showarrow=False,
                           font=dict(color='white', size=11), bgcolor='rgba(0,0,0,.55)')
        hx, hy = -np.sin(np.radians(desde)), -np.cos(np.radians(desde))
        fig.add_annotation(x=2.2 + hx * .6, y=1.3 + hy * .6, ax=2.2 - hx * .6, ay=1.3 - hy * .6, xref='x', yref='y',
                           axref='x', ayref='y', showarrow=True, arrowhead=3, arrowwidth=6, arrowcolor='#1f6feb', text='')
        fig.add_annotation(x=2.2, y=1.95, text=f'<b>viento hacia</b><br>{vel:.1f} m/s', showarrow=False, font=dict(color='#1f6feb'))
        fig.update_layout(xaxis=dict(range=[-1.7, 2.9], visible=False),
                          yaxis=dict(range=[-1.7, 2.3], visible=False, scaleanchor='x'),
                          height=560, margin=dict(l=0, r=0, t=0, b=0), plot_bgcolor='#f5f6f8')
        a, b = st.columns([1.3, 1])
        a.plotly_chart(fig, width='stretch')
        b.metric('Combustible de la celda central', D.CLASES_COMB[k])
        if k < 0:
            b.error('Celda no combustible: nunca se enciende (p = 0).')
        b.metric('Probabilidad de ignición por minuto', f'{100 * p_tot:.1f} %',
                 f'≈ {1 / p_tot:.1f} min en promedio' if p_tot > 0 else 'sin vecinas ardiendo', delta_color='off')
        b.caption('Borde rojo = vecina ardiendo; el grosor de la flecha crece con p. El viento favorece a las vecinas a '
                  'barlovento (la llama empuja hacia donde sopla) y la pendiente favorece a las que están cuesta abajo.')
        st.dataframe(pd.DataFrame([{
            'Vecina': x['nombre'], 'Combustible vecina': D.CLASES_COMB[x['clase_vecina']],
            'θs pendiente (°)': round(x['theta_s'], 1), 'p_s': round(x['p_s'], 3), 'cos θ (viento)': round(x['cos_theta'], 2),
            'p_w': round(x['p_w'], 3), 'p_veg destino': x['p_veg'], 'p (por minuto)': f"{100 * x['p']:.2f} %"} for x in rows]),
            hide_index=True, width='stretch')

    # ------------------------------------------------------------ C) autómata en vivo
    if _sel == 2:
        st.markdown('**Autómata celular en vivo** sobre una ventana del terreno real: se enciende la celda central y se '
                    'ejecuta el mismo código del modelo (`simular`). Cambia el viento o el relieve para ver cómo '
                    'deforman la propagación.')
        c1, c2, c3 = st.columns(3)
        town = c1.selectbox('Ignición cerca de', list(D.TOWNS), index=2, key='ct')
        wind_mode = c2.radio('Viento', ['ERA5 real', 'Sin viento', 'Fuerte del NE (10 m/s)'], key='cw')
        flat = c3.checkbox('Terreno plano (ignora pendiente)', False)
        half, seed, dur = 40, 1, 120
        ra, ca = town_center_cell(town)
        r = int(np.clip(ra, half, D.SHAPE[0] - half - 1))
        c = int(np.clip(ca, half, D.SHAPE[1] - half - 1))
        sl = (slice(r - half, r + half), slice(c - half, c + half))
        clase, elev = g['clase'][sl].copy(), g['elevacion_m'][sl].copy()
        if clase[half, half] < 0:
            ys, xs = np.nonzero(clase >= 0)
            i = int(np.argmin((ys - half) ** 2 + (xs - half) ** 2))
            ign = (int(ys[i]), int(xs[i]))
        else:
            ign = (half, half)
        if flat:
            elev = np.full_like(elev, float(elev.mean()))
        v0, d0 = D.viento_en(240)
        wv, wd = {'ERA5 real': (v0, d0), 'Sin viento': (0.0, 0.0), 'Fuerte del NE (10 m/s)': (10.0, 45.0)}[wind_mode]
        ent = M.Entradas(clase=clase, elevacion=elev, resolucion=100.0, ignicion=ign,
                         viento_minuto=np.array([0.0, float(dur)]), viento_velocidad=np.array([wv, wv]),
                         viento_desde_grados=np.array([wd, wd]), horizonte_min=float(dur))
        llegada = M.simular(ent, P, int(seed))
        t = st.slider('Minuto', 0, dur, min(40, dur), key='ctm')
        st_map = np.where(clase < 0, 0, 1).astype(float)
        burning = np.isfinite(llegada) & (llegada <= t) & (t < llegada + P.duracion_min)
        done = np.isfinite(llegada) & (t >= llegada + P.duracion_min)
        st_map[burning], st_map[done] = 2, 3
        x0, y0 = D.X0 + (c - half) * D.RES, D.Y0 - (r - half) * D.RES
        xs_ = x0 + (np.arange(2 * half) + .5) * D.RES
        ys_ = y0 - (np.arange(2 * half) + .5) * D.RES
        cols = {0: '#b0b0b0', 1: '#9ccc65', 2: '#ff3d00', 3: '#212121'}
        fig = go.Figure(go.Heatmap(z=st_map, x=xs_, y=ys_, zmin=-.5, zmax=3.5, showscale=False, xgap=1, ygap=1,
                                   colorscale=_discrete_scale([0, 1, 2, 3], cols), hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=[x0 + (ign[1] + .5) * D.RES], y=[y0 - (ign[0] + .5) * D.RES], mode='markers',
                                 name='Ignición', marker=dict(symbol='star', size=16, color='#ffd400',
                                                              line=dict(width=1.5, color='black'))))
        if st.checkbox('Superponer carreteras (vectorial)', True, key='cr'):
            fig.add_trace(roads_trace(S, '#1f6feb', 2))
        plain_layout(fig, ([x0, x0 + 2 * half * D.RES], [y0 - 2 * half * D.RES, y0]), height=640)
        a, b = st.columns([2.2, 1])
        a.plotly_chart(fig, width='stretch')
        cnt = [(clase < 0).sum(), ((~burning) & (~done) & (clase >= 0)).sum(), burning.sum(), done.sum()]
        b.markdown('**Leyenda de estados**<br>' + '<br>'.join(
            f"<span style='background:{cols[i]};padding:1px 12px;border:1px solid #666'>&nbsp;</span> {nm}: <b>{int(n):,}</b> celdas"
            for i, (nm, n) in enumerate(zip(['No combustible', 'Susceptible', 'Ardiendo', 'Consumida'], cnt))),
            unsafe_allow_html=True)
        b.metric('Área afectada', f'{int(burning.sum() + done.sum())} ha')
        b.caption(f'Cada celda arde {P.duracion_min:.0f} min y luego queda consumida. Viento efectivo: '
                  f'{wv * P.factor_viento:.1f} m/s desde {wd:.0f}°.')
        ts = np.arange(0, dur + 1)
        bu = [(np.isfinite(llegada) & (llegada <= m) & (m < llegada + P.duracion_min)).sum() for m in ts]
        co = [(np.isfinite(llegada) & (m >= llegada + P.duracion_min)).sum() for m in ts]
        gf = go.Figure()
        gf.add_trace(go.Scatter(x=ts, y=bu, name='Ardiendo', line=dict(color='#ff3d00')))
        gf.add_trace(go.Scatter(x=ts, y=co, name='Consumida', line=dict(color='#bdbdbd')))
        gf.add_vline(x=t, line_dash='dash')
        gf.update_layout(height=300, margin=dict(t=10, b=30), xaxis_title='minuto', yaxis_title='celdas',
                         legend=dict(orientation='h', y=-0.3))
        st.plotly_chart(gf, width='stretch')
