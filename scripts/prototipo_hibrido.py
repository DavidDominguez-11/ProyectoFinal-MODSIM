"""Prototipo didáctico de fuego celular y evacuación sobre una vía.

Todos los números y la geometría son supuestos de demostración. No son una
reconstrucción, calibración ni predicción del Camp Fire de 2018.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path


WIDTH = 6
HEIGHT = 3
HORIZON_MIN = 20
FIRE_STEP_MIN = 2
EDGE_TRAVEL_MIN = 2
ROAD_ROW = 2
EXIT_NODE = 6  # Destino absorbente fuera de la grilla de fuego.


@dataclass
class Group:
    name: str
    people: int
    origin: int
    preparation_min: int
    node: int
    edge_to: int | None = None
    arrival_min: int | None = None
    finish_min: int | None = None
    first_exposure_min: int | None = None
    queue_min: int = 0


def make_groups() -> list[Group]:
    # Tamaños, posiciones y demoras inventados para la prueba de integración.
    return [
        Group("A", 2, 1, 1, 1),
        Group("B", 3, 1, 2, 1),
        Group("C", 1, 2, 1, 2),
    ]


def spread_fire(burning: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Cada dos minutos el fuego alcanza vecinas al este y al sur."""
    next_burning = set(burning)
    for x, y in burning:
        for neighbor in ((x + 1, y), (x, y + 1)):
            nx, ny = neighbor
            if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                next_burning.add(neighbor)
    return next_burning


def node_burning(node: int, burning: set[tuple[int, int]]) -> bool:
    return node != EXIT_NODE and (node, ROAD_ROW) in burning


def run_scenario(alert_min: int) -> dict:
    if not 0 <= alert_min <= HORIZON_MIN:
        raise ValueError("alert_min debe estar dentro del horizonte")

    groups = make_groups()
    initial_people = sum(group.people for group in groups)
    burning = {(0, 0)}
    fire_arrival = {(0, 0): 0}
    history = []
    maximum_edge_occupancy = 0

    for minute in range(HORIZON_MIN + 1):
        if minute and minute % FIRE_STEP_MIN == 0:
            next_burning = spread_fire(burning)
            for cell in next_burning - burning:
                fire_arrival[cell] = minute
            burning = next_burning

        # Los arribos se procesan antes de nuevas entradas al tramo.
        for group in groups:
            if group.arrival_min == minute:
                if group.edge_to is None:
                    raise AssertionError("arribo sin tramo activo")
                group.node = group.edge_to
                group.edge_to = None
                group.arrival_min = None
                if group.node == EXIT_NODE:
                    group.finish_min = minute

        # La exposición se evalúa al inicio del minuto para posición o tramo.
        for group in groups:
            if group.finish_min is not None or group.first_exposure_min is not None:
                continue
            on_dangerous_node = node_burning(group.node, burning)
            on_dangerous_edge = (
                group.edge_to is not None and node_burning(group.edge_to, burning)
            )
            if on_dangerous_node or on_dangerous_edge:
                group.first_exposure_min = minute

        # Una arista dirigida admite un solo grupo a la vez. La espera se mide
        # por minuto en el nodo de origen de la siguiente arista.
        occupied = {group.node for group in groups if group.edge_to is not None}
        if len(occupied) != sum(group.edge_to is not None for group in groups):
            raise AssertionError("capacidad de una arista excedida")
        maximum_edge_occupancy = max(maximum_edge_occupancy, 1 if occupied else 0)

        for group in groups:
            if group.finish_min is not None or group.edge_to is not None:
                continue
            if minute < alert_min + group.preparation_min:
                continue
            if group.node == EXIT_NODE:
                raise AssertionError("un grupo en la salida debe estar terminado")
            if group.node in occupied:
                group.queue_min += 1
                continue
            occupied.add(group.node)
            group.edge_to = group.node + 1
            group.arrival_min = minute + EDGE_TRAVEL_MIN

        if sum(group.people for group in groups) != initial_people:
            raise AssertionError("la población no se conserva")
        history.append(
            {
                "minute": minute,
                "burning_cells": len(burning),
                "people_exposed_cumulative": sum(
                    group.people for group in groups if group.first_exposure_min is not None
                ),
                "people_at_exit": sum(
                    group.people for group in groups if group.finish_min is not None
                ),
            }
        )

    return {
        "alert_min": alert_min,
        "people_initial": initial_people,
        "people_at_exit": sum(
            group.people for group in groups if group.finish_min is not None
        ),
        "people_exposed_cumulative": sum(
            group.people for group in groups if group.first_exposure_min is not None
        ),
        "total_queue_group_minutes": sum(group.queue_min for group in groups),
        "maximum_edge_occupancy": maximum_edge_occupancy,
        "fire_arrival_at_road_min": {
            str(x): fire_arrival.get((x, ROAD_ROW)) for x in range(WIDTH)
        },
        "groups": [
            {
                "name": group.name,
                "people": group.people,
                "origin": group.origin,
                "preparation_min": group.preparation_min,
                "finish_min": group.finish_min,
                "first_exposure_min": group.first_exposure_min,
                "queue_min": group.queue_min,
            }
            for group in groups
        ],
        "history": history,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="guarda el JSON además de mostrarlo")
    args = parser.parse_args()
    result = {
        "classification": "demostracion_sintetica_no_historica",
        "units": {"time": "minutos", "population": "personas ponderadas"},
        "assumptions": {
            "grid_cells": [WIDTH, HEIGHT],
            "initial_fire_cell": [0, 0],
            "fire_rule": "cada 2 min, una celda al este y una al sur",
            "road_nodes": "(x,2), x=1..5; salida absorbente x=6",
            "edge_travel_min": EDGE_TRAVEL_MIN,
            "edge_capacity": "un grupo simultáneo por arista",
            "horizon_min": HORIZON_MIN,
            "exposure": "posición o extremo de tramo ardiendo al inicio de un minuto",
        },
        "scenarios": {
            "base": run_scenario(alert_min=4),
            "alerta_anticipada": run_scenario(alert_min=0),
        },
    }
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
