"""Exporta una réplica ilustrativa verificable para el visor, sin alterar producción.

Requiere la red vial regenerada por red_vial.py. El JSON es una nueva corrida:
su hash vial y sus métricas quedan declarados y no se atribuyen al lote publicado.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.evacuacion.experimentos import make_groups, prepare_network, scenario_inputs, summarize_replica
from scripts.evacuacion.motor import simulate


def main():
    network_path = ROOT / "data/procesado/red_vial.json"
    network_bytes = network_path.read_bytes()
    raw_network = json.loads(network_bytes)
    contract = json.loads((ROOT / "salidas/fuego/contrato.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "config/escenarios_evacuacion.json").read_text(encoding="utf-8"))
    published = json.loads((ROOT / "salidas/evacuacion_final/summary.json").read_text(encoding="utf-8"))
    network_hash = hashlib.sha256(network_bytes).hexdigest()
    published_hash = published["metadata"]["input_sha256"]["network"]
    network = prepare_network(raw_network, contract)
    with np.load(ROOT / "data/procesado/grilla_fuego.npz", allow_pickle=False) as grid:
        population = np.asarray(grid["poblacion"], dtype=np.float64)
    with np.load(ROOT / "salidas/fuego/llegada_replicas.npz", allow_pickle=False) as fire_data:
        fire = np.asarray(fire_data["llegada_min"][0], dtype=np.int16)
        seed = int(fire_data["semillas"][0])
    groups, attachment = make_groups(population, network, contract, config,
                                     config["preparation_seed_start"])
    count = min(36, len(groups))
    selected = [groups[i] for i in np.linspace(0, len(groups) - 1, count, dtype=int)]
    traced_ids = {g["id"] for g in selected}
    adapted, prepared, closed, intervention = scenario_inputs(network, groups, config, "base")
    print(f"Simulando base, fuego {seed}, {len(groups)} grupos, {len(traced_ids)} trazados", flush=True)
    def progress(sample):
        print(f"min={sample['time_min']:.1f} "
              f"safe={sample['people_safe']:.1f} "
              f"remaining={sample['people_remaining']:.1f}", flush=True)
    result = simulate(adapted, prepared, fire.tolist(), horizon=contract["horizonte_min"],
                      closed_edges=closed, retain_details=False, trace_group_ids=traced_ids,
                      progress=progress)
    metrics = summarize_replica(result)
    nodes = {node["id"]: [node["x"], node["y"]] for node in adapted["nodes"]}
    edges = {edge["id"]: edge for edge in adapted["edges"]}
    roads = [[*nodes[edge["u"]], *nodes[edge["v"]]]
             for edge in adapted["edges"] if int(edge["id"][1:]) % 2 == 0]
    records = []
    for group in prepared:
        if group["id"] not in traced_ids:
            continue
        end = next(g for g in result["groups"] if g["id"] == group["id"])
        records.append({"id": group["id"], "people": group["people"],
                        "origin_cell": group["origin_cell"], "origin_node": group["node"],
                        "origin_xy": nodes[group["node"]],
                        "alert_min": group["alert_min"],
                        "preparation_min": group["preparation_min"],
                        "ready_min": group["ready_min"],
                        "final_state": end["state"], "final_node": end["node"],
                        "finish_min": end["finish_min"], "exposed_by_horizon": end["exposed"]})
    traversals = []
    for record in result["traced_traversals"]:
        edge = edges[record["edge"]]
        traversals.append({**record, "u": edge["u"], "v": edge["v"],
                           "planned_end_min": record["start_min"] + edge["travel_min"],
                           "from_xy": nodes[edge["u"]], "to_xy": nodes[edge["v"]],
                           "road_name": edge["name"]})
    used_edges = {record["edge"] for record in traversals}
    edge_details = {identifier: {"u": edges[identifier]["u"],
                                 "v": edges[identifier]["v"],
                                 "capacity_groups": edges[identifier]["capacity"],
                                 "travel_min": edges[identifier]["travel_min"],
                                 "road_name": edges[identifier]["name"]}
                    for identifier in sorted(used_edges)}
    connectivity = raw_network["metadata"]["connectivity"]
    # El campo histórico compacto contiene eventos reales seleccionados; no hay
    # una fila por cada minuto ni se interpolan contadores de personas.
    artifact = {"schema": "demo_process_replay", "version": 1,
                "classification": "new_illustrative_run",
                "scenario": "base", "replica": 0, "fire_seed": seed,
                "preparation_seed": config["preparation_seed_start"],
                "network_sha256": network_hash,
                "published_network_sha256": published_hash,
                "network_matches_published": network_hash == published_hash,
                "network_source": raw_network["metadata"]["source_url"],
                "group_count": attachment["group_count"],
                "people_total": attachment["people_total"],
                "network_stats": {"nodes": len(raw_network["nodes"]),
                                  "directed_edges": len(raw_network["edges"]),
                                  "destinations": len(raw_network["destinations"]),
                                  "components": connectivity["component_count"],
                                  "nodes_without_exit": connectivity["nodes_without_exit"]},
                "trace_selection": "36 índices equidistantes en el orden determinista de grupos; muestra, no todos",
                "roads": roads, "exits": [{"node": d["node"], "xy": nodes[d["node"]]}
                                         for d in adapted["destinations"] if d["kind"] == "safe"],
                "groups": records, "traversals": traversals,
                "edge_details": edge_details,
                "history": result["history"], "metrics": metrics,
                "record_counts": result["detail_retention"],
                "intervention": intervention}
    output = ROOT / "salidas/demo_proceso.json"
    output.write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":"),
                                 allow_nan=False), encoding="utf-8")
    print(f"Exportado {output} ({output.stat().st_size} bytes); "
          f"red coincide: {artifact['network_matches_published']}; "
          f"personas seguras: {metrics['people_safe']:.3f}; "
          f"recorridos trazados: {len(traversals)}", flush=True)


if __name__ == "__main__":
    main()
