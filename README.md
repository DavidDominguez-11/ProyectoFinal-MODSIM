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

**Parte 2 completada en implementación y experimentos comparativos:** terminaron las 120 corridas (30 por cada uno de cuatro escenarios, 30 fuegos distintos por escenario y preparación pareada), con cuatro procesos y horizonte de 480 min. Se conservaron 50314 grupos / 42388.94983696542 personas ponderadas. La producción terminó con código 0 y `FULL_PARALLEL_120_REPLICA_CHECK_PASS` en **17849.23 s (4 h 57 min 29 s)**. La suite de **63 pruebas**, la verificación independiente de código/concurrencia y entorno, y las comprobaciones completas de resultados aprobaron.

El módulo de fuego tiene calibración, validación y sensibilidad documentadas; **eso no valida la evacuación**. Esta combina población residencial y carreteras reales con respuesta **hipotética**, no reconstrucción de políticas históricas ni predicción de seguridad/mortalidad. Bajo estos supuestos, la alerta temprana mejora la fracción segura antes del fuego ~3.18 puntos porcentuales; cerrar Skyway la reduce ~22.09 pp y aumentar capacidad en una salida la reduce ~1.61 pp. El mecanismo de este último efecto no se aisló: **no permite recomendar políticas ni afirmar que más capacidad siempre perjudica**. Los IC, colas, tiempos condicionales y limitaciones están en [el informe de evacuación](docs/modelo_evacuacion.md#producción-completada-resultados-para-el-informe-s27-y-s29).

Resultados compactos versionados: [replicas.csv](salidas/evacuacion_final/replicas.csv), [summary.json](salidas/evacuacion_final/summary.json), [métricas](salidas/evacuacion_final/metrics.png), [CDF condicional](salidas/evacuacion_final/cdf.png) y [colas](salidas/evacuacion_final/queues.png). Están listos para integrar en la **Parte 3**, aún pendiente: evidencia histórica de avisos/cierres/refugios, informe PDF, registro de IA, diapositivas y video. Los documentos del avance parcial conservan el estado de aquella entrega; no describen el estado actual.

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
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/evacuacion/experimentos.py --smoke --replicas 2 --scenario base --workers 2 --output salidas/evacuacion_smoke_parallel2_reproduccion
# Solo después de medir RAM/rendimiento y verificar equivalencia:
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/evacuacion/experimentos.py --replicas 30 --workers 2 --output salidas/evacuacion_reproduccion
```

`--workers N` admite únicamente enteros 1..4 (predeterminado 1, secuencial). Con N>1 usa procesos `spawn`, no threads: la invocación del script es segura; quien importe `run_experiments(..., workers=N)` debe llamarlo bajo `if __name__ == '__main__':` desde un módulo importable, no desde un notebook/REPL. Cada proceso recibe las entradas validadas una vez y conserva su propia memoria; no elegir automáticamente los 15 núcleos. La ruta rápida muestra dos workers; cuatro también están soportados y se usaron en producción tras medir. En el equipo de **24 GiB**, el ensayo de dos procesos reportó 2180825088 bytes de RSS máximo: se presupuestó conservadoramente `4 × 2180825088 = 8723300352 bytes` más padre y reserva. El benchmark compacto secuencial midió 1229602816 bytes (~1.23 GB) con igualdad exacta frente al modo completo; la réplica real r0 paralela también coincidió. En producción, `/usr/bin/time -l` reportó 5048844288 bytes de RSS máximo, **no la suma de todos los procesos ni su huella conjunta**. No trasladar ese presupuesto a otra máquina sin medir. Las variables de la orden limitan BLAS/OMP sin cambiar el entorno global ni agregar dependencias.

Cada réplica r usa RNG local PCG64 con semilla `2000+r` y fuego `[r]`; los escenarios regeneran la misma preparación independientemente del proceso/orden de llegada. Solo el padre escribe CSV/JSON/figuras, en orden réplica–escenario, con hasta `2*N` trabajos pendientes. Ante error/Ctrl-C cancela pendientes y espera los activos para no dejar hijos huérfanos; puede demorar en salir. Los productos numéricos no dependen de N; solo `metadata.worker_count` cambia. `salidas/evacuacion` contiene parciales del lote secuencial detenido; `salidas/evacuacion_final` contiene la producción completada: **no borrar ni sobrescribir ninguno**. Reproducir siempre en un directorio nuevo o vacío, como los de las órdenes anteriores.

La descarga corresponde a TIGER/Line 2018 de Butte County. El resto de las entradas de fuego y población ya está versionado. La ejecución completa produce 30 réplicas pareadas por cada uno de cuatro escenarios (120 corridas), con semillas, métricas, IC y figuras. Usá un directorio de salida nuevo o vacío; el programa rechaza sobrescribir evidencia existente. Para probar rendimiento sin resultados finales, agregá `--smoke --replicas 1 --scenario base --output salidas/evacuacion_smoke_reproduccion` en lugar de los argumentos de la corrida completa.

`data/procesado/red_vial.json`, las pruebas smoke y las trayectorias/distribuciones voluminosas se regeneran y no se versionan. En particular, `distribution.csv` (~156 MB) y el ejemplo acotado (~200 KB) están ignorados por Git: no depender de ellos como archivos persistentes del repositorio. `replicas.csv`, `summary.json` y las tres figuras finales son los productos compactos versionados. Consultá [modelo_evacuacion.md](docs/modelo_evacuacion.md) para todas las opciones CLI (`--help`), arquitectura, restricciones de spawn/cancelación de Python 3.12 y resultados con IC.
