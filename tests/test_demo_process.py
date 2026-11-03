"""Las posiciones visuales no deben adelantar ni inventar llegadas."""

import unittest

from demo_process import group_position, latest_history


class ProcessProjectionTests(unittest.TestCase):
    def test_group_moves_only_during_recorded_traversal(self):
        group = {"id": "g1", "origin_xy": [0, 0], "ready_min": 5,
                 "finish_min": 20, "final_state": "safe"}
        traversal = {"group": "g1", "start_min": 10, "end_min": 20,
                     "planned_end_min": 20, "from_xy": [0, 0],
                     "to_xy": [100, 0], "outcome": "arrived"}
        self.assertEqual(group_position(group, [traversal], 4), ([0, 0], "Preparándose o esperando alerta"))
        self.assertEqual(group_position(group, [traversal], 7)[0], [0, 0])
        self.assertEqual(group_position(group, [traversal], 15)[0], [50, 0])
        self.assertEqual(group_position(group, [traversal], 20), ([100, 0], "Llegó a salida segura"))

    def test_latest_snapshot_never_uses_future(self):
        history = [{"time_min": 0, "people_safe": 0},
                   {"time_min": 12, "people_safe": 3}]
        self.assertEqual(latest_history(history, 10)["people_safe"], 0)


if __name__ == "__main__":
    unittest.main()
