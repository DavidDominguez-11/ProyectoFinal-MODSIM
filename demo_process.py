"""Lectura y reconstrucción limitada de una réplica ilustrativa del proceso."""

from __future__ import annotations

import json
import math
from pathlib import Path


def load_process(root: Path, bundle) -> dict | None:
    path = Path(root) / "salidas/demo_proceso.json"
    if not path.is_file():
        return None
    process = json.loads(path.read_text(encoding="utf-8"))
    if (process.get("schema") != "demo_process_replay" or process.get("version") != 1 or
            process.get("classification") != "new_illustrative_run" or
            process.get("scenario") != "base" or process.get("replica") != 0 or
            process.get("fire_seed") != int(bundle.fire_seeds[0]) or
            process.get("people_total") != bundle.summary["metadata"]["attachment"]["people_total"] or
            len(process.get("groups", [])) != 36 or
            not process.get("history") or
            process["history"][0]["time_min"] != 0 or
            process["history"][-1]["time_min"] != 480):
        raise ValueError("La réplica visual no coincide con la grilla o su contrato")
    if (process["published_network_sha256"] !=
            bundle.summary["metadata"]["input_sha256"]["network"] or
            process["network_matches_published"] !=
            (process["network_sha256"] == process["published_network_sha256"])):
        raise ValueError("Procedencia vial visual inconsistente")
    ids = {g["id"] for g in process["groups"]}
    stats = process.get("network_stats", {})
    if (stats.get("nodes") != 31670 or stats.get("directed_edges") != 64098 or
            stats.get("destinations") != len(process.get("exits", [])) or
            not process.get("edge_details")):
        raise ValueError("Metadatos de la red visual incompletos")
    if len(ids) != 36 or any(t["group"] not in ids or
                             t["edge"] not in process["edge_details"] or
                             t["start_min"] > t["end_min"] or
                             t["planned_end_min"] < t["end_min"] or
                             not 0 <= t["start_min"] <= t["end_min"] <= 480
                             for t in process["traversals"]):
        raise ValueError("Recorridos visuales inválidos")
    if any(a["time_min"] > b["time_min"] for a, b in
           zip(process["history"], process["history"][1:])):
        raise ValueError("Historia visual fuera de orden")
    last = process["history"][-1]
    if (not math.isclose(last["people_safe"] + last["people_temporary"] +
                         last["people_remaining"], process["people_total"], rel_tol=1e-9) or
            not math.isclose(last["people_safe"], process["metrics"]["people_safe"],
                             rel_tol=1e-12)):
        raise ValueError("La réplica visual no conserva población o sus métricas")
    return process


def group_position(group: dict, traversals: list[dict], minute: float) -> tuple[list[float], str]:
    """Posición ilustrativa dentro de un tramo de velocidad constante."""
    if not 0 <= minute <= 480 or not math.isfinite(minute):
        raise ValueError("Minuto fuera del horizonte")
    relevant = sorted((t for t in traversals if t["group"] == group["id"]),
                      key=lambda t: t["start_min"])
    if minute < group["ready_min"]:
        return group["origin_xy"], "Preparándose o esperando alerta"
    point = group["origin_xy"]
    for record in relevant:
        if minute < record["start_min"]:
            break
        if minute < record["end_min"] and record["planned_end_min"] > record["start_min"]:
            fraction = (minute - record["start_min"]) / (record["planned_end_min"] - record["start_min"])
            xy = [a + fraction * (b - a) for a, b in
                  zip(record["from_xy"], record["to_xy"])]
            return xy, "En tramo vial (posición interpolada)"
        point = record["to_xy"] if record["outcome"] == "arrived" else record["from_xy"]
    if group["finish_min"] is not None and minute >= group["finish_min"]:
        return point, "Llegó a salida segura" if group["final_state"] == "safe" else "Llegó a destino"
    return point, "En nodo; detalle de espera no registrado"


def latest_history(history: list[dict], minute: float) -> dict:
    return max((sample for sample in history if sample["time_min"] <= minute),
               key=lambda sample: sample["time_min"])
