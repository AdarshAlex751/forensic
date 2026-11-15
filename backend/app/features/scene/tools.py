"""Spatial interfaces: scan estimates are not proven physical minimums."""
from .config import ROOM_IDS, load_mapping, get_config
from .sweep_graph import route
from .devices import coverage_for


def _validate(room: str) -> None:
    if room not in {row["id"] for row in get_config()["rooms"]}:
        raise ValueError(f"Unknown case room: {room!r}")


def walk_time(room_a: str, room_b: str) -> dict:
    _validate(room_a)
    _validate(room_b)
    if room_a == room_b:
        return {"seconds": 0, "path": [room_a], "status": "same_room"}
    if {room_a, room_b} == {"230", "219"}:
        return {"seconds": 74, "path": [room_a, room_b], "status": "configured_case_time"}
    mapping = load_mapping()
    rooms = mapping.get("rooms", {})
    if room_a in rooms and room_b in rooms:
        result = route(mapping.get("sweeps", []), rooms[room_a]["id"], rooms[room_b]["id"])
        return {**result, "path": [room_a, room_b]}
    raise ValueError("Walking route has not been mapped for this room pair.")


def ap_covers(ap_id: str, room_id: str) -> bool:
    _validate(room_id)
    return coverage_for(ap_id, room_id, "wifi_ap")


def camera_sees(camera_id: str, room_id: str) -> bool:
    _validate(room_id)
    return coverage_for(camera_id, room_id, "camera")
