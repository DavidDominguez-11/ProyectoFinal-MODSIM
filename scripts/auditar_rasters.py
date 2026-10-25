"""Audita recortes remotos de combustible LANDFIRE y elevación USGS.

Los recortes sirven para comprobar acceso y cobertura inicial sobre Paradise.
Todavía no son las capas finales de la simulación.
"""

from __future__ import annotations

import io
import json
import urllib.parse
import urllib.request

import numpy as np
import rasterio

from auditar_poblacion import BBOX


SERVICES = {
    "landfire_2016_fbfm40": (
        "https://lfps.usgs.gov/arcgis/rest/services/"
        "Landfire_LF2016/LF2016_FBFM40_CONUS/ImageServer/exportImage"
    ),
    "usgs_3dep_elevation": (
        "https://elevation.nationalmap.gov/arcgis/rest/services/"
        "3DEPElevation/ImageServer/exportImage"
    ),
}


def audit_image_service(name: str, endpoint: str) -> dict[str, object]:
    parameters = {
        "bbox": BBOX,
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": "256,256",
        "format": "tiff",
        "interpolation": "RSP_NearestNeighbor",
        "f": "json",
    }
    url = endpoint + "?" + urllib.parse.urlencode(parameters)
    with urllib.request.urlopen(url, timeout=90) as response:
        export = json.load(response)
    if "href" not in export:
        raise RuntimeError(f"La exportación {name} no devolvió archivo: {export}")
    with urllib.request.urlopen(export["href"], timeout=90) as response:
        contents = response.read()

    with rasterio.io.MemoryFile(contents) as memory:
        with memory.open() as dataset:
            array = dataset.read(1, masked=True)
            values = array.compressed()
            result: dict[str, object] = {
                "source": endpoint,
                "request_bbox": BBOX,
                "returned_extent": export.get("extent"),
                "download_bytes": len(contents),
                "crs": str(dataset.crs),
                "shape": [dataset.height, dataset.width],
                "valid_cells": int(values.size),
                "nodata": dataset.nodata,
            }
            if name == "landfire_2016_fbfm40":
                codes, counts = np.unique(values, return_counts=True)
                result["code_counts"] = {
                    str(int(code)): int(count) for code, count in zip(codes, counts)
                }
                result["warning"] = (
                    "Los códigos son categorías FBFM40; no son probabilidades "
                    "de ignición ni velocidades de propagación."
                )
            else:
                result["minimum"] = float(np.min(values)) if values.size else None
                result["maximum"] = float(np.max(values)) if values.size else None
                result["warning"] = (
                    "Servicio dinámico 3DEP; comprobar versión y fecha de la "
                    "capa fuente antes de tratarla como terreno de 2018."
                )
    return result


def main() -> None:
    result = {
        name: audit_image_service(name, endpoint)
        for name, endpoint in SERVICES.items()
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
