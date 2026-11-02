# Evacuación y experimentos Camp Fire
Objective: complete Part 2; direct local commits to main per explicit user choice, no push or PR.
Delivery: separate reviewable work units (~1,600–2,200 authored lines forecast); Python unittest in .venv.

## Specs
S1. User authorization: "dale siguele"; scope confirmed: "Sí, completar evacuación y experimentos".
S2. Selected scope (verbatim existing team specification):

**Objetivo:** simular cómo evacúan las personas por las carreteras mientras avanza el fuego, y comparar escenarios.

### Tareas

1. **Red vial.**
   - Convertir las carreteras TIGER/Line 2018 de Butte County en un grafo dirigido. El enlace ya está en [scripts/auditar_geografia.py](../scripts/auditar_geografia.py).
   - Recortarlo al dominio: UTM 10N, límites en [config/dominio.json](../config/dominio.json).
   - Comprobar que la red esté conectada y definir las salidas del dominio. Las principales son Skyway hacia Chico, Clark Rd, Pentz Rd y Neal Rd.
   - Asignar a cada tramo largo, velocidad y capacidad. Si no hay dato documentado, usar un supuesto explícito y decir de dónde sale.
2. **Grupos de evacuados.**
   - Crearlos a partir de la población por celda. Cada agente representa un hogar o grupo con un peso en personas.
   - Darles un retraso de salida aleatorio, con su distribución justificada.
   - La población debe conservarse en todo momento.
3. **Simulación de evacuación por eventos.**
   - Alerta, preparación, salida, avance por tramos con colas cuando se llena la capacidad, cambio de ruta ante cierres, y llegada a destino.
   - Distinguir **refugio temporal** de **destino seguro**.
4. **Acople con el fuego.**
   - Un tramo o celda está en peligro en el minuto *t* si `0 <= llegada_min[r, fila, col] <= t` (ver [contrato.json](../salidas/fuego/contrato.json)).
   - Cerrar los tramos alcanzados por el fuego y registrar la exposición potencial de los agentes.
5. **Monte Carlo.**
   - Al menos 30 réplicas por escenario, con semillas registradas.
   - **Cada réplica de evacuación debe usar una réplica de fuego distinta** (hay 30 en `llegada_replicas.npz`), no solo la mediana.
6. **Escenarios.** Como mínimo:
   - base;
   - alerta más temprana (por ejemplo, 30 min antes);
   - cierre o apertura de una ruta;
   - más capacidad en un destino.

   Cambiar **un solo factor** a la vez respecto de la base.
7. **Métricas y gráficas.** Para cada escenario, con intervalos de confianza:
   - fracción de personas que llega a un destino seguro antes del fuego;
   - distribución del tiempo de evacuación;
   - personas con exposición potencial;
   - longitud y duración de las colas.
8. **Pruebas automáticas** en `tests/`:
   - se conserva la población;
   - ningún tramo supera su capacidad;
   - nadie transita por un tramo cerrado;
   - los resultados se repiten con la misma semilla.
9. **Redacción.** Escribir para el informe las secciones de solución, arquitectura y resultados de su parte, con un documento parecido a [modelo_fuego.md](modelo_fuego.md).

### Qué necesita de la Parte 3

Una tabla de parámetros con su fuente: horas de aviso por zona, cierres de vías con hora, y ubicación y capacidad de refugios y albergues. Mientras llega, se puede avanzar con supuestos y reemplazarlos después.

### Base de partida

El prototipo sintético [scripts/prototipo_hibrido.py](../scripts/prototipo_hibrido.py) ya acopla una grilla de fuego, tramos con capacidad y grupos de evacuados. Sirve como esqueleto.

S3. Delivery override: "commits directos a main".

## Tasks
T1 | S1-S2 | inline | in_progress | Prepare isolated runner and freeze evacuation dependencies; commit pending.
T2 | S1-S2 | delegated parallel independent road builder and event engine | pending | Tests/docs with each unit; commits pending.
T3 | S1-S2 | inline | pending | Integrate population/fire inputs, run 30 paired replicas per scenario, export metrics/plots; commit pending.
T4 | S1-S3 | inline plus independent high-risk verifier | pending | Reproduce full suite, document results/limitations and update README/team status; commit pending.

## Log
L1. User: "dale siguele"
L2. Scope selection: "Sí, completar evacuación y experimentos"
L3. Delivery selection: "commits directos a main". Overrides default feature-branch workflow; local commits only.
L4. Baseline cd86868; clean main. Existing prototype tests pass; system Python lacks numpy. Existing fire outputs/grids are tracked. Historical evacuation evidence is Part 3 and remains unavailable; use explicitly labeled assumptions as allowed by team spec.
L5. Architecture assumptions: standalone road JSON and pure-Python discrete-event engine are independent units sharing only a documented JSON interface. Network: nodes [{id,x,y}], edges [{id,u,v,length_m,travel_min,capacity, cells:[[row,col],...]}], destinations [{node,kind:"safe"|"temporary",capacity}], metadata. Directed edges model both directions where historical direction is unavailable, explicitly hypothetical. Engine input groups [{id,people,node,ready_min,origin_cell}], fire arrival 2D lists with -1 sentinel; horizon minutes. Core callable simulate(network,groups,fire,horizon=480,closed_edges=[]) returns JSON-compatible metrics/history/trajectory summaries; no numpy/geospatial imports in core.
L6. Risk: item 5 for new isolated dependency setup; new separate modules otherwise no existing public contracts changed. Independent verification required after implementation. No historical safety predictions.
