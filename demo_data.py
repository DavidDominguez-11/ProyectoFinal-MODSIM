"""Lectura y controles de consistencia para el visor de resultados existentes.

Este módulo no importa los motores ni ejecuta simulaciones o descargas.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


SCENARIOS = ("base", "early_alert", "skyway_closed", "exit_capacity")


@dataclass(frozen=True)
class DemoBundle:
    contract: dict
    config: dict
    domain: dict
    summary: dict
    replicas: pd.DataFrame
    arrivals: np.ndarray
    fire_seeds: np.ndarray
    population: np.ndarray
    fuel_class: np.ndarray
    elevation: np.ndarray
    slope: np.ndarray
    perimeter: np.ndarray
    source_checks: dict[str, str]


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_bundle(root: Path) -> DemoBundle:
    """Cargar artefactos de confianza y rechazar combinaciones incompatibles."""
    root = Path(root)
    paths = {
        "grid": root / "data/procesado/grilla_fuego.npz",
        "fire": root / "salidas/fuego/llegada_replicas.npz",
        "contract": root / "salidas/fuego/contrato.json",
        "config": root / "config/escenarios_evacuacion.json",
        "domain": root / "config/dominio.json",
        "summary": root / "salidas/evacuacion_final/summary.json",
        "replicas": root / "salidas/evacuacion_final/replicas.csv",
        "network": root / "data/procesado/red_vial.json",
    }
    missing = [key for key in ("grid", "fire", "contract", "config", "domain", "summary", "replicas")
               if not paths[key].is_file()]
    _require(not missing, f"Faltan artefactos requeridos: {', '.join(missing)}")

    contract, config, domain = (_json(paths[key]) for key in ("contract", "config", "domain"))
    summary = _json(paths["summary"])
    metadata = summary["metadata"]
    _require(metadata["classification"] == "hypothetical_mc" and not metadata["provisional"],
             "El resumen no corresponde a la producción hipotética completa")
    _require(contract == metadata["contract"] and config == metadata["config"],
             "Configuración o contrato difieren del resumen de producción")
    _require(contract["crs"] == domain["crs"] == "EPSG:32610", "CRS incompatibles")
    _require(contract["horizonte_min"] == domain["horizonte_min"] == 480,
             "Horizonte incompatible")
    shape = tuple(contract["forma_filas_columnas"])
    _require(len(shape) == 2 and all(isinstance(v, int) and v > 0 for v in shape),
             "Forma inválida del contrato")
    _require(set(summary["scenarios"]) == set(SCENARIOS), "Escenarios incompletos")
    _require(set(summary["paired_differences_vs_base"]) == set(SCENARIOS[1:]),
             "Comparaciones pareadas incompletas")

    checks: dict[str, str] = {}
    for key in ("grid", "fire"):
        _require(_sha256(paths[key]) == metadata["input_sha256"][key],
                 f"El archivo {key} no coincide con el usado en producción")
        checks[key] = "SHA-256 idéntico al registro de producción"
    for key in ("contract", "config"):
        raw = paths[key].read_bytes()
        recorded = metadata["input_sha256"][key]
        if hashlib.sha256(raw).hexdigest() == recorded:
            checks[key] = "SHA-256 idéntico al registro de producción"
        elif hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == recorded:
            checks[key] = "Contenido JSON idéntico; solo difieren finales de línea CRLF/LF"
        else:
            # La igualdad semántica se exigió arriba; otras diferencias de formato
            # quedan visibles y no se presentan como hash idéntico.
            checks[key] = "Contenido JSON idéntico; bytes distintos del registro"
    if paths["network"].is_file():
        if _sha256(paths["network"]) == metadata["input_sha256"]["network"]:
            checks["network"] = "SHA-256 idéntico al registro de producción"
        else:
            checks["network"] = "Red regenerada: SHA-256 distinto; no atribuir a las 120 corridas"
    else:
        checks["network"] = "No está en esta copia; red vial exacta sin verificar"

    with np.load(paths["grid"], allow_pickle=False) as grid:
        population = np.asarray(grid["poblacion"], dtype=np.float64)
        fuel_class = np.asarray(grid["clase"], dtype=np.int8)
        elevation = np.asarray(grid["elevacion_m"], dtype=np.float64)
        slope = np.asarray(grid["pendiente_grados"], dtype=np.float64)
        perimeter = np.asarray(grid["dentro_perimetro"], dtype=bool)
    with np.load(paths["fire"], allow_pickle=False) as fire:
        arrivals = np.asarray(fire["llegada_min"], dtype=np.int16)
        fire_seeds = np.asarray(fire["semillas"], dtype=np.int64)
    _require(population.shape == perimeter.shape == shape, "Grilla incompatible")
    _require(fuel_class.shape == elevation.shape == slope.shape == shape,
             "Capas SIG incompatibles")
    _require(np.isfinite(elevation).all() and np.isfinite(slope).all() and
             np.isin(fuel_class, [-1, 0, 1, 2, 3, 4, 5, 6]).all(),
             "Combustible, elevación o pendiente inválidos")
    _require(arrivals.shape == (30, *shape) and fire_seeds.shape == (30,),
             "Se esperaban 30 réplicas de fuego sobre la grilla contratada")
    _require(np.isfinite(population).all() and (population >= 0).all(),
             "Población inválida")
    _require(((arrivals == -1) | ((arrivals >= 0) & (arrivals <= 480))).all(),
             "Tiempos de llegada del fuego inválidos")
    _require(len(set(fire_seeds.tolist())) == 30, "Semillas de fuego repetidas")

    replicas = pd.read_csv(paths["replicas"])
    expected_rows = [(r, scenario) for r in range(30) for scenario in SCENARIOS]
    observed_rows = list(zip(replicas["replica"], replicas["scenario"]))
    _require(observed_rows == expected_rows, "CSV sin las 120 corridas en orden canónico")
    _require((replicas["fire_index"].to_numpy() == replicas["replica"].to_numpy()).all(),
             "Índice de fuego no pareado")
    _require((replicas["fire_seed"].to_numpy() == fire_seeds[replicas["replica"]]).all(),
             "Semillas de fuego no coinciden")
    _require((replicas["preparation_seed"].to_numpy() ==
              config["preparation_seed_start"] + replicas["replica"].to_numpy()).all(),
             "Semillas de preparación no pareadas")
    _require(not replicas["provisional"].any(), "El CSV contiene corridas provisionales")
    total = float(metadata["attachment"]["people_total"])
    _require(np.allclose(replicas["people_total"], total, rtol=1e-12, atol=1e-9),
             "Masa inicial inconsistente")
    _require(math.isclose(math.fsum(population.flat), total, rel_tol=1e-12),
             "Población de la grilla no coincide con la producción")
    conserved = replicas[["people_safe", "people_temporary", "people_remaining"]].sum(axis=1)
    _require(np.allclose(conserved, total, rtol=1e-9), "La masa no se conserva en el CSV")
    _require((replicas["people_safe_before_fire"] <= replicas["people_safe"] + 1e-7).all()
             and (replicas["people_exposed"] <= total + 1e-7).all(),
             "Cotas poblacionales inconsistentes")
    for scenario in SCENARIOS:
        for key in ("fraction_safe_before_fire", "people_exposed", "queue_duration_min"):
            current = float(replicas.loc[replicas["scenario"] == scenario, key].mean())
            recorded = summary["scenarios"][scenario][key]["mean"]
            _require(math.isclose(current, recorded, rel_tol=1e-10, abs_tol=1e-9),
                     f"CSV y resumen difieren para {scenario}/{key}")
    return DemoBundle(contract, config, domain, summary, replicas, arrivals,
                      fire_seeds, population, fuel_class, elevation, slope, perimeter, checks)


def fire_snapshot(arrivals: np.ndarray, replica: int, minute: int) -> np.ndarray:
    """Minuto de llegada visible hasta t; NaN para celdas aún no alcanzadas."""
    if not 0 <= replica < len(arrivals) or not 0 <= minute <= 480:
        raise ValueError("Réplica o minuto fuera del contrato")
    layer = arrivals[replica]
    return np.where((layer >= 0) & (layer <= minute), layer, np.nan)


def paired_values(replicas: pd.DataFrame, scenario: str, metric: str) -> np.ndarray:
    """Alternativa menos base, por el mismo índice de réplica."""
    if scenario not in SCENARIOS[1:] or metric not in replicas.columns:
        raise ValueError("Escenario o métrica inválida")
    base = replicas.loc[replicas["scenario"] == "base"].sort_values("replica")
    other = replicas.loc[replicas["scenario"] == scenario].sort_values("replica")
    if not np.array_equal(base["replica"].to_numpy(), other["replica"].to_numpy()):
        raise ValueError("Réplicas no pareadas")
    return other[metric].to_numpy(dtype=float) - base[metric].to_numpy(dtype=float)
