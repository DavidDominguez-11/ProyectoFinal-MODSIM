"""Utilidades compartidas por los scripts del módulo de fuego.

Define rutas, lectura del dominio y la grilla común en UTM 10N. Ningún
script de este módulo debe construir su propia grilla: todos usan esta.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

# Si PROJ_LIB/PROJ_DATA/GDAL_DATA apuntan a otra instalación (por ejemplo la de
# PostGIS), rasterio y pyproj fallan con "proj.db ... from another PROJ
# installation". Sin estas variables, usan la base de datos que traen consigo.
for _variable in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_variable, None)

from rasterio.transform import Affine, from_origin  # noqa: E402


RAIZ = Path(__file__).resolve().parents[2]
CONFIG = RAIZ / "config"
CRUDO = RAIZ / "data" / "crudo"
PROCESADO = RAIZ / "data" / "procesado"
SALIDAS = RAIZ / "salidas" / "fuego"


@dataclass(frozen=True)
class Grilla:
    crs: str
    xmin: float
    ymax: float
    resolucion: float
    ancho: int
    alto: int

    @property
    def transform(self) -> Affine:
        return from_origin(self.xmin, self.ymax, self.resolucion, self.resolucion)

    @property
    def xmax(self) -> float:
        return self.xmin + self.ancho * self.resolucion

    @property
    def ymin(self) -> float:
        return self.ymax - self.alto * self.resolucion

    def celda(self, x: float, y: float) -> tuple[int, int] | None:
        """Fila y columna de un punto en metros UTM, o None si cae fuera."""
        col = int((x - self.xmin) // self.resolucion)
        fila = int((self.ymax - y) // self.resolucion)
        if 0 <= fila < self.alto and 0 <= col < self.ancho:
            return fila, col
        return None


def leer_dominio() -> dict:
    with open(CONFIG / "dominio.json", encoding="utf-8") as archivo:
        return json.load(archivo)


def grilla_dominio(dominio: dict | None = None) -> Grilla:
    dominio = dominio or leer_dominio()
    limites = dominio["limites_utm"]
    resolucion = float(dominio["resolucion_m"])
    return Grilla(
        crs=dominio["crs"],
        xmin=limites["xmin"],
        ymax=limites["ymax"],
        resolucion=resolucion,
        ancho=round((limites["xmax"] - limites["xmin"]) / resolucion),
        alto=round((limites["ymax"] - limites["ymin"]) / resolucion),
    )
