"""Comprueba dos capas TIGER/Line 2018 del caso Camp Fire.

Descarga archivos temporales; no guarda copias de datos brutos en el repositorio.
Requiere geopandas y un motor de lectura de shapefiles compatible.
"""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd


SOURCES = {
    "butte_roads_2018": "https://www2.census.gov/geo/tiger/TIGER2018/ROADS/tl_2018_06007_roads.zip",
    "california_places_2018": "https://www2.census.gov/geo/tiger/TIGER2018/PLACE/tl_2018_06_place.zip",
}
PARADISE_GEOID = "0655520"


def read_shapefile_zip(url: str) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    request = urllib.request.Request(url, headers={"User-Agent": "MODSIM-research-audit/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        contents = response.read()

    with tempfile.TemporaryDirectory() as directory:
        with zipfile.ZipFile(io.BytesIO(contents)) as archive:
            archive.extractall(directory)
        paths = list(Path(directory).glob("*.shp"))
        if len(paths) != 1:
            raise ValueError(f"Se esperaba un shapefile en {url}; se encontraron {len(paths)}")
        frame = gpd.read_file(paths[0])

    metadata: dict[str, object] = {
        "url": url,
        "bytes": len(contents),
        "sha256": hashlib.sha256(contents).hexdigest(),
        "features": len(frame),
        "crs": str(frame.crs),
        "bounds": [float(value) for value in frame.total_bounds],
    }
    return frame, metadata


def main() -> None:
    roads, roads_metadata = read_shapefile_zip(SOURCES["butte_roads_2018"])
    places, places_metadata = read_shapefile_zip(SOURCES["california_places_2018"])

    paradise = places.loc[places["GEOID"] == PARADISE_GEOID]
    if len(paradise) != 1 or paradise.iloc[0]["NAME"] != "Paradise":
        raise ValueError("No se encontró el polígono único de Paradise en la capa de 2018")

    paradise_in_roads_crs = paradise.to_crs(roads.crs)
    intersecting_roads = roads.loc[roads.intersects(paradise_in_roads_crs.geometry.iloc[0])]
    paradise_utm = paradise.to_crs("EPSG:32610")

    result = {
        "case": "Camp Fire, Paradise, Butte County, California",
        "road_dataset": roads_metadata,
        "place_dataset": places_metadata,
        "paradise": {
            "geoid": PARADISE_GEOID,
            "name": "Paradise",
            "bounds": [float(value) for value in paradise.total_bounds],
            "area_square_km": float(paradise_utm.area.iloc[0] / 1_000_000),
            "road_segments_intersecting_boundary": len(intersecting_roads),
            "road_feature_classes": {
                str(code): int(count)
                for code, count in intersecting_roads["MTFCC"].value_counts().items()
            },
        },
        "interpretation": "Intersección geométrica; no acredita conectividad, sentido, velocidad ni capacidad vial.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
