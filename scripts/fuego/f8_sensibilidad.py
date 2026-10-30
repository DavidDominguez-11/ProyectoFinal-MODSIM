"""Fase 8: análisis de sensibilidad del modelo de fuego.

Parte de los parámetros calibrados y cambia un factor a la vez:
- paramétrica: cada parámetro calibrado x0.75 y x1.25 (p_veg urbano ±0.2);
- estructural: sin focos, sin pendiente, viento ERA5 sin factor, paso de 2 min
  y celdas de 200 m.
Para cada caso se corren las mismas semillas y se reportan la pérdida en
validación, el área quemada, la comisión fuera del perímetro final y el minuto
en que el fuego entra a Paradise (dato que usa el módulo de evacuación).
"""

from __future__ import annotations

import argparse
import csv
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from comun import SALIDAS
from evaluacion import cargar_observadas, metricas, promedio
from modelo_fuego import Entradas, cargar_entradas, cargar_parametros, simular


SEMILLA_BASE = 5000


def agregar_200m(entradas: Entradas) -> Entradas:
    """Grilla de 200 m: clase por moda de cada bloque 2x2, elevación media."""
    filas, columnas = (s // 2 * 2 for s in entradas.clase.shape)

    def bloques(arreglo):
        return arreglo[:filas, :columnas].reshape(filas // 2, 2, columnas // 2, 2).swapaxes(1, 2).reshape(
            filas // 2, columnas // 2, 4)

    clases = bloques(entradas.clase).astype(int) + 1  # -1 -> 0 para bincount
    moda = np.apply_along_axis(lambda v: np.bincount(v, minlength=8).argmax(), 2, clases) - 1
    return Entradas(
        clase=moda.astype(np.int8),
        elevacion=bloques(entradas.elevacion).mean(axis=2),
        resolucion=entradas.resolucion * 2,
        ignicion=(entradas.ignicion[0] // 2, entradas.ignicion[1] // 2),
        viento_minuto=entradas.viento_minuto,
        viento_velocidad=entradas.viento_velocidad,
        viento_desde_grados=entradas.viento_desde_grados,
        horizonte_min=entradas.horizonte_min,
    )


def a_100m(llegada: np.ndarray, forma: tuple[int, int]) -> np.ndarray:
    fina = np.full(forma, np.nan, dtype=np.float32)
    ampliada = np.repeat(np.repeat(llegada, 2, axis=0), 2, axis=1)
    fina[:ampliada.shape[0], :ampliada.shape[1]] = ampliada
    return fina


def casos(base) -> list[tuple[str, str, object]]:
    lista = [("base", "base", base)]
    for nombre in ["p_h", "factor_viento", "p_foco", "distancia_foco_m", "duracion_min"]:
        for factor in (0.75, 1.25):
            lista.append(("parametrica", f"{nombre} x{factor}", base.con(**{nombre: getattr(base, nombre) * factor})))
    for delta in (-0.2, 0.2):
        p_veg = (base.p_veg[0] + delta, *base.p_veg[1:])
        lista.append(("parametrica", f"p_veg urbano {delta:+.1f}", base.con(p_veg=p_veg)))
    lista += [
        ("estructural", "sin focos", base.con(p_foco=0.0)),
        ("estructural", "sin pendiente", base.con(a_pendiente=0.0)),
        ("estructural", "viento ERA5 sin factor", base.con(factor_viento=1.0)),
        ("estructural", "paso 2 min", base.con(paso_min=2.0)),
        ("estructural", "celdas 200 m", base),
    ]
    return lista


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicas", type=int, default=10)
    args = parser.parse_args()

    entradas = cargar_entradas()
    gruesa = agregar_200m(entradas)
    base = cargar_parametros()
    validacion = cargar_observadas("validacion")
    perimetro = entradas.extra["dentro_perimetro"]
    paradise = entradas.extra["mascara_paradise"]

    filas = []
    for tipo, nombre, parametros in casos(base):
        corridas, entrada_paradise = [], []
        for r in range(args.replicas):
            if nombre == "celdas 200 m":
                llegada = a_100m(simular(gruesa, parametros, SEMILLA_BASE + r), entradas.clase.shape)
            else:
                llegada = simular(entradas, parametros, SEMILLA_BASE + r)
            corridas.append(metricas(llegada, validacion, entradas.horizonte_min, perimetro))
            en_paradise = llegada[paradise]
            entrada_paradise.append(np.nanmin(en_paradise) if np.any(~np.isnan(en_paradise)) else np.nan)
        fila = {"tipo": tipo, "caso": nombre, **promedio(corridas),
                "entrada_paradise_min": float(np.nanmedian(entrada_paradise))}
        filas.append(fila)
        print(f"{nombre:28s} pérdida {fila['perdida_min']:6.1f}  área {fila['area_quemada_ha']:8.0f} ha  "
              f"fuera {fila['frac_fuera_perimetro_quemada']:.0%}  Paradise {fila['entrada_paradise_min']:.0f} min")

    SALIDAS.mkdir(parents=True, exist_ok=True)
    with open(SALIDAS / "sensibilidad.csv", "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0]))
        escritor.writeheader()
        escritor.writerows(filas)
    (SALIDAS / "sensibilidad.json").write_text(
        json.dumps({"replicas": args.replicas, "semilla_base": SEMILLA_BASE, "casos": filas},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    referencia = filas[0]
    otros = filas[1:]
    figura, ejes = plt.subplots(1, 3, figsize=(16, 6), sharey=True)
    etiquetas = [f["caso"] for f in otros]
    posiciones = np.arange(len(otros))
    for eje, (clave, titulo) in zip(ejes, [
        ("perdida_min", "Pérdida en validación (min)"),
        ("area_quemada_ha", "Área quemada a las 14:25 (ha)"),
        ("entrada_paradise_min", "Minuto de entrada a Paradise"),
    ]):
        cambio = [f[clave] - referencia[clave] for f in otros]
        colores = ["tab:gray" if f["tipo"] == "estructural" else "tab:blue" for f in otros]
        eje.barh(posiciones, cambio, color=colores)
        eje.axvline(0, color="k", lw=0.8)
        eje.set_title(f"{titulo}\nbase = {referencia[clave]:.0f}; barra = cambio")
    ejes[0].set_yticks(posiciones, etiquetas)
    ejes[0].invert_yaxis()
    figura.suptitle("Sensibilidad un factor a la vez (azul: paramétrica, gris: estructural)")
    figura.tight_layout()
    figura.savefig(SALIDAS / "fig_sensibilidad.png", dpi=130)


if __name__ == "__main__":
    main()
