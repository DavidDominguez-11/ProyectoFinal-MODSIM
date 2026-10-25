"""Comprobaciones de integración del prototipo sintético."""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from prototipo_hibrido import HORIZON_MIN, run_scenario  # noqa: E402


class HybridPrototypeTests(unittest.TestCase):
    def test_fuego_agentes_y_capacidad_estan_acoplados(self) -> None:
        base = run_scenario(alert_min=4)
        early = run_scenario(alert_min=0)

        self.assertEqual(base["fire_arrival_at_road_min"], early["fire_arrival_at_road_min"])
        self.assertEqual(base["fire_arrival_at_road_min"]["1"], 6)
        self.assertEqual(base["maximum_edge_occupancy"], 1)
        self.assertEqual(early["maximum_edge_occupancy"], 1)
        self.assertEqual(base["total_queue_group_minutes"], 1)
        self.assertEqual(base["people_initial"], 6)
        self.assertEqual(base["people_at_exit"], 6)
        self.assertEqual(early["people_at_exit"], 6)
        self.assertEqual(base["people_exposed_cumulative"], 5)
        self.assertEqual(early["people_exposed_cumulative"], 0)
        self.assertEqual(len(base["history"]), HORIZON_MIN + 1)

    def test_repeticion_y_conservacion(self) -> None:
        self.assertEqual(run_scenario(alert_min=4), run_scenario(alert_min=4))
        for entry in run_scenario(alert_min=4)["history"]:
            self.assertLessEqual(entry["people_at_exit"], 6)
            self.assertLessEqual(entry["people_exposed_cumulative"], 6)


if __name__ == "__main__":
    unittest.main()
