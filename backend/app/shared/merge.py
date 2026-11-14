"""Merges each slice's output files into one findings dict.

Per file: use data/<slice>/<file> when USE_REAL_<SLICE>=true and the file exists,
otherwise data/<slice>/fake/<file>.
"""
import json
import logging
from pathlib import Path
from typing import Any

from app.shared.config import DATA_DIR, use_real

log = logging.getLogger(__name__)


def load(slice_name: str, filename: str) -> Any:
    real = DATA_DIR / slice_name / filename
    fake = DATA_DIR / slice_name / "fake" / filename
    path: Path = fake
    if use_real(slice_name):
        if real.exists():
            path = real
        else:
            log.warning("USE_REAL_%s=true but %s is missing; using fake", slice_name.upper(), real)
    return json.loads(path.read_text(encoding="utf-8"))


def build_findings() -> dict[str, Any]:
    verification = load("investigator", "verification.json")
    verified_ids = set(verification.get("verified_event_ids", []))
    events = [{**e, "verified": e["id"] in verified_ids} for e in load("evidence", "events.json")]
    return {
        "case": load("evidence", "case.json"),
        "evidence": load("evidence", "evidence.json"),
        "persons": load("analysis", "persons.json"),
        "devices": load("scene", "devices.json"),
        "rooms": load("scene", "rooms.json"),
        "events": events,
        "edges": load("analysis", "edges.json"),
        "contradictions": load("analysis", "contradictions.json"),
        "hypotheses": load("investigator", "hypotheses.json"),
        "requests": load("investigator", "requests.json"),
        "notes": load("investigator", "notes.json"),
        "verification": verification,
        "eval": load("scene", "eval.json"),
    }
