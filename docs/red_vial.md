# Red vial dirigida para evacuación

`scripts/evacuacion/red_vial.py` convierte carreteras TIGER/Line 2018 de Butte County en el contrato JSON compartido con el motor de evacuación. Conserva componentes aislados y solo propone salidas donde las vías principales cruzan el límite del dominio. No acredita rutas seguras ni condiciones históricas.

## Uso

Desde la raíz, con el entorno geoespacial existente:

```bash
.venv/bin/python scripts/evacuacion/red_vial.py --help
.venv/bin/python scripts/evacuacion/red_vial.py --roads data/crudo/evacuacion/tl_2018_06007_roads.zip
```

Solo `--download` autoriza acceso a la fuente oficial; reutiliza la caché si existe:

```bash
.venv/bin/python scripts/evacuacion/red_vial.py --download
```

Los valores predeterminados son `--domain config/dominio.json` y `--output data/procesado/red_vial.json`, relativos a la raíz del proyecto. Las rutas explícitas son relativas al directorio actual. La CLI imprime el resumen de conectividad y guarda el JSON; no ejecuta simulaciones. La caché está en `data/crudo/evacuacion/` (ignorada por Git).

El ZIP se inspecciona y entrega como bytes a GeoPandas, sin extracción ni interpolación de rutas internas en una ruta GDAL. Se rechazan rutas absolutas, componentes `..`, barras inversas, dos puntos y archivos con más de un shapefile. La lectura local no accede a la red.

## API y contrato L5

`build_network(roads, domain)` acepta un `GeoDataFrame` en **EPSG:32610** y un diccionario como `config/dominio.json`. No descarga, escribe archivos ni modifica el frame. La CLI sí reproyecta la fuente antes de invocar la función. Se admiten `LineString` y `MultiLineString`; geometrías vacías/nulas se omiten y otras geometrías se rechazan. `FULLNAME` y `MTFCC` son opcionales.

| Campo | Contenido |
|---|---|
| `nodes` | `[{id, x, y}]`, coordenadas UTM en metros |
| `edges` | `[{id, u, v, length_m, travel_min, capacity, cells, name, mtfcc}]` |
| `destinations` | `[{node, kind: "safe", capacity: 100000}]` |
| `metadata` | Fuente, dominio, supuestos, parámetros usados, nombres de salida faltantes y conectividad |

Los identificadores son cadenas únicas y estables para la misma entrada; las celdas son pares `[fila, columna]`, con fila 0 al norte. El JSON es serializable sin valores no finitos. No se genera el campo opcional `node.cell`: en límites de grilla un nodo puede tocar varias celdas.

### Topología y fuego

1. Recortar exactamente al rectángulo del dominio en UTM.
2. Unir geometrías para dividir cruces, extremos y solapes; conservar los vértices intermedios genuinos de TIGER como nodos. También se conservan tramos que atraviesan el dominio sin ningún vértice original interior.
3. Crear dos aristas opuestas por segmento geométrico único. En solapes, elegir el atributo menor lexicográficamente por nombre y código, sin duplicar capacidad.
4. Enumerar **todas** las celdas cerradas intersectadas por cada tramo, incluidos contactos con esquinas y ambos lados de una línea de grilla. No basta con sus extremos ni con rellenar su rectángulo envolvente.

Los cruces geométricos se interpretan a nivel: no se distinguen puentes o túneles. No se agregan enlaces para unir componentes desconectados. La enumeración conservadora permite al motor cerrar un tramo si cualquiera de sus celdas es alcanzada por el fuego; puede cerrar antes que una superposición más fina.

### Parámetros hipotéticos

Sin datos históricos de velocidades y capacidad, se adopta esta jerarquía explícita de escenario, **no una estimación empírica**:

| MTFCC | Velocidad (km/h) | Capacidad por arista dirigida (grupos activos simultáneos) |
|---|---:|---:|
| S1100 | 70 | 40 |
| S1200 | 50 | 25 |
| S1400 | 30 | 10 |
| Desconocido u otro | 20 | 5 |

La longitud se obtiene de la geometría en metros. `travel_min = length_m / (speed_kmh * 1000 / 60)` es estrictamente positivo. La capacidad es un entero positivo y no representa personas, caudal horario ni carriles históricos. Las direcciones opuestas tienen capacidades independientes: la bidireccionalidad es un supuesto, no una afirmación sobre el contraflujo de 2018. Los valores efectivamente usados se guardan en `metadata.road_parameters`.

### Salidas y componentes aislados

Se reconocen palabras completas Skyway, Clark, Pentz y Neal en `FULLNAME`, sin distinguir mayúsculas. Una salida requiere un extremo recortado en el límite y una porción de la carretera original fuera del dominio. Un fondo de saco o una carretera que solo termina en el límite no genera salida. Los nombres sin cruces disponibles se enumeran en `metadata.missing_exit_names`.

Cada salida representa un **destino seguro absorbente hipotético fuera del dominio**, no un refugio temporal ni un albergue histórico. Su capacidad finita inicial es 100000 personas ponderadas admitidas; la integración puede reducir una salida para un escenario de restricción. El motor debe aplicar esa capacidad de destino independientemente de la de cada tramo.

`metadata.connectivity` contiene:

- `component_count` y `components`, con identificador, lista de nodos, cantidad, salidas y `has_exit` por componente;
- `nodes_without_exit` y `fraction_nodes_without_exit` (0 para una red vacía).

La fracción mide **nodos, no habitantes**. La integración debe conservar los grupos asignados a nodos sin salida y sumar su peso poblacional para informar la fracción de habitantes sin ruta; nunca eliminarlos ni inventar puentes. En esta red bidireccional, pertenecer a una componente con salida equivale a poder alcanzarla antes de cierres, colas y agotamiento de capacidad.

## Verificación

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_red_vial.py' -v
```

Las pruebas usan geometrías proyectadas sintéticas y ZIP locales temporales. Verifican recorte, cruces, vértices, bidireccionalidad, longitudes, tiempos, capacidades, celdas, componentes, salidas permitidas/faltantes, entradas vacías, validación y CLI sin descarga. No dependen del historial Git ni construyen la red de producción.

## Fuente y límites

Fuente oficial: <https://www2.census.gov/geo/tiger/TIGER2018/ROADS/tl_2018_06007_roads.zip>, la misma URL de `scripts/auditar_geografia.py`. La geometría y los códigos provienen de TIGER; velocidades, capacidades, direcciones y seguridad fuera del dominio son supuestos que deben reemplazarse cuando la Parte 3 aporte evidencia. El módulo no importa ni modifica el prototipo sintético.
