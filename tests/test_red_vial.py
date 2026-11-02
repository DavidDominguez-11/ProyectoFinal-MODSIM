"""Contrato público de preparación vial, sin datos reales ni acceso a red."""
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/evacuacion/red_vial.py"
DOMAIN = {"crs": "EPSG:32610", "limites_utm": {
    "xmin": 0, "xmax": 400, "ymin": 0, "ymax": 400}, "resolucion_m": 100}


def roads(lines, names=None, codes=None):
    return gpd.GeoDataFrame({"FULLNAME": names or ["Local"] * len(lines),
                             "MTFCC": codes or ["S1400"] * len(lines)},
                            geometry=lines, crs="EPSG:32610")


class RoadNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("red_vial", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def build(self, frame):
        return self.module.build_network(frame, DOMAIN)

    def test_crossings_vertices_clipping_and_directed_attributes(self):
        frame = roads([LineString([(-50, 150), (150, 150), (450, 150)]),
                       LineString([(250, 50), (250, 250)])],
                      ["Skyway", "Local"], ["S1200", "S1400"])
        original = frame.copy()
        result = self.build(frame)
        points = {(n["x"], n["y"]) for n in result["nodes"]}
        self.assertEqual(points, {(0, 150), (150, 150), (250, 150),
                                  (400, 150), (250, 50), (250, 250)})
        self.assertEqual(len(result["edges"]), 10)
        pairs = {(e["u"], e["v"]) for e in result["edges"]}
        self.assertTrue(all((v, u) in pairs for u, v in pairs))
        self.assertAlmostEqual(sum(e["length_m"] for e in result["edges"]), 1200)
        for edge in result["edges"]:
            self.assertGreater(edge["travel_min"], 0)
            self.assertIsInstance(edge["capacity"], int)
            self.assertGreater(edge["capacity"], 0)
            speed = result["metadata"]["road_parameters"][edge["mtfcc"]]["speed_kmh"]
            self.assertAlmostEqual(edge["travel_min"], edge["length_m"] / (speed * 1000 / 60))
        self.assertTrue(frame.equals(original))
        self.assertEqual(result, self.build(frame))
        json.dumps(result, allow_nan=False)

    def test_all_intersected_cells_include_grid_line_neighbors(self):
        result = self.build(roads([LineString([(-10, 200), (410, 200)])], ["Clark Rd"]))
        expected = {(row, col) for row in (1, 2) for col in range(4)}
        self.assertEqual(len(result["edges"]), 2)
        self.assertEqual({tuple(c) for c in result["edges"][0]["cells"]}, expected)
        self.assertEqual(len(result["destinations"]), 2)

    def test_diagonal_cells_are_conservative_but_not_whole_bounding_box(self):
        result = self.build(roads([LineString([(20, 20), (380, 380)])]))
        cells = {tuple(c) for c in result["edges"][0]["cells"]}
        self.assertIn((2, 1), cells)  # Contacto exacto con esquina de celda.
        self.assertNotIn((0, 0), cells)
        self.assertNotIn((3, 3), cells)

    def test_real_components_and_exit_reachability(self):
        result = self.build(roads([LineString([(-50, 50), (150, 50)]),
                                  LineString([(200, 250), (300, 250)])],
                                 ["Neal Rd", "Local"]))
        summary = result["metadata"]["connectivity"]
        self.assertEqual(summary["component_count"], 2)
        self.assertEqual(summary["nodes_without_exit"], 2)
        self.assertEqual(summary["fraction_nodes_without_exit"], 0.5)
        self.assertEqual(sum(c["node_count"] for c in summary["components"]), 4)
        self.assertEqual(len(result["destinations"]), 1)
        destination = result["destinations"][0]
        self.assertEqual(destination["kind"], "safe")
        self.assertIsInstance(destination["capacity"], int)
        self.assertGreater(destination["capacity"], 0)
        self.assertEqual(set(result["metadata"]["missing_exit_names"]), {"Skyway", "Clark", "Pentz"})

    def test_no_arbitrary_dead_end_or_boundary_touch_exits(self):
        result = self.build(roads([LineString([(0, 100), (100, 100)]),
                                  LineString([(-50, 250), (100, 250)]),
                                  LineString([(-50, 300), (450, 300)])],
                                 ["Skyway", "Unknown Rd", "Pentz Rd"]))
        self.assertEqual(len(result["destinations"]), 2)
        nodes = {n["id"]: n for n in result["nodes"]}
        self.assertTrue(all(nodes[d["node"]]["y"] == 300 for d in result["destinations"]))

    def test_multilines_overlaps_endpoint_junctions_and_fallback(self):
        result = self.build(roads([
            MultiLineString([[(10, 50), (150, 50)], [(150, 50), (250, 50)]]),
            LineString([(100, 50), (200, 50)]),
            LineString([(150, 50), (150, 100)])], codes=["UNKNOWN", "S1400", "S1400"]))
        self.assertEqual(result["metadata"]["connectivity"]["component_count"], 1)
        self.assertEqual(len(result["edges"]), 10)
        self.assertIn("UNKNOWN", result["metadata"]["road_parameters"])
        self.assertEqual(len({(e["u"], e["v"]) for e in result["edges"]}), 10)

    def test_all_named_exits_and_optional_source_fields(self):
        result = self.build(roads([
            LineString([(-10, y), (410, y)]) for y in (50, 150, 250, 350)],
            ["SKYWAY", "Clark Road", "Pentz Rd", "Neal Rd"]))
        self.assertEqual(len(result["destinations"]), 8)
        self.assertEqual(result["metadata"]["missing_exit_names"], [])
        self.assertEqual(result["metadata"]["connectivity"]["nodes_without_exit"], 0)
        frame = gpd.GeoDataFrame(geometry=[LineString([(10, 10), (20, 20)])], crs=32610)
        fallback = self.build(frame)
        self.assertEqual(fallback["edges"][0]["capacity"], 5)
        self.assertEqual(fallback["edges"][0]["name"], "")
        self.assertEqual(fallback["metadata"]["road_parameters"]["UNKNOWN"]["speed_kmh"], 20)

    def test_empty_and_outside_inputs(self):
        for frame in (roads([]), roads([LineString([(-50, -50), (-20, -20)])])):
            result = self.build(frame)
            self.assertEqual(result["nodes"], [])
            self.assertEqual(result["edges"], [])
            self.assertEqual(result["destinations"], [])
            self.assertEqual(result["metadata"]["connectivity"]["fraction_nodes_without_exit"], 0)

    def test_reject_invalid_crs_and_domain(self):
        frame = roads([LineString([(10, 10), (20, 20)])])
        with self.assertRaises(ValueError):
            self.build(frame.to_crs(4326))
        for change in ({"resolucion_m": 0}, {"crs": "EPSG:4326"},
                       {"limites_utm": {"xmin": 0, "xmax": math.nan, "ymin": 0, "ymax": 400}}):
            with self.assertRaises(ValueError):
                self.module.build_network(frame, {**DOMAIN, **change})

    def test_cli_help_and_local_zip_output_without_download(self):
        help_run = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(help_run.returncode, 0, help_run.stderr)
        self.assertIn("--download", help_run.stdout)
        self.assertIn("dominio", help_run.stdout)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            frame = roads([LineString([(-10, 50), (410, 50)])], ["Skyway"])
            frame.to_file(directory / "roads.shp")
            archive = directory / "roads.zip"
            with zipfile.ZipFile(archive, "w") as output:
                for path in directory.glob("roads.*"):
                    if path.suffix != ".zip":
                        output.write(path, path.name)
            domain = directory / "domain.json"
            domain.write_text(json.dumps(DOMAIN))
            target = directory / "nested/network.json"
            run = subprocess.run([sys.executable, str(SCRIPT), "--roads", str(archive),
                                  "--domain", str(domain), "--output", str(target)],
                                 cwd=directory, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(target.read_text())
            self.assertEqual(len(result["destinations"]), 2)
            self.assertFalse((directory / "data/crudo").exists())
            with zipfile.ZipFile(archive, "a") as output:
                output.writestr("../escape.txt", "no")
            target = directory / "rejected.json"
            run = subprocess.run([sys.executable, str(SCRIPT), "--roads", str(archive),
                                  "--domain", str(domain), "--output", str(target)],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertFalse(target.exists())
            self.assertFalse((directory.parent / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
