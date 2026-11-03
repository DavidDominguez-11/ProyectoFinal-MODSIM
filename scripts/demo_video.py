"""Demostración corta para el video: corre el fuego y resume la evacuación.

No escribe archivos. Corre tres simulaciones del fuego con los parámetros
calibrados y muestra los resultados guardados de las 120 corridas de evacuación
(las corridas completas tardan horas, por eso no se repiten aquí).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts" / "fuego"))

import numpy as np  # noqa: E402

from modelo_fuego import cargar_entradas, cargar_parametros, simular  # noqa: E402


NOMBRES = {
    "base": "Base (alerta 07:50)",
    "early_alert": "Alerta 30 min antes",
    "skyway_closed": "Skyway cerrado",
    "exit_capacity": "Más capacidad en una salida",
}


def main() -> None:
    print("=== Modelo del fuego (autómata celular calibrado) ===")
    entradas = cargar_entradas()
    parametros = cargar_parametros()
    paradise = entradas.extra["mascara_paradise"]
    for semilla in (1, 2, 3):
        inicio = time.perf_counter()
        llegada = simular(entradas, parametros, semilla=semilla)
        entrada = np.nanmin(llegada[paradise])
        print(f"Simulación {semilla}: {np.sum(~np.isnan(llegada)):,} ha quemadas a las 14:25 | "
              f"el fuego entra a Paradise en el minuto {entrada:.0f} | {time.perf_counter() - inicio:.1f} s")
    print("NIST registró los primeros fuegos en Paradise en el minuto 84.\n")

    print("=== Evacuación: 120 simulaciones (30 por escenario) ===")
    resumen = json.loads((RAIZ / "salidas" / "evacuacion_final" / "summary.json").read_text(encoding="utf-8"))
    for clave, nombre in NOMBRES.items():
        m = resumen["scenarios"][clave]
        fraccion = m["fraction_safe_before_fire"]
        print(f"{nombre:30s} seguras antes del fuego: {100 * fraccion['mean']:5.1f} % "
              f"[{100 * fraccion['ci95'][0]:.1f}; {100 * fraccion['ci95'][1]:.1f}] | "
              f"expuestas: {m['people_exposed']['mean']:,.0f}")


if __name__ == "__main__":
    main()
