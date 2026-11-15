import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.features.scene import config, router


class SavedViewsTests(unittest.TestCase):
    def test_view_direction_round_trips_without_real_mapping_changes(self):
        sweep = {"id": "test-position", "position": {"x": 1, "y": 2, "z": 3}, "neighbors": []}
        with TemporaryDirectory() as directory, patch.object(config, "SCENE_DIR", Path(directory)), patch.object(router, "SCENE_DIR", Path(directory)):
            result = router.save_mapping(router.RoomMapping.model_validate({
                "model_id": config.model_id(), "room_id": "217", "sweep": sweep,
                "sweeps": [sweep], "view_rotation": {"x": -12, "y": 125},
            }))
            self.assertEqual(result["model_id"], config.model_id())
            rooms = router.config()["rooms"]
            view = next(room for room in rooms if room["id"] == "217")
            self.assertEqual(view["sweep"], "test-position")
            self.assertEqual(view["view_rotation"], {"x": -12, "y": 125})
            self.assertEqual(view["label"], "Halvorsen suite")


if __name__ == "__main__":
    unittest.main()
