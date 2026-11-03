"""Cuatro vistas de conceptos MODSIM, siempre ligadas a archivos del proyecto."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from demo_data import SCENARIOS, DemoBundle, fire_snapshot
from demo_process import group_position, latest_history


FUEL_NAMES = {
    -1: "No combustible", 0: "Urbano (clase del modelo)",
    1: "Pasto GR", 2: "Pasto arbustivo GS", 3: "Arbustal SH",
    4: "Sotobosque TU", 5: "Hojarasca TL", 6: "Restos de corta SB",
}


def _source(files: str) -> None:
    st.caption(f"Fuente del proyecto: `{files}`")


def _xy(bundle: DemoBundle) -> tuple[np.ndarray, np.ndarray]:
    transform = bundle.contract["transform_gdal"]
    x = transform[0] + (np.arange(bundle.population.shape[1]) + .5) * transform[1]
    y = transform[3] + (np.arange(bundle.population.shape[0]) + .5) * transform[5]
    return x, y


def _road_overlay(fig: go.Figure, process: dict) -> None:
    xs, ys = [], []
    for x0, y0, x1, y1 in process["roads"]:
        xs.extend((x0, x1, None))
        ys.extend((y0, y1, None))
    fig.add_trace(go.Scattergl(x=xs, y=ys, mode="lines", name="Carreteras vectoriales",
                               line=dict(color="rgba(30,41,59,.42)", width=.8),
                               hoverinfo="skip"))


def _route_figure(bundle: DemoBundle, process: dict, group: dict, minute: int) -> go.Figure:
    x, y = _xy(bundle)
    fire = fire_snapshot(bundle.arrivals, 0, minute)
    fig = go.Figure(go.Heatmap(x=x, y=y, z=fire, zmin=0, zmax=max(minute, 1),
                               colorscale="Oranges", opacity=.55, showscale=False,
                               hovertemplate="Fuego llegó: min %{z:.0f}<extra></extra>"))
    _road_overlay(fig, process)
    fig.add_trace(go.Scattergl(x=[d["xy"][0] for d in process["exits"]],
                               y=[d["xy"][1] for d in process["exits"]],
                               mode="markers", name="Salidas hipotéticas",
                               marker=dict(color="#7c3aed", symbol="diamond", size=12),
                               hoverinfo="skip"))
    visible = [record for record in process["traversals"]
               if record["group"] == group["id"] and record["start_min"] <= minute]
    paths_x, paths_y = [], []
    for record in visible:
        if record["outcome"] == "arrived" and record["end_min"] <= minute:
            end_xy = record["to_xy"]
        elif minute < record["end_min"]:
            fraction = (minute - record["start_min"]) / (
                record["planned_end_min"] - record["start_min"])
            end_xy = [a + fraction * (b - a) for a, b in
                      zip(record["from_xy"], record["to_xy"])]
        else:
            continue
        paths_x.extend((record["from_xy"][0], end_xy[0], None))
        paths_y.extend((record["from_xy"][1], end_xy[1], None))
    fig.add_trace(go.Scattergl(x=paths_x, y=paths_y, mode="lines",
                               name="Ruta recorrida", line=dict(color="#1d4ed8", width=3),
                               hoverinfo="skip"))
    position, state = group_position(group, process["traversals"], minute)
    fig.add_trace(go.Scattergl(x=[position[0]], y=[position[1]], mode="markers",
                               name="Grupo", marker=dict(color="#0f766e", size=13,
                                                           line=dict(color="white", width=2)),
                               text=[state], hovertemplate="%{text}<extra></extra>"))
    coords = [group["origin_xy"]]
    for record in visible:
        coords.extend((record["from_xy"], record["to_xy"]))
    xs, ys = [p[0] for p in coords], [p[1] for p in coords]
    pad = max(800, .12 * max(max(xs) - min(xs), max(ys) - min(ys)))
    fig.update_layout(height=540, title=f"Grupo {group['id']} · minuto {minute}",
                      xaxis_title="Este UTM 10N (m)", yaxis_title="Norte UTM 10N (m)",
                      xaxis_range=[min(xs) - pad, max(xs) + pad],
                      yaxis_range=[min(ys) - pad, max(ys) + pad],
                      margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h"))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


def grid_page(bundle: DemoBundle, process: dict | None) -> None:
    st.title("1 · Territorio y fuego")
    st.caption("**MODSIM · SIG + autómata celular:** grilla de 205 × 278 celdas de 100 m; "
               "ocho vecinas de Moore; carreteras vectoriales sobre capas ráster.")
    a, b, c = st.columns([2, 1, 2])
    layer = a.selectbox("Capa SIG", ["Clase de combustible", "Elevación", "Población residencial",
                                    "Llegada del fuego"], index=3)
    replica = b.selectbox("Fuego", range(30),
                          format_func=lambda i: f"{i + 1:02d}")
    minute = c.slider("Minuto desde 06:25", 0, 480, 120, key="grid_minute")
    roads = st.checkbox("Superponer carreteras vectoriales TIGER 2018", value=True,
                        disabled=process is None)
    x, y = _xy(bundle)
    if layer == "Clase de combustible":
        z, label, colors = bundle.fuel_class, "Código de clase", "Viridis"
    elif layer == "Elevación":
        z, label, colors = bundle.elevation, "Metros", "Earth"
    elif layer == "Población residencial":
        z, label, colors = bundle.population, "Personas ponderadas/celda", "Blues"
    else:
        z, label, colors = fire_snapshot(bundle.arrivals, replica, minute), "Min de llegada", "Oranges"
    fig = go.Figure(go.Heatmap(x=x, y=y, z=z, colorscale=colors,
                               colorbar=dict(title=label),
                               hovertemplate="Este %{x:.0f} m<br>Norte %{y:.0f} m<br>Valor %{z:.3f}<extra></extra>"))
    if roads and process is not None:
        _road_overlay(fig, process)
    fig.update_layout(height=470, title=f"{layer} · EPSG:32610", xaxis_title="Este UTM (m)",
                      yaxis_title="Norte UTM (m)", margin=dict(l=10, r=10, t=45, b=10))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(fig, width="stretch")
    st.caption("El fuego colorea celdas **alcanzadas hasta ese minuto**, no las que están "
               "ardiendo en ese instante. Las carreteras superpuestas proceden de la red "
               "ilustrativa regenerada.")

    st.subheader("Vecindad de Moore · 3 × 3")
    ignition = np.argwhere(bundle.arrivals[replica] == 0)
    default_row, default_col = (map(int, ignition[0]) if len(ignition) else
                                (bundle.population.shape[0] // 2, bundle.population.shape[1] // 2))
    left, right = st.columns(2)
    row = left.number_input("Fila central", min_value=1, max_value=bundle.population.shape[0] - 2,
                            value=max(1, min(default_row, bundle.population.shape[0] - 2)))
    col = right.number_input("Columna central", min_value=1, max_value=bundle.population.shape[1] - 2,
                             value=max(1, min(default_col, bundle.population.shape[1] - 2)))
    row, col = int(row), int(col)
    neighborhood = bundle.arrivals[replica, row - 1:row + 2, col - 1:col + 2]
    reached = np.where((neighborhood >= 0) & (neighborhood <= minute), 1, 0)
    tile = go.Figure(go.Heatmap(z=reached, x=[col - 1, col, col + 1],
                                y=[row - 1, row, row + 1],
                                colorscale=[[0, "#f1f5f9"], [1, "#ea580c"]],
                                showscale=False, hovertemplate="Fila %{y}, columna %{x}<br>Alcanzada: %{z}<extra></extra>"))
    tile.add_shape(type="rect", x0=col - .5, x1=col + .5, y0=row - .5, y1=row + .5,
                   line=dict(color="#1d4ed8", width=4))
    tile.update_layout(height=250, xaxis_title="Columna", yaxis_title="Fila",
                       title="Centro azul · ocho vecinas · naranja: fuego ya llegó",
                       margin=dict(l=10, r=10, t=45, b=10))
    tile.update_yaxes(autorange="reversed", scaleanchor="x", scaleratio=1)
    a, b = st.columns([1, 1])
    a.plotly_chart(tile, width="stretch")
    code = int(bundle.fuel_class[row, col])
    arrival = int(bundle.arrivals[replica, row, col])
    b.markdown(f"**Celda central ({row}, {col})**")
    b.write(f"Combustible: **{FUEL_NAMES[code]}** (código {code})")
    b.write(f"Elevación: **{bundle.elevation[row, col]:.1f} m** · "
            f"Pendiente ráster: **{bundle.slope[row, col]:.1f}°**")
    b.write(f"Población estimada: **{bundle.population[row, col]:.3f} personas ponderadas**")
    b.write("Primer fuego: " + (f"minuto **{arrival}**" if arrival >= 0 else
                                 "**no llegó durante los 480 min**"))
    st.caption("El fuego considera combustible, viento y pendiente entre celdas; también "
               "puede generar focos adelantados por brasas. La pendiente mostrada es "
               "descriptiva: la regla usa diferencias de elevación entre vecinos.")
    _source("data/procesado/grilla_fuego.npz · scripts/fuego/modelo_fuego.py · "
            "scripts/fuego/f2_preparar_grilla.py · salidas/fuego/llegada_replicas.npz")


def network_page(bundle: DemoBundle, process: dict | None) -> None:
    st.title("2 · Red vial y rutas")
    if process is None:
        st.warning("La vista vial necesita `salidas/demo_proceso.json`.")
        return
    st.caption("**MODSIM · Redes:** nodos conectados por aristas dirigidas `u → v`; "
               "las seis salidas son destinos hipotéticos.")
    stats = process["network_stats"]
    st.write(f"**{stats['nodes']:,} nodos · {stats['directed_edges']:,} aristas dirigidas · "
             f"{stats['components']} componentes · {stats['destinations']} salidas.** "
             f"{stats['nodes_without_exit']} nodos no tienen camino hacia una salida antes "
             "de cierres y fuego.")
    groups = process["groups"]
    default = next((i for i, g in enumerate(groups)
                    if g["people"] >= 2.9 and g["final_state"] == "safe"), 0)
    chosen = st.selectbox("Grupo para seguir sobre el grafo", [g["id"] for g in groups],
                          index=default, key="network_group")
    minute = st.slider("Minuto de la ruta", 0, 480, 95, key="network_minute")
    group = next(g for g in groups if g["id"] == chosen)
    st.plotly_chart(_route_figure(bundle, process, group, minute), width="stretch")
    st.caption("Azul: tramos efectivamente iniciados por este grupo, en dirección "
               "**u → v**. El mapa no dibuja una ruta planeada inmutable. Morado: salidas; "
               "verde: posición ilustrativa dentro del tramo actual.")
    traveled = [t for t in process["traversals"] if t["group"] == chosen and
                t["start_min"] <= minute]
    if traveled:
        row = traveled[-1]
        edge = process["edge_details"][row["edge"]]
        st.write(f"**Última arista:** `{row['edge']}` · {edge['u']} → {edge['v']} · "
                 f"{edge['road_name'] or 'vía sin nombre'} · "
                 f"{edge['travel_min']:.2f} min · "
                 f"capacidad **{edge['capacity_groups']} grupos simultáneos**.")
    else:
        st.write("El grupo aún no ha iniciado un tramo vial en el minuto elegido.")
    with st.expander("Cómo selecciona una ruta · detalles para preguntas"):
        st.markdown("""
1. Descarta destinos que ya alcanzó el fuego o cuya capacidad disponible no admite el peso completo del grupo.
2. Calcula caminos hacia destinos seguros sobre aristas aún abiertas, usando **tiempo fijo de recorrido** como costo; si no hay camino seguro, considera destinos temporales.
3. Desde el nodo actual toma la **primera arista** del mejor camino. Los empates se resuelven de forma determinista por identificadores.
4. Si la arista está llena, el grupo espera. Cuando cambia la red o una reserva, el motor puede volver a calcular la ruta.
""")
        st.caption("Cada segmento TIGER se modela en ambos sentidos como supuesto; no hay sentidos "
                   "históricos ni restricciones de giro. El acceso celda–nodo es instantáneo. "
                   "La réplica visual guarda tramos iniciados, no rutas candidatas rechazadas. "
                   "Su red regenerada difiere en SHA-256 de la usada en las 120 corridas.")
    _source("scripts/evacuacion/red_vial.py · scripts/evacuacion/experimentos.py · "
            "scripts/evacuacion/motor.py · salidas/demo_proceso.json")


def des_page(bundle: DemoBundle, process: dict | None) -> None:
    st.title("3 · Eventos y colas")
    if process is None:
        st.warning("La vista temporal necesita `salidas/demo_proceso.json`.")
        return
    st.caption("**MODSIM · DES:** grupos como entidades; aristas con capacidad como recursos; "
               "el reloj salta al siguiente evento y registra la espera.")
    st.graphviz_chart('''digraph {rankdir=LR; node [shape=box,style="rounded,filled",fontname="Arial"];
      grupo [label="Grupo\norigen · peso · demora",fillcolor="#dbeafe"];
      cola [label="Cola FIFO\no espera sin ruta",fillcolor="#fef3c7"];
      arista [label="Arista vial\ncapacidad en grupos",fillcolor="#ddd6fe"];
      destino [label="Salida\ncapacidad en personas",fillcolor="#dcfce7"];
      grupo -> cola -> arista -> destino;
      fuego [label="Fuego: cierre/peligro",fillcolor="#fee2e2"];
      fuego -> arista; fuego -> cola;}''', width="stretch")
    st.write("**Si coinciden en un instante:** cierre → peligro en nodo/origen → "
             "llegada a tramo → grupo listo → muestra. Después se despachan las colas.")
    minute = st.slider("Minuto para inspeccionar la cola", 0, 480, 180, key="des_minute")
    history = process["history"]
    sample = latest_history(history, minute)
    a, b, c = st.columns(3)
    a.metric("En cola · último registro", f"{sample['queue_groups']} grupos")
    b.metric("Peso en cola", f"{sample['queue_people']:.1f} personas")
    c.metric("Registro en minuto", f"{sample['time_min']:.2f}")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[s["time_min"] for s in history],
                             y=[s["queue_people"] for s in history], mode="lines",
                             line_shape="hv", name="Personas ponderadas en cola",
                             line=dict(color="#b45309", width=3)))
    fig.add_vline(x=minute, line_dash="dash", line_color="#334155")
    fig.update_layout(height=300, xaxis_title="Min desde 06:25",
                      yaxis_title="Personas ponderadas en cola",
                      margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch")
    st.caption("La curva usa muestras compactas de eventos reales. Su área visual **no** se "
               "usa para calcular la espera: el motor integra exactamente todos los intervalos.")
    m = process["metrics"]
    a, b, c = st.columns(3)
    a.metric("Duración con cola", f"{m['queue_duration_min']:.1f} min")
    b.metric("Espera acumulada", f"{m['queue_person_minutes']:.0f} personas·min")
    c.metric("Máximo en cola", f"{m['max_queue_groups']:.0f} grupos")
    st.caption("Métricas exactas de la réplica ilustrativa completa. La capacidad vial se mide "
               "en **grupos simultáneos**; esperar sin ruta también cuenta como cola.")
    with st.expander("Prioridades y cálculo de espera · detalles para preguntas"):
        st.dataframe([
            {"Orden": 0, "Evento": "Cierre de arista por fuego"},
            {"Orden": 1, "Evento": "Fuego en nodo o celda de origen"},
            {"Orden": 2, "Evento": "Llegada al final de un tramo"},
            {"Orden": 3, "Evento": "Grupo termina preparación"},
            {"Orden": 4, "Evento": "Muestra del estado"},
        ], hide_index=True, width="stretch")
        st.write("El motor integra la cola entre **todos** los eventos. La curva visible "
                 "contiene solo registros compactos; no sirve para recalcular la integral exacta.")
    _source("scripts/evacuacion/motor.py · docs/motor_evacuacion.md · salidas/demo_proceso.json")


def agents_page(bundle: DemoBundle, process: dict | None) -> None:
    st.title("4 · Grupos y resultados")
    st.caption("**MODSIM · entidades heterogéneas y Monte Carlo:** cada grupo tiene origen, "
               "peso, demora y estado; 30 fuegos y preparaciones se comparan en cuatro escenarios.")
    if process is not None:
        groups = process["groups"]
        default = next((i for i, g in enumerate(groups)
                        if g["people"] >= 2.9 and g["final_state"] == "safe"), 0)
        left, right = st.columns(2)
        selected = left.selectbox("Grupo de ejemplo · réplica ilustrativa",
                                  [g["id"] for g in groups], index=default,
                                  key="agent_group")
        group = next(g for g in process["groups"] if g["id"] == selected)
        minute = right.slider("Minuto del grupo", 0, 480, 100, key="agent_minute")
        _, visual_state = group_position(group, process["traversals"], minute)
        st.write(f"**Origen:** celda {tuple(group['origin_cell'])} · "
                 f"**peso:** {group['people']:.2f} personas ponderadas · "
                 f"**preparación:** {group['preparation_min']:.2f} min · "
                 f"**listo:** min {group['ready_min']:.2f} · "
                 f"**ahora:** {visual_state}.")
    st.subheader("Resultado principal · 120 corridas finales")
    st.caption("Intervenciones frente a base: alerta 85 → 55 min; cierre inicial de "
               "Skyway; capacidad de una salida 5 000 → 10 000 personas.")
    names = ["Base", "Alerta temprana", "Skyway cerrado", "Capacidad ×2"]
    entries = [bundle.summary["scenarios"][key]["fraction_safe_before_fire"]
               for key in SCENARIOS]
    means = [entry["mean"] * 100 for entry in entries]
    errors = [(entry["ci95"][1] - entry["mean"]) * 100 for entry in entries]
    fig = go.Figure(go.Bar(x=names, y=means,
                           marker_color=["#475569", "#0f766e", "#b45309", "#6d28d9"],
                           error_y=dict(type="data", array=errors, visible=True),
                           text=[f"{v:.1f}%" for v in means], textposition="outside"))
    fig.update_layout(height=390, yaxis_title="% de población segura antes del fuego",
                      yaxis_range=[0, max(60, max(means) + 12)],
                      margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch")
    st.caption("Barras: media de 30 corridas por escenario; líneas: IC del 95 % entre "
               "réplicas con parámetros fijos. La mayor capacidad de una salida produjo "
               "un resultado inferior al base en este modelo; su mecanismo no se aisló.")
    if st.checkbox("Mostrar matriz de las 30 réplicas (opcional)"):
        st.write("Cada fila comparte fuego y preparación entre los cuatro escenarios; "
                 "solo cambia la intervención. Color = porcentaje seguro antes del fuego.")
        matrix = bundle.replicas.pivot(index="replica", columns="scenario",
                                       values="fraction_safe_before_fire").loc[:, list(SCENARIOS)]
        heat = go.Figure(go.Heatmap(z=matrix.to_numpy() * 100, x=names,
                                    y=[f"{i:02d} · fuego {int(bundle.fire_seeds[i])} · "
                                       f"prep {bundle.config['preparation_seed_start'] + i}"
                                       for i in matrix.index], colorscale="YlGnBu",
                                    colorbar=dict(title="% seguro")))
        heat.update_layout(height=580, xaxis_title="Escenario",
                           yaxis_title="Par de semillas", margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(heat, width="stretch")
        st.caption("La ficha del grupo procede de una réplica ilustrativa separada. "
                   "Las barras y esta matriz proceden de las 120 corridas finales. "
                   "Estos grupos no son hogares históricos ni agentes con decisiones autónomas.")
    _source("scripts/evacuacion/experimentos.py · config/escenarios_evacuacion.json · "
            "salidas/evacuacion_final/replicas.csv · salidas/demo_proceso.json")
