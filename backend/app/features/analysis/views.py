"""Page-ready fields for the two analysis pages. Presentation only: nothing here changes a score or a finding.

Page "Red flags" (anomalies): each person gets a rank, plain-language red flags (feature vs own baseline)
and context facts (work-order coverage), and every line cites the events behind it.

Page "Contradictions" (fact -> evidence chain): each contradiction gets a title, two sides to show side by side,
a chain (finding -> each cited event -> its source line), a time and room for the timeline/scene, and a
`change` marker against the previous run, so a finding that appears after released evidence (C3, the parking
exit log) is shown as new or updated. Ids are kept stable across reruns.

All added fields are new (CONTRACTS rule 6: adding a field is fine).
"""
from collections import defaultdict
from typing import Any

from app.features.analysis import anomaly_features, timeutil, vocab

# ---------------------------------------------------------------- red flags (anomalies)

FEATURE_LABELS = {
    "after_hours_minutes": ("after-hours minutes on the floor", "{v:.0f} min after hours"),
    "after_hours_badge_reads": ("after-hours badge reads", "{v:.0f} badge read(s) after hours"),
    "distinct_rooms": ("distinct rooms", "in {v:.0f} different rooms"),
    "files_touched": ("files touched", "touched {v:.0f} file(s)"),
    "bytes_copied": ("bytes copied", "copied {mb:.1f} MB"),
    "usb_mounts": ("USB mounts", "{v:.0f} USB mount(s)"),
}


def _day_events(events: list[dict], person: str, day: str) -> list[dict]:
    out = [e for e in events if e.get("person") == person and e.get("t") and e.get("type") in anomaly_features.PRESENCE
           and str(timeutil.local_day(timeutil.parse(e["t"]))) == day]
    return sorted(out, key=lambda e: timeutil.parse(e["t"]))


def _feature_events(evs: list[dict]) -> dict[str, list[str]]:
    """Which events produced each feature value (same definitions as anomaly_features.daily_features)."""
    after = [e for e in evs if timeutil.is_after_hours(timeutil.parse(e["t"]))]
    first_in_room: dict[str, str] = {}
    for e in evs:
        if e.get("room"):
            first_in_room.setdefault(e["room"], e["id"])
    return {
        "after_hours_minutes": [after[0]["id"], after[-1]["id"]] if len(after) > 1 else [],
        "after_hours_badge_reads": [e["id"] for e in after if e["type"] in vocab.BADGE],
        "distinct_rooms": list(first_in_room.values()),
        "files_touched": [e["id"] for e in evs if e["type"] in vocab.FILE_ACCESS],
        "bytes_copied": [e["id"] for e in evs if e["type"] in vocab.FILE_COPY],
        "usb_mounts": [e["id"] for e in evs if e["type"] in vocab.USB],
    }


def _work_order_events(events: list[dict], person: str, day: str) -> list[str]:
    return [e["id"] for e in events if e.get("type") in vocab.MAINTENANCE and e.get("person") == person
            and (e.get("attrs") or {}).get("start", "")[:10] == day]


def red_flags(persons: list[dict], events: list[dict]) -> list[dict]:
    """Adds anomaly_rank, red_flags and context to each person (in place) and returns them."""
    ranked = sorted((p for p in persons if p.get("anomaly", 0) > 0), key=lambda p: -p["anomaly"])
    for i, p in enumerate(ranked, start=1):
        p["anomaly_rank"] = i
    for p in persons:
        p.setdefault("anomaly_rank", None)
        f = p.get("features") or {}
        day = f.get("day")
        p["red_flags"], p["context"] = [], []
        if not day:
            continue
        evs = _day_events(events, p["id"], day)
        cited = _feature_events(evs)
        for name, (label, fmt) in FEATURE_LABELS.items():
            value, dev = f.get(name, 0.0), f.get(f"{name}_dev", 0.0)
            if value <= 0 or dev <= 0:  # only what is above this person's own usual day
                continue
            baseline = round(value - dev, 2)
            text = fmt.format(v=value, mb=value / 1e6)
            usual = f"usually {baseline / 1e6:.1f} MB" if name == "bytes_copied" else f"usually {baseline:g}"
            p["red_flags"].append({
                "feature": name, "label": label, "value": value, "baseline": baseline,
                "text": f"{text} on {day} ({usual})", "events": cited[name],
            })
        covered, late = f.get("after_hours_in_work_order_minutes", 0.0), f.get("after_hours_minutes", 0.0)
        if covered > 0:
            p["context"].append({
                "kind": "work_order",
                "text": f"{covered:.0f} of {late:.0f} after-hours minutes fall inside a maintenance window assigned to them.",
                "events": _work_order_events(events, p["id"], day),
            })
    return persons


# ---------------------------------------------------------------- contradictions (fact -> evidence chain)

TITLES = {
    "custody_mismatch": "Evidence file fails its manifest hash",
    "impossible_travel": "Same identity in two rooms faster than the walk",
    "wifi_after_last_badge": "Laptop on Wi-Fi after the last badge-out",
    "camera_gap_without_work_order": "Camera offline with no work order",
    "leave_time_claim": "Stated leaving time vs the records",
    "drive_history_claim": "Stated drive history vs USB history",
    "nli": "Statement contradicted by the records",
}
CLAIM_RULES = {"leave_time_claim", "drive_history_claim", "nli"}


def _sides(c: dict, by_id: dict[str, dict]) -> list[dict]:
    """Two sides of the conflict, shown side by side. Each side cites its own events."""
    ev, rule = c.get("events") or [], c.get("rule")
    if rule in CLAIM_RULES:
        a, b = ("Said", ev[:1]), ("Records", ev[1:])
    elif rule == "custody_mismatch":
        a, b = ("Manifest", []), (f"Events from {c.get('file')}", ev)
    elif rule == "camera_gap_without_work_order":
        a, b = ("Camera log", ev), ("Work orders", [])
    else:
        a, b = ("First record", ev[:1]), ("Second record", ev[1:])
    out = []
    for label, ids in (a, b):
        quotes = [by_id[x]["source"]["quote"] for x in ids[:3] if x in by_id]
        if label == "Manifest":
            quotes = [f"{c.get('file')} does not match its manifest hash"]
        if label == "Work orders":
            quotes = ["No maintenance window or work order covers this camera at that time"]
        out.append({"label": label, "events": ids, "quotes": quotes, "more": max(0, len(ids) - 3)})
    return out


def _chain(c: dict, by_id: dict[str, dict]) -> list[dict]:
    """finding -> fact (event) -> evidence (source line + file hash)."""
    return [
        {"event": x, "t": e.get("t"), "type": e.get("type"), "person": e.get("person"),
         "room": e.get("room"), "device": e.get("device"), "source": e.get("source")}
        for x in c.get("events") or [] if (e := by_id.get(x))
    ]


def _when_where(c: dict, by_id: dict[str, dict]) -> tuple[str | None, str | None]:
    """Time and room of the conflict for the timeline and the scene: the records, not the statement."""
    ev = [by_id[x] for x in c.get("events") or [] if x in by_id]
    records = [e for e in ev if e.get("type") not in vocab.STATEMENT | vocab.MESSAGE] or ev
    if c.get("rule") == "custody_mismatch":
        return None, None
    t = min((e["t"] for e in records if e.get("t")), key=timeutil.parse, default=None)
    rooms = [e["room"] for e in records if e.get("room")]
    room = rooms[-1] if c.get("rule") == "impossible_travel" and rooms else (rooms[0] if rooms else None)
    return t, room


def _key(c: dict) -> str:
    """Identity of a finding across reruns: same rule, same first cited event (the claim or first record),
    same persons. A finding whose other cited records change (new evidence) keeps its key and id."""
    ev = c.get("events") or []
    return "|".join([c.get("rule", ""), ev[0] if ev else "", ",".join(sorted(c.get("persons") or [])),
                     c.get("file") or ""])


def number(found: list[dict], events: list[dict], previous: list[dict] | None = None) -> list[dict]:
    """Ids c1.. (stable across reruns), sources (CONTRACTS rule 9) and the page fields.

    `previous` is the last contradictions.json. With it, a finding gets change = "new" (not there before) or
    "updated" (same finding, different cited records, e.g. once the parking exit log is released).
    """
    by_id = {e["id"]: e for e in events}
    prev = {c.get("key") or _key(c): c for c in previous or []}
    next_n = max((int(c["id"][1:]) for c in previous or [] if str(c.get("id", "c")).lstrip("c").isdigit()), default=0)
    out = []
    for c in found:
        k = _key(c)
        old = prev.get(k)
        if old:
            cid = old["id"]
            change = "updated" if sorted(old.get("events") or []) != sorted(c.get("events") or []) else None
        else:
            next_n += 1
            cid, change = f"c{next_n}", ("new" if previous else None)
        t, room = _when_where(c, by_id)
        out.append({
            "id": cid, **c,
            "sources": [by_id[x]["source"] for x in c["events"] if x in by_id],
            "title": TITLES.get(c.get("rule"), "Contradiction"),
            "sides": _sides(c, by_id),
            "chain": _chain(c, by_id),
            "t": t,
            "room": room,
            "change": change,
            "key": k,
        })
    return sorted(out, key=lambda c: int(c["id"][1:]))


def changed(contradictions: list[dict]) -> list[str]:
    """Ids of findings that are new or updated since the previous run, in id order."""
    return [c["id"] for c in sorted(contradictions, key=lambda c: int(c["id"][1:])) if c.get("change")]


def latest_change(contradictions: list[dict]) -> str | None:
    """Id of the finding the page opens on after a rerun: the first new/updated one."""
    ids = changed(contradictions)
    return ids[0] if ids else None


def groups(contradictions: list[dict]) -> list[dict[str, Any]]:
    """Cards grouped by rule, so many findings of one kind collapse into one stack on the page."""
    g: dict[str, list[str]] = defaultdict(list)
    for c in contradictions:
        g[c.get("rule", "")].append(c["id"])
    return [{"rule": r, "title": TITLES.get(r, r), "count": len(ids), "ids": ids} for r, ids in g.items()]
