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
