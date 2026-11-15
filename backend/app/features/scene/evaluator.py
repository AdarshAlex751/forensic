"""Judge-only evaluation; only this module reads the hidden answer key.

Key contract: planted[].sources = [{file, line}]. IDs are never match criteria.
The obsolete event-only key yields pending, not a fabricated score.
"""
import json
from .config import ROOT


def _sources(item: dict) -> frozenset:
    rows = item.get("sources", [])
    if item.get("source"):
        rows = [*rows, item["source"]]
    return frozenset((row["file"].replace("\\", "/"), row["line"])
                     for row in rows if isinstance(row, dict)
                     and isinstance(row.get("file"), str) and type(row.get("line")) is int
                     and row["line"] > 0)


def evaluate(answer_key: dict, contradictions: list, events: list, runtime_s: float = 0) -> dict:
    planted = answer_key.get("planted", [])
    base = {"planted": len(planted), "found": 0, "false_alarms": 0, "runtime_s": runtime_s, "missed": []}
    if not planted or any(not _sources(item) for item in planted):
        return {**base, "status": "pending", "reason": "Waiting for the CASE.md answer key with file-and-line citations."}
    by_event = {event["id"]: event for event in events}
    detected = []
    for finding in contradictions:
        citations = set(_sources(finding))
        for event_id in finding.get("events", []):
            citations.update(_sources(by_event.get(event_id, {})))
        detected.append((finding, citations))
    matched_findings = set()
    found = 0
    missed = []
    for planted_item in planted:
        required = _sources(planted_item)
        matches = [index for index, (finding, citations) in enumerate(detected)
                   if finding.get("kind") == planted_item.get("kind") and required <= citations]
        if matches:
            found += 1
            matched_findings.update(matches)
        else:
            missed.append({"id": planted_item["id"], "why": "No finding with the required file-and-line citations."})
    return {**base, "status": "evaluated", "found": found,
            "false_alarms": len(detected) - len(matched_findings), "missed": missed}


def get_evaluation() -> dict:
    pending = {"status": "pending", "reason": "Waiting for real case analysis and source-cited answer key.",
               "planted": 0, "found": 0, "false_alarms": 0, "runtime_s": 0, "missed": []}
    try:
        key = json.loads((ROOT / "data/evidence/answer_key.json").read_text(encoding="utf-8"))
        validation = evaluate(key, [], [])
        if validation["status"] == "pending":
            return validation
        events = json.loads((ROOT / "data/evidence/events.json").read_text(encoding="utf-8"))
        findings = json.loads((ROOT / "data/analysis/contradictions.json").read_text(encoding="utf-8"))
        return evaluate(key, findings, events)
    except (OSError, ValueError, KeyError, TypeError):
        return pending
