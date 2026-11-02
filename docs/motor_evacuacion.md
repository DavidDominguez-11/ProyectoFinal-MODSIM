# Motor de evacuación por eventos

`scripts/evacuacion/motor.py` simula grupos ponderados sobre una red dirigida, sin NumPy, aleatoriedad interna ni dependencia del prototipo sintético. Conserva grupos desconectados y pesos fraccionarios. Es un modelo hipotético para comparar escenarios, **no una validación histórica ni una predicción de seguridad**.

## Uso mínimo

```python
from scripts.evacuacion.motor import simulate

network = {
    "nodes": [{"id": "a", "x": 0, "y": 0, "cell": [0, 0]},
              {"id": "b", "x": 1, "y": 0, "cell": [0, 1]}],
    "edges": [{"id": "ab", "u": "a", "v": "b", "length_m": 100,
               "travel_min": 2, "capacity": 1, "cells": [[0, 1]]}],
    "destinations": [{"node": "b", "kind": "safe", "capacity": 10.5}],
    "metadata": {},
}
groups = [{"id": "hogar-1", "people": 2.5, "node": "a",
           "ready_min": 5, "origin_cell": [0, 0]}]
result = simulate(network, groups, [[-1, -1]], horizon=480, closed_edges=[])
assert result["people_safe_before_fire"] == 2.5
```

El integrador genera `ready_min` incluyendo alerta y preparación con una semilla registrada. Para Monte Carlo debe proporcionar una réplica distinta de fuego por corrida. El motor no crea hogares ni elige distribuciones de preparación.

## Contrato de entrada

| Campo | Unidad y validación |
|---|---|
| Identificadores de nodos, tramos y grupos | Cadenas no vacías y únicas dentro de cada categoría. |
| `x`, `y` | Coordenadas finitas; `cell: [fila, columna]` es opcional. |
| `length_m`, `travel_min` | Números finitos estrictamente positivos. El tiempo es fijo, sin modelo dinámico de velocidad. |
| Capacidad vial | Entero positivo de **grupos simultáneos**, independiente del peso del grupo. |
| Capacidad de destino | Número finito no negativo de **personas**, puede ser fraccionario. Un destino por nodo. |
| `people` | Peso finito estrictamente positivo, nunca redondeado a personas enteras. |
| `ready_min`, `horizon` | Minutos finitos no negativos. Se admiten grupos listos después del horizonte. |
| `origin_cell` | Celda obligatoria del hogar; puede diferir del nodo vial asignado. |
| `fire` | Lista de listas rectangular no vacía; `-1` significa sin llegada observada, los demás valores son minutos finitos no negativos. |
| `cells` de cada tramo | Lista de celdas cubiertas; vacía significa sin fuego observado sobre el tramo. |
| `closed_edges` | Identificadores existentes cerrados desde el minuto cero; por defecto vacío (`None` internamente evita un argumento mutable). |

Las celdas explícitas deben estar dentro de la grilla. Si falta `node.cell`, se invierte la transformación afín `metadata.transform_gdal`, en orden GDAL, incluyendo rotación. Si tampoco existe transformación, o la coordenada transformada cae fuera de la grilla, ese nodo no tiene fuego observado. **El integrador debe agregar `node.cell` cuando la red no aporta transformación.** Esto no sustituye la comprobación de `origin_cell` antes de la salida.

Las entradas inválidas producen `ValueError` antes de iniciar la simulación. Ninguna entrada se modifica. No se permite capacidad infinita: incluso los destinos de salida necesitan una capacidad finita explícita.

## Progreso opcional sin alterar resultados

`simulate(network, groups, fire, horizon=480, closed_edges=None, *, progress=None, retain_details=True)` acepta un callback solo por palabra clave. Por defecto no emite avisos ni cambia el objeto de resultado. Con `progress=callable`, después del despacho y snapshot de un lote se entrega un diccionario nuevo con `time_min`, `horizon`, `event_batches`, `people_safe`, `people_temporary` y `people_remaining`. Se informa el primer lote (t=0), luego cada ≥30 minutos modelados respecto del último aviso y siempre el horizonte (incluido horizonte cero sin duplicados).

El callback no recibe referencias a grupos, rutas ni historia. No introduce RNG, eventos adicionales, relojes por evento, hilos ni dependencias. Sus excepciones se propagan; debe limitarse a observar y no modificar entradas externas. Un lote lento o un intervalo largo en tiempo de pared puede retrasar avisos: no es un temporizador de salud ni garantía de tiempo máximo entre mensajes. El runner imprime estos avisos y las fases con `flush`, añadiendo tiempo de pared solo en stdout.

## Retención opcional de detalles

La API pública conserva **por defecto** historia y travesías completas (`retain_details=True`). El runner usa `retain_details=False`: retiene las primeras 100 travesías y como máximo 481 muestras de historia, sin cambiar ningún evento, grupo, ruta, reserva, tiempo ni fuego. Guarda el primer evento real de cada franja de 1/480 del horizonte, más el horizonte; incluye cero, sin interpolar ni añadir eventos. Para horizonte 480 son franjas de un minuto. Para horizonte cero guarda una sola muestra. Las muestras conservan población y tiempos estrictamente crecientes, pero **no** sirven para integrar colas.

Ambos modos calculan `queue_duration_min` en línea: antes de cada lote real integran el indicador `queue_groups > 0` durante el intervalo transcurrido. Una suma de parciales flotantes reproduce `math.fsum` de los intervalos completos sin retenerlos. Las integrales de grupos/personas, exposición y máximos tampoco dependen del muestreo. Se comprueba cada travesía al terminar, interrumpirse o alcanzar el horizonte; los invariantes no se calculan sobre las primeras 100. Los registros activos siguen disponibles para identidad de llegadas e interrupciones y se liberan al finalizar (salvo los primeros 100 ilustrativos).

Solo el resultado compacto añade `detail_retention`: `history_records` cuenta todos los lotes de tiempo distintos que habría guardado el modo completo; `traversal_records` cuenta cada inicio, incluidas interrupciones y viajes truncados. No son longitudes de muestras. Incluye límites y criterios de selección. Los estados finales de **todos** los grupos, llegadas ponderadas completas, destinos y máximos por arista siguen disponibles en ambos modos.

El runner exporta aparte `example_replica.json`, esquema `evacuation_representative_example` versión 1: escalares/métricas exactos, conteos originales/exportados y truncamiento explícito; primeros 100 grupos de entrada/finales y travesías, historia ilustrativa. Si se proyecta un resultado completo se conserva la selección previa de hasta 481 índices uniformes, incluidos extremos. Omite mapas de ocupación/destinos y llegadas individuales (estas siguen exactas en `distribution.csv`). Véase [modelo_evacuacion.md](modelo_evacuacion.md).

## Decisiones de simulación

- Se procesan eventos con `heapq`: primero cierres, después fuego en nodos/orígenes, después llegadas y finalmente preparación. La igualdad temporal con el fuego **no** acredita una llegada segura por ese tramo.
- La ruta minimiza tiempo de viaje hacia destinos seguros alcanzables con capacidad para **todo** el grupo. Solo si no existe ruta segura se busca refugio temporal. No anticipa cierres futuros ni optimiza congestión futura.
- La capacidad de destino se reserva al entrar al primer tramo, se mantiene durante el recorrido y se convierte en ocupación al llegar. Una interrupción libera la reserva. Un lote de cierres libera las reservas de grupos en espera para permitir su redirección. Si un cierre aguas abajo vuelve inalcanzable el destino mientras el grupo ocupa otro tramo, al llegar al siguiente nodo libera la reserva y busca otra ruta.
- Si el fuego alcanza un tramo ocupado, la travesía termina inmediatamente; el grupo queda expuesto y vuelve al último nodo de salida. Si ese nodo está quemado, queda `stranded`; en caso contrario intenta otra ruta. No continúa dentro del tramo cerrado.
- La exposición potencial se acumula: origen antes de preparación, nodo mientras espera o tramo ocupado al cerrarse. Un grupo expuesto que llega luego a destino cuenta como `people_safe`, pero nunca como `people_safe_before_fire`.
- Los destinos `safe` son absorbentes: se supone que salir por ellos termina la exposición modelada. Un refugio `temporary` no es seguro; si su nodo arde, sus ocupantes quedan expuestos y varados. No se modela una segunda evacuación espontánea desde refugios.
- Las colas son FIFO por orden de incorporación y desempate por orden de grupos de entrada. Entre tramos disponibles no se impone bloqueo por una cola de otro tramo. Los tramos equivalentes se desempatan por identificador de destino y luego de tramo.
- Los grupos sin ruta permanecen `waiting`; los no preparados permanecen `preparing`. Ambos conservan su masa en `people_remaining`. El horizonte trunca viajes y colas sin inventar llegadas.

## Arquitectura y escala

Las tablas de rutas usan Dijkstra **inverso multifuente**, no una búsqueda por hogar. La caché se indexa por conjunto de destinos factibles y se invalida ante cambios de topología. Cada minuto de eventos agrupa todos los cierres simultáneos antes del despacho; el número de revisiones globales no depende del número de tramos que cierran dentro del lote.

El despacho mantiene colas bloqueadas por tramo y despierta plazas al liberarse capacidad. Un índice por peso despierta grupos cuya factibilidad cambia al reservar capacidad de destino. Los nodos mantienen residentes y las reservas mantienen sus titulares: preparación y llegadas ordinarias no recorren todos los hogares. Las muestras poblacionales usan acumuladores, no sumas completas por evento. Los cierres sí pueden despertar colas en toda la red; muchos conjuntos distintos de destinos factibles pueden requerir varias tablas por topología.

La prueba pública de escala procesa 50.000 grupos de 0,125 personas, cuatro plazas viales y un grupo desconectado. No representa el costo de 120 corridas sobre la red geográfica: ese tiempo y su memoria todavía deben medirse en integración. El modo compacto evita retener un diccionario de historia por lote y millones de travesías terminadas; no reduce la cantidad de eventos procesados ni garantiza una mejora de tiempo determinada.

## Esquema completo de salida JSON

Los siguientes valores ilustran el ejemplo mínimo. Los objetos no contienen infinitos, conjuntos ni referencias a entradas.

```json
{
  "people_total": 2.5,
  "people_safe": 2.5,
  "people_safe_before_fire": 2.5,
  "people_temporary": 0.0,
  "people_remaining": 0.0,
  "people_exposed": 0.0,
  "queue_group_minutes": 0.0,
  "queue_person_minutes": 0.0,
  "queue_duration_min": 0.0,
  "max_queue_groups": 0,
  "max_queue_people": 0.0,
  "capacity_invariant": true,
  "no_closed_edge_traversal": true,
  "edge_max_occupancy": {"ab": 1},
  "destination_people": {"b": 2.5},
  "evacuation_times": [{"time_min": 7, "people": 2.5}],
  "history": [
    {"time_min": 0, "people_safe": 0.0, "people_temporary": 0.0,
     "people_remaining": 2.5, "people_exposed": 0.0,
     "queue_groups": 0, "queue_people": 0.0},
    {"time_min": 5, "people_safe": 0.0, "people_temporary": 0.0,
     "people_remaining": 2.5, "people_exposed": 0.0,
     "queue_groups": 0, "queue_people": 0.0},
    {"time_min": 7, "people_safe": 2.5, "people_temporary": 0.0,
     "people_remaining": 0.0, "people_exposed": 0.0,
     "queue_groups": 0, "queue_people": 0.0},
    {"time_min": 480, "people_safe": 2.5, "people_temporary": 0.0,
     "people_remaining": 0.0, "people_exposed": 0.0,
     "queue_groups": 0, "queue_people": 0.0}
  ],
  "traversals": [
    {"group": "hogar-1", "edge": "ab", "start_min": 5,
     "end_min": 7, "outcome": "arrived"}
  ],
  "groups": [
    {"id": "hogar-1", "people": 2.5, "node": "b", "state": "safe",
     "edge": null, "destination": "b", "finish_min": 7, "exposed": false}
  ]
}
```

| Salida | Interpretación |
|---|---|
| `people_total` | Masa inicial; `safe + temporary + remaining` la conserva con tolerancia flotante. |
| `people_exposed` | Subconjunto transversal de la población, no una categoría adicional de conservación ni mortalidad. |
| `evacuation_times` | Llegadas seguras con su peso, para distribuciones/percentiles ponderados; minutos desde el inicio global, no desde preparación. |
| `history` | Muestras posteriores al despacho, incluye cero y horizonte. Completa por defecto; selección ilustrativa acotada en modo compacto, no interpolable para métricas exactas. |
| Métricas de cola | Integrales exactas hasta horizonte; incluyen espera sin ruta y excluyen preparación, tránsito y refugios. Máximos después del despacho, no esperas de duración cero. |
| `destination_people` | Ocupación final por personas, sin reservas todavía en tránsito. |
| `groups.state` | `preparing`, `waiting`, `traveling`, `safe`, `temporary` o `stranded`. `node` es el último nodo alcanzado y `edge` el tramo activo, si existe. |
| `groups.finish_min` | Minuto de llegada a destino, o `null`; un refugio que posteriormente arde conserva su minuto de llegada, pero cambia a `stranded`. |
| `traversals.outcome` | `arrived`, `interrupted` o `horizon`; intervalos activos semiabiertos, sin ocupación posterior al cierre. |
| Invariantes booleanos | Capacidad simultánea observada y ausencia de ocupación posterior al cierre; no implican seguridad histórica. |

## Verificación y límites

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_motor_evacuacion.py' -v
```

Las pruebas usan solamente `simulate`: conservación fraccionaria e historial, FIFO e integrales, cierres iniciales/durante tránsito/en igualdad, redirección, reservas y capacidades de destino, refugios, exposición persistente, transformación, horizonte, desconexión, repetibilidad, serialización JSON y validación sin mutaciones. Comparan todos los escalares, estados finales, llegadas ponderadas, destinos y máximos por arista entre modos; un caso de miles de eventos comprueba límites, conteos e interrupción posterior a las primeras 100 travesías. Cubren S2.2 (masa y consumo de preparación externa), S2.3, S2.4 y S2.8. La generación aleatoria de hogares pertenece al integrador, no al motor.

**Risk:** la unidad contiene acople de eventos, reservas y rutas; requiere revisión independiente y pruebas integradas con la red y las 30 réplicas de fuego. No hay calibración de congestión, tiempos ni exposición contra evacuaciones históricas.
