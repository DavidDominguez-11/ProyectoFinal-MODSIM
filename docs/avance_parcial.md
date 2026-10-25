# Avance parcial — simulación de incendios y evacuación

**Proyecto:** Modelación y Simulación, Universidad del Valle de Guatemala  
**Estado:** propuesta técnica y auditoría inicial de fuentes; todavía no hay simulador ni resultados experimentales.  
**Fecha de preparación:** 24 de octubre de 2026  
**Equipo:** cinco integrantes; distribución de responsabilidades pendiente de acuerdo interno.  
**Tema:** aprobado según la confirmación del equipo y la evidencia incluida en `docs/aprobacion.pdf`.

## 1. Problema y pregunta de investigación

Los incendios forestales pueden avanzar mientras las personas reciben una alerta, deciden salir y recorren una red vial con capacidad limitada. La propagación, el comportamiento individual y la disponibilidad de rutas se afectan mutuamente. Un modelo que considere solo el área quemada o solo el tiempo de viaje no permite estudiar esas interacciones.

**Pregunta principal:** ¿cómo cambian el tiempo de evacuación y la población potencialmente expuesta cuando se modifica el momento de la alerta, la disponibilidad de rutas y la capacidad de respuesta en un incendio histórico concreto?

**Caso candidato:** Camp Fire del 8 de noviembre de 2018, en el corredor de Pulga–Concow–Paradise, condado de Butte, California. Se propone estudiar las primeras horas del incidente. El límite geográfico exacto y el intervalo final se fijarán después de inspeccionar conjuntamente las observaciones y las capas geográficas. NIST documentó el avance del fuego mediante observaciones con hora y reconstruyó avisos, evacuación, tráfico, cierres y áreas de refugio temporal [1, 2]. El condado publicó un informe sobre su respuesta y los albergues habilitados [3]. Esta combinación de fuentes justifica estudiar el caso; **todavía no demuestra** que cada capa pueda descargarse y acoplarse con la calidad necesaria.

**Tipo de resultado esperado:** análisis retrospectivo y comparativo de escenarios. El modelo no será un sistema de predicción operativa ni producirá recomendaciones de evacuación para una emergencia real.

## 2. Objetivos y alcance

### Objetivo general

Construir y evaluar un modelo híbrido que acople propagación simplificada del fuego, decisiones de evacuación y tránsito por carreteras para comparar estrategias de respuesta en un sector delimitado del Camp Fire.

### Objetivos específicos

1. Preparar capas geográficas con proyección, período y resolución compatibles.
2. Representar el avance del fuego con una grilla y contrastar puntos o intervalos de llegada con observaciones históricas.
3. Representar grupos de personas y equipos de respuesta como agentes con estados y reglas explícitas.
4. Simular desplazamiento y espera sobre una red de carreteras con cierres y destinos de capacidad limitada.
5. Comparar escenarios con múltiples réplicas, cuantificar incertidumbre y comprobar sensibilidad a los supuestos más importantes.

### Límites deliberados

- El foco es un **sector y un período** del incendio, no la reproducción de todo el evento de 17 días.
- Un agente de evacuación puede representar un hogar o grupo de personas con un peso poblacional conocido; no se afirmará que representa a una familia histórica identificada.
- El modelo de fuego será simplificado. Para este caso debe considerar la posibilidad de focos adelantados por brasas (*spotting*), porque NIST documenta que contribuyeron al avance sobre Paradise [1]. Su frecuencia y alcance serán parámetros a justificar y someter a sensibilidad.
- El efecto de brigadistas será una regla de intervención acotada y explícita. No se estimará capacidad real de extinción a partir de un conteo de personal.
- Se distinguirán **salidas hacia zonas seguras**, **áreas temporales de refugio ante el fuego** y **albergues para desplazados**. NIST documenta las primeras áreas temporales; el informe del condado describe albergues [2, 3]. No son destinos equivalentes.
- Muertes, lesiones o pérdidas económicas reales quedan fuera de las métricas predictivas: los datos disponibles no permiten inferirlas a partir de una grilla y reglas simples.

## 3. Relación entre componentes y temas del curso

| Componente | Estado y mecanismo propuesto | Tema de clase |
|---|---|---|
| Incendio | Celda no combustible, susceptible, ardiendo o consumida; transiciones según vecindad, combustible, pendiente, viento y focos adelantados | Autómatas celulares; modelado espacial; variables aleatorias |
| Grupos evacuados | Estado sin alertar, alertado, preparando salida, en ruta, en refugio temporal o en destino seguro; exposición potencial registrada aparte | ABM; heterogeneidad; diagramas de estado; retrasos |
| Brigadas | Posición, disponibilidad y acción local definida en un escenario | ABM; recursos de respuesta |
| Carreteras | Grafo dirigido con tiempos de tránsito, capacidad y aristas abiertas o cerradas | Redes; caminos; movilidad |
| Movimiento y admisión | Eventos de salida, entrada a tramo, fin de tránsito, cierre, llegada y admisión; espera cuando se agota capacidad | DES; colas y recursos |
| Contabilidad poblacional | Totales de personas por estado, calculados a partir de los agentes; transiciones conservan población | Stocks, flujos y espacio de estados |
| Réplicas | Semillas registradas, distribuciones de parámetros inciertos e intervalos de resultados | Monte Carlo; validación estocástica |

**Acoplamiento temporal propuesto:** el reloj avanza por pasos de la grilla de fuego y procesa todos los eventos de tránsito y decisión programados hasta el siguiente paso. Al terminar el paso se actualizan peligros y cierres; los agentes pueden reconsiderar su ruta. El orden exacto de actualización debe especificarse antes de implementar, pues puede cambiar los resultados.

## 4. Auditoría inicial de datos

**Estado de esta auditoría:** se confirmaron páginas y productos en fuentes primarias. Aún no se han descargado, inspeccionado ni armonizado archivos para el sector candidato. Por tanto, la tabla no equivale a una certificación de cobertura o calidad local.

| Necesidad | Fuente encontrada | Uso previsto | Estado y límite |
|---|---|---|---|
| Cronología del fuego | NIST, estudio de progresión y mapas por intervalos [1] | Referencia histórica para llegada y dirección de avance | Fuente identificada. Mapas e informes requieren extracción o digitalización controlada; no asumir que hay una grilla horaria lista para usar. |
| Avisos, evacuación, tráfico y áreas temporales | NIST, estudio NETTRA [2] | Definir y contrastar eventos observables | Fuente identificada. No proporciona trayectorias completas de cada evacuado. |
| Albergues y respuesta institucional | Informe posterior del condado de Butte [3] | Identificar tipos de destinos y algunos tiempos de habilitación | Fuente identificada. Capacidad individual y ocupación por hora siguen sin verificarse. |
| Combustible y vegetación previos al incendio | LANDFIRE 2016 Remap [4] | Susceptibilidad relativa de celdas | Producto identificado; pendiente descargar recorte, revisar categorías y comprobar representatividad en 2018. |
| Elevación | USGS 3DEP [5] | Pendiente local | Producto identificado; pendiente comprobar fecha, cobertura y resolución útil. |
| Carreteras próximas al evento | TIGER/Line 2018, condado de Butte [6] | Geometría inicial del grafo | Archivo de carreteras identificado; pendiente revisar conectividad, sentidos, accesos y aptitud para calcular tiempos. La geometría por sí sola no da capacidad ni velocidad histórica. |
| Población previa al evento | ACS de cinco años 2013–2017 [7] | Totales agregados para generar agentes ponderados | API identificada; pendiente elegir geografía y variables, descargar estimaciones y márgenes de error. No son domicilios individuales. |
| Viento histórico | Reanálisis ERA5 [8], o mediciones locales si se comprueba acceso | Dirección e intensidad por período | Fuente general identificada; su escala espacial puede ser demasiado gruesa para vientos locales. Comparar con observaciones del caso antes de usarla. |
| Perímetro final | CAL FIRE FRAP [9] | Comprobación espacial global, si se extiende el horizonte | Producto identificado. Un perímetro final no aporta la hora de llegada de cada celda. |
| Capacidad de albergues, brigadas, tiempos individuales de salida y capacidad vial | Registros históricos por localizar | Parámetros de la simulación | **No verificados.** Si no hay registros utilizables, serán supuestos explícitos y se analizará su sensibilidad. |

No se usará un mapa de cobertura de **2021** como si describiera automáticamente el combustible anterior al incendio de **2018**. Tampoco se interpretarán puntos satelitales de fuego activo como un perímetro continuo o una medida directa de superficie quemada [10].

## 5. Variables, estados y reglas por especificar

### Incendio

- **Estado mínimo por celda:** posición, clase de combustible, elevación, estado de combustión y tiempo de ignición si ocurre.
- **Entradas:** ignición inicial, vecindad, dirección e intensidad del viento, pendiente, parámetros de propagación y de *spotting*.
- **Salida:** mapa de tiempos de llegada y área afectada dentro del dominio.
- **Regla:** probabilidad de ignición que depende de los factores anteriores; debe quedar en una ecuación reproducible con parámetros, unidades y fuente o calibración. No se fijan coeficientes antes de revisar datos.

### Evacuación

- **Estado mínimo por agente:** tamaño del grupo, origen, ubicación o tramo actual, destino, estado de evacuación y tiempos programados de alerta y salida.
- **Reglas:** recibir alerta; esperar el retraso de decisión; elegir ruta disponible; avanzar respetando capacidad; cambiar de ruta ante cierres; registrar llegada y episodios de exposición potencial.
- **Heterogeneidad:** retraso de salida y tamaño del grupo, sujetos a distribuciones justificadas. Movilidad reducida solo si se encuentra un dato defendible o se presenta claramente como escenario.

### Vías, refugios y recursos

- **Aristas:** longitud, tiempo base de recorrido, capacidad hipotética o documentada, estado abierto/cerrado.
- **Destinos:** ubicación, tipo, horario de apertura y capacidad si se obtiene.
- **Brigadas:** ubicación inicial, disponibilidad y efecto local definido. Un escenario de reubicación debe mantener constante el número total de brigadas para comparar solo la asignación.
- **Contabilidad:** personas iniciales = personas sin alertar + alertadas o en preparación + en tránsito + en refugio temporal + en destino seguro. Estas categorías serán mutuamente excluyentes. La exposición potencial será un indicador acumulado separado, pues una persona puede quedar expuesta y luego alcanzar un destino. Las transiciones y unidades se comprobarán en cada paso.

## 6. Diseño de escenarios y métricas

**Escenario base:** condiciones y eventos históricos que puedan documentarse, con supuestos explícitos para lo que falte. No se etiquetará como reconstrucción exacta.

| Experimento | Cambio frente a la base | Condición de comparación |
|---|---|---|
| Alerta más temprana | Adelantar un intervalo definido y justificado el aviso a ciertos agentes o zonas | Mantener la misma población, fuego y red iniciales |
| Rutas | Cerrar o habilitar una arista en el momento especificado | Explicar si es cierre observado o intervención hipotética |
| Brigadas | Redistribuir recursos existentes con una regla local de actuación | Mantener el total de recursos constante |
| Destinos | Añadir o ampliar capacidad en un destino identificable | Diferenciar capacidad documentada de capacidad supuesta |

**Métricas principales:** fracción de personas que alcanza una salida o destino definido como seguro antes de la llegada modelada del fuego; distribución del tiempo hasta ese destino; personas con exposición potencial según una definición espacial y temporal explícita; longitud y duración de filas; utilización de tramos o destinos; y área afectada dentro del dominio. Un refugio temporal no se clasificará automáticamente como destino seguro. Cada métrica tendrá unidad, denominador y período de observación.

Las diferencias entre escenarios se reportarán con múltiples corridas y semillas reproducibles, junto con intervalos de incertidumbre. Si se varían simultáneamente parámetros del fuego y de evacuación, se separará la incertidumbre propia de cada módulo para no atribuirle a una política un efecto causado por otra variación.

## 7. Verificación, validación y límites de interpretación

1. **Verificación del programa:** comprobar conservación de población, ausencia de ocupaciones superiores a capacidad, inexistencia de tránsito por aristas cerradas, orden temporal de eventos y reproducibilidad con una semilla fija.
2. **Pruebas de casos límite:** sin viento, sin combustible, sin evacuados, capacidad vial muy alta y destino sin cupo. Las respuestas esperadas se definirán antes de correr el modelo.
3. **Contraste histórico del fuego:** comparar tiempos o zonas de llegada agregadas con observaciones de NIST [1]. Una observación usada para ajustar parámetros no se volverá a presentar como prueba independiente.
4. **Contraste de evacuación:** comparar órdenes de magnitud y sucesos verificables de NIST y Butte County [2, 3], indicando dónde solo hay evidencia cualitativa.
5. **Sensibilidad:** variar tamaño de celda, paso temporal, retrasos, propagación, *spotting*, capacidad vial y capacidad de destinos. Reportar cuáles supuestos cambian las conclusiones.
6. **Límite:** una coincidencia parcial con el incendio histórico no valida por sí sola tiempos individuales de evacuación, lesiones ni seguridad de rutas futuras.

## 8. Trabajo paralelo para cinco integrantes

La siguiente distribución propone responsables por **entregable verificable**; no asigna nombres ni presupone habilidades del equipo. La integración y revisión cruzada pertenecen a todos.

| Frente | Entregable inicial | Interfaz con el resto |
|---|---|---|
| 1. Caso y evidencia | Cronología con eventos y citas precisas de NIST y Butte County | Entrega puntos y períodos de contraste; identifica qué datos son solo narrativos |
| 2. Geodatos | Inventario de archivos, licencias, fecha, resolución, sistema de coordenadas y recortes | Entrega capas alineadas y un registro de procedencia |
| 3. Fuego | Reglas, parámetros y prototipo de grilla con *spotting* acotado | Entrega tiempo de ignición por celda y estado del peligro por paso |
| 4. Evacuación y red | Agentes, rutas, eventos, colas, cierres y destinos | Consume peligro y población; entrega trayectoria y estado de cada agente |
| 5. Experimentos e informe | Configuraciones, semillas, métricas, gráficos, validación y borrador del informe | Consume salidas de los módulos; comprueba consistencia y prepara resultados |

**Acuerdos de integración necesarios desde el inicio:** un único sistema de coordenadas proyectadas, unidades comunes (metros y minutos u horas), contrato de entradas y salidas de cada módulo, convención de fechas/zonas horarias, identificadores de celdas y aristas, y formato de configuración de escenarios. Cada frente debe documentar qué recibió, transformó y entregó.

## 9. Estado real del avance y próximos hitos

**Completado al redactar este documento:** tema propuesto y aprobado según el equipo; lectura de requisitos del curso; comparación preliminar de incendios candidatos; selección razonada del Camp Fire como candidato; identificación de fuentes oficiales; delimitación conceptual del modelo y de sus límites de validación.

**Pendiente antes de afirmar viabilidad local:** descargar muestras o recortes de las capas; confirmar cobertura temporal y espacial; comprobar que las carreteras forman un grafo utilizable; revisar qué lugares de destino y qué capacidades tienen soporte documental; seleccionar el dominio y el período definitivos.

**Pendiente de desarrollo:** ecuaciones y parámetros; código ejecutable; pruebas; experimentos; resultados; informe PDF; repositorio público reproducible; video; diapositivas y exposición. Ninguno de esos elementos se presenta aquí como terminado.

**Siguiente hito inmediato:** una ficha de datos por fuente con URL exacta de descarga, versión, licencia, formato, cobertura, tamaño, fecha de referencia y observaciones de calidad. Con esa evidencia se congelará el alcance espacial y temporal. Luego se podrá fijar la especificación matemática e iniciar los módulos.

## 10. Referencias de la auditoría

1. NIST, *A Case Study of the Camp Fire—Fire Progression Timeline* y mapas: https://www.nist.gov/programs-projects/wildland-urban-interface-wui-fire-data-collection-parcel-vulnerabilities/nist/fire
2. NIST, *Notification, Evacuation, Traffic, and Temporary Refuge Areas (NETTRA)*: https://www.nist.gov/publications/case-study-camp-fire-notification-evacuation-traffic-and-temporary-refuge-areas-nettra
3. Butte County, *Camp Fire After Action Report*: https://www.buttecounty.net/DocumentCenter/View/3849/Camp-Fire-After-Action-Report-PDF
4. LANDFIRE, *2016 Remap*: https://landfire.gov/data/lf2016
5. USGS, *The National Map—3DEP elevation data*: https://www.usgs.gov/faqs/what-types-elevation-datasets-are-available-what-formats-do-they-come-and-where-can-i-download
6. U.S. Census Bureau, *TIGER/Line Roads 2018*: https://www2.census.gov/geo/tiger/TIGER2018/ROADS/
7. U.S. Census Bureau, *ACS 2017 Five-Year Data*: https://www.census.gov/data/developers/data-sets/acs-5year/2017.html
8. Copernicus Climate Change Service, *ERA5 Reanalysis*: https://climate.copernicus.eu/climate-reanalysis
9. CAL FIRE, *Historical Fire Perimeters*: https://www.fire.ca.gov/what-we-do/fire-resource-assessment-program/fire-perimeters
10. NASA Earthdata, explicación de límites de detecciones activas frente a perímetros: https://forum.earthdata.nasa.gov/viewtopic.php?t=5200

## 11. Registro inicial de uso de IA

Para cumplir la política del proyecto, el equipo debe conservar los prompts relevantes y evaluarlos críticamente. En esta etapa se utilizó IA para leer las guías del curso, relacionar la propuesta con los paradigmas vistos, buscar candidatos de incendio y estructurar esta auditoría. La propuesta inicial de usar Guatemala se descartó como ubicación preferida después de la observación del profesor comunicada por el equipo. La selección del Camp Fire se apoya en fuentes institucionales citadas, pero aún requiere verificar archivos descargados. No se han generado datos experimentales ni se ha validado un simulador. En el informe final habrá que conservar ejemplos concretos de prompts, respuestas acertadas o fallidas, verificaciones independientes y decisiones del equipo.
