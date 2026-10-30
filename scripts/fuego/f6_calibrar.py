"""Fase 6: calibra los parámetros del fuego con el conjunto de calibración.

Búsqueda en dos etapas: muestreo por hipercubo latino en todo el rango y
refinamiento local alrededor de los mejores candidatos. El objetivo es la
pérdida asimétrica de llegada en los bloques de calibración (ver evaluacion.py),
promediada sobre varias réplicas estocásticas, más una penalización proporcional a la
fracción del terreno fuera del perímetro final de CAL FIRE que el modelo quema
(terreno que nunca ardió en los 17 días). Sin esa restricción el MAE se
minimiza quemando casi todo el dominio, porque las observaciones dentro de
Paradise se reparten a lo largo de horas.
Las celdas de validación no se usan aquí.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
from scipy.stats import qmc

from comun import SALIDAS
from evaluacion import cargar_observadas, metricas, promedio
from modelo_fuego import Parametros, cargar_entradas, guardar_parametros, simular


# Parámetros calibrados y sus rangos. El resto queda en los valores de la literatura.
# p_h y p_foco se muestrean en escala logarítmica porque sus valores plausibles
# abarcan varios órdenes de magnitud con celdas de 100 m y pasos de 1 min.
RANGOS = {
    "p_h": (0.005, 0.5),
    "factor_viento": (0.5, 4.0),
    "p_foco": (0.0005, 0.05),
    "distancia_foco_m": (100.0, 3000.0),
    "p_veg_urbano": (-0.9, 0.5),
    "duracion_min": (5.0, 60.0),
}
LOGARITMICOS = {"p_h", "p_foco"}
SEMILLA = 20181108
# Minutos de penalización si ardiera todo el terreno fuera del perímetro final.
PESO_COMISION_MIN = 120.0


def a_unidad(nombre: str, valor: float) -> float:
    bajo, alto = RANGOS[nombre]
    if nombre in LOGARITMICOS:
        return (np.log(valor) - np.log(bajo)) / (np.log(alto) - np.log(bajo))
    return (valor - bajo) / (alto - bajo)


def desde_unidad(nombre: str, u: float) -> float:
    bajo, alto = RANGOS[nombre]
    if nombre in LOGARITMICOS:
        return float(np.exp(np.log(bajo) + u * (np.log(alto) - np.log(bajo))))
    return float(bajo + u * (alto - bajo))


def construir(valores: dict[str, float]) -> Parametros:
    base = Parametros()
    p_veg = (valores["p_veg_urbano"], *base.p_veg[1:])
    otros = {k: v for k, v in valores.items() if k != "p_veg_urbano"}
    return base.con(p_veg=p_veg, **otros)


def evaluar(entradas, observadas, valores, replicas, semilla_base) -> dict[str, float]:
    parametros = construir(valores)
    corridas = [metricas(simular(entradas, parametros, semilla_base + r), observadas,
                         entradas.horizonte_min, entradas.extra["dentro_perimetro"])
                for r in range(replicas)]
    resultado = {**valores, **promedio(corridas)}
    resultado["objetivo"] = (resultado["perdida_min"]
                             + PESO_COMISION_MIN * resultado["frac_fuera_perimetro_quemada"])
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--muestras", type=int, default=120)
    parser.add_argument("--refinamiento", type=int, default=60)
    parser.add_argument("--replicas", type=int, default=3)
    args = parser.parse_args()

    entradas = cargar_entradas()
    observadas = cargar_observadas("calibracion")
    nombres = list(RANGOS)
    rng = np.random.default_rng(SEMILLA)

    def valores_de(u: np.ndarray) -> dict[str, float]:
        return {n: desde_unidad(n, x) for n, x in zip(nombres, u)}

    resultados = []
    muestras = qmc.LatinHypercube(d=len(nombres), seed=rng).random(args.muestras)
    for i, fila in enumerate(muestras):
        resultados.append(evaluar(entradas, observadas, valores_de(fila), args.replicas, SEMILLA))
        if (i + 1) % 20 == 0:
            mejor = min(resultados, key=lambda r: r["objetivo"])
            print(f"etapa 1: {i + 1}/{args.muestras}, mejor objetivo {mejor['objetivo']:.1f} (pérdida {mejor['perdida_min']:.1f}, MAE {mejor['mae_min']:.1f} min, {mejor['area_quemada_ha']:.0f} ha, fuera de perímetro {mejor['frac_fuera_perimetro_quemada']:.0%})")

    # Refinamiento: perturbaciones gaussianas (10 % del rango) de los 5 mejores.
    for i in range(args.refinamiento):
        elite = sorted(resultados, key=lambda r: r["objetivo"])[:5]
        padre = np.array([a_unidad(n, elite[i % 5][n]) for n in nombres])
        hijo = np.clip(padre + rng.normal(0, 0.1, len(nombres)), 0, 1)
        resultados.append(evaluar(entradas, observadas, valores_de(hijo), args.replicas, SEMILLA))
        if (i + 1) % 20 == 0:
            mejor = min(resultados, key=lambda r: r["objetivo"])
            print(f"etapa 2: {i + 1}/{args.refinamiento}, mejor objetivo {mejor['objetivo']:.1f} (pérdida {mejor['perdida_min']:.1f}, MAE {mejor['mae_min']:.1f} min, {mejor['area_quemada_ha']:.0f} ha, fuera de perímetro {mejor['frac_fuera_perimetro_quemada']:.0%})")

    # Confirmación con más réplicas y semillas nuevas de los 5 mejores candidatos.
    finalistas = sorted(resultados, key=lambda r: r["objetivo"])[:5]
    confirmados = [evaluar(entradas, observadas, {n: f[n] for n in nombres}, 10, SEMILLA + 1000)
                   for f in finalistas]
    mejor = min(confirmados, key=lambda r: r["objetivo"])
    valores = {n: mejor[n] for n in nombres}
    guardar_parametros(construir(valores), {
        "calibracion": {
            "objetivo": "Pérdida asimétrica de llegada en bloques de calibración NIST + penalización por quemar fuera del perímetro final, 10 réplicas",
            "peso_comision_min": PESO_COMISION_MIN,
            "metricas_calibracion": {k: v for k, v in mejor.items() if k not in nombres},
            "rangos": RANGOS,
            "evaluaciones": len(resultados) + len(confirmados),
            "semilla": SEMILLA,
        }
    })

    SALIDAS.mkdir(parents=True, exist_ok=True)
    (SALIDAS / "calibracion_busqueda.json").write_text(
        json.dumps({"busqueda": resultados, "confirmacion": confirmados}, indent=1), encoding="utf-8")
    print(json.dumps(mejor, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
