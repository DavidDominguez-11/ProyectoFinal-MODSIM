"""Fase 2: convierte las capas descargadas en la grilla de entrada del modelo.

Produce data/procesado/grilla_fuego.npz con:
- clase: grupo de combustible FBFM40 (ver CLASES), -1 si no combustible;
- elevacion_m, pendiente_grados;
- poblacion: residentes estimados por celda, reescalados para que Paradise
  sume el total institucional del 1 de enero de 2018;
- dentro_perimetro: celdas cuyo centro cae en el perímetro final del incendio.
También guarda metadatos y una figura de control.
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.features import geometry_mask

from comun import CRUDO, PROCESADO, SALIDAS, grilla_dominio
from f1_descargar_capas import NODATA_WORLDPOP


# Grupos de Scott y Burgan (2005) según la centena/decena del código FBFM40.
# 91 (urbano) no es combustible en FBFM40, pero NIST documenta propagación entre
# estructuras en Paradise; se trata como clase propia con su parámetro calibrable.
CLASES = {
    0: ("urbano", (91, 91)),
    1: ("pasto_GR", (101, 109)),
    2: ("pasto_arbustivo_GS", (121, 124)),
    3: ("arbustal_SH", (141, 149)),
    4: ("sotobosque_TU", (161, 165)),
    5: ("hojarasca_TL", (181, 189)),
    6: ("restos_corta_SB", (201, 204)),
}
# 92 nieve, 93 agrícola, 98 agua, 99 suelo desnudo: no combustibles.

POBLACION_PARADISE_2018 = 26_581  # BCAG / Departamento de Finanzas, 1 ene 2018.


def clasificar(codigos: np.ndarray) -> np.ndarray:
    clase = np.full(codigos.shape, -1, dtype=np.int8)
    for indice, (_, (minimo, maximo)) in CLASES.items():
        clase[(codigos >= minimo) & (codigos <= maximo)] = indice
    return clase


def pendiente(elevacion: np.ndarray, resolucion: float) -> np.ndarray:
    dz_dy, dz_dx = np.gradient(elevacion, resolucion)
    return np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))


def main() -> None:
    grilla = grilla_dominio()
    with rasterio.open(CRUDO / "combustible_fbfm40.tif") as dataset:
        codigos = dataset.read(1)
    with rasterio.open(CRUDO / "elevacion_3dep.tif") as dataset:
        elevacion = dataset.read(1).astype("float32")
    with rasterio.open(CRUDO / "poblacion_worldpop2018.tif") as dataset:
        poblacion = dataset.read(1).astype("float64")
    poblacion[poblacion >= NODATA_WORLDPOP] = 0.0

    clase = clasificar(codigos)
    paradise = gpd.read_file(CRUDO / "limite_paradise.geojson").to_crs(grilla.crs)
    mascara_paradise = geometry_mask(
        paradise.geometry, out_shape=clase.shape, transform=grilla.transform, invert=True
    )
    suma_paradise = float(poblacion[mascara_paradise].sum())
    factor = POBLACION_PARADISE_2018 / suma_paradise
    poblacion_ajustada = poblacion * factor
    perimetro = gpd.read_file(CRUDO / "perimetro_final_camp.geojson").to_crs(grilla.crs)
    dentro_perimetro = geometry_mask(
        perimetro.geometry, out_shape=clase.shape, transform=grilla.transform, invert=True
    )

    PROCESADO.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        PROCESADO / "grilla_fuego.npz",
        clase=clase,
        codigo_fbfm40=codigos,
        elevacion_m=elevacion,
        pendiente_grados=pendiente(elevacion, grilla.resolucion).astype("float32"),
        poblacion=poblacion_ajustada.astype("float32"),
        mascara_paradise=mascara_paradise,
        dentro_perimetro=dentro_perimetro,
    )

    conteo = {CLASES[c][0] if c >= 0 else "no_combustible": int((clase == c).sum())
              for c in [-1, *CLASES]}
    meta = {
        "crs": grilla.crs,
        "transform_gdal": list(grilla.transform.to_gdal()),
        "forma_filas_columnas": [grilla.alto, grilla.ancho],
        "resolucion_m": grilla.resolucion,
        "celdas_por_clase": conteo,
        "celdas_dentro_perimetro_final": int(dentro_perimetro.sum()),
        "codigos_fbfm40_presentes": sorted(int(c) for c in np.unique(codigos)),
        "poblacion": {
            "suma_worldpop_paradise": round(suma_paradise, 1),
            "control_paradise_bcag_2018": POBLACION_PARADISE_2018,
            "factor_reescalado": round(factor, 4),
            "suma_dominio_ajustada": round(float(poblacion_ajustada.sum()), 1),
            "nota": "Estimación residencial; no es población presente a la hora del incendio.",
        },
    }
    (PROCESADO / "grilla_fuego_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    SALIDAS.mkdir(parents=True, exist_ok=True)
    extension = [grilla.xmin, grilla.xmax, grilla.ymin, grilla.ymax]
    figura, ejes = plt.subplots(1, 3, figsize=(16, 4.5))
    capas = [
        (np.ma.masked_less(clase, 0), "tab10", "Clase de combustible (gris: no combustible)"),
        (elevacion, "terrain", "Elevación (m)"),
        (np.ma.masked_equal(poblacion_ajustada, 0), "magma_r", "Residentes estimados por celda"),
    ]
    for eje, (datos, mapa, titulo) in zip(ejes, capas):
        eje.set_facecolor("0.85")
        imagen = eje.imshow(datos, cmap=mapa, extent=extension)
        eje.contour(mascara_paradise, levels=[0.5], colors="k", linewidths=0.8,
                    extent=extension, origin="upper")
        eje.contour(dentro_perimetro, levels=[0.5], colors="red", linewidths=0.8,
                    linestyles="--", extent=extension, origin="upper")
        eje.set_title(titulo)
        figura.colorbar(imagen, ax=eje, shrink=0.8)
    figura.suptitle("Grilla común UTM 10N, 100 m. Negro: Paradise (TIGER 2018). Rojo: perímetro final CAL FIRE")
    figura.tight_layout()
    figura.savefig(SALIDAS / "fig_capas.png", dpi=130)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
