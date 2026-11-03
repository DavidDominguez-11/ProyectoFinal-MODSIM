"""Concepto 4 · Agentes heterogéneos y corridas múltiples (Monte Carlo)."""
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scipy import stats

from scripts.demo import datos as D
from scripts.demo.ui import XC, YC, banner, base_layout, pick_run, view_for
from scripts.demo.ui_extra import lazy_tabs, seg_xy

PURPLE = '#8e44ad'
STATE_LABEL = {0: 'A salvo (salió del dominio)', 2: 'Alcanzado por el fuego', 4: 'Esperando en cola al terminar', 5: 'En ruta al terminar'}
STATE_COLOR = {0: '#1db954', 2: '#e5134b', 4: '#7b2cbf', 5: '#1f77ff'}
SC_COLOR = {'base': '#6c757d', 'early_alert': '#1db954', 'skyway_closed': '#e5134b', 'exit_capacity': '#1f6feb'}


def render(S, runs):
    banner('agent', '4', 'Agentes y corridas múltiples (Monte Carlo)',
           'Cada <b>agente</b> es un grupo con atributos propios (origen, peso, demora, estado) que toma decisiones '
           'locales; por eso la población es <b>heterogénea</b>. Como la preparación y el fuego son aleatorios, un solo '
           'resultado no basta: se ejecutan <b>corridas múltiples</b> con semillas registradas y se reportan medias e '
           'intervalos de confianza.',
           '<code>scripts/evacuacion/experimentos.py</code>: <code>make_groups()</code> (agentes) y '
           '<code>run_experiments()</code> (30 réplicas × 4 escenarios, semillas pareadas)',
           ['<b>Agente = grupo:</b> origen (celda y nodo), peso (personas), demora (alerta + preparación Gamma) y estado.',
            '<b>Heterogeneidad:</b> cada grupo tiene su propia demora de salida; el fuego es distinto en cada réplica.',
            '<b>Monte Carlo pareado:</b> la réplica <i>r</i> usa el fuego <i>r</i> (semilla 1000+r) y preparación 2000+r en los 4 escenarios.',
            '<b>Resultados:</b> media ± IC 95 % (t de Student) sobre 30 réplicas.'])
    _sel = lazy_tabs(['👥 A · Agentes: origen, peso, demora y estado', '🎲 B · Corridas múltiples (Monte Carlo)',
                                   '🔥 C · Variabilidad del fuego entre réplicas'], 'agent', '#8e44ad')
    cfg = json.loads((D.ROOT / 'config/escenarios_evacuacion.json').read_text())

    # ------------------------------------------------------------ A) agentes
    if _sel == 0:
        sc, rep, T = pick_run(runs, 'ag')
        w = T['g_people']
        G = len(w)
        alert = cfg['base_alert_min'] + (cfg['early_alert_delta_min'] if sc == 'early_alert' else 0)
        prep = np.maximum(T['g_ready'] - alert, 0)
        fin = T['g_finish']
        m = st.columns(5)
        m[0].metric('Agentes (grupos)', f'{G:,}')
        m[1].metric('Personas', f'{w.sum():,.0f}')
        m[2].metric('Peso medio', f'{w.mean():.2f}', 'personas por grupo (máx. 3)', delta_color='off')
        m[3].metric('Alerta (igual para todos)', f'{alert:.0f} min')
        m[4].metric('Demora de preparación', f'{prep.mean():.1f} min', f'Gamma(forma 2, escala {cfg["preparation_gamma_scale_min"]:.0f})', delta_color='off')
        a, b = st.columns(2)
        xs = np.linspace(0, float(np.percentile(prep, 99.8)), 200)
        fh = go.Figure()
        fh.add_trace(go.Histogram(x=prep, histnorm='probability density', nbinsx=60, name='Agentes simulados', marker_color=PURPLE, opacity=.65))
        fh.add_trace(go.Scatter(x=xs, y=stats.gamma.pdf(xs, cfg['preparation_gamma_shape'], scale=cfg['preparation_gamma_scale_min']),
                                name='Gamma teórica', line=dict(color='#ffd400', width=3)))
        fh.update_layout(height=320, margin=dict(t=30, b=30), title='Demora de preparación de los agentes (min)', xaxis_title='min después de la alerta',
                         yaxis_title='densidad', legend=dict(orientation='h', y=-0.3))
        a.plotly_chart(fh, width='stretch')
        fw = go.Figure(go.Histogram(x=w, nbinsx=40, marker_color=PURPLE))
        fw.update_layout(height=320, margin=dict(t=30, b=30), title='Peso de los agentes (personas por grupo)', xaxis_title='personas', yaxis_title='grupos', yaxis_type='log')
        b.plotly_chart(fw, width='stretch')
        st.caption('La preparación es **independiente por agente** (heterogeneidad): se muestrea de una Gamma asimétrica y positiva; '
                   'el histograma simulado reproduce la curva teórica.')
        c1, c2, c3 = st.columns(3)
        color_by = c1.selectbox('Colorear el mapa de agentes por', ['Estado final', 'Demora de preparación (min)', 'Peso (personas)', 'Minuto de llegada a la salida'])
        zone = c2.selectbox('Zona', ['Todo el dominio'] + list(D.TOWNS), key='agz')
        frac = c3.slider('Agentes dibujados (%)', 10, 100, 60, key='agf')
        sel = np.random.default_rng(5).random(G) < frac / 100
        ox, oy = S['xy'][T['g_node'], 0].astype(np.float32), S['xy'][T['g_node'], 1].astype(np.float32)
        fm = go.Figure()
        if color_by.startswith('Estado'):
            for k, lab in STATE_LABEL.items():
                mk = sel & (T['g_state'] == k)
                fm.add_trace(go.Scattergl(x=ox[mk], y=oy[mk], mode='markers', name=f'{lab} ({w[T["g_state"] == k].sum():,.0f} pers.)',
                                          marker=dict(size=4, color=STATE_COLOR[k]), hoverinfo='skip'))
        else:
            val, name, cs = {'Demora de preparación (min)': (prep, 'min', 'Viridis'), 'Peso (personas)': (w, 'personas', 'Plasma'),
                             'Minuto de llegada a la salida': (np.where(fin >= 0, fin, np.nan), 'min', 'Turbo')}[color_by]
            mk = sel & np.isfinite(val)
            fm.add_trace(go.Scattergl(x=ox[mk], y=oy[mk], mode='markers', name='Agentes', marker=dict(size=4, color=val[mk], colorscale=cs,
                                      colorbar=dict(title=name, thickness=12, len=.5)), hoverinfo='skip'))
        base_layout(fm, view_for(zone, 4), height=620)
        st.plotly_chart(fm, width='stretch')
        st.markdown('**Ficha de un agente**')
        moved = np.flatnonzero(T['moved'])
        gid = st.number_input('Número de agente (0 – %d)' % (G - 1), 0, G - 1, int(moved[len(moved) // 3]), key='agid')
        e_, s_, en_, oc_ = D.group_path(S, T, int(gid))
        cx, cy = T['g_cell'][gid]
        card = {'id': f'g{int(gid):07d}', 'origen (fila, columna)': f'({cx}, {cy})', 'nodo vial de origen': f'n{T["g_node"][gid]}',
                'peso (personas)': round(float(w[gid]), 2), 'alerta (min)': alert, 'demora de preparación (min)': round(float(prep[gid]), 1),
                'sale a los (min)': round(float(T['g_ready'][gid]), 1), 'tramos recorridos': int(len(e_)),
                'estado final': STATE_LABEL.get(int(T['g_state'][gid]), str(T['g_state'][gid])),
                'llegó a la salida (min)': round(float(fin[gid]), 1) if fin[gid] >= 0 else '—', 'expuesto al fuego': bool(T['g_exposed'][gid])}
        k1, k2 = st.columns([1, 2])
        k1.dataframe(pd.DataFrame({'atributo': list(card), 'valor': [str(v) for v in card.values()]}), hide_index=True, width='stretch', height=420)
        tl = go.Figure()
        ready = float(T['g_ready'][gid])
        tl.add_trace(go.Bar(y=['Preparación'], x=[ready], base=[0], orientation='h', marker_color='#8e9aaf', name='Preparación'))
        prev = ready
        for i, ed in enumerate(e_):
            if s_[i] > prev + 1e-6:
                tl.add_trace(go.Bar(y=['Espera en cola'], x=[s_[i] - prev], base=[prev], orientation='h', marker_color='#7b2cbf', showlegend=False))
            tl.add_trace(go.Bar(y=['Recorrido'], x=[max(en_[i] - s_[i], .05)], base=[s_[i]], orientation='h', marker_color='#1f77ff' if oc_[i] == 0 else '#e5134b',
                                showlegend=False, hovertext=S['edge_name'][ed] or f'tramo {ed}'))
            prev = en_[i]
        tl.update_layout(barmode='overlay', height=300, xaxis_title='min desde la ignición', margin=dict(t=10, b=30), showlegend=False, xaxis_range=[0, 480])
        k2.plotly_chart(tl, width='stretch')
        st.caption('La vida del agente: se prepara (gris), espera en cola (morado) y recorre aristas (azul; rojo = interrumpido por el fuego).')

    # ------------------------------------------------------------ B) Monte Carlo
    rep_df = pd.read_csv(D.FINAL / 'replicas.csv')
    rep_df['pct'] = 100 * rep_df.fraction_safe_before_fire
    if _sel == 1:
        st.markdown('**Diseño experimental:** 30 réplicas × 4 escenarios = **120 corridas**. Cada réplica *r* usa el mismo fuego '
                    '(semilla 1000+*r*) y la misma preparación de los agentes (semilla 2000+*r*) en los 4 escenarios, '
                    'de modo que la diferencia entre escenarios se debe solo a la intervención (**muestreo pareado**).')
        labels = {'pct': '% de personas seguras antes del fuego', 'people_exposed': 'Personas con exposición potencial',
                  'evacuation_mean_min': 'Tiempo medio de llegada (min)', 'max_queue_people': 'Cola máxima (personas)'}
        metric = st.selectbox('Métrica', list(labels), format_func=labels.get)
        mlabel = labels[metric]
        fig = go.Figure()
        for s_name in D.SCENARIO_LABELS:
            d = rep_df[rep_df.scenario == s_name].sort_values('replica')
            fig.add_trace(go.Scatter(x=d.replica, y=d[metric], mode='lines+markers', name=D.SCENARIO_LABELS[s_name], line=dict(color=SC_COLOR[s_name], width=2)))
        fig.update_layout(height=420, margin=dict(t=30, b=30), title='Cada réplica (semilla) en los 4 escenarios — las líneas se mueven juntas porque comparten fuego y preparación',
                          xaxis_title='réplica r (fuego 1000+r, preparación 2000+r)', yaxis_title=mlabel, legend=dict(orientation='h', y=-0.3))
        st.plotly_chart(fig, width='stretch')
        a, b = st.columns(2)
        scn = a.selectbox('Escenario para la convergencia', list(D.SCENARIO_LABELS), format_func=D.SCENARIO_LABELS.get, key='mcs')
        v = rep_df[rep_df.scenario == scn].sort_values('replica')[metric].values
        n = np.arange(2, len(v) + 1)
        mean = np.array([v[:k].mean() for k in n])
        half = np.array([stats.t.ppf(.975, k - 1) * v[:k].std(ddof=1) / np.sqrt(k) for k in n])
        fc = go.Figure()
        fc.add_trace(go.Scatter(x=np.r_[n, n[::-1]], y=np.r_[mean + half, (mean - half)[::-1]], fill='toself', fillcolor='rgba(142,68,173,.25)', line=dict(width=0), name='IC 95 %'))
        fc.add_trace(go.Scatter(x=n, y=mean, line=dict(color=PURPLE, width=3), name='Media acumulada'))
        fc.update_layout(height=380, margin=dict(t=30, b=30), title='Convergencia: la media y su IC al sumar réplicas', xaxis_title='número de réplicas', yaxis_title=mlabel, legend=dict(orientation='h', y=-0.3))
        a.plotly_chart(fc, width='stretch')
        b.markdown('**Resumen sobre las 30 réplicas** (media ± IC 95 %)')
        rows = []
        for s_name in D.SCENARIO_LABELS:
            x = rep_df[rep_df.scenario == s_name][metric].values
            h = stats.t.ppf(.975, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x))
            rows.append({'Escenario': D.SCENARIO_LABELS[s_name], 'Media': round(float(x.mean()), 2), '± IC 95 %': round(float(h), 2),
                         'Mín': round(float(x.min()), 2), 'Máx': round(float(x.max()), 2)})
        b.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        base = rep_df[rep_df.scenario == 'base'].sort_values('replica')[metric].values
        fd = go.Figure()
        for s_name in ['early_alert', 'skyway_closed', 'exit_capacity']:
            diff = rep_df[rep_df.scenario == s_name].sort_values('replica')[metric].values - base
            fd.add_trace(go.Box(y=diff, name=D.SCENARIO_LABELS[s_name], marker_color=SC_COLOR[s_name], boxpoints='all', jitter=.4, pointpos=0, boxmean=True))
        fd.add_hline(y=0, line_dash='dash')
        fd.update_layout(height=340, margin=dict(t=30, b=30), showlegend=False, title='Diferencia pareada respecto a la base, réplica por réplica', yaxis_title=f'Δ {mlabel}')
        st.plotly_chart(fd, width='stretch')

    # ------------------------------------------------------------ C) variabilidad del fuego
    if _sel == 2:
        fire = S['fire']
        area = (fire >= 0).sum((1, 2))
        base = rep_df[rep_df.scenario == 'base'].sort_values('replica')
        order = np.argsort(area)
        picks = [int(order[0]), int(order[len(order) // 2]), int(order[-1])]
        st.markdown('**Misma ignición, 30 fuegos distintos:** la estocasticidad del autómata produce huellas y áreas diferentes, y eso '
                    'se propaga a la evacuación.')
        fm = make_subplots(rows=1, cols=3, subplot_titles=[f'Réplica {r} · {area[r]:,} ha ({lab})' for r, lab in zip(picks, ['mínima', 'mediana', 'máxima'])])
        for i, r in enumerate(picks):
            z = np.where(fire[r] >= 0, fire[r], np.nan).astype(np.float32)
            fm.add_trace(go.Heatmap(z=z, x=XC, y=YC, colorscale='Turbo', zmin=0, zmax=480, showscale=(i == 2), colorbar=dict(title='min', thickness=10)), row=1, col=i + 1)
            fm.update_xaxes(visible=False, row=1, col=i + 1)
            fm.update_yaxes(visible=False, row=1, col=i + 1)
        fm.update_layout(height=330, margin=dict(t=40, b=10, l=0, r=0))
        st.plotly_chart(fm, width='stretch')
        a, b = st.columns(2)
        fa = go.Figure(go.Bar(x=np.arange(30), y=area, marker_color='#e5134b'))
        fa.update_layout(height=320, margin=dict(t=30, b=30), title='Área quemada por réplica (ha)', xaxis_title='réplica', yaxis_title='ha')
        a.plotly_chart(fa, width='stretch')
        r_, p_ = stats.pearsonr(area, base.pct.values)
        fs = go.Figure(go.Scatter(x=area, y=base.pct.values, mode='markers+text', text=[str(i) for i in range(30)], textposition='top center',
                                  marker=dict(size=10, color=PURPLE)))
        coef = np.polyfit(area, base.pct.values, 1)
        xx = np.array([area.min(), area.max()])
        fs.add_trace(go.Scatter(x=xx, y=np.polyval(coef, xx), mode='lines', line=dict(color='#111', dash='dash'), name='tendencia'))
        fs.update_layout(height=320, margin=dict(t=30, b=30), showlegend=False, title=f'Escenario base: ¿más fuego = menos evacuados a tiempo? (r = {r_:.2f})',
                         xaxis_title='área quemada (ha)', yaxis_title='% seguros antes del fuego')
        b.plotly_chart(fs, width='stretch')
        seeds = pd.DataFrame({'Réplica': np.arange(30), 'Semilla de fuego': S['seeds'], 'Semilla de preparación': cfg['preparation_seed_start'] + np.arange(30),
                              'Área quemada (ha)': area})
        for s_name in D.SCENARIO_LABELS:
            seeds[f'% seguro · {D.SCENARIO_LABELS[s_name]}'] = rep_df[rep_df.scenario == s_name].sort_values('replica').pct.round(1).values
        st.markdown('**Registro de semillas y resultados por réplica**')
        st.dataframe(seeds, hide_index=True, width='stretch', height=320)
