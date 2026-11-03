# Simulación de incendio y evacuación: Camp Fire 2018

Proyecto final de **Modelación y Simulación**, Universidad del Valle de Guatemala, noviembre de 2026.

Modelo híbrido que acopla la propagación del fuego con la evacuación de la población en el Camp Fire (California, 8 de noviembre de 2018). Sirve para comparar escenarios de respuesta, por ejemplo avisar antes o perder una carretera.

| Entregable          | Enlace                                                                                 |
| ------------------- | -------------------------------------------------------------------------------------- |
| Video demostrativo  | https://youtu.be/TN2KcyJn2pY                                                           |
| Informe final (PDF) | [entregables/Informe_Final_MODSIM.pdf](entregables/Informe_Final_MODSIM.pdf)           |
| Presentación (PDF)  | [entregables/Presentacion_Final_MODSIM.pdf](entregables/Presentacion_Final_MODSIM.pdf) |

---

## El problema

En un incendio que alcanza zonas habitadas ocurren tres cosas a la vez: el fuego avanza, la población recibe la alerta y se prepara, y todos intentan salir por pocas carreteras. El Camp Fire llegó a Paradise en aproximadamente hora y media.

**Pregunta:** ¿cuántas personas logran salir antes de que llegue el fuego si cambia la hora de la alerta, se pierde una ruta o se amplía una salida?

## La solución

| Componente    | Técnica                                                  | Detalle                                                                                                                                                                                         |
| ------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fuego         | Autómata celular estocástico (Alexandridis et al., 2008) | Celdas de 100 m y pasos de 1 min. La ignición depende del combustible, la pendiente y el viento. Incluye brasas que saltan delante del frente. Calibrado y validado con observaciones del NIST. |
| Evacuación    | Agentes y eventos discretos                              | 50 314 grupos sobre la red vial real (TIGER/Line 2018). Colas por capacidad, cierres de vías por fuego y búsqueda de rutas con Dijkstra.                                                        |
| Acople        | Fuego → evacuación                                       | Una vía se cierra en el minuto en que el fuego alcanza cualquiera de sus celdas.                                                                                                                |
| Incertidumbre | Monte Carlo                                              | 30 simulaciones por escenario, con fuegos pareados entre escenarios e intervalos de confianza del 95 %.                                                                                         |

## Resultados principales

**Fuego (validación con 118 zonas no usadas en la calibración):**

- El fuego entra a Paradise en el minuto 110. Según el NIST, en el minuto 84.
- Quema el 12 % del terreno que en la realidad nunca ardió. Un modelo radial simple quema el 100 %.
- Sin brasas, el fuego llega a Paradise 71 minutos más tarde.

**Evacuación (120 simulaciones):**

| Escenario                   | Personas que salen antes del fuego |
| --------------------------- | ---------------------------------: |
| Base (alerta 07:50)         |                             42,9 % |
| Alerta 30 min antes         |                   46,1 % (+3,2 pp) |
| Skyway cerrado              |                  20,8 % (−22,1 pp) |
| Más capacidad en una salida |                   41,3 % (−1,6 pp) |

**Límites:** la hora de alerta, la preparación y las capacidades de evacuación son supuestos, no datos históricos. Los resultados sirven para comparar escenarios, no para predecir lo que ocurrió.

---

## Estructura

```
config/              Dominio, parámetros calibrados del fuego y escenarios de evacuación
data/procesado/      Grilla, observaciones NIST limpias y viento (versionados)
scripts/fuego/       f1 a f8: datos, modelo, calibración, validación y sensibilidad
scripts/evacuacion/  Red vial, motor de eventos y experimentos
scripts/demo_video.py  Demostración rápida (3 s)
salidas/fuego/       Llegada del fuego por simulación, figuras y validación
salidas/evacuacion_final/  Resultados de las 120 simulaciones y figuras
tests/               63 pruebas automáticas
docs/                Documentación técnica de cada módulo
entregables/         Informe y presentación
```

## Cómo correrlo

**Requisitos:** Python 3.12 (también funciona con 3.11) e internet solo para descargar los datos crudos.

### 1. Instalar

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-evacuacion.txt
```

macOS / Linux:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-evacuacion.txt
```

En los comandos siguientes, en macOS o Linux cambien `.venv\Scripts\python` por `.venv/bin/python` y `\` por `/`.

### 2. Verificar y ver el modelo funcionando

```powershell
.venv\Scripts\python -m unittest discover -s tests -v   # 63 pruebas, ~1 min
.venv\Scripts\python scripts\demo_video.py              # 3 simulaciones de fuego + resumen de evacuación
```

Esto funciona sin descargar nada, porque los datos procesados y los resultados ya están en el repositorio.

### 3. Reproducir todo desde cero

**Fuego** (unos 10 min en total):

```powershell
.venv\Scripts\python scripts\fuego\f1_descargar_capas.py      # descarga combustible, elevación, población y perímetro
.venv\Scripts\python scripts\fuego\f2_preparar_grilla.py
.venv\Scripts\python scripts\fuego\f3_observaciones_nist.py   # descarga y limpia observaciones NIST
.venv\Scripts\python scripts\fuego\f4_viento.py               # descarga viento ERA5
.venv\Scripts\python scripts\fuego\f6_calibrar.py             # ~5 min
.venv\Scripts\python scripts\fuego\f7_validar_exportar.py     # 30 simulaciones + validación
.venv\Scripts\python scripts\fuego\f8_sensibilidad.py         # ~2,5 min
```

**Evacuación** (las 120 simulaciones tardaron ~5 h con 4 procesos):

```powershell
.venv\Scripts\python scripts\evacuacion\red_vial.py --download
.venv\Scripts\python scripts\evacuacion\experimentos.py --smoke --replicas 1 --scenario base --output salidas\evacuacion_prueba
.venv\Scripts\python scripts\evacuacion\experimentos.py --replicas 30 --workers 2 --output salidas\evacuacion_reproduccion
```

El segundo comando es una prueba corta (~7 min) y el tercero es la corrida completa. Usen siempre una carpeta de salida nueva: el programa no sobrescribe resultados existentes. Las opciones completas están en [docs/modelo_evacuacion.md](docs/modelo_evacuacion.md).

Los datos crudos se guardan en `data/crudo/`, que no se sube al repositorio. Las semillas están registradas, así que los resultados se repiten exactamente.

## Datos

Todas las fuentes son públicas: LANDFIRE 2016 (combustible), USGS 3DEP (elevación), WorldPop 2018 (población), NIST TN 2135 apéndice F (observaciones del fuego), ERA5 vía Open-Meteo (viento), TIGER/Line 2018 (carreteras y límites) y el perímetro final de CAL FIRE vía NIFC.

## Documentación

- [Modelo del fuego](docs/modelo_fuego.md): datos, ecuaciones, calibración, validación y sensibilidad
- [Modelo de evacuación](docs/modelo_evacuacion.md): escenarios, métricas y resultados con intervalos
- [Red vial](docs/red_vial.md) y [motor de eventos](docs/motor_evacuacion.md)
- [Instrucciones del curso](docs/proyecto_final_modelacionysimulacion.md) y [evidencia de aprobación del tema](docs/aprobacion.pdf)
- Proceso: [avance parcial](docs/avance_parcial.md), [auditoría de datos](docs/auditoria_datos.md), [cronología de avisos](docs/cronologia_base.md), [prototipo sintético](docs/prototipo_avance.md) y [división del trabajo](docs/pendientes_equipo.md)

El registro de uso de inteligencia artificial está en la sección 5.2 del informe.

## Referencias principales

1. Maranghides, A., et al. (2021). _A case study of the Camp Fire: Fire progression timeline_ (NIST TN 2135). https://doi.org/10.6028/NIST.TN.2135
2. Maranghides, A., et al. (2023). _A case study of the Camp Fire: Notification, evacuation, traffic, and temporary refuge areas_ (NIST TN 2252). https://doi.org/10.6028/NIST.TN.2252
3. Alexandridis, A., Vakalis, D., Siettos, C. I., & Bafas, G. V. (2008). A cellular automata model for forest fire spread prediction. _Applied Mathematics and Computation, 204_(1), 191–201.
4. Dijkstra, E. W. (1959). A note on two problems in connexion with graphs. _Numerische Mathematik, 1_, 269–271.
5. Harris, C. R., et al. (2020). Array programming with NumPy. _Nature, 585_, 357–362.
