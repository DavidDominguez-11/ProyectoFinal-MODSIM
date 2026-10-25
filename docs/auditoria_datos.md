# Auditoría reproducible de datos — Camp Fire

**Fecha:** 24 de octubre de 2026.  
**Propósito:** distinguir fuentes localizadas, archivos efectivamente inspeccionados y datos que siguen faltando para el avance parcial.  
**Estado:** auditoría inicial; todavía no se han preparado capas finales ni corrido simulaciones.

## 1. Hallazgos comprobados con archivos

Los scripts [auditar_geografia.py](../scripts/auditar_geografia.py), [auditar_poblacion.py](../scripts/auditar_poblacion.py), [auditar_rasters.py](../scripts/auditar_rasters.py) y [auditar_nist.py](../scripts/auditar_nist.py) descargan temporalmente fuentes oficiales o institucionales, verifican sus campos y muestran resultados. No guardan los archivos brutos en el repositorio.

| Archivo o servicio | Comprobación ejecutada | Resultado observado |
|---|---|---|
| [TIGER/Line 2018, carreteras de Butte County](https://www2.census.gov/geo/tiger/TIGER2018/ROADS/tl_2018_06007_roads.zip) | Descarga, apertura del shapefile y lectura de geometrías | 2 153 457 bytes; SHA-256 `6772d5902b13c1187cf8bb797a222aabb28f06e52024f13aedab64a328c04697`; 9 530 segmentos LineString; CRS EPSG:4269. |
| [TIGER/Line 2018, lugares de California](https://www2.census.gov/geo/tiger/TIGER2018/PLACE/tl_2018_06_place.zip) | Descarga y selección de `GEOID=0655520` | 9 434 512 bytes; SHA-256 `e95c233451b461fb246966edb935553ecb505105036a9bc24170a7f5d6b8d1b4`; un polígono llamado Paradise; CRS EPSG:4269. |
| Cruce de ambas capas | Intersección geométrica | El polígono de Paradise tiene aproximadamente 47,45 km² al proyectarlo en UTM 10N; 1 087 segmentos del archivo vial tocan el polígono. Esto **no** prueba que formen una red transitable conectada. |
| [WorldPop, servicio de población a 100 m](https://worldpop.arcgis.com/arcgis/rest/services/WorldPop_Total_Population_100m/ImageServer) | Solicitud de GeoTIFF para 2018 y recorte rectangular alrededor de Paradise | Descarga de 66 352 bytes, 110 × 92 celdas, CRS EPSG:4326. Suma aproximada de 28 407 residentes estimados en celdas cuyos centros caen dentro del polígono; 28 645 si se incluyen todas las celdas tocadas por el borde. |
| [Butte County Association of Governments, población histórica](https://www.bcag.org/population-estimates-historical) | Lectura de la tabla que reproduce estimaciones del Departamento de Finanzas de California | Paradise: **26 581 residentes estimados al 1 de enero de 2018**. Es un total municipal de referencia anterior al incendio. |
| [LANDFIRE 2016, FBFM40](https://lfps.usgs.gov/arcgis/rest/services/Landfire_LF2016/LF2016_FBFM40_CONUS/ImageServer) | Exportación de un recorte TIFF de Paradise | 256 × 256 celdas válidas, 131 912 bytes, EPSG:4326, 21 códigos de categoría observados. El código más frecuente fue `186`, con 20 391 celdas en este recorte. Los códigos aún deben cruzarse con el diccionario oficial; no equivalen directamente a probabilidades de ignición. |
| [USGS 3DEP, servicio de elevación](https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer) | Exportación de un recorte TIFF de Paradise | 256 × 256 celdas válidas, 262 982 bytes, EPSG:4326; valores entre aproximadamente 179 y 739 en la capa devuelta. La fecha de las fuentes del servicio dinámico todavía debe verificarse. |
| [NIST, Appendix F Fire Spread Data](https://catalog.data.gov/dataset/data-supporting-the-case-study-of-the-2018-camp-fire) | Descarga y lectura de libro Excel oficial | 438 645 bytes; SHA-256 `14fac49ca633d4c944fcb2ba2b22e95ea8751b8d0dd58216a836d2b6e89268a3`; 15 hojas; 2 839 apariciones de filas no vacías; 2 236 claves distintas al combinar identificador, fecha, hora, posición y tipo. Las hojas comparten observaciones: no se sumarán filas como eventos independientes. |

El total de WorldPop por centros de celda excede al total municipal de referencia en aproximadamente **6,9 %**. Es una diferencia entre dos estimaciones construidas con métodos y geográficas distintos; no es evidencia de que una sea el conteo real exacto. Se recomienda usar el total institucional como control agregado y el ráster solo como distribución espacial aproximada, documentando cualquier reescalado aplicado. No se debe convertir el ráster en supuestos domicilios individuales.

### Anomalía crítica en la hoja de NIST

Las **2 839 apariciones de filas** del libro Excel tienen año **2021** en la columna `Date`, aunque el caso y el informe NIST describen el incendio del **8 de noviembre de 2018**. Se comprobó un ejemplo concreto: la fuente `911-001-1` figura en la hoja `Concow` del Excel con `Date=2021-11-08` y `Time=06:25`, mientras la [tabla 10 de NIST TN 2252](https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.2252.pdf) la identifica como la primera llamada sobre el incendio de 2018 a las 06:25. La coincidencia de identificador y hora refuerza que existe una inconsistencia de año en ese registro, sin explicar su origen ni demostrar que cada fila pueda corregirse del mismo modo. El script mantiene y reporta el dato bruto; **no lo corrige automáticamente**. Antes de derivar tiempos de llegada hay que documentar una regla de fecha y revisar el significado de la ventana de observación. Los códigos de tipo de fuego (`V`, `S`, `R`, `O`, `C`) deben interpretarse con el diccionario del informe, antes de usarlos para filtrar observaciones. Hay 284 identificadores de fuente distintos, pero un identificador puede producir más de una observación; deduplicar solo por identificador perdería datos.

### Extensión comprobada

- El polígono TIGER/Line de Paradise tiene caja envolvente aproximada `[-121.655652, 39.725361, -121.564452, 39.801543]` en coordenadas geográficas. **Esa caja se usó solo para auditar población**; no es aún el dominio de simulación del fuego.
- El archivo de carreteras cubre Butte County. Su caja envolvente es `[-122.053919, 39.303629, -121.077346, 40.151979]`; por tanto incluye el entorno general de Paradise y permite plantear un recorte que también incorpore vías de salida.
- Las geometrías TIGER/Line están en EPSG:4269 y el ráster exportado en EPSG:4326. Para medir distancias y construir la red habrá que reproyectar a un sistema métrico común, verificar la transformación y conservar los metadatos originales.

## 2. Fuentes localizadas, todavía sin archivo auditado

| Fuente | Qué aporta | Verificación pendiente |
|---|---|---|
| [NIST: Fire Progression Timeline](https://www.nist.gov/programs-projects/wildland-urban-interface-wui-fire-data-collection-parcel-vulnerabilities/nist/fire) | Informe y mapas por intervalos horarios que acompañan la hoja Excel auditada | Elegir observaciones válidas, resolver la anomalía de fecha, y separar calibración de contraste; no asumir que las observaciones puntuales son perímetros completos. |
| [NIST: NETTRA](https://www.nist.gov/publications/case-study-camp-fire-notification-evacuation-traffic-and-temporary-refuge-areas-nettra) | Avisos, tráfico, cierres, exposición y áreas temporales de refugio | La tabla 10 de avisos ya se resumió en [cronologia_base.md](cronologia_base.md). Falta extraer tráfico, cierres y refugios. No son trayectorias individuales exhaustivas. |
| [Butte County: informe posterior](https://www.buttecounty.net/DocumentCenter/View/3849/Camp-Fire-After-Action-Report-PDF) | Apertura de albergues y decisiones de respuesta | Extraer sedes, horas y capacidades que realmente aparezcan; marcar como desconocidas las demás. |
| [LANDFIRE 2016 Remap](https://landfire.gov/data/lf2016) | Combustibles y vegetación previos al incendio | El recorte de Paradise ya se leyó. Falta ampliar al origen y corredores de salida, interpretar códigos y verificar la resolución original en el terreno elegido. |
| [USGS 3DEP](https://www.usgs.gov/faqs/what-types-elevation-datasets-are-available-what-formats-do-they-come-and-where-can-i-download) | Elevación para calcular pendiente | El recorte de Paradise ya se leyó. Falta ampliar al dominio y comprobar metadatos de fecha y resolución de la fuente dinámica. |
| [ERA5](https://climate.copernicus.eu/climate-reanalysis) | Viento horario histórico | Descargar período, convertir unidades y contrastar con observaciones locales; su resolución espacial es gruesa para viento en cañones. |

## 3. Accesos y límites detectados

- Una solicitud a la [API ACS 2017 del Censo](https://www.census.gov/data/developers/data-sets/acs-5year/2017.html) devolvió una página **“Missing Key”**. Por ahora no se incluye una tabla ACS descargada. El servicio de WorldPop permitió auditar un recorte espacial sin descargar su archivo nacional completo.
- El [GeoTIFF nacional WorldPop 2018](https://data.worldpop.org/GIS/Population/Global_2000_2020/2018/USA/usa_ppp_2018.tif) anuncia 4 004 758 472 bytes. Descargarlo entero sería desproporcionado para este caso; el recorte solicitado al servicio de imágenes tiene 66 352 bytes. No se ha verificado todavía la versión y método exactos que el servicio Esri utiliza para el corte temporal de 2018 frente al producto original.
- El recorte de WorldPop procede de una **estimación de población residencial**. Su suma sobre un polígono depende de la regla usada para las celdas de borde. No representa población efectivamente presente a la hora del incendio ni número de vehículos.
- TIGER/Line aporta geometría vial, no velocidades de 2018, sentidos operativos durante el incendio, flujos de tránsito ni capacidad de cada tramo. Una simulación de colas viales necesitará parámetros documentados o rangos de escenario.
- Un perímetro final del incendio y una detección satelital de fuego activo no constituyen por sí solos una cronología de llegada del fuego a cada celda. Las observaciones de NIST son más pertinentes para el período inicial.
- El servicio USGS 3DEP informa que su mosaico dinámico incorpora fuentes publicadas hasta septiembre de 2026. La elevación del terreno puede ser útil, pero no se etiquetará como una captura histórica de 2018 sin revisar el origen de los píxeles.
- Refugios temporales ante el fuego y albergues para desplazados tienen funciones distintas. Ninguna cifra de capacidad de refugios se ha verificado aún.

## 4. Decisión provisional y criterio para cerrarla

El caso **sigue siendo viable como candidato** porque ya se comprobaron físicamente una capa vial de 2018, el límite municipal de 2018, recortes de población, combustible y elevación, y una hoja oficial con observaciones geolocalizadas del fuego. No está cerrada su viabilidad total: falta limpiar la cronología, ampliar recortes al dominio completo y resolver viento, tránsito y capacidades de refugios.

El recorte final del estudio se fijará solo después de responder con datos a estas cuatro comprobaciones:

1. ¿Las capas de combustible y elevación, comprobadas sobre Paradise, cubren también la zona de ignición y los caminos de salida elegidos?
2. ¿Qué observaciones de NIST permiten medir tiempos o zonas de llegada tras revisar fecha, ventana temporal y duplicados, sin usar las mismas para ajuste y validación?
3. ¿La red vial recortada conecta orígenes y destinos plausibles, y cuáles cierres tienen hora documentada?
4. ¿Qué capacidades de albergues o vías están documentadas y cuáles deberán permanecer como escenarios?

Si alguna respuesta impide el corredor completo, se reducirá el sector o se elegirá un subproblema medible; no se completarán huecos con cifras presentadas como históricas.

## 5. Reproducción de esta auditoría

Las versiones verificadas en este entorno están en [requirements-audit.txt](../requirements-audit.txt). Desde la raíz del repositorio:

```powershell
python -m pip install -r requirements-audit.txt
python scripts/auditar_geografia.py
python scripts/auditar_poblacion.py
python scripts/auditar_rasters.py
python scripts/auditar_nist.py
```

Los valores pueden cambiar si la fuente remota actualiza archivos o métodos. Los hashes de los ZIP y la fecha de esta auditoría permiten detectar cambios. Los resultados numéricos de esta página son **evidencia de acceso y consistencia preliminar**, no resultados del proyecto de simulación.
