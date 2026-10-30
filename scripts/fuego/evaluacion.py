"""Métricas de contraste entre llegada simulada y llegada observada por NIST.

Las observaciones mezclan el paso del frente con estructuras que se encienden
horas después dentro de Paradise. Para comparar la llegada del frente:

1. Se agrega en bloques de BLOQUE_CELDAS x BLOQUE_CELDAS celdas (500 m): la
   llegada observada del bloque es su primera observación y la simulada es la
   primera celda del bloque que arde.
2. La observación es una cota superior (alguien vio el fuego ya presente), por
   lo que llegar tarde se penaliza con peso 1 y llegar antes con PESO_ANTICIPO.

Un bloque que no arde dentro del horizonte se cuenta como si llegara en
horizonte + PENALIZACION_MIN.
"""

from __future__ import annotations

import csv

import numpy as np

from comun import PROCESADO


BLOQUE_CELDAS = 5
PENALIZACION_MIN = 60.0
TOLERANCIA_MIN = 60.0
PESO_ANTICIPO = 0.5


def cargar_observadas(conjunto: str | None = None) -> dict[str, np.ndarray]:
    """Llegada observada por bloque de 500 m (fila y columna del bloque)."""
    with open(PROCESADO / "llegada_observada_celdas.csv", encoding="utf-8") as archivo:
        filas = [f for f in csv.DictReader(archivo) if conjunto in (None, f["conjunto"])]
    bloques: dict[tuple[int, int], tuple[float, float]] = {}
    for f in filas:
        clave = (int(f["fila"]) // BLOQUE_CELDAS, int(f["col"]) // BLOQUE_CELDAS)
        minuto, ventana = float(f["minuto_llegada_obs"]), float(f["ventana_min"])
        if clave not in bloques or minuto < bloques[clave][0]:
            bloques[clave] = (minuto, ventana)
    claves = sorted(bloques)
    return {
        "fila": np.array([c[0] for c in claves]),
        "col": np.array([c[1] for c in claves]),
        "minuto": np.array([bloques[c][0] for c in claves]),
        "ventana": np.array([bloques[c][1] for c in claves]),
    }


def llegada_por_bloque(llegada: np.ndarray) -> np.ndarray:
    """Primera llegada de cada bloque; NaN si ninguna celda del bloque arde."""
    filas, columnas = llegada.shape
    alto = -(-filas // BLOQUE_CELDAS) * BLOQUE_CELDAS
    ancho = -(-columnas // BLOQUE_CELDAS) * BLOQUE_CELDAS
    relleno = np.full((alto, ancho), np.inf)
    relleno[:filas, :columnas] = np.where(np.isnan(llegada), np.inf, llegada)
    minimo = relleno.reshape(alto // BLOQUE_CELDAS, BLOQUE_CELDAS,
                             ancho // BLOQUE_CELDAS, BLOQUE_CELDAS).min(axis=(1, 3))
    return np.where(np.isinf(minimo), np.nan, minimo)


def perdida(error: np.ndarray) -> np.ndarray:
    return np.where(error > 0, error, -PESO_ANTICIPO * error)


def metricas(llegada: np.ndarray, observadas: dict[str, np.ndarray], horizonte: float,
             dentro_perimetro: np.ndarray | None = None) -> dict[str, float]:
    simulada = llegada_por_bloque(llegada)[observadas["fila"], observadas["col"]]
    alcanzada = ~np.isnan(simulada)
    simulada = np.where(alcanzada, simulada, horizonte + PENALIZACION_MIN)
    error = simulada - observadas["minuto"]
    quemada = ~np.isnan(llegada)
    resultado = {
        "perdida_min": float(np.mean(perdida(error))),
        "mae_min": float(np.mean(np.abs(error))),
        "sesgo_min": float(np.mean(error)),
        "frac_dentro_tolerancia": float(np.mean(np.abs(error) <= TOLERANCIA_MIN)),
        "frac_alcanzada": float(np.mean(alcanzada)),
        # Consistente con la cota superior: la simulación llega antes de la observación + ventana.
        "frac_llega_antes_de_obs": float(np.mean(simulada <= observadas["minuto"] + observadas["ventana"])),
        "area_quemada_ha": float(np.sum(quemada)),
    }
    if dentro_perimetro is not None:
        # Comisión: terreno que el modelo quema y que nunca ardió en todo el incendio.
        resultado["frac_fuera_perimetro_quemada"] = float(np.mean(quemada[~dentro_perimetro]))
    return resultado


def promedio(lista: list[dict[str, float]]) -> dict[str, float]:
    return {clave: float(np.mean([m[clave] for m in lista])) for clave in lista[0]}
