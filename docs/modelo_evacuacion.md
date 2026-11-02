# Evacuación reproducible y comparación de escenarios

`scripts/evacuacion/experimentos.py` integra la población residencial, las réplicas de fuego y la red vial dirigida con el motor por eventos existente. Exporta métricas por réplica, intervalos de confianza y gráficas sin descargar datos. **Los parámetros son hipotéticos y reemplazables: no constituyen reconstrucción histórica, predicción de seguridad ni mortalidad.** Los resultados geográficos de producción deben generarse y revisarse antes de redactar conclusiones numéricas.

## Ejecución desde la raíz

Primero medir una sola corrida real; luego comparar las 120 corridas. Usar directorios nuevos o vacíos para no mezclar evidencia:

```sh
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR="$PWD/.cache/matplotlib" .venv/bin/python scripts/evacuacion/experimentos.py --smoke --replicas 1 --scenario base --output salidas/evacuacion_smoke_compact
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR="$PWD/.cache/matplotlib" .venv/bin/python scripts/evacuacion/experimentos.py --replicas 30 --output salidas/evacuacion
```

Para comprobar los cuatro escenarios con una réplica: `--smoke --replicas 1`, sin `--scenario`. El programa imprime con `flush` las fases `preflight start/done`, `simulate start/done` (fin con tiempo de pared antes de distribución/exportación), `distribution done`, `example done`, `plots start/done` y `experiment complete`. Durante la simulación, el callback opcional `simulate(..., progress=callable)` informa tiempo modelado, horizonte, lotes procesados y personas seguras/restantes al inicio, cada ≥30 minutos modelados y al horizonte. El runner añade tiempo de pared solo a stdout; no lanza procesos secundarios. Un lote costoso puede demorar el siguiente aviso: estos mensajes prueban avance observado, no garantizan un latido cada cierto segundo. Una interrupción puede dejar resultados parciales: no reutilizar ese directorio como corrida final. La existencia de `summary.json` por sí sola no garantiza que todas las figuras hayan terminado: comprobar también el código de salida.

| Opción | Predeterminado / significado |
|---|---|
| `--network` | `data/procesado/red_vial.json`, contrato público de `build_network` |
| `--grid` | `data/procesado/grilla_fuego.npz`, campo `poblacion` |
| `--fire` | `salidas/fuego/llegada_replicas.npz`, `llegada_min` y `semillas` |
| `--contract` | `salidas/fuego/contrato.json`, forma, transformación, CRS y horizonte |
| `--config` | `config/escenarios_evacuacion.json`, todos los supuestos reemplazables |
| `--output` | `salidas/evacuacion`, directorio nuevo o vacío |
| `--replicas` | 30 por escenario; no puede exceder las réplicas de fuego disponibles |
| `--smoke` | Permite menos de 30; **siempre** etiqueta salidas como provisionales, incluso con 30 |
| `--scenario` | `base`, `early_alert`, `skyway_closed` o `exit_capacity`; sin opción corre los cuatro |
| `--help` | Ayuda completa, sin leer datos ni crear salidas |

Las rutas predeterminadas son relativas a la raíz del proyecto, independientemente del directorio actual. Las rutas explícitas son relativas al directorio actual. El preflight valida archivos completos, forma, masa, fuego, semillas únicas, parámetros, geometría y contrato vial antes de crear el directorio de salida. Una entrada rechazada no crea archivos ni incrementa contadores. El adaptador no descarga, recorta ni muestrea población.

## Solución: población y fuego sin pérdida de masa

1. Convertir `poblacion` a float64 y sumar con `math.fsum`. Cada celda positiva produce grupos de hasta 3 personas ponderadas y un grupo adicional por **todo resto positivo**, incluso minúsculo. Se conserva `origin_cell`; no se fuerza un censo entero.
2. Transformar centros de celda con los seis coeficientes GDAL, incluida rotación. Asignar el nodo euclídeo más cercano con `scipy.spatial.cKDTree`, desempate por distancia y luego identificador lexicográfico. Conservar todos los nodos y componentes: ninguna población desconectada se elimina.
3. Invertir `contract.transform_gdal` para agregar `node.cell` a **cada** nodo y copiar la transformación a `metadata.transform_gdal`. Se usa `floor` y se sujeta un nodo exactamente sobre el límite exterior a la celda interior adyacente. La tolerancia de inversión es 1e-8 celdas, no un permiso para admitir nodos externos. En líneas interiores corresponde la celda determinada por `floor`; las aristas conservan sus celdas conservadoras del constructor vial.
4. Generar preparación con un RNG local NumPy `default_rng`/PCG64. `preparation_min ~ gamma(shape=2, scale=10 min)`; alerta base uniforme a 85 min desde las 06:25. Los grupos conservan `alert_min`, `preparation_min` y `ready_min = alert_min + preparation_min` por separado.
5. La réplica `r` toma directamente `llegada_min[r]`, su `semillas[r]` y preparación `2000+r`. Nunca usa la mediana ni repite un índice de fuego dentro de un escenario. Comparte grupos, preparación y fuego entre escenarios; no reinicia un generador global.

**Limitaciones explícitas:** la población representa residencia estimada, no presencia durante el incendio; la gamma solo expresa preparación positiva/asimétrica, sin ajuste histórico. El salto celda–nodo es instantáneo: no consume tiempo ni modela exposición durante el acceso, aunque el motor sí comprueba fuego en el origen antes de salir. Un resto fraccionario consume una plaza vial completa. La discretización no equivale a hogares observados. Alertas zonales, cierres históricos y refugios reales siguen pendientes de Parte 3.

`attachment` informa masa original y de grupos, cantidad de grupos/celdas positivas, número de celdas de origen sin salida (`no_exit_origins`), personas y fracción sin salida, nodos sin salida y distancias de acceso mínima/máxima/media/p50/p90 por origen, además de media ponderada por personas. La conectividad se calcula por alcanzabilidad dirigida inversa hacia destinos seguros, antes de cierres, fuego y agotamiento de capacidad; no se confunde fracción de nodos con fracción poblacional.

## Escenarios de un solo factor

| Escenario | Único cambio respecto de base |
|---|---|
| `base` | Ninguno: **todas** las salidas seguras reciben 5000 personas de capacidad, sustituyendo los 100000 genéricos del grafo |
| `early_alert` | Alerta 30 min antes, a 55 min; idéntica preparación |
| `skyway_closed` | Cierre desde t=0 de todas las aristas con la palabra completa Skyway en su nombre, ambas direcciones |
| `exit_capacity` | Una sola salida pasa de 5000 a 10000 personas; las restantes quedan en 5000 |

`capacity_target_node: null` elige el identificador de salida segura lexicográficamente menor; se puede reemplazar por un nodo explícito válido. El nodo objetivo, número de aristas Skyway y cantidad efectivamente cerrada se registran en cada corrida. No cambian capacidades viales, velocidades, grupos ni fuego entre escenarios. La selección por nombre no cierra Clark/Pentz/Neal incidentalmente. No se inventa contraflujo. Los valores y la justificación/advertencias están en el JSON de configuración, no ocultos en datos supuestamente históricos.

## Arquitectura y API

El integrador importa únicamente `motor.simulate` como contrato público del motor. Lee el JSON generado por `red_vial.build_network` sin alterar ese constructor ni duplicar enrutamiento, colas, reservas, cierres o exposición. El motor valida la red durante el preflight mediante una llamada pública sin grupos, sin fuego observado y horizonte cero. Las corridas usan `simulate(..., retain_details=False)` sin opción CLI nueva: solo limita la retención de detalles, no la simulación. La API del motor conserva el modo completo por defecto.

| Callable | Resultado / responsabilidad |
|---|---|
| `prepare_network(network, contract)` | Copia completa con celdas de nodos y transformación |
| `make_groups(population, network, contract, config, seed)` | `(groups, attachment)`; pesos, preparación y asignación deterministas |
| `scenario_inputs(network, groups, config, scenario)` | `(network_copy, groups_copy, closed_edges, intervention)` |
| `load_inputs(paths, replicas, smoke)` | Preflight sin escrituras; retorna entradas, resumen de acceso y hashes |
| `evacuation_statistics(arrivals)` | Media y percentiles ponderados, conteo de grupos y masa segura |
| `queue_duration(history)` | Compatibilidad con historias públicas completas anteriores; nunca integrar muestras compactas |
| `confidence_interval(values)` | `{n, mean, ci95}`; excluye `None`; IC nulo cuando n<2 |
| `summarize_replica(result)` | Métricas compactas y comprobaciones de invariantes del motor |
| `run_experiments(paths, replicas=30, smoke=False, scenarios=None)` | Ejecuta secuencialmente, escribe productos y retorna resumen |
| `main(argv=None)` | CLI; entradas inválidas terminan con código no cero |

`paths` contiene las claves de ruta de la tabla CLI, incluido `output`. No se modifican las entradas. Véanse [motor_evacuacion.md](motor_evacuacion.md) y [red_vial.md](red_vial.md) para unidades e invariantes completos.

## Resultados y esquema de productos

| Producto | Contenido |
|---|---|
| `replicas.csv` | Una fila por escenario/réplica, semillas/índices, intervención, clasificación y métricas |
| `summary.json` | `metadata`, `scenarios[escenario][métrica] = {n, mean, ci95}` y `paired_differences_vs_base` |
| `distribution.csv` | Llegadas seguras exactas por escenario/réplica: tiempo, personas, masa acumulada y CDF condicional; no redondea pesos |
| `example_replica.json` | Primera corrida: ejemplo representativo acotado, métricas escalares exactas y conteos completos; **no** trayectoria completa |
| `cdf.png` | CDF ponderada de llegadas seguras agrupadas por masa de las réplicas, intervalos uniformes configurables (`distribution_bins=480`); el CSV conserva tiempos exactos |
| `metrics.png` | Fracción segura antes del fuego y exposición: media e IC t 95% |
| `queues.png` | Integrales, máximos y duración de colas, más tiempo medio de llegada segura: medias e IC t 95% |

El ejemplo usa `schema: evacuation_representative_example`, `version: 1`, `representative: true`, descripción y metadatos `run`. `metrics` conserva todas las métricas de la corrida completa. `result` conserva los escalares del motor (incluidos invariantes), pero solo los primeros 100 `groups` y `traversals`; `input_groups` contiene los primeros 100 grupos de entrada. `history` contiene como máximo 481 muestras: el primer evento real de cada franja de 1/480 del horizonte, más el horizonte, incluidos cero y horizonte sin duplicados. Son detalles representativos, no interpolación ni fuente de métricas. La proyección de un resultado público completo conserva el criterio anterior de índices uniformemente espaciados (`floor(i*(N-1)/(K-1))`).

`record_counts`, `exported_counts`, `truncated` y `selection` explicitan para cada colección su tamaño original exacto, exportado, truncamiento y criterio. En modo compacto los conteos de historia y travesías provienen de contadores de todos los lotes/inicios, no de la longitud retenida. `evacuation_times`, `edge_max_occupancy` y `destination_people` se omiten completamente del ejemplo: solo sus conteos y los totales/invariantes escalares permanecen. Las llegadas exactas siguen en `distribution.csv`. Ningún muestreo ilustrativo altera población, dinámica, estadísticas o productos exactos; la cantidad exportada no crece con eventos, grupos, tramos o travesías.

Métricas por réplica:

- `people_total`, `people_safe`, `people_safe_before_fire`, `people_exposed`, `people_temporary`, `people_remaining`: personas ponderadas. Exposición es un subconjunto transversal, no una categoría adicional de conservación.
- `fraction_safe_before_fire`: denominador toda la masa inicial, incluidos orígenes desconectados.
- `queue_group_minutes`, `queue_person_minutes`: integrales del motor (grupos·min y personas·min), no suma de eventos. `max_queue_groups`, `max_queue_people`: máximos simultáneos. `queue_duration_min`: integral exacta en línea del indicador de cola no vacía antes de cada lote real; incluye espera sin ruta y excluye preparación/tránsito. `summarize_replica` usa este escalar autoritativo, nunca la historia ilustrativa; solo acepta historia completa como compatibilidad para resultados antiguos sin el escalar.
- `evacuation_mean_min`, `evacuation_p50_min`, `evacuation_p90_min`: distribución ponderada **condicional a llegadas seguras**, minutos desde ignición. Percentil por inversa de CDF discreta (primer tiempo con peso acumulado suficiente). `safe_arrival_count` cuenta grupos y `safe_arrival_people` su masa. Sin llegadas, los tres tiempos son `null`, nunca cero.

Cada IC usa estadísticas de réplicas independientes, error estándar muestral y cuantil Student-t bilateral 95% con n−1 grados de libertad. No se tratan hogares como réplicas independientes. Las diferencias pareadas se calculan alternativa menos base, por el mismo índice de fuego/preparación; valores nulos se excluyen por pareja. Se informa n efectivo por métrica. Una sola réplica tiene media pero no IC. El IC no se recorta artificialmente a [0,1]. La CDF agrupada pondera personas seguras, no sustituye el promedio por réplica ni su IC.

`metadata` guarda SHA256 de los cinco archivos de entrada, configuración completa y supuestos, contrato, versiones/RNG, semillas por corrida, clasificación provisional, unidades, método estadístico e información de acceso. JSON se escribe con `allow_nan=False`; no incluye NaN/Infinity. No se usan tiempos de ejecución en productos deterministas; se imprimen en stdout.

## Escala, evidencia y límites de resultados

El grafo disponible al integrar tiene 31670 nodos, 64098 aristas dirigidas, seis salidas y 18 componentes; 935 nodos no tienen salida. La grilla es 205×278 con 40542 celdas positivas; el archivo contiene 30 fuegos con semillas 1000–1029. Estas dimensiones son evidencia de entradas, **no resultados de las 120 corridas**. Los totales precisos de habitantes y su inaccesibilidad se calculan desde los archivos y se publican en cada ejecución, no se copian de resúmenes redondeados.

Se retiene una sola salida compacta del motor en memoria por vez y un solo ejemplo representativo acotado en disco. Las llegadas exactas se transmiten a CSV por réplica; entre corridas solo quedan estadísticas escalares y histogramas gráficos acotados. Dentro de una corrida se retienen hasta 481 muestras de historia, primeras 100 travesías y registros activos hasta terminar, sin colecciones ocultas de detalles completados. Se conservan todos los estados finales, llegadas ponderadas y mapas de máximos/destinos. Los invariantes cubren **cada** travesía real, no solo la muestra. `metadata.detail_recording` documenta estos límites de registro; no describe cambios del modelo. El CSV de distribución puede ser grande; el ejemplo no exporta historias ni trayectorias completas. Ninguno es necesario para volver a calcular las medias/IC desde `replicas.csv`. La CDF gráfica agrupa tiempos en intervalos, pero conserva pesos; esto es una resolución visual, no muestreo ni aproximación de la simulación.

El motor cachea rutas multifuente, pero las reservas, cierres y cambios de destinos factibles pueden invalidar cachés. No hay garantía de tiempo/memoria del lote real hasta medirlo; no sustituir población por una muestra para esconder un problema de rendimiento. Si la prueba real es lenta, registrar el tiempo y evaluar el motor en una unidad separada, sin cambiar silenciosamente semántica.

## Comprobación geográfica preliminar

La prueba `--smoke --replicas 1 --scenario base` con exportación acotada terminó con código 0 y `REAL_SMOKE_CHECK_PASS`. Se conservaron **42388,94983696542 personas ponderadas** en **50314 grupos**, sin violaciones de capacidad ni tránsito por vías cerradas; se generaron las tres figuras. De esa población, 94,98908536263116 personas (0,224089 %) quedan asignadas a componentes sin salida antes de considerar el fuego. No se eliminaron de los denominadores.

La corrida anterior, con retención completa dentro del motor, tardó 434,51 s (aproximadamente 7 min 15 s); la simulación consumió 419,67 s. `/usr/bin/time -l` registró 7795638272 bytes de RSS máximo y 13745613048 bytes de huella máxima de memoria en macOS. El ejemplo representativo ocupó 214095 bytes y todos los productos de esta prueba, 1684830 bytes. La exportación anterior sin límites se interrumpió por crecimiento excesivo; el archivo parcial de 9,84 GB se eliminó con autorización. Las métricas de la nueva corrida coinciden con la fila provisional anterior.

El modo compacto todavía necesita una nueva medición real en un directorio nuevo (`salidas/evacuacion_smoke_compact`). La reducción de detalles retenidos no garantiza un tiempo objetivo ni convierte la prueba anterior en evidencia del nuevo rendimiento.

**Esto verifica una sola réplica; no sustituye las 30 por escenario ni permite concluir cuál intervención es mejor.** El lote completo de 120 corridas se detuvo por exceder el tiempo disponible; conserva resultados parciales, pero no cumple todavía las 30 réplicas por escenario. Una extrapolación de la base da unas 14–15 horas; los otros escenarios pueden costar distinto. No paralelizar sin evaluar primero la memoria disponible. Los resultados finales y sus IC quedan pendientes del código de salida y de la revisión del lote completo.

## Verificación automatizada

```sh
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR="$PWD/.cache/matplotlib" .venv/bin/python -m unittest discover -s tests -p 'test_experimentos_evacuacion.py' -v
PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR="$PWD/.cache/matplotlib" .venv/bin/python -m unittest discover -s tests -v
```

Las pruebas usan NPZ y grafos sintéticos pequeños, incluida CLI en directorios temporales aislados: masa/restos minúsculos, conectividad, celdas de borde/rotación y empates, alertas/preparación separadas, un solo factor, dos sentidos de Skyway, elección de una única salida, repetibilidad, semillas/fuegos distintos y pareados, Student-t, tiempos nulos, integrales de cola, invariantes del motor, rechazos sin escrituras, smoke, selección, esquema, distribución y figuras. Una prueba de 30 réplicas **sintéticas** verifica el contrato Monte Carlo sin ejecutar el lote geográfico. Cobertura de integración: S2.2 y S2.5–S2.9; S2.3–S2.4 se reutilizan del motor.

**Risk:** integración de gran escala, distribución de preparación y acceso instantáneo sin calibración histórica; rendimiento real pendiente y revisión independiente requerida antes de interpretar escenarios.
