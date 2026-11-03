# Demo en vivo (Streamlit, rama `test`)

Tres secciones, una por concepto de la materia, cada una con su color. No modifica el motor ni los resultados versionados.

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-demo.txt   # Windows
.venv/Scripts/python scripts/evacuacion/red_vial.py --download                        # genera data/procesado/red_vial.json
.venv/Scripts/python scripts/demo/precomputar.py --scenario base --replica 0           # ~10-15 min y ~12 GB de RAM
.venv/Scripts/python -m streamlit run scripts/demo/app.py
```

`precomputar.py` ejecuta el motor con `retain_details=True` y guarda `salidas/demo/<escenario>_r<n>.npz` (~190 MB, ignorado por Git). La sección 3 usa esa corrida (agentes); además su vista Monte Carlo usa los 120 resultados versionados en `salidas/evacuacion_final/`.

| Color | Concepto | Subvistas |
|---|---|---|
| Verde | 1 · Grillas, autómatas y SIG | capas ráster + vectorial; vecindad de Moore con la fórmula real; autómata en vivo |
| Azul | 2 · Redes: grafo vial dirigido | estructura y sentido de las aristas; componentes y destinos; rutas con Dijkstra y cierres |
| Morado | 3 · Agentes y corridas múltiples | atributos de los grupos; Monte Carlo pareado; variabilidad del fuego |

Enlaces directos: `?p=<sección 0-2>&sub=<subvista 0-2>`, por ejemplo `http://localhost:8501/?p=1&sub=2`.

## Verificaciones hechas

- **Vecindad de Moore:** la probabilidad que muestra el demo coincide, en las 8 direcciones, con la frecuencia observada al simular el modelo real (3 000 semillas por dirección, dentro del IC 95 %).
- **Rutas:** la distancia a la salida del árbol de Dijkstra coincide con un Dijkstra hacia adelante independiente (8 orígenes al azar).

Los parámetros de evacuación (alertas, capacidades, velocidades) son supuestos hipotéticos; el demo no valida el modelo contra datos históricos.
