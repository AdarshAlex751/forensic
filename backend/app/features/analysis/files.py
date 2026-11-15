"""Inputs and outputs for the analysis slice.

Reads only the files CONTRACTS.md lists for Person 3; writes only data/analysis/*.json.
"""
import csv
import json
from pathlib import Path
from typing import Any

from app.shared.config import DATA_DIR, use_real
from app.shared.merge import load

OUT_DIR = DATA_DIR / "analysis"


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def load_events() -> list[dict]:
    """All events. Real events.json already holds story + background (FORMAT.md section 1);
    the fake splits background into events_baseline.json, so add it only in fake mode."""
    events = load("evidence", "events.json")
    if not use_real("evidence"):
        baseline = DATA_DIR / "evidence" / "fake" / "events_baseline.json"
        if baseline.exists():
            events = events + json.loads(baseline.read_text(encoding="utf-8"))
    # Released evidence (the parking exit log) needs nothing here: after approval, release.py marks it released
    # and the evidence stage writes its events into events.json, then the pipeline reruns this slice.
    return events


def load_inputs() -> dict[str, Any]:
    return {
        "events": load_events(),
        "evidence": load("evidence", "evidence.json"),
        "inventory": _read_csv(DATA_DIR / "evidence" / "inventory.csv"),
        "devices_csv": _read_csv(DATA_DIR / "evidence" / "devices.csv"),
        "devices": load("scene", "devices.json"),
        "rooms": load("scene", "rooms.json"),
    }


def load_previous(name: str, out_dir: Path | None = None) -> list[dict] | None:
    """The last written data/analysis/<name>.json, or None on a first run."""
    path = (out_dir or OUT_DIR) / f"{name}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_outputs(outputs: dict[str, list], out_dir: Path | None = None) -> None:
    """outputs: {"persons": [...], "edges": [...]}; writes <name>.json for each."""
    out = out_dir or OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    for name, data in outputs.items():
        tmp = out / f"{name}.json.tmp"
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(out / f"{name}.json")  # atomic swap so the merge never reads half a file
