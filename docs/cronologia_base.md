# Cronología base verificable — Camp Fire, 8 de noviembre de 2018

**Estado:** extracción inicial para el avance parcial, no cronología exhaustiva ni datos de entrada listos para simulación. Las horas se transcriben como aparecen en la tabla 10 del informe NETTRA de NIST; antes de unirlas a otras fuentes se documentará explícitamente la zona horaria. Los identificadores de la última columna permiten localizar cada evidencia en el informe.

| Hora indicada por NIST | Hecho documentado | Naturaleza del dato y uso posible | Fuente interna |
|---|---|---|---|
| 06:25 | Se recibe la primera llamada al 911 que informa de fuego en Feather River Canyon, cerca de Camp Creek Road y Poe Dam. | **Reporte de fuego.** Es un hito de detección, no la hora exacta de ignición. | `911-001-1` |
| 06:31 | El centro de comunicaciones despacha la respuesta inicial. | **Acción institucional.** Puede acotar el inicio de la movilización; no indica llegada al lugar. | `VTD-32` |
| 06:44 | El primer vehículo de bomberos que llega observa el fuego desde CA-70; otro entra a Pulga e inicia evacuaciones puerta a puerta. | **Observación y acción local.** No implica que todos los residentes de Pulga recibieran aviso a esa hora. | `TD-028`, `TD-029`, `VTD-32` |
| 06:55 | El mando solicita órdenes de evacuación para Pulga y mantener alerta a las áreas vecinas. | **Solicitud de orden.** No equivale a entrega de mensajes a hogares. | `TD-028`, `VTD-32` |
| 07:13 | La oficina del sheriff de Butte activa CodeRED para Pulga. | **Activación de sistema de aviso.** No cuantifica destinatarios, entrega ni lectura. | `BCSO` |
| 07:22 | El mando confirma una advertencia de evacuación para Concow; aún se determinaban las áreas de evacuación inmediata. | **Decisión institucional.** La extensión espacial precisa requiere comprobar el mapa de zonas. | `VTD-32` |
| 07:30 | Se documenta un aviso de civil a civil en Paradise/Magalia aconsejando evacuar a familiares. | **Aviso interpersonal.** Evidencia heterogeneidad de canales, no cobertura general. | `TD-058` |
| 07:32 | El mando solicita una advertencia de evacuación para el lado oeste de Pentz Road en Paradise. El informe marca “west [sic]”. | **Solicitud con ambigüedad geográfica original.** No se usará para asignar automáticamente polígonos de alerta. | `VTD-32` |
| 07:37 | El mando solicita una orden de evacuación para Concow y el centro de comunicaciones avisa a la oficina del sheriff. | **Solicitud y comunicación institucional.** Falta verificar la difusión a residentes. | `VTD-32` |
| 07:43 | Autoridades empiezan a recorrer Pentz Road desde Skyway para comunicar la advertencia a residentes. | **Inicio de avisos presenciales en un corredor.** No constituye hora uniforme de recepción. | `VTD-32` |
| 07:46 | El mando amplía las órdenes para incluir el lado este de Pentz Road en zonas 3, 8, 14 y Lower Pentz de Paradise. | **Orden delimitada por zonas citadas.** Hay que cruzar las zonas con cartografía histórica antes de programarla. | `VTD-32` |
| 07:49–07:59 | Personas que llaman al 911 desde Paradise reciben indicación de evacuar de inmediato si están en zonas bajo orden; a otras se les pide permanecer alertas. | **Comunicación a quienes llamaron.** No se extrapola a todos los hogares. | `911-065-1`, `911-065-5`, `911-1027-3`, `911-1032-1` |

**Fuente:** NIST, *A Case Study of the Camp Fire—Notification, Evacuation, Traffic, and Temporary Refuge Areas*, [Technical Note 2252, tabla 10](https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.2252.pdf). La tabla resume acciones de aviso; las descripciones aquí son paráfrasis en español. El informe principal y su [suplemento](https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.2252sup.pdf) contienen más sucesos, incluidos tráfico y refugios temporales.

## Cómo se usará sin atribuirle más precisión de la que tiene

1. **Reloj del modelo:** el evento inicial del escenario aún no está fijado. La llamada de 06:25 puede servir de referencia temporal documentada, pero no demuestra la hora de ignición. Al combinar fuego, evacuación y viento se hará una única conversión de hora y fecha con su zona horaria explícita.
2. **Alertas a agentes:** la hora de solicitud, la emisión institucional, la entrega de un mensaje y la decisión de salir son eventos diferentes. Solo se impondrán horas exactas a una zona si hay evidencia de su cobertura y del tipo de evento. Para recepción y demora individuales harán falta registros o rangos de escenario.
3. **Validación:** estos hitos pueden comprobar secuencias y ventanas plausibles. No proporcionan recuentos de vehículos, hogares evacuados o capacidad vial por minuto.
4. **Cruce con la hoja de fuego:** el identificador `911-001-1` aparece en la tabla de NIST de 2018 y también en el libro oficial de observaciones de fuego. Su presencia ayuda a detectar la discrepancia del año `2021` en la columna `Date` del libro; no autoriza a sustituir automáticamente todas sus fechas. Véase [auditoria_datos.md](auditoria_datos.md).

## Próxima extracción de evidencia

Revisar las tablas de tráfico, cierres y áreas temporales de refugio del NETTRA, consignando **hora, lugar, fuente y tipo de hecho**. Después, contrastar una muestra de puntos del libro de fuego con la narrativa y los mapas de NIST. Esos dos controles son necesarios antes de definir un sector y un horizonte reproducibles.
