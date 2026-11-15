import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.features.scene.tools import walk_time, camera_sees
from app.features.scene.config import get_config

class SceneContractTests(unittest.TestCase):
    def test_configured_walk_survives_mapping(self):
        with patch("app.features.scene.tools.load_mapping", side_effect=AssertionError("should not measure configured route")):
            for a,b in [("230","219"),("219","230")]:
                self.assertEqual(walk_time(a,b)["seconds"],74)
                self.assertEqual(walk_time(a,b)["path"],[a,b])
    def test_case_configuration(self):
        config=get_config()
        self.assertEqual(config["crime_room"],"219")
        self.assertEqual(config["utc_offset"],"-05:00")
        self.assertTrue(any(d["id"]=="lt-219" and d["network"]=="air_gapped" for d in config["devices"]))
    def test_unknown_coverage_is_not_false_evidence(self):
        with self.assertRaises(ValueError): camera_sees("cam-03","219")
        with self.assertRaises(ValueError): walk_time("lobby","219")
