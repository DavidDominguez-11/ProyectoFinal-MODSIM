# Entorno reproducible de evacuación

La Parte 2 usa Python 3.12 y `requirements-evacuacion.txt`, que congela el entorno realmente instalado. No modifica las dependencias ni las salidas del módulo de fuego.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-evacuacion.txt
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
```

Si no usás uv, creá el entorno con `python3.12 -m venv .venv` e instalá con `.venv/bin/python -m pip install -r requirements-evacuacion.txt`.

El Python del sistema puede carecer de NumPy; eso impide importar las pruebas de fuego. El entorno virtual resuelve esa dependencia sin instalar paquetes globalmente. `.venv/` y `.cache/` no se versionan. Las versiones congeladas registran el entorno de esta ejecución, no validan por sí mismas el modelo científico.
