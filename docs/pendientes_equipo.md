# Pendientes del equipo: qué le toca a cada quien

**Actualizado:** 29 de octubre de 2026
**Entrega final en Canvas:** 2 de noviembre de 2026

El trabajo está dividido en tres partes. Cada persona termina la suya completa, sin mezclar tareas con las demás. Las partes se conectan por archivos acordados (ver "Qué se entregan entre partes").

| Parte | Responsable | Estado |
|---|---|---|
| 1. Datos reales y modelo del fuego | Persona 1 | ✅ Terminada |
| 2. Evacuación, red vial y experimentos | Persona 2 | ⏳ Pendiente |
| 3. Evidencia del caso y entregables | Persona 3 | ⏳ Pendiente |

---

## Parte 1: fuego (terminada)

Ya existe el modelo del fuego del Camp Fire. Cubre de las 06:25 a las 14:25 del 8 de noviembre de 2018, sobre una grilla de celdas de 100 m que incluye Pulga, Concow, Paradise y Magalia. Está calibrado y validado con observaciones de NIST, y tiene análisis de sensibilidad.

- Documentación completa, con texto listo para el informe: [modelo_fuego.md](modelo_fuego.md)
- Archivos que usa la Parte 2: carpeta [salidas/fuego/](../salidas/fuego/) (ver [contrato.json](../salidas/fuego/contrato.json))
- Población por celda: `data/procesado/grilla_fuego.npz` (campo `poblacion`), en la misma grilla que el fuego

---

## Parte 2: evacuación, red vial y experimentos

**Objetivo:** simular cómo evacúan las personas por las carreteras mientras avanza el fuego, y comparar escenarios.

### Tareas

1. **Red vial.**
   - Convertir las carreteras TIGER/Line 2018 de Butte County en un grafo dirigido. El enlace ya está en [scripts/auditar_geografia.py](../scripts/auditar_geografia.py).
   - Recortarlo al dominio: UTM 10N, límites en [config/dominio.json](../config/dominio.json).
   - Comprobar que la red esté conectada y definir las salidas del dominio. Las principales son Skyway hacia Chico, Clark Rd, Pentz Rd y Neal Rd.
   - Asignar a cada tramo largo, velocidad y capacidad. Si no hay dato documentado, usar un supuesto explícito y decir de dónde sale.
2. **Grupos de evacuados.**
   - Crearlos a partir de la población por celda. Cada agente representa un hogar o grupo con un peso en personas.
   - Darles un retraso de salida aleatorio, con su distribución justificada.
   - La población debe conservarse en todo momento.
3. **Simulación de evacuación por eventos.**
   - Alerta, preparación, salida, avance por tramos con colas cuando se llena la capacidad, cambio de ruta ante cierres, y llegada a destino.
   - Distinguir **refugio temporal** de **destino seguro**.
4. **Acople con el fuego.**
   - Un tramo o celda está en peligro en el minuto *t* si `0 <= llegada_min[r, fila, col] <= t` (ver [contrato.json](../salidas/fuego/contrato.json)).
   - Cerrar los tramos alcanzados por el fuego y registrar la exposición potencial de los agentes.
5. **Monte Carlo.**
   - Al menos 30 réplicas por escenario, con semillas registradas.
   - **Cada réplica de evacuación debe usar una réplica de fuego distinta** (hay 30 en `llegada_replicas.npz`), no solo la mediana.
6. **Escenarios.** Como mínimo:
   - base;
   - alerta más temprana (por ejemplo, 30 min antes);
   - cierre o apertura de una ruta;
   - más capacidad en un destino.

   Cambiar **un solo factor** a la vez respecto de la base.
7. **Métricas y gráficas.** Para cada escenario, con intervalos de confianza:
   - fracción de personas que llega a un destino seguro antes del fuego;
   - distribución del tiempo de evacuación;
   - personas con exposición potencial;
   - longitud y duración de las colas.
8. **Pruebas automáticas** en `tests/`:
   - se conserva la población;
   - ningún tramo supera su capacidad;
   - nadie transita por un tramo cerrado;
   - los resultados se repiten con la misma semilla.
9. **Redacción.** Escribir para el informe las secciones de solución, arquitectura y resultados de su parte, con un documento parecido a [modelo_fuego.md](modelo_fuego.md).

### Qué necesita de la Parte 3

Una tabla de parámetros con su fuente: horas de aviso por zona, cierres de vías con hora, y ubicación y capacidad de refugios y albergues. Mientras llega, se puede avanzar con supuestos y reemplazarlos después.

### Base de partida

El prototipo sintético [scripts/prototipo_hibrido.py](../scripts/prototipo_hibrido.py) ya acopla una grilla de fuego, tramos con capacidad y grupos de evacuados. Sirve como esqueleto.

---

## Parte 3: evidencia del caso y entregables

**Objetivo:** reunir los datos históricos que necesita la evacuación y producir todo lo que se entrega en Canvas.

### Tareas

1. **Evidencia para la Parte 2** (**entregar lo antes posible, idealmente el 30 de octubre**).
   - Extraer del informe NETTRA de NIST (TN 2252) y del *After Action Report* del condado de Butte:
     - horas de aviso y órdenes de evacuación por zona (ya hay un avance en [cronologia_base.md](cronologia_base.md));
     - cierres de vías con hora;
     - refugios temporales y albergues, con ubicación y capacidad si aparece.
   - Entregarlo como una tabla (CSV o Markdown) con la fuente y la página de cada dato. Lo que no aparezca se marca como "sin dato".
2. **Verificaciones pendientes de la Parte 1:**
   - Confirmar en NIST TN 2135 el significado de los códigos de tipo de fuego V, S, R, C y O. Se dedujeron de las descripciones.
   - Revisar la cita de Alexandridis et al. (2008).
3. **Informe final en PDF**, con las 8 secciones de la guía:
   1. descripción del problema;
   2. análisis;
   3. propuesta de solución;
   4. descripción de la solución;
   5. herramientas aplicadas;
   6. resultados;
   7. conclusiones;
   8. bibliografía.

   Debe incluir el **enlace visible al repositorio público**. Conviene armar una plantilla desde el inicio para que las partes 1 y 2 peguen ahí sus secciones.
4. **Registro de uso de IA**, que es obligatorio. Juntar los prompts más relevantes de cada integrante. Para cada uno: si funcionó o falló, por qué, y cómo se verificó. La sección 9 de [modelo_fuego.md](modelo_fuego.md) ya tiene el de la Parte 1.
5. **Diapositivas en PDF**, **máximo 10**: problema, solución propuesta, modelo, herramientas, resultados y conclusiones. Valen 5 de los 30 puntos.
6. **Video demostrativo:** el programa corriendo, más la explicación de la metodología y los hallazgos.
7. **Repositorio:**
   - comprobar que es público;
   - actualizar el [README](../README.md) con instrucciones claras para reproducir todo;
   - quitar del README las frases que dicen que aún no hay simulación calibrada.

---

## Qué se entregan entre partes

| De | Para | Qué | Cuándo |
|---|---|---|---|
| Parte 1 | Parte 2 | Llegada del fuego por réplica y población por celda | ✅ Listo |
| Parte 3 | Parte 2 | Tabla de avisos, cierres y refugios con fuentes | 30 de octubre |
| Parte 3 | Partes 1 y 2 | Plantilla del informe | 30 de octubre |
| Parte 2 | Parte 3 | Resultados, gráficas y su sección del informe | 1 de noviembre |
| Todas | Todas | Revisión final y ensayo de la presentación | 2 de noviembre |

## Calendario

| Día | Parte 2 | Parte 3 |
|---|---|---|
| 30 oct | Red vial y simulación de evacuación con fuego real | Tabla de evidencia y plantilla del informe |
| 31 oct | Monte Carlo y escenarios | Informe (secciones 1, 2, 5, 8), diapositivas y registro de IA |
| 1 nov | Métricas, gráficas y redacción de su sección | Integra el informe, video y repositorio |
| 2 nov | Revisión final y ensayo, **todas juntas** | ← |

## Para la presentación oral (10 de 30 puntos)

Cualquiera puede recibir una pregunta sobre cualquier parte. Antes del 2 de noviembre, cada persona debe explicarles su parte a las demás. Como mínimo, todas deben poder responder:

- qué es el autómata celular del fuego y cómo se calibró;
- cómo funciona la evacuación;
- qué muestran los resultados de los escenarios;
- cuáles son las principales limitaciones del modelo.
