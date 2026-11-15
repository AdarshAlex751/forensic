"""CASE.md scene IDs and explicit unmeasured placeholders."""
import csv
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCENE_DIR = ROOT / "data" / "scene"
ROOM_IDS = tuple(str(number) for number in range(210, 231))
DEMO_WALK = {"seconds": 74, "path": ["230", "219"], "status": "configured_case_time"}


def load_mapping() -> dict:
    path = SCENE_DIR / "mapping.json"
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if value.get("model_id") == model_id() else {}


def model_id() -> str:
    return os.getenv("VITE_MATTERPORT_MODEL_ID", "P3S6VUTP3qB").strip() or "P3S6VUTP3qB"


def get_config() -> dict:
    mappings = load_mapping().get("rooms", {})
    labels = {"217": "Halvorsen suite", "219": "Secure room - isolated laptop", "230": "Far-end badge room"}
    inventory_path = ROOT / "data/evidence/devices.csv"
    inventory = []
    if inventory_path.exists():
        with inventory_path.open(encoding="utf-8-sig", newline="") as stream:
            inventory = list(csv.DictReader(stream))
        # Ignore obsolete fixtures rather than mixing case identities.
        if not any(row.get("device_id") == "lt-219" for row in inventory):
            inventory = []
    location_ids = list(dict.fromkeys([*ROOM_IDS, "corridor-219", *[row["room"] for row in inventory if row.get("room")]]))
    rooms = []
    for room_id in location_ids:
        mapping = mappings.get(room_id, {})
        position = mapping.get("position", {})
        rooms.append({"id": room_id, "label": labels.get(room_id, "Corridor outside 219" if room_id == "corridor-219" else f"Room {room_id}"),
                      "floor": 2, "sweep": mapping.get("id", ""), "view_rotation": mapping.get("view_rotation"),
                      "tag_xyz": [position.get(axis, 0) for axis in ("x", "y", "z")],
                      "mapping_status": "operator_mapped" if mapping else "unmapped"})
    by_id = {room["id"]: room for room in rooms}
    definitions = [(row["device_id"], row["type"], row["room"]) for row in inventory] if inventory else [(f"rdr-{room}", "badge_reader", room) for room in ROOM_IDS] + [("lt-219", "laptop", "219"), ("cam-03", "camera", "corridor-219")]
    devices = [{"id": device, "type": kind, "room": room,
                "sweep": by_id[room]["sweep"], "tag_xyz": by_id[room]["tag_xyz"],
                "mapping_status": by_id[room]["mapping_status"],
                **({"network": "air_gapped"} if device == "lt-219" else {})}
               for device, kind, room in definitions]
    count = sum(room["mapping_status"] == "operator_mapped" for room in rooms)
    return {"case_id": "1010F", "title": "The Titan Files", "model_id": model_id(),
            "time_zone": "EST", "utc_offset": "-05:00", "crime_room": "219",
            "mapping_status": "mapped" if count == len(rooms) else "partial" if count else "unmapped",
            "rooms": rooms, "devices": devices, "demo_walk": dict(DEMO_WALK),
            "coverage_status": "unmapped", "walk_time_status": "sweep_estimates" if count else "unmeasured"}
