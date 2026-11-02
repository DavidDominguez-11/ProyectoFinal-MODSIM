# ProyectoFinal-MODSIM

Proyecto final de Modelación y Simulación: simulación híbrida de propagación de incendios forestales y evacuación.

## Documentos

- [Avance parcial y plan técnico](docs/avance_parcial.md)
- [Auditoría de datos y resultados reproducibles](docs/auditoria_datos.md)
- [Cronología inicial de avisos con fuentes NIST](docs/cronologia_base.md)
- [Prototipo ejecutable y resultados sintéticos](docs/prototipo_avance.md)
- [Módulo de fuego: datos, modelo, calibración y validación](docs/modelo_fuego.md)
- [Pendientes del equipo: qué le toca a cada quien](docs/pendientes_equipo.md)
- [Instrucciones del proyecto](docs/proyecto_final_modelacionysimulacion.md)
- [Indicaciones de Canvas](docs/proyecto.md)
- [Evidencia de aprobación](docs/aprobacion.pdf)

## Estado

El módulo de fuego tiene calibración, validación y sensibilidad documentadas. La evacuación integra población residencial y carreteras reales con parámetros de respuesta **hipotéticos**; no es una reconstrucción histórica ni una predicción de seguridad. Las pruebas automáticas pasan; la medición geográfica y los experimentos están en ejecución. Los documentos del avance parcial conservan el estado de aquella entrega.

- [Evacuación: modelo, supuestos, métricas y escenarios](docs/modelo_evacuacion.md)
- [Construcción y auditoría de la red vial](docs/red_vial.md)
- [Motor de evacuación por eventos](docs/motor_evacuacion.md)
- [Entorno reproducible](docs/entorno_evacuacion.md)

## Reproducir evacuación

Desde la raíz del repositorio, con Python 3.12 y uv:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-evacuacion.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/evacuacion/red_vial.py --download
.venv/bin/python scripts/evacuacion/experimentos.py --replicas 30 --output salidas/evacuacion
```

La descarga corresponde a TIGER/Line 2018 de Butte County. El resto de las entradas de fuego y población ya está versionado. La ejecución completa produce 30 réplicas pareadas por cada uno de cuatro escenarios (120 corridas), con semillas, métricas, IC y figuras. Usá un directorio de salida nuevo o vacío; el programa rechaza sobrescribir evidencia existente. Para probar rendimiento sin resultados finales, agregá `--smoke --replicas 1 --scenario base --output salidas/evacuacion_smoke_base` en lugar de los argumentos de la corrida completa.

`data/procesado/red_vial.json`, las pruebas smoke y las trayectorias/distribuciones voluminosas se regeneran y no se versionan. `replicas.csv`, `summary.json` y las tres figuras de la corrida final son los productos compactos de resultados. Los avisos zonales, refugios y cierres históricos de la Parte 3 y los entregables finales siguen pendientes.
