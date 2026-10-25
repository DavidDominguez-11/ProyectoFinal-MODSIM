# Prototipo ejecutable del avance parcial

**Clasificación:** demostración sintética de integración. Ninguna coordenada, hora, población, velocidad, capacidad ni regla de propagación de este prototipo representa una medición del Camp Fire. Sus resultados no permiten concluir que adelantar una alerta histórica habría salvado a un número determinado de personas.

## Qué ejecuta

El programa [prototipo_hibrido.py](../scripts/prototipo_hibrido.py) une tres componentes en un reloj discreto de un minuto:

1. **Fuego celular:** grilla de 6 × 3 celdas. Parte de `(0,0)` en el minuto 0. Cada dos minutos, cada celda alcanzada transmite fuego a su vecina al este y al sur, cuando existe. Las celdas permanecen marcadas como alcanzadas.
2. **Red y colas:** una ruta dirigida pasa por los nodos `(1,2)` a `(5,2)` y termina en una salida absorbente fuera de la grilla. Cada tramo tarda dos minutos y admite un grupo a la vez. Un grupo que intenta entrar a un tramo ocupado espera en su nodo.
3. **Agentes:** A, B y C representan, respectivamente, 2, 3 y 1 personas ponderadas. Empiezan en los nodos 1, 1 y 2, con demoras de preparación de 1, 2 y 1 minutos. No son hogares reales.

Al inicio de cada minuto se actualiza el fuego cuando corresponde, se procesan arribos, se registra exposición potencial y después se admiten nuevas entradas a los tramos. Un grupo se considera **expuesto potencialmente** si al inicio del minuto está sobre una celda alcanzada o atraviesa un tramo cuyo extremo está alcanzado. Esta marca no detiene al grupo ni representa lesión o muerte. Por eso una persona puede figurar a la vez en la métrica acumulada de exposición y en la métrica de llegada final. El programa comprueba durante la corrida que ninguna arista contiene más de un grupo y que el total poblacional se conserva.

## Comparación reproducible

La única diferencia entre escenarios es el minuto de alerta, contado desde una ignición **inventada** del prototipo: minuto 4 en la base y minuto 0 en la alternativa. El adelanto de cuatro minutos es un valor de demostración, no una propuesta inferida del informe histórico.

| Métrica al minuto 20 | Base | Alerta adelantada |
|---|---:|---:|
| Personas ponderadas iniciales | 6 | 6 |
| Personas ponderadas que llegaron a la salida | 6 | 6 |
| Personas ponderadas con exposición potencial acumulada | 5 | 0 |
| Espera acumulada en cola, en grupos × minuto | 1 | 1 |
| Primera llegada del fuego al nodo vial 1 | Minuto 6 | Minuto 6 |

**Lectura correcta:** en este ejemplo construido, adelantar la alerta evita la exposición potencial de dos grupos que suman cinco personas ponderadas. Es una prueba de que los componentes interactúan y de que las métricas cambian al variar una entrada. El resultado depende por completo de las reglas y cifras supuestas.

La salida completa, incluidos tiempos por grupo y serie temporal, se guarda en [resultado_prototipo.json](resultado_prototipo.json). La ejecución no requiere paquetes externos:

```powershell
python scripts/prototipo_hibrido.py --output docs/resultado_prototipo.json
python -m unittest discover -s tests -v
```

## Qué demuestra y qué falta

Este corte funcional demuestra: actualización de fuego en grilla, movimiento sobre un grafo, espera por capacidad, estados de grupos, dos escenarios comparables y salida cuantitativa reproducible. Hay pruebas de conservación, capacidad, llegada del fuego a la vía y repetibilidad.

Para el proyecto final aún faltan geografía real alineada, combustible y pendiente interpretados, viento histórico, reglas de propagación justificadas y posible *spotting*, red vial con conectividad y cierres, fuentes para destinos y capacidad, brigadas, calibración y contraste independientes, sensibilidad y múltiples réplicas. El modelo sintético actual es determinista, por lo que **no realiza Monte Carlo**. Tampoco valida seguridad física: el indicador de exposición es una abstracción para comprobar el acoplamiento.

## Registro de uso de IA de esta iteración

Se solicitó a la IA implementar el prototipo mínimo mencionado como siguiente hito del avance. La IA propuso la grilla, la vía y las cifras sintéticas, escribió el programa y documentó su carácter no histórico. La revisión humana del equipo debe comprobar las reglas y decidir cuáles se conservan o sustituyen al construir el modelo con datos del caso.
