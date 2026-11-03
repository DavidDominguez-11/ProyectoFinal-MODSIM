# Demo visual en Streamlit (rama `test`)

Interfaz para ver el incendio, los recorridos de evacuación y la comparación de escenarios. No modifica el motor ni los resultados versionados.

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-demo.txt   # Windows
.venv/Scripts/python scripts/evacuacion/red_vial.py --download                        # genera data/procesado/red_vial.json
.venv/Scripts/python scripts/demo/precomputar.py --scenario all --replica 0           # ~10-15 min y ~12 GB de RAM por escenario
.venv/Scripts/python -m streamlit run scripts/demo/app.py
```

`precomputar.py` ejecuta el motor con `retain_details=True` (todas las trayectorias) y guarda `salidas/demo/<escenario>_r<n>.npz` (~190 MB cada uno, ignorado por Git). Correr los escenarios uno a uno si la RAM es limitada.

Vistas: simulación animada (fuego + grupos por estado), rutas de grupos concretos y mapa de congestión, incendio solo (30 réplicas, probabilidad de quema, observaciones NIST), comparación de escenarios (120 corridas versionadas) y resumen de supuestos.

Los parámetros de evacuación son hipotéticos; el demo no valida el modelo contra datos históricos.

## Secciones por concepto de la materia

La barra lateral separa cuatro conceptos, cada uno con su color y un banner que explica qué es y en qué archivo del proyecto está:

| Color | Concepto | Subvistas |
|---|---|---|
| Verde | Grillas, autómatas y SIG | capas ráster + vectorial; vecindad de Moore con la fórmula real; autómata en vivo sobre terreno real |
| Azul | Redes: grafo vial dirigido | estructura (nodos, aristas, sentido); componentes y destinos; selección de rutas con Dijkstra y cierres |
| Naranja | DES: entidades, recursos y colas | anatomía; agenda de eventos ordenada; saturación de aristas; colas y espera |
| Morado | Agentes y corridas múltiples | atributos de los grupos; Monte Carlo pareado; variabilidad del fuego |

Enlaces directos: `?p=<vista>&sub=<subvista>` (desde 0), por ejemplo `http://localhost:8501/?p=1&sub=2`.
