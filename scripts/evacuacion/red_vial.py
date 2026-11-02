"""Prepara una red TIGER recortada; no simula ni acredita seguridad histórica."""
from __future__ import annotations

import argparse
from collections import deque
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import urllib.request
import zipfile

import geopandas as gpd
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[2]
SOURCE_URL = "https://www2.census.gov/geo/tiger/TIGER2018/ROADS/tl_2018_06007_roads.zip"
EXIT_NAMES = ("Skyway", "Clark", "Pentz", "Neal")
# Supuestos de escenario, no valores observados ni capacidades vehiculares.
PARAMETERS = {"S1100": (70, 40), "S1200": (50, 25), "S1400": (30, 10)}
FALLBACK = (20, 5)
EXIT_CAPACITY = 100000


def _lines(geometry):
    if geometry.is_empty:
        return
    if geometry.geom_type == "LineString":
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from _lines(part)


def _label(value, fallback):
    return value if isinstance(value, str) else fallback


def build_network(roads, domain):
    """Devuelve el contrato L5; roads debe estar proyectado en EPSG:32610.

    Conserva componentes aislados. Las intersecciones geométricas se interpretan
    a nivel (TIGER no aporta aquí elevación ni restricciones de giro).
    """
    if roads.crs is None or roads.crs.to_epsg() != 32610 or domain.get("crs") != "EPSG:32610":
        raise ValueError("La red y el dominio requieren EPSG:32610")
    limits = domain["limites_utm"]
    xmin, xmax, ymin, ymax = (float(limits[k]) for k in ("xmin", "xmax", "ymin", "ymax"))
    resolution = float(domain["resolucion_m"])
    if not all(math.isfinite(v) for v in (xmin, xmax, ymin, ymax, resolution)) or not (
        xmin < xmax and ymin < ymax and resolution > 0
    ):
        raise ValueError("Límites y resolución del dominio inválidos")
    boundary = box(xmin, ymin, xmax, ymax)
    rows = math.ceil((ymax - ymin) / resolution)
    columns = math.ceil((xmax - xmin) / resolution)
    sources, labels, exit_points = [], [], {}
    for _, record in roads.iterrows():
        geometry = record.geometry
        if geometry is None or geometry.is_empty:
            continue
        if geometry.geom_type not in ("LineString", "MultiLineString") or not geometry.is_valid:
            raise ValueError("Se requieren geometrías lineales válidas")
        name = _label(record.get("FULLNAME"), "")
        code = _label(record.get("MTFCC"), "UNKNOWN")
        for original in _lines(geometry):
            original = LineString([(x, y) for x, y, *_ in original.coords])
            for clipped in _lines(original.intersection(boundary)):
                if clipped.length <= 0:
                    continue
                sources.append(clipped)
                labels.append((name, code))
                # Exige carretera con porción exterior: tocar el límite no basta.
                if original.difference(boundary).length > 0:
                    for coordinate in (clipped.coords[0], clipped.coords[-1]):
                        point = Point(coordinate)
                        if boundary.boundary.distance(point) < 1e-8:
                            for canonical in EXIT_NAMES:
                                if re.search(r"\b" + canonical + r"\b", name, re.IGNORECASE):
                                    exit_points.setdefault(tuple(coordinate), set()).add(canonical)

    def cells_for(line):
        left, bottom, right, top = line.bounds
        # Una celda cerrada puede tocar el tramo en un borde o esquina.
        c0 = max(0, math.ceil((left - xmin) / resolution) - 1)
        c1 = min(columns - 1, math.floor((right - xmin) / resolution))
        r0 = max(0, math.ceil((ymax - top) / resolution) - 1)
        r1 = min(rows - 1, math.floor((ymax - bottom) / resolution))
        return [[r, c] for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)
                if line.intersects(box(xmin + c * resolution, max(ymin, ymax - (r + 1) * resolution),
                                       min(xmax, xmin + (c + 1) * resolution), ymax - r * resolution))]

    segments = {}
    if sources:
        tree = STRtree(sources)
        for line in _lines(unary_union(sources)):
            coordinates = list(line.coords)
            for start, end in zip(coordinates, coordinates[1:]):
                if start == end:
                    continue
                key = tuple(sorted((tuple(start), tuple(end))))
                segment = LineString(key)
                midpoint = segment.interpolate(0.5, normalized=True)
                candidates = [int(i) for i in tree.query(midpoint.buffer(1e-7))
                              if sources[int(i)].distance(midpoint) < 1e-7]
                # Solapes: un solo par dirigido; selección estable por nombre/código.
                selected = min(candidates, key=lambda i: labels[i])
                segments[key] = labels[selected]
    coordinates = sorted({point for key in segments for point in key})
    node_ids = {point: f"n{i}" for i, point in enumerate(coordinates)}
    nodes = [{"id": node_ids[p], "x": p[0], "y": p[1]} for p in coordinates]
    edges, used_parameters = [], {}
    neighbors = {n["id"]: set() for n in nodes}
    for key, (name, code) in sorted(segments.items()):
        line = LineString(key)
        speed, capacity = PARAMETERS.get(code, FALLBACK)
        used_parameters[code] = {"speed_kmh": speed, "capacity_groups": capacity}
        u, v = (node_ids[p] for p in key)
        neighbors[u].add(v)
        neighbors[v].add(u)
        cells = cells_for(line)
        for start, end in ((u, v), (v, u)):
            edges.append({"id": f"e{len(edges)}", "u": start, "v": end,
                          "length_m": line.length, "travel_min": line.length / (speed * 1000 / 60),
                          "capacity": capacity, "cells": cells, "name": name, "mtfcc": code})
    destinations = [{"node": node_ids[p], "kind": "safe", "capacity": EXIT_CAPACITY}
                    for p in sorted(exit_points) if p in node_ids]
    exit_nodes = {d["node"] for d in destinations}
    components, visited, unreachable = [], set(), 0
    for node in neighbors:
        if node in visited:
            continue
        queue, members = deque([node]), set([node])
        visited.add(node)
        while queue:
            for neighbor in sorted(neighbors[queue.popleft()]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    members.add(neighbor)
                    queue.append(neighbor)
        has_exit = bool(members & exit_nodes)
        if not has_exit:
            unreachable += len(members)
        components.append({"id": f"c{len(components)}", "nodes": sorted(members),
                           "node_count": len(members), "has_exit": has_exit,
                           "exit_nodes": sorted(members & exit_nodes)})
    available = {name for p, names in exit_points.items() if p in node_ids for name in names}
    return {"nodes": nodes, "edges": edges, "destinations": destinations,
            "metadata": {"crs": "EPSG:32610", "source_url": SOURCE_URL,
                         "domain": domain, "road_parameters": used_parameters,
                         "missing_exit_names": [n for n in EXIT_NAMES if n not in available],
                         "connectivity": {"component_count": len(components), "components": components,
                                          "nodes_without_exit": unreachable,
                                          "fraction_nodes_without_exit": unreachable / len(nodes) if nodes else 0},
                         "assumptions": {
                             "direction": "Bidireccional hipotética; sin sentidos históricos.",
                             "junctions": "Cruces geométricos a nivel; sin puentes, túneles ni restricciones de giro.",
                             "road_parameters": "Velocidades y capacidades hipotéticas por MTFCC; desconocido: 20 km/h, 5 grupos.",
                             "capacity_unit": "Grupos simultáneamente activos por arista dirigida, no personas ni vehículos/hora.",
                             "destinations": "Cruces de límite: destinos seguros absorbentes hipotéticos fuera del dominio, no albergues históricos.",
                             "destination_capacity": EXIT_CAPACITY,
                             "reachability": "Fracción de nodos, no población; asignar habitantes sin eliminarlos en componentes sin salida.",
                             "cells": "Todas las celdas cerradas intersectadas; fila 0 al norte, columna 0 al oeste."}}}


def _read_zip(path):
    # GDAL recibe bytes, nunca una ruta ZIP compuesta con nombres no confiables.
    contents = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(contents)) as archive:
        shapefiles = []
        for info in archive.infolist():
            name = info.filename
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts or "\\" in name or ":" in name:
                raise ValueError("Ruta insegura en ZIP")
            if member.suffix.lower() == ".shp":
                shapefiles.append(name)
        if len(shapefiles) != 1:
            raise ValueError("El ZIP debe contener exactamente un shapefile")
    return gpd.read_file(io.BytesIO(contents))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepara la red vial TIGER dentro del dominio; supuestos hipotéticos.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--roads", type=Path, help="ZIP local de carreteras TIGER (sin descarga)")
    source.add_argument("--download", action="store_true", help="Autorizar descarga oficial si no existe caché local")
    parser.add_argument("--domain", type=Path, default=ROOT / "config/dominio.json", help="Archivo JSON del dominio")
    parser.add_argument("--output", type=Path, default=ROOT / "data/procesado/red_vial.json", help="JSON de salida")
    args = parser.parse_args(argv)
    path = args.roads
    if args.download:
        path = ROOT / "data/crudo/evacuacion/tl_2018_06007_roads.zip"
        if not path.exists():
            with urllib.request.urlopen(SOURCE_URL, timeout=90) as response:
                contents = response.read()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
    frame = _read_zip(path).to_crs("EPSG:32610")
    result = build_network(frame, json.loads(args.domain.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result["metadata"]["connectivity"], ensure_ascii=False))


if __name__ == "__main__":
    main()
