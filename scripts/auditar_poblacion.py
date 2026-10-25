"""Audita un recorte WorldPop 2018 para Paradise.

El resultado es una estimación espacial de residentes, no un conteo de
evacuados ni una reconstrucción de domicilios individuales.
"""

from __future__ import annotations

import io
import json
import urllib.parse
import urllib.request

import numpy as np
import rasterio
from rasterio.features import geometry_mask

from auditar_geografia import PARADISE_GEOID, SOURCES, read_shapefile_zip


SERVICE = (
    "https://worldpop.arcgis.com/arcgis/rest/services/"
    "WorldPop_Total_Population_100m/ImageServer/exportImage"
)
# Extensión envolvente del polígono TIGER/Line 2018 de Paradise.
BBOX = "-121.655652,39.725361,-121.564452,39.801543"
TIME_2018_UTC_MS = 1514764800000


def main() -> None:
    parameters = {
        "bbox": BBOX,
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": "110,92",
        "format": "tiff",
        "time": str(TIME_2018_UTC_MS),
        "f": "json",
    }
    url = SERVICE + "?" + urllib.parse.urlencode(parameters)
    with urllib.request.urlopen(url, timeout=60) as response:
        export = json.load(response)
    if "href" not in export:
        raise RuntimeError(f"La exportación no devolvió un archivo: {export}")
    with urllib.request.urlopen(export["href"], timeout=60) as response:
        contents = response.read()

    places, _ = read_shapefile_zip(SOURCES["california_places_2018"])
    paradise = places.loc[places["GEOID"] == PARADISE_GEOID]
    if len(paradise) != 1:
        raise ValueError("No se encontró Paradise en TIGER/Line 2018")

    with rasterio.io.MemoryFile(contents) as memory:
        with memory.open() as dataset:
            array = dataset.read(1, masked=True)
            values = array.compressed()
            polygon = paradise.to_crs(dataset.crs).geometry.iloc[0]
            center_mask = geometry_mask(
                [polygon], out_shape=array.shape, transform=dataset.transform, invert=True
            )
            touched_mask = geometry_mask(
                [polygon],
                out_shape=array.shape,
                transform=dataset.transform,
                invert=True,
                all_touched=True,
            )
            result = {
                "source": SERVICE,
                "selected_time_utc_ms": TIME_2018_UTC_MS,
                "request_bbox": BBOX,
                "returned_extent": export.get("extent"),
                "crs": str(dataset.crs),
                "shape": [dataset.height, dataset.width],
                "nodata": dataset.nodata,
                "valid_cells": int(values.size),
                "sum_in_rectangular_crop": float(np.sum(values)),
                "sum_in_paradise_center_cells": float(np.sum(array[center_mask])),
                "sum_in_paradise_all_touched_cells": float(np.sum(array[touched_mask])),
                "paradise_center_cells": int(np.sum(center_mask)),
                "min_cell": float(np.min(values)) if values.size else None,
                "max_cell": float(np.max(values)) if values.size else None,
                "download_bytes": len(contents),
                "interpretation": (
                    "Estimación rasterizada; las celdas de borde cambian el total. "
                    "No identifica hogares ni evacuados reales."
                ),
            }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
