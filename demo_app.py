"""Visor de los resultados existentes del proyecto Camp Fire.

Uso: streamlit run demo_app.py
No descarga datos, no recalibra y no ejecuta simulaciones.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from demo_data import SCENARIOS, DemoBundle, fire_snapshot, load_bundle, paired_values
from demo_process import group_position, latest_history, load_process


ROOT = Path(__file__).resolve().parent
NAMES = {
    "base": "Base",
    "early_alert": "Alerta 30 min antes",
    "skyway_closed": "Skyway cerrado",
    "exit_capacity": "Capacidad de una salida ×2",
}
COLORS = {
    "base": "#475569",
    "early_alert": "#0f766e",
    "skyway_closed": "#b45309",
    "exit_capacity": "#6d28d9",
}
METRICS = {
    "fraction_safe_before_fire": ("Fracción segura antes del fuego", "% de la población inicial", 100.0),
    "people_exposed": ("Exposición potencial acumulada", "personas ponderadas", 1.0),
    "people_safe": ("Llegadas a salida segura", "personas ponderadas", 1.0),
    "evacuation_mean_min": ("Tiempo medio de llegada segura", "min desde 06:25; solo quienes llegan", 1.0),
    "queue_duration_min": ("Duración con alguna cola", "min; incluye espera sin ruta", 1.0),
    "max_queue_people": ("Máximo simultáneo en cola", "personas ponderadas", 1.0),
    "queue_person_minutes": ("Espera acumulada", "personas ponderadas · min", 1.0),
}


def data() -> DemoBundle:
    # Las entradas son pequeñas; comprobarlas en cada interacción evita servir
    # resultados en caché si alguno de los archivos locales cambia.
    return load_bundle(ROOT)


def fmt(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}".replace(",", " ")


def show_source(path: str, explanation: str) -> None:
    st.caption(f"Fuente local: `{path}` · {explanation}")


def page_home(bundle: DemoBundle) -> None:
    st.title("Camp Fire: fuego y evacuación")
    st.write("Explorador de un **modelo retrospectivo e hipotético** del corredor Pulga–Concow–Paradise, "
             "California, el 8 de noviembre de 2018. El reloj computacional abarca 06:25–14:25. "
             "Las 06:25 corresponden a la primera llamada registrada, no a una ignición física comprobada.")
    attachment = bundle.summary["metadata"]["attachment"]
    a, b, c, d = st.columns(4)
    a.metric("Grilla", "205 × 278")
    a.caption("100 m por celda")
    b.metric("Fuegos distintos", "30")
    b.caption("Semillas 1000–1029")
    c.metric("Grupos modelados", f"{attachment['group_count']:,}".replace(",", " "))
    d.metric("Corridas de evacuación", "120")
    d.caption("4 escenarios × 30")
    st.info("La población es una estimación residencial ponderada. Alertas, preparación, velocidades, "
            "capacidades y cierres de los escenarios de evacuación son supuestos explícitos. "
            "La exposición potencial no representa lesiones ni fallecimientos.")
    st.subheader("Recorrido de la demo")
    st.graphviz_chart('''digraph {
      rankdir=LR; bgcolor="transparent";
      node [shape=box, style="rounded,filled", color="#cbd5e1", fillcolor="#f8fafc", fontname="Arial"];
      fuentes [label="Fuentes y grilla"]; fuego [label="30 campos de fuego"];
      grupos [label="Población y red vial"]; motor [label="Motor por eventos"];
      resultados [label="120 corridas y métricas"];
      fuentes -> fuego; fuentes -> grupos; fuego -> motor; grupos -> motor; motor -> resultados;
    }''', width="stretch")
    st.write("Usa el menú lateral para recorrer el método, el avance del fuego y una réplica visual "
             "de rutas y grupos; después compara escenarios y revisa los límites de cada conclusión.")
    show_source("config/dominio.json · salidas/fuego/contrato.json · salidas/evacuacion_final/summary.json",
                "cifras tomadas de los archivos del proyecto")


def page_flow(bundle: DemoBundle) -> None:
    st.title("Flujo técnico")
    st.write("El fuego se calcula primero. Sus tiempos de llegada condicionan la evacuación: "
             "cierran vías y marcan exposición. La evacuación no retroalimenta la propagación del fuego.")
    st.graphviz_chart('''digraph {
      rankdir=TB; bgcolor="transparent";
      node [shape=box, style="rounded,filled", fillcolor="#eff6ff", color="#93c5fd", fontname="Arial"];
      datos [label="LANDFIRE · 3DEP · WorldPop · NIST · ERA5"];
      grilla [label="Grilla UTM 10N · 100 m · 205 × 278"];
      fuego [label="Autómata celular + focos adelantados"];
      salida [label="llegada_min[réplica, fila, columna]"];
      carreteras [label="TIGER 2018 → grafo dirigido"];
      grupos [label="Población → 50 314 grupos ponderados"];
      motor [label="Eventos · rutas · capacidad · fuego"];
      resultados [label="CSV de réplicas → medias · IC · pares"];
      datos -> grilla -> fuego -> salida -> motor -> resultados;
      carreteras -> motor; grupos -> motor;
    }''', width="stretch")
    with st.expander("1 · Datos y reloj", expanded=True):
        st.write("El dominio usa EPSG:32610. Los rásteres se alinean en celdas de 100 m. "
                 "WorldPop distribuye población residencial; se reescala para que Paradise sume "
                 "26 581 habitantes estimados por BCAG/DOF. El total modelado del dominio es "
                 f"{fmt(bundle.summary['metadata']['attachment']['people_total'], 4)} personas ponderadas.")
        st.warning("Una auditoría previa obtuvo ~28 407 en otro recorte WorldPop, frente a "
                   "18 319,7 antes del reescalado en la grilla final. La causa de esa diferencia "
                   "no está resuelta; el reescalado no valida la distribución espacial.")
        show_source("scripts/fuego/f1_descargar_capas.py · f2_preparar_grilla.py · data/procesado/grilla_fuego_meta.json",
                    "preparación y metadatos")
    with st.expander("2 · Fuego y contraste histórico"):
        st.write("Cada minuto, el autómata evalúa las ocho vecinas de Moore. Combina combustible, "
                 "viento y pendiente, y permite focos adelantados por brasas. Seis parámetros "
                 "se calibraron con observaciones NIST; otras observaciones se reservaron para evaluar tiempos.")
        st.write("En validación se reportó un MAE de 105,1 min y 41,7 % de bloques dentro de ±60 min. "
                 "El perímetro final también participó en la calibración, por lo que la evaluación "
                 "espacial contra ese mismo perímetro no es totalmente independiente.")
        st.warning("La documentación afirma que celdas vecinas nunca quedaron en conjuntos distintos; "
                   "una revisión del CSV encontró 24 pares adyacentes a lados de límites de bloque. "
                   "Es una partición por bloques, sin margen de separación.")
        show_source("scripts/fuego/modelo_fuego.py · evaluacion.py · salidas/fuego/validacion.json",
                    "modelo y evaluación")
    with st.expander("3 · Red vial y grupos"):
        st.write("TIGER/Line 2018 define la geometría de la red. Cada segmento se convierte en "
                 "dos aristas dirigidas con velocidad y capacidad supuestas. Una arista se cierra "
                 "cuando el fuego alcanza alguna celda que intersecta. Cada celda poblada se divide "
                 "en grupos de hasta tres personas ponderadas y se asocia al nodo vial más cercano.")
        st.write("La red reportada en la integración tiene 31 670 nodos, 64 098 aristas y seis salidas "
                 "hipotéticas. La página de rutas usa una red regenerada cuyo hash difiere del "
                 "registrado en las 120 corridas; se identifica como réplica ilustrativa nueva.")
        show_source("scripts/evacuacion/red_vial.py · experimentos.py · salidas/evacuacion_final/summary.json",
                    "constructor, adaptación y resumen")
    with st.expander("4 · Eventos y comparación"):
        st.write("El motor procesa cierres por fuego, peligro en nodos, llegadas y grupos listos en "
                 "orden temporal. Administra colas por capacidad y reserva plazas en destinos. "
                 "Cada escenario usa los mismos grupos y el mismo fuego para una réplica dada. "
                 "Las diferencias son alternativa menos base por réplica, con IC Student-t 95 %.")
        st.write("Las velocidades viales son fijas; la congestión se representa mediante espera "
                 "por capacidad, no mediante reducción dinámica de velocidad. No se modelan "
                 "brigadas, refugios históricos ni rutas reales de personas identificadas.")
        show_source("scripts/evacuacion/motor.py · experimentos.py · config/escenarios_evacuacion.json",
                    "reglas y supuestos")


def fire_figure(bundle: DemoBundle, replica: int, minute: int, perimeter: bool) -> go.Figure:
    grid = fire_snapshot(bundle.arrivals, replica, minute)
    transform = bundle.contract["transform_gdal"]
    x = transform[0] + (np.arange(grid.shape[1]) + .5) * transform[1]
    y = transform[3] + (np.arange(grid.shape[0]) + .5) * transform[5]
    fig = go.Figure()
    fig.add_trace(go.Heatmap(x=x, y=y, z=grid, zmin=0, zmax=max(minute, 1),
                             colorscale=[[0, "#fff7ed"], [.25, "#fdba74"],
                                         [.55, "#f97316"], [1, "#991b1b"]],
                             colorbar=dict(title="Min de llegada"),
                             hovertemplate="Este %{x:.0f} m<br>Norte %{y:.0f} m<br>Primer fuego: min %{z:.0f}<extra></extra>"))
    if perimeter:
        fig.add_trace(go.Contour(x=x, y=y, z=bundle.perimeter.astype(int),
                                 contours=dict(start=.5, end=.5, size=1, coloring="none"),
                                 line=dict(color="#0f172a", width=1.5),
                                 showscale=False, hoverinfo="skip", name="Perímetro final"))
    fig.update_layout(height=620, margin=dict(l=15, r=15, t=35, b=15),
                      title=f"Réplica {replica + 1} · semilla {bundle.fire_seeds[replica]} · minuto {minute}",
                      xaxis_title="Este UTM 10N (m)", yaxis_title="Norte UTM 10N (m)",
                      paper_bgcolor="white", plot_bgcolor="#f1f5f9")
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


def page_fire(bundle: DemoBundle) -> None:
    st.title("Avance espacial del fuego")
    st.write("Selecciona una de las **30 realizaciones guardadas** y mueve el reloj. Cada celda "
             "coloreada muestra el primer minuto en que el modelo la encendió; una celda sin color "
             "aún no fue alcanzada en el minuto mostrado.")
    left, right = st.columns([1, 2])
    with left:
        replica = st.selectbox("Réplica de fuego", range(30),
                               format_func=lambda r: f"{r + 1:02d} · semilla {bundle.fire_seeds[r]}")
    with right:
        minute = st.slider("Minutos desde 06:25", 0, 480, 120, step=5)
    perimeter = st.checkbox("Contorno del perímetro final del incendio (26 nov 2018)", value=False)
    clock = datetime(2018, 11, 8, 6, 25) + timedelta(minutes=minute)
    layer = bundle.arrivals[replica]
    reached = int(np.count_nonzero((layer >= 0) & (layer <= minute)))
    c1, c2, c3 = st.columns(3)
    c1.metric("Hora del reloj modelado", clock.strftime("%H:%M"))
    c2.metric("Celdas alcanzadas hasta ahora", f"{reached:,}".replace(",", " "))
    c3.metric("Área de esas celdas", f"{reached:,} ha".replace(",", " "))
    st.plotly_chart(fire_figure(bundle, replica, minute, perimeter), width="stretch")
    st.caption("Una celda de 100 × 100 m equivale a 1 ha. La escala de colores se ajusta al "
               "minuto seleccionado, así que un mismo color no indica siempre la misma hora. "
               "El mapa muestra la réplica modelada, "
               "no un perímetro observado a esa hora. El contorno opcional corresponde al "
               "perímetro final de días después y sirve solo de referencia espacial.")
    show_source("salidas/fuego/llegada_replicas.npz · salidas/fuego/contrato.json",
                "matrices y coordenadas verificadas al cargar")


def process_figure(bundle: DemoBundle, process: dict, minute: int, chosen: str) -> go.Figure:
    transform = bundle.contract["transform_gdal"]
    grid = fire_snapshot(bundle.arrivals, 0, minute)
    x = transform[0] + (np.arange(grid.shape[1]) + .5) * transform[1]
    y = transform[3] + (np.arange(grid.shape[0]) + .5) * transform[5]
    fig = go.Figure(go.Heatmap(x=x, y=y, z=grid, zmin=0, zmax=max(minute, 1),
                               colorscale="Oranges", opacity=.58, showscale=False,
                               hovertemplate="Fuego modelado: min %{z:.0f}<extra></extra>"))
    roads = process["roads"]
    road_x, road_y = [], []
    for x0, y0, x1, y1 in roads:
        road_x.extend((x0, x1, None))
        road_y.extend((y0, y1, None))
    fig.add_trace(go.Scattergl(x=road_x, y=road_y, mode="lines", name="Red vial regenerada",
                               line=dict(color="rgba(71,85,105,.32)", width=.6),
                               hoverinfo="skip"))
    if process.get("exits"):
        fig.add_trace(go.Scattergl(x=[d["xy"][0] for d in process["exits"]],
                                   y=[d["xy"][1] for d in process["exits"]],
                                   mode="markers", name="Salidas hipotéticas",
                                   marker=dict(color="#7c3aed", symbol="diamond", size=13,
                                               line=dict(color="white", width=1)),
                                   text=[d["node"] for d in process["exits"]],
                                   hovertemplate="Salida hipotética %{text}<extra></extra>"))
    groups = process["groups"] if chosen == "Todos" else [g for g in process["groups"] if g["id"] == chosen]
    selected_ids = {g["id"] for g in groups}
    paths_x, paths_y = [], []
    for record in process["traversals"]:
        if record["group"] in selected_ids and record["start_min"] <= minute:
            if record["outcome"] == "arrived" and record["end_min"] <= minute:
                end_xy = record["to_xy"]
            elif minute < record["end_min"]:
                fraction = (minute - record["start_min"]) / (record["planned_end_min"] - record["start_min"])
                end_xy = [a + fraction * (b - a) for a, b in
                          zip(record["from_xy"], record["to_xy"])]
            else:
                continue
            paths_x.extend((record["from_xy"][0], end_xy[0], None))
            paths_y.extend((record["from_xy"][1], end_xy[1], None))
    fig.add_trace(go.Scattergl(x=paths_x, y=paths_y, mode="lines", name="Tramos iniciados por la muestra",
                               line=dict(color="#1d4ed8", width=3), hoverinfo="skip"))
    points = [group_position(g, process["traversals"], minute) for g in groups]
    fig.add_trace(go.Scattergl(x=[p[0][0] for p in points], y=[p[0][1] for p in points],
                               mode="markers", name="Grupos de la muestra",
                               marker=dict(color="#0f766e", size=10, line=dict(color="white", width=1)),
                               text=[f"{g['id']} · {g['people']:.2f} personas ponderadas · {p[1]}"
                                     for g, p in zip(groups, points)],
                               hovertemplate="%{text}<extra></extra>"))
    fig.update_layout(height=640, margin=dict(l=10, r=10, t=35, b=10),
                      title=f"Réplica ilustrativa · minuto {minute} · 06:25 + {minute} min",
                      xaxis_title="Este UTM 10N (m)", yaxis_title="Norte UTM 10N (m)",
                      plot_bgcolor="#f8fafc", legend=dict(orientation="h"))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


def page_process(bundle: DemoBundle) -> None:
    st.title("Rutas y grupos en el tiempo")
    process = load_process(ROOT, bundle)
    if process is None:
        st.warning("No se encontró `salidas/demo_proceso.json`. Esta página requiere generar "
                   "una nueva réplica visual con la red vial y el motor del proyecto.")
        return
    st.warning("Esta es una **nueva réplica ilustrativa** del escenario base, fuego 1000 y "
               "preparación 2000. La red TIGER regenerada tiene la misma estructura reportada "
               "(31 670 nodos y 64 098 aristas), pero su SHA-256 difiere del lote de 120 "
               "corridas. Sus números no se presentan como resultados publicados.")
    if "process_minute" not in st.session_state:
        st.session_state.process_minute = 0
    previous, advance = st.columns([1, 1])
    if previous.button("↩ Inicio", width="stretch"):
        st.session_state.process_minute = 0
    if advance.button("▶ Avanzar 5 min", width="stretch"):
        st.session_state.process_minute = min(480, st.session_state.process_minute + 5)
    minute = st.slider("Reloj del proceso · minutos desde 06:25", 0, 480,
                       step=1, key="process_minute")
    alert_at = bundle.config["base_alert_min"]
    if minute < alert_at:
        st.info(f"Antes de la alerta hipotética uniforme (minuto {fmt(alert_at, 0)}). "
                "El fuego puede avanzar mientras los grupos siguen preparándose.")
    else:
        st.info(f"La alerta hipotética ocurrió en el minuto {fmt(alert_at, 0)}. "
                "Cada grupo sale cuando termina su preparación; el motor recalcula rutas "
                "ante cierres, capacidad y destinos disponibles.")
    group_ids = [g["id"] for g in process["groups"]]
    chosen = st.selectbox("Seguir grupo", ["Todos", *group_ids],
                          help="Los 36 grupos son una muestra determinista de 50 314, no todos los grupos.")
    sample = latest_history(process["history"], minute)
    a, b, c, d = st.columns(4)
    a.metric("Hora modelada", (datetime(2018, 11, 8, 6, 25) + timedelta(minutes=minute)).strftime("%H:%M"))
    b.metric("Llegaron a salida", fmt(sample["people_safe"], 1))
    c.metric("En cola", fmt(sample["queue_people"], 1))
    d.metric("Exposición acumulada", fmt(sample["people_exposed"], 1))
    st.caption(f"Contadores del último evento conservado: minuto {sample['time_min']:.3f}. "
               "Entre registros no se inventan valores. Las cifras son personas ponderadas, "
               "no individuos observados.")
    st.plotly_chart(process_figure(bundle, process, minute, chosen), width="stretch")
    st.caption("Gris: red vial regenerada. Naranja: celdas que el fuego modelado ya alcanzó. "
               "Morado: salidas hipotéticas. Azul: porción recorrida en tramos de la muestra. Verde: "
               "posición ilustrativa del grupo; sobre un tramo se interpola linealmente entre "
               "inicio y fin porque el motor guarda el tramo y su tiempo, no coordenadas continuas.")
    if chosen != "Todos":
        group = next(g for g in process["groups"] if g["id"] == chosen)
        position, state = group_position(group, process["traversals"], minute)
        taken = [t for t in process["traversals"] if t["group"] == chosen and t["start_min"] <= minute]
        st.subheader(f"Grupo {chosen}")
        st.write(f"Representa **{fmt(group['people'], 3)} personas ponderadas**; "
                 f"se prepara hasta el minuto {fmt(group['ready_min'], 2)}. "
                 f"Estado visual actual: **{state}**. Ha iniciado {len(taken)} tramos.")
        row, col = group["origin_cell"]
        origin_fire = int(bundle.arrivals[0, row, col])
        st.caption("Fuego modelado en la celda de origen: " +
                   (f"minuto {origin_fire}" if origin_fire >= 0 else "no llegó dentro de 480 min") +
                   ". Esto no indica por sí solo que el grupo estuviera allí cuando llegó.")
        if taken:
            st.dataframe([{"Sale (min)": round(t["start_min"], 2),
                           "Termina (min)": round(t["end_min"], 2),
                           "Vía": t["road_name"] or "Sin nombre TIGER",
                           "Resultado": t["outcome"]} for t in taken],
                         hide_index=True, width="stretch")
        st.caption("El motor puede cambiar la ruta por cierres, capacidad y destinos disponibles. "
                   "El historial exportado guarda tramos efectivamente iniciados; no un plan fijo completo.")
    st.subheader("Evolución de la réplica")
    history = process["history"]
    timeline = go.Figure()
    for key, name, color in (("people_safe", "Llegadas seguras", "#0f766e"),
                             ("queue_people", "En cola", "#2563eb"),
                             ("people_exposed", "Exposición acumulada", "#c2410c")):
        timeline.add_trace(go.Scatter(x=[h["time_min"] for h in history],
                                      y=[h[key] for h in history], mode="lines",
                                      line_shape="hv", name=name, line=dict(color=color)))
    timeline.add_vline(x=minute, line_dash="dash", line_color="#334155")
    timeline.update_layout(height=380, xaxis_title="Min desde 06:25",
                           yaxis_title="Personas ponderadas", margin=dict(l=10, r=10, t=15, b=10))
    st.plotly_chart(timeline, width="stretch")
    st.caption("Historia compacta: primer evento real de cada franja de un minuto más el horizonte. "
               "Los saltos visuales entre registros no reconstruyen todos los eventos internos.")
    show_source("salidas/demo_proceso.json · scripts/evacuacion/exportar_demo_proceso.py",
                "réplica nueva, identificada y separada de las 120 corridas finales")


def metric_figure(bundle: DemoBundle, metric: str) -> go.Figure:
    title, unit, factor = METRICS[metric]
    entries = [bundle.summary["scenarios"][scenario][metric] for scenario in SCENARIOS]
    means = [e["mean"] * factor if e["mean"] is not None else None for e in entries]
    errors = [(e["ci95"][1] - e["mean"]) * factor if e["ci95"] else 0 for e in entries]
    fig = go.Figure(go.Bar(x=[NAMES[s] for s in SCENARIOS], y=means,
                           marker_color=[COLORS[s] for s in SCENARIOS],
                           error_y=dict(type="data", array=errors, visible=True),
                           customdata=np.asarray([e["ci95"] for e in entries], dtype=float) * factor,
                           hovertemplate="%{x}<br>Media: %{y:.3f}<br>IC 95 %: "
                                         "[%{customdata[0]:.3f}, %{customdata[1]:.3f}]<extra></extra>"))
    fig.update_layout(title=title, yaxis_title=unit, height=490,
                      margin=dict(l=20, r=20, t=55, b=20))
    return fig


def paired_figure(bundle: DemoBundle, scenario: str, metric: str) -> go.Figure:
    title, unit, factor = METRICS[metric]
    values = paired_values(bundle.replicas, scenario, metric) * factor
    recorded = bundle.summary["paired_differences_vs_base"][scenario][metric]
    mean = recorded["mean"] * factor
    low, high = (v * factor for v in recorded["ci95"])
    fig = go.Figure()
    fig.add_hrect(y0=low, y1=high, fillcolor=COLORS[scenario], opacity=.13,
                  line_width=0, annotation_text="IC 95 % de la media")
    fig.add_hline(y=0, line_dash="dash", line_color="#94a3b8")
    fig.add_hline(y=mean, line_color=COLORS[scenario],
                  annotation_text=f"Media {mean:+.3f}")
    fig.add_trace(go.Scatter(x=np.arange(1, len(values) + 1), y=values, mode="markers",
                             marker=dict(color=COLORS[scenario], size=8),
                             hovertemplate="Par %{x}<br>Diferencia: %{y:+.3f}<extra></extra>"))
    fig.update_layout(title=f"{NAMES[scenario]} − base · {title.lower()}",
                      xaxis_title="Índice del par de réplicas", yaxis_title=f"Diferencia ({unit})",
                      height=425, margin=dict(l=20, r=20, t=55, b=20))
    return fig


def page_results(bundle: DemoBundle) -> None:
    st.title("Comparación de escenarios")
    st.write("Cada escenario usa 30 fuegos y 30 preparaciones. Para el mismo índice de réplica, "
             "los insumos son iguales entre escenarios; cambia un factor. Los IC muestran "
             "variación entre réplicas **con parámetros fijos**, no incertidumbre histórica.")
    config = bundle.config
    st.dataframe({
        "Escenario": [NAMES[s] for s in SCENARIOS],
        "Cambio frente a base": [
            f"Alerta a {fmt(config['base_alert_min'], 0)} min; salidas de {fmt(config['base_exit_capacity_people'], 0)} personas",
            f"Alerta a {fmt(config['base_alert_min'] + config['early_alert_delta_min'], 0)} min",
            f"Cierre inicial de aristas nombradas {config['closed_corridor']}",
            f"Una salida: {fmt(config['base_exit_capacity_people'], 0)} → {fmt(config['increased_exit_capacity_people'], 0)} personas",
        ],
    }, hide_index=True, width="stretch")
    metric = st.selectbox("Métrica para comparar", list(METRICS),
                          format_func=lambda key: METRICS[key][0])
    st.plotly_chart(metric_figure(bundle, metric), width="stretch")
    if metric == "evacuation_mean_min":
        st.warning("El tiempo medio se calcula únicamente entre grupos que llegaron a una salida "
                   "segura. Un tiempo menor con Skyway cerrado puede reflejar que llegaron muchos "
                   "menos grupos; no significa una evacuación global mejor.")
    elif metric in ("queue_duration_min", "max_queue_people", "queue_person_minutes"):
        st.caption("La cola incluye espera sin ruta. Su duración y tamaño no se deben interpretar "
                   "por separado de las llegadas y de la exposición.")
    st.subheader("Diferencias pareadas frente a base")
    scenario = st.selectbox("Alternativa", SCENARIOS[1:], format_func=lambda s: NAMES[s])
    st.plotly_chart(paired_figure(bundle, scenario, metric), width="stretch")
    st.caption("Cada punto es alternativa menos base con el mismo fuego y preparación. La franja "
               "es el IC 95 % de la **media de las 30 diferencias**, no un intervalo que contiene "
               "el 95 % de los puntos.")
    if scenario == "exit_capacity":
        st.warning("Aquí aumentar la capacidad de una salida redujo la fracción segura antes del "
                   "fuego. El mecanismo no fue aislado; el resultado no justifica una política "
                   "general sobre capacidad.")
    with st.expander("Distribución temporal publicada"):
        st.image(str(ROOT / "salidas/evacuacion_final/cdf.png"),
                 caption="CDF agrupada y condicionada a llegada segura. La distribución exacta "
                         "por llegada no está versionada; esta figura publicada no es un IC.")
    show_source("salidas/evacuacion_final/replicas.csv · summary.json · cdf.png",
                "120 filas, estadísticas y figura originales")


def page_limits(bundle: DemoBundle) -> None:
    st.title("Procedencia y límites")
    st.write("El visor lee archivos locales. La página de proceso muestra una réplica visual "
             "nueva y separada del lote final, generada con el motor y una red vial regenerada. "
             "Solo 36 grupos tienen recorridos exportados; sus posiciones dentro de tramos "
             "se interpolan para la visualización.")
    st.subheader("Comprobación de archivos al abrir la demo")
    st.dataframe({"Entrada": list(bundle.source_checks),
                  "Estado": list(bundle.source_checks.values())},
                 hide_index=True, width="stretch")
    st.write("También se comprueban forma de grilla, 30 semillas de fuego, las 120 filas del CSV, "
             "emparejamiento, masa poblacional y la concordancia de métricas principales con el resumen.")
    st.subheader("Qué representa cada capa")
    st.markdown("""
| Elemento | Lectura correcta |
|---|---|
| NIST y red TIGER 2018 | Observaciones de fuego y geometría vial usadas como insumos históricos. |
| WorldPop ajustado | Distribución residencial estimada y reescalada; no personas presentes. |
| 30 mapas de fuego | Realizaciones de un modelo calibrado, no observaciones directas celda por celda. |
| Alertas, preparación, capacidad, velocidades y cierre Skyway | Supuestos de escenarios de evacuación. |
| Exposición potencial | Marca computacional acumulativa; no daño, lesión ni mortalidad. |
| Salida «segura» | Destino absorbente hipotético en el límite del mapa; no albergue histórico identificado. |
""")
    st.subheader("Pendientes relevantes")
    st.warning("La diferencia entre los dos recortes WorldPop sigue sin explicación comprobada. "
               "La documentación de fuego exagera la separación espacial entre conjuntos. "
               "La evacuación carece de calibración histórica de alertas, tráfico y refugios. "
               "La entrega académica final y la evidencia formal de aprobación requieren revisión separada.")
    st.caption("Los detalles y resultados originales están en `docs/modelo_fuego.md`, "
               "`docs/modelo_evacuacion.md`, `docs/auditoria_datos.md` y el segundo informe parcial.")


st.set_page_config(page_title="Camp Fire · visor del proyecto", page_icon="🔥", layout="wide")
try:
    bundle = data()
except (ValueError, KeyError, OSError, TypeError) as error:
    st.error(f"No se puede mostrar una combinación de datos no verificada: {error}")
    st.stop()

st.sidebar.title("Camp Fire · MODSIM")
page = st.sidebar.radio("Explorar", ["Inicio", "Flujo técnico", "Fuego en el tiempo",
                                        "Rutas y grupos", "Escenarios y resultados", "Procedencia y límites"])
st.sidebar.caption("Resultados finales + réplica visual identificada")

if page == "Inicio":
    page_home(bundle)
elif page == "Flujo técnico":
    page_flow(bundle)
elif page == "Fuego en el tiempo":
    page_fire(bundle)
elif page == "Rutas y grupos":
    page_process(bundle)
elif page == "Escenarios y resultados":
    page_results(bundle)
else:
    page_limits(bundle)
