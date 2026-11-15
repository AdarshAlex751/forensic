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


def fill_persons(events: list[dict[str, Any]], persons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill each event's `person` from the persons' aliases ("kind:value", e.g. "badge:40388") matched against the
    event's raw `actor` ({kind, value}). Evidence leaves `person` null (data/evidence/FORMAT.md); this is the one place
    that resolves it, the same pattern as `verified`. An event that already has a person keeps it, and an alias shared by
    two people is ambiguous, so it resolves to nobody. Inputs are not mutated."""
    index: dict[tuple[str, str], str | None] = {}
    for p in persons:
        pid = p.get("id")
        for alias in p.get("aliases") or []:
            if not pid or not isinstance(alias, str) or ":" not in alias:
                continue
            kind, value = alias.split(":", 1)
            key = (kind.strip().lower(), value.strip().lower())
            index[key] = pid if index.get(key, pid) == pid else None
    out = []
    for e in events:
        actor = e.get("actor") or {}
        pid = None if e.get("person") or not actor else index.get((str(actor.get("kind", "")).lower(), str(actor.get("value", "")).lower()))
        out.append({**e, "person": pid} if pid else e)
    return out


def build_findings() -> dict[str, Any]:
    verification = load("investigator", "verification.json")
    verified_ids = set(verification.get("verified_event_ids", []))
    persons = load("analysis", "persons.json")
    events = [{**e, "verified": e["id"] in verified_ids} for e in fill_persons(load("evidence", "events.json"), persons)]
    return {
        "case": load("evidence", "case.json"),
        "evidence": load("evidence", "evidence.json"),
        "persons": persons,
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
