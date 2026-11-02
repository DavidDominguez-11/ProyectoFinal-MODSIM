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

El módulo de fuego tiene calibración, validación y sensibilidad documentadas. La evacuación integra población residencial y carreteras reales con parámetros de respuesta **hipotéticos**; no es una reconstrucción histórica ni una predicción de seguridad. Las pruebas automáticas y una réplica geográfica completa pasan; el lote de 120 experimentos se detuvo por exceder el tiempo disponible y sigue pendiente. La prueba real tardó unos 7 min 15 s y llegó a 7,8 GB de RSS: reservá tiempo y memoria, y no confundas una prueba `--smoke` con resultados finales. El benchmark compacto terminó con equivalencia exacta frente al modo completo: 377,38 s y 1,23 GB de RSS máximo. La prueba real paralela sigue pendiente; todavía no se ha medido su aceleración ni confirmado RAM para cuatro procesos. Los documentos del avance parcial conservan el estado de aquella entrega.

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
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/evacuacion/experimentos.py --smoke --replicas 2 --scenario base --workers 2 --output salidas/evacuacion_smoke_parallel2
# Solo después de medir RAM/rendimiento y verificar equivalencia:
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/evacuacion/experimentos.py --replicas 30 --workers 2 --output salidas/evacuacion_final
```

`--workers N` admite únicamente enteros 1..4 (predeterminado 1, secuencial). Con N>1 usa procesos `spawn`, no threads: la invocación del script es segura; quien importe `run_experiments(..., workers=N)` debe llamarlo bajo `if __name__ == '__main__':` desde un módulo importable, no desde un notebook/REPL. Cada proceso recibe las entradas validadas una vez y conserva su propia memoria; no elegir automáticamente los 15 núcleos ni usar 4 hasta medir RAM. Las variables de la orden limitan BLAS/OMP sin cambiar el entorno global ni agregar dependencias.

Cada réplica r usa RNG local PCG64 con semilla `2000+r` y fuego `[r]`; los escenarios regeneran la misma preparación independientemente del proceso/orden de llegada. Solo el padre escribe CSV/JSON/figuras, en orden réplica–escenario, con hasta `2*N` trabajos pendientes. Ante error/Ctrl-C cancela pendientes y espera los activos para no dejar hijos huérfanos; puede demorar en salir. Los productos numéricos no dependen de N; solo `metadata.worker_count` cambia. `salidas/evacuacion` contiene parciales detenidos: **no borrar ni sobrescribir**; la nueva corrida final usa `salidas/evacuacion_final`.

La descarga corresponde a TIGER/Line 2018 de Butte County. El resto de las entradas de fuego y población ya está versionado. La ejecución completa produce 30 réplicas pareadas por cada uno de cuatro escenarios (120 corridas), con semillas, métricas, IC y figuras. Usá un directorio de salida nuevo o vacío; el programa rechaza sobrescribir evidencia existente. Para probar rendimiento sin resultados finales, agregá `--smoke --replicas 1 --scenario base --output salidas/evacuacion_smoke_base` en lugar de los argumentos de la corrida completa.

`data/procesado/red_vial.json`, las pruebas smoke y las trayectorias/distribuciones voluminosas se regeneran y no se versionan. `replicas.csv`, `summary.json` y las tres figuras de la corrida final son los productos compactos de resultados. Los avisos zonales, refugios y cierres históricos de la Parte 3 y los entregables finales siguen pendientes.
