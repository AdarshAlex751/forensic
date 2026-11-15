"""Explicit case coverage, independent of camera navigation and device uptime."""
import json
from .config import SCENE_DIR


class UnknownCoverageError(ValueError):
    """Missing coverage is unknown, never a negative observation."""


def coverage_for(device_id: str, room_id: str, kind: str) -> bool:
    try:
        data = json.loads((SCENE_DIR / "coverage.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UnknownCoverageError("Scene coverage configuration is unavailable.") from exc
    if data.get("case_id") != "1010F":
        raise UnknownCoverageError("Coverage configuration belongs to a different case.")
    records = data.get("devices", {})
    record = records.get(device_id)
    if not isinstance(record, dict) or record.get("type") != kind:
        raise UnknownCoverageError(f"No {kind} coverage configured for {device_id!r}.")
    covered = record.get("covered_rooms", [])
    excluded = record.get("excluded_rooms", [])
    if not isinstance(covered, list) or not isinstance(excluded, list):
        raise ValueError("Coverage room lists must be arrays.")
    if any(not isinstance(room, str) for room in covered + excluded):
        raise ValueError("Coverage room IDs must be strings.")
    if set(covered) & set(excluded):
        raise ValueError("Coverage has conflicting included and excluded rooms.")
    if room_id in covered or room_id in excluded:
        if not record.get("source"):
            raise UnknownCoverageError("Coverage decisions require a source or approved scenario basis.")
        return room_id in covered
    raise UnknownCoverageError(f"Coverage of {room_id!r} by {device_id!r} is not configured.")
