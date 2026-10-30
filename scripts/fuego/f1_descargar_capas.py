"""Fase 1: descarga combustible, elevación y población en la grilla común.

Cada servicio ArcGIS ImageServer se consulta con la caja del dominio en
UTM 10N y el tamaño exacto de la grilla, de modo que los tres GeoTIFF
quedan alineados celda por celda. Los archivos se guardan en data/crudo/,
que no se sube al repositorio.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
import urllib.request

import numpy as np
import rasterio

from comun import CRUDO, RAIZ, grilla_dominio

sys.path.insert(0, str(RAIZ / "scripts"))
from auditar_geografia import PARADISE_GEOID, SOURCES, read_shapefile_zip  # noqa: E402


# WorldPop no declara nodata en la exportación; marca las celdas vacías con ~3.4e38.
NODATA_WORLDPOP = 1e30


# Combustible: nearest, porque los códigos FBFM40 son categorías.
# Elevación: bilineal. Población: nearest para no inventar conteos al interpolar.
CAPAS = {
    "combustible_fbfm40": {
        "url": (
            "https://lfps.usgs.gov/arcgis/rest/services/"
            "Landfire_LF2016/LF2016_FBFM40_CONUS/ImageServer/exportImage"
        ),
        "interpolacion": "RSP_NearestNeighbor",
        "pixel": "S16",
    },
    "elevacion_3dep": {
        "url": (
            "https://elevation.nationalmap.gov/arcgis/rest/services/"
            "3DEPElevation/ImageServer/exportImage"
        ),
        "interpolacion": "RSP_BilinearInterpolation",
        "pixel": "F32",
    },
    "poblacion_worldpop2018": {
        "url": (
            "https://worldpop.arcgis.com/arcgis/rest/services/"
            "WorldPop_Total_Population_100m/ImageServer/exportImage"
        ),
        "interpolacion": "RSP_NearestNeighbor",
        "pixel": "F32",
        "time": "1514764800000",  # 1 de enero de 2018, UTC.
    },
}


def descargar(nombre: str, capa: dict) -> dict:
    grilla = grilla_dominio()
    epsg = grilla.crs.split(":")[1]
    parametros = {
        "bbox": f"{grilla.xmin},{grilla.ymin},{grilla.xmax},{grilla.ymax}",
        "bboxSR": epsg,
        "imageSR": epsg,
        "size": f"{grilla.ancho},{grilla.alto}",
        "format": "tiff",
        "pixelType": capa["pixel"],
        "interpolation": capa["interpolacion"],
        "f": "json",
    }
    if "time" in capa:
        parametros["time"] = capa["time"]
    url = capa["url"] + "?" + urllib.parse.urlencode(parametros)
    with urllib.request.urlopen(url, timeout=120) as respuesta:
        exportacion = json.load(respuesta)
    if "href" not in exportacion:
        raise RuntimeError(f"{nombre}: el servicio no devolvió archivo: {exportacion}")
    with urllib.request.urlopen(exportacion["href"], timeout=120) as respuesta:
        contenido = respuesta.read()

    destino = CRUDO / f"{nombre}.tif"
    destino.write_bytes(contenido)
    with rasterio.open(destino) as dataset:
        datos = dataset.read(1, masked=True)
        if (dataset.width, dataset.height) != (grilla.ancho, grilla.alto):
            raise ValueError(f"{nombre}: tamaño {dataset.width}x{dataset.height} distinto a la grilla")
        return {
            "archivo": str(destino.relative_to(CRUDO.parents[1])),
            "bytes": len(contenido),
            "sha256": hashlib.sha256(contenido).hexdigest(),
            "crs": str(dataset.crs),
            "forma": [dataset.height, dataset.width],
            "celdas_validas": int(datos.count()),
            "minimo": float(datos.min()),
            "maximo": float(datos.max()),
            "extension_devuelta": exportacion.get("extent"),
        }


def descargar_paradise() -> dict:
    """Guarda el límite TIGER/Line 2018 de Paradise para el control de población."""
    lugares, metadatos = read_shapefile_zip(SOURCES["california_places_2018"])
    paradise = lugares.loc[lugares["GEOID"] == PARADISE_GEOID, ["GEOID", "NAME", "geometry"]]
    if len(paradise) != 1:
        raise ValueError("No se encontró Paradise en TIGER/Line 2018")
    paradise.to_file(CRUDO / "limite_paradise.geojson", driver="GeoJSON")
    return {"archivo": "data/crudo/limite_paradise.geojson", "fuente": metadatos["url"],
            "sha256_zip": metadatos["sha256"]}


PERIMETRO_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0/query"
)


def descargar_perimetro() -> dict:
    """Perímetro final del Camp Fire (CAL FIRE, 26 nov 2018) desde el servicio de NIFC."""
    parametros = {
        "where": "INCIDENT='CAMP' AND FIRE_YEAR='2018' AND SOURCE='CALFIRE' AND GIS_ACRES > 100000",
        "outFields": "INCIDENT,FIRE_YEAR,GIS_ACRES,AGENCY,SOURCE,DATE_CUR",
        "outSR": "4326",
        "f": "geojson",
    }
    url = PERIMETRO_URL + "?" + urllib.parse.urlencode(parametros)
    with urllib.request.urlopen(url, timeout=120) as respuesta:
        contenido = respuesta.read()
    datos = json.loads(contenido)
    if len(datos.get("features", [])) != 1:
        raise ValueError(f"Se esperaba un perímetro final; llegaron {len(datos.get('features', []))}")
    (CRUDO / "perimetro_final_camp.geojson").write_bytes(contenido)
    return {"archivo": "data/crudo/perimetro_final_camp.geojson", "fuente": url,
            "sha256": hashlib.sha256(contenido).hexdigest(),
            "atributos": datos["features"][0]["properties"]}


def main() -> None:
    CRUDO.mkdir(parents=True, exist_ok=True)
    resumen = {nombre: descargar(nombre, capa) for nombre, capa in CAPAS.items()}
    poblacion = resumen["poblacion_worldpop2018"]
    with rasterio.open(CRUDO / "poblacion_worldpop2018.tif") as dataset:
        valores = dataset.read(1).astype("float64")
    validos = valores < NODATA_WORLDPOP
    poblacion["maximo"] = float(valores[validos].max())
    poblacion["celdas_sin_dato"] = int((~validos).sum())
    poblacion["suma_dominio"] = float(valores[validos].sum())
    resumen["limite_paradise"] = descargar_paradise()
    resumen["perimetro_final"] = descargar_perimetro()
    (CRUDO / "capas_descargadas.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
