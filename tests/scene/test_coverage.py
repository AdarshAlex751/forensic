import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.features.scene.tools import ap_covers, camera_sees
from app.features.scene.devices import UnknownCoverageError


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch("app.features.scene.devices.SCENE_DIR", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def write(self, kind="wifi_ap", device="test-ap", **changes):
        record = dict(type=kind, covered_rooms=["230"], excluded_rooms=["219"], source="test fixture only")
        record.update(changes)
        (self.root / "coverage.json").write_text(json.dumps(dict(case_id="1010F", devices={device:record})))

    def test_explicit_positive_negative_and_unknown(self):
        self.write()
        self.assertIs(ap_covers("test-ap", "230"), True)
        self.assertIs(ap_covers("test-ap", "219"), False)
        with self.assertRaises(UnknownCoverageError): ap_covers("test-ap", "217")
        with self.assertRaises(UnknownCoverageError): ap_covers("missing", "230")

    def test_camera_and_device_type(self):
        self.write(kind="camera", device="cam-03")
        self.assertIs(camera_sees("cam-03", "230"), True)
        with self.assertRaises(UnknownCoverageError): ap_covers("cam-03", "230")

    def test_conflicting_coverage_rejected(self):
        self.write(excluded_rooms=["230"])
        with self.assertRaises(ValueError): ap_covers("test-ap", "230")

    def test_missing_source_and_file_are_unknown(self):
        with self.assertRaises(UnknownCoverageError): ap_covers("test-ap", "230")
        self.write(source=None)
        with self.assertRaises(UnknownCoverageError): ap_covers("test-ap", "230")
