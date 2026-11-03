"""Controles del visor contra los artefactos de producción versionados."""

from pathlib import Path
import unittest

import numpy as np

from demo_data import fire_snapshot, load_bundle, paired_values


ROOT = Path(__file__).resolve().parents[1]


class DemoDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle(ROOT)

    def test_real_artifacts_have_paired_120_runs_and_matching_population(self):
        bundle = self.bundle
        self.assertEqual(bundle.arrivals.shape, (30, 205, 278))
        self.assertEqual(len(bundle.replicas), 120)
        self.assertEqual(bundle.fire_seeds.tolist(), list(range(1000, 1030)))
        self.assertAlmostEqual(bundle.population.sum(), 42388.94983696542)
        self.assertEqual(bundle.summary["metadata"]["classification"], "hypothetical_mc")

    def test_fire_snapshot_never_shows_future_or_unburned_cells(self):
        bundle = self.bundle
        minute = 120
        visible = fire_snapshot(bundle.arrivals, 0, minute)
        expected = (bundle.arrivals[0] >= 0) & (bundle.arrivals[0] <= minute)
        np.testing.assert_array_equal(np.isfinite(visible), expected)
        np.testing.assert_array_equal(visible[expected], bundle.arrivals[0][expected])
        with self.assertRaises(ValueError):
            fire_snapshot(bundle.arrivals, 30, minute)

    def test_paired_differences_match_published_mean(self):
        bundle = self.bundle
        for scenario in ("early_alert", "skyway_closed", "exit_capacity"):
            values = paired_values(bundle.replicas, scenario, "fraction_safe_before_fire")
            self.assertEqual(len(values), 30)
            self.assertAlmostEqual(values.mean(), bundle.summary["paired_differences_vs_base"]
                                   [scenario]["fraction_safe_before_fire"]["mean"])


if __name__ == "__main__":
    unittest.main()
