"""Fase 7: Monte Carlo con parámetros calibrados, validación y exportación.

1. Corre N réplicas con config/parametros_fuego.json y semillas registradas.
2. Valida contra los bloques NIST reservados (conjunto "validacion"), que no se
   usaron en la calibración, y compara con dos referencias evaluadas igual:
   - modelo nulo radial: llegada = distancia a la ignición / velocidad constante,
     con la velocidad ajustada en el conjunto de calibración;
   - piso de ruido: error al predecir cada bloque con la mediana de sus bloques
     vecinos observados a 1 km o menos (variabilidad propia de los datos).
3. Exporta para el módulo de evacuación (contrato en salidas/fuego/contrato.json).
"""

from __future__ import annotations

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio

from comun import SALIDAS
from evaluacion import (BLOQUE_CELDAS, PENALIZACION_MIN, cargar_observadas, llegada_por_bloque,
                        metricas, perdida)
from modelo_fuego import cargar_entradas, cargar_parametros, simular


SEMILLA_BASE = 1000
SIN_LLEGADA = -1


def intervalo(valores: list[float]) -> dict[str, float]:
    arreglo = np.asarray(valores)
    media = float(arreglo.mean())
    mitad = 1.96 * float(arreglo.std(ddof=1)) / np.sqrt(len(arreglo))
    return {"media": round(media, 3), "ic95": [round(media - mitad, 3), round(media + mitad, 3)]}


def centro_bloque(obs) -> tuple[np.ndarray, np.ndarray]:
    """Fila y columna (en celdas) del centro de cada bloque observado."""
    mitad = (BLOQUE_CELDAS - 1) / 2
    return obs["fila"] * BLOQUE_CELDAS + mitad, obs["col"] * BLOQUE_CELDAS + mitad


def resumen_error(prediccion: np.ndarray, obs) -> dict[str, float]:
    error = prediccion - obs["minuto"]
    return {"perdida_min": float(np.mean(perdida(error))), "mae_min": float(np.mean(np.abs(error)))}


def modelo_radial(ignicion, resolucion, cal, val, horizonte, dentro_perimetro) -> dict[str, float]:
    def prediccion(obs, velocidad):
        fila, col = centro_bloque(obs)
        distancia = np.hypot(fila - ignicion[0], col - ignicion[1]) * resolucion
        return np.minimum(distancia / velocidad, horizonte + PENALIZACION_MIN)

    velocidades = np.arange(10.0, 301.0)  # m/min
    perdidas = [np.mean(perdida(prediccion(cal, v) - cal["minuto"])) for v in velocidades]
    mejor = float(velocidades[int(np.argmin(perdidas))])
    filas, columnas = np.indices(dentro_perimetro.shape)
    quemada = np.hypot(filas - ignicion[0], columnas - ignicion[1]) * resolucion / mejor <= horizonte
    return {"velocidad_m_min": mejor, **resumen_error(prediccion(val, mejor), val),
            "area_quemada_ha": float(quemada.sum()),
            "frac_fuera_perimetro_quemada": float(np.mean(quemada[~dentro_perimetro]))}


def piso_de_ruido(obs, radio_bloques: float = 2) -> dict[str, float]:
    prediccion, usados = [], []
    for i in range(len(obs["minuto"])):
        cerca = np.hypot(obs["fila"] - obs["fila"][i], obs["col"] - obs["col"][i]) <= radio_bloques
        cerca[i] = False
        if cerca.sum() >= 3:
            prediccion.append(np.median(obs["minuto"][cerca]))
            usados.append(i)
    sub = {k: v[usados] for k, v in obs.items()}
    return {"bloques_evaluados": len(usados), **resumen_error(np.array(prediccion), sub)}


def guardar_tif(ruta, datos, grilla, nodata) -> None:
    with rasterio.open(ruta, "w", driver="GTiff", height=grilla.alto, width=grilla.ancho, count=1,
                       dtype=datos.dtype, crs=grilla.crs, transform=grilla.transform,
                       nodata=nodata, compress="deflate") as destino:
        destino.write(datos, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicas", type=int, default=30)
    args = parser.parse_args()

    entradas = cargar_entradas()
    parametros = cargar_parametros()
    grilla = entradas.extra["grilla"]
    horizonte = entradas.horizonte_min
    calibracion = cargar_observadas("calibracion")
    validacion = cargar_observadas("validacion")

    llegadas = np.stack([simular(entradas, parametros, SEMILLA_BASE + r) for r in range(args.replicas)])
    met_val = [metricas(l, validacion, horizonte, entradas.extra["dentro_perimetro"]) for l in llegadas]
    met_cal = [metricas(l, calibracion, horizonte, entradas.extra["dentro_perimetro"]) for l in llegadas]

    validacion_resumen = {
        "replicas": args.replicas,
        "semillas": [SEMILLA_BASE, SEMILLA_BASE + args.replicas - 1],
        "bloques_500m_validacion": int(len(validacion["minuto"])),
        "bloques_500m_calibracion": int(len(calibracion["minuto"])),
        "validacion": {k: intervalo([m[k] for m in met_val]) for k in met_val[0]},
        "calibracion": {k: intervalo([m[k] for m in met_cal]) for k in met_cal[0]},
        "referencias": {
            "modelo_radial": modelo_radial(entradas.ignicion, grilla.resolucion, calibracion, validacion,
                                           horizonte, entradas.extra["dentro_perimetro"]),
            "piso_de_ruido_validacion": piso_de_ruido(validacion),
        },
    }

    # Exportación para el módulo de evacuación.
    SALIDAS.mkdir(parents=True, exist_ok=True)
    enteros = np.where(np.isnan(llegadas), SIN_LLEGADA, np.round(llegadas)).astype(np.int16)
    np.savez_compressed(SALIDAS / "llegada_replicas.npz", llegada_min=enteros,
                        semillas=np.arange(SEMILLA_BASE, SEMILLA_BASE + args.replicas))
    probabilidad = np.mean(~np.isnan(llegadas), axis=0).astype(np.float32)
    with np.errstate(all="ignore"):
        mediana = np.nanmedian(np.where(np.isnan(llegadas), np.inf, llegadas), axis=0)
    mediana = np.where(np.isfinite(mediana), mediana, SIN_LLEGADA).astype(np.float32)
    guardar_tif(SALIDAS / "llegada_mediana_min.tif", mediana, grilla, SIN_LLEGADA)
    guardar_tif(SALIDAS / "probabilidad_quema.tif", probabilidad, grilla, None)
    contrato = {
        "descripcion": "Salida del módulo de fuego para el módulo de evacuación.",
        "crs": grilla.crs,
        "transform_gdal": list(grilla.transform.to_gdal()),
        "forma_filas_columnas": [grilla.alto, grilla.ancho],
        "resolucion_m": grilla.resolucion,
        "minuto_cero": "2018-11-08T06:25 hora local (ignición)",
        "horizonte_min": horizonte,
        "archivos": {
            "llegada_replicas.npz": "llegada_min[replica, fila, col]: minuto entero de ignición; -1 = no arde en el horizonte. 'semillas' lista la semilla de cada réplica.",
            "llegada_mediana_min.tif": "Mediana entre réplicas del minuto de llegada; -1 = no arde en más de la mitad de las réplicas.",
            "probabilidad_quema.tif": "Fracción de réplicas en que la celda arde dentro del horizonte.",
        },
        "uso": "Una celda está en peligro en el minuto t de la réplica r si 0 <= llegada_min[r, f, c] <= t. "
               "Fila 0 es el norte; coordenada x = xmin + (col + 0.5) * res, y = ymax - (fila + 0.5) * res.",
        "parametros": "config/parametros_fuego.json",
    }
    (SALIDAS / "contrato.json").write_text(json.dumps(contrato, ensure_ascii=False, indent=2), encoding="utf-8")
    (SALIDAS / "validacion.json").write_text(json.dumps(validacion_resumen, ensure_ascii=False, indent=2),
                                             encoding="utf-8")

    figuras(llegadas, mediana, probabilidad, entradas, validacion, calibracion)
    print(json.dumps(validacion_resumen, ensure_ascii=False, indent=2))


def figuras(llegadas, mediana, probabilidad, entradas, validacion, calibracion) -> None:
    grilla = entradas.extra["grilla"]
    horizonte = entradas.horizonte_min
    extension = [grilla.xmin, grilla.xmax, grilla.ymin, grilla.ymax]

    def coordenadas(obs):
        fila, col = centro_bloque(obs)
        return (grilla.xmin + (col + 0.5) * grilla.resolucion,
                grilla.ymax - (fila + 0.5) * grilla.resolucion)

    figura, ejes = plt.subplots(1, 2, figsize=(15, 5.5))
    eje = ejes[0]
    imagen = eje.imshow(np.ma.masked_less(mediana, 0), cmap="inferno_r", vmin=0, vmax=horizonte,
                        extent=extension)
    eje.contour(entradas.extra["dentro_perimetro"], levels=[0.5], colors="royalblue", linewidths=1,
                linestyles="--", extent=extension, origin="upper")
    for obs, marcador, nombre in [(calibracion, "o", "calibración"), (validacion, "^", "validación")]:
        x, y = coordenadas(obs)
        eje.scatter(x, y, c=obs["minuto"], cmap="inferno_r", vmin=0, vmax=horizonte, s=14,
                    marker=marcador, edgecolors="k", linewidths=0.4, label=f"NIST {nombre} (bloque 500 m)")
    eje.legend(loc="lower right", fontsize=8)
    eje.set_title("Llegada simulada (mediana de réplicas) y observada, minutos desde 06:25")
    figura.colorbar(imagen, ax=eje, shrink=0.8, label="minutos")

    eje = ejes[1]
    imagen = eje.imshow(probabilidad, cmap="Reds", vmin=0, vmax=1, extent=extension)
    eje.contour(entradas.extra["dentro_perimetro"], levels=[0.5], colors="royalblue", linewidths=1,
                linestyles="--", extent=extension, origin="upper")
    eje.set_title(f"Probabilidad de arder antes de 14:25 ({len(llegadas)} réplicas)")
    figura.colorbar(imagen, ax=eje, shrink=0.8)
    figura.suptitle("Azul discontinuo: perímetro final CAL FIRE (26 nov 2018)")
    figura.tight_layout()
    figura.savefig(SALIDAS / "fig_llegada_mapa.png", dpi=130)

    figura, ejes = plt.subplots(1, 2, figsize=(13, 5))
    por_bloque = np.stack([llegada_por_bloque(l)[validacion["fila"], validacion["col"]] for l in llegadas])
    simulada = np.median(np.where(np.isnan(por_bloque), horizonte + PENALIZACION_MIN, por_bloque), axis=0)
    ejes[0].scatter(validacion["minuto"], simulada, s=12, alpha=0.6)
    ejes[0].plot([0, horizonte], [0, horizonte], "k--", lw=1)
    ejes[0].fill_between([0, horizonte], [-60, horizonte - 60], [60, horizonte + 60], color="0.85",
                         label="±60 min")
    ejes[0].set_xlabel("Llegada observada NIST (min)")
    ejes[0].set_ylabel("Llegada simulada, mediana (min)")
    ejes[0].set_title("Validación: bloques de 500 m no usados en la calibración")
    ejes[0].legend()

    minutos = np.arange(0, horizonte + 1, 5)
    area = np.array([[np.sum(l <= m) for m in minutos] for l in llegadas])
    ejes[1].fill_between(minutos, np.percentile(area, 5, axis=0), np.percentile(area, 95, axis=0),
                         alpha=0.3, label="percentiles 5-95")
    ejes[1].plot(minutos, np.median(area, axis=0), label="mediana")
    ejes[1].set_xlabel("Minutos desde la ignición")
    ejes[1].set_ylabel("Área quemada (ha)")
    ejes[1].set_title("Crecimiento del área quemada entre réplicas")
    ejes[1].legend()
    figura.tight_layout()
    figura.savefig(SALIDAS / "fig_validacion.png", dpi=130)


if __name__ == "__main__":
    main()
