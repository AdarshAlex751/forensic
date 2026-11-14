"""Background behaviour of everyone on the floor, 02-23 to 03-08, as Records.

Reuses the simulation in fakes/make_baseline.py (same seed), so the generated case has exactly the background
behaviour the fakes already describe. The story people's 03-04 evening is left out here; story.py supplies it.

Also derives each person's day on the floor (first arrival, last departure), which other builders use for parking,
email timing and so on.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from functools import cache

from ..fakes import make_baseline as mb
from .csv_writer import parse_row
from .records import EventSpec, Record
from .world import parse_ts


class _RecordingGen(mb.Gen):
    """The baseline simulation, collecting Records instead of event dicts."""

    def __init__(self):
        super().__init__()
        self.records: list[Record] = []

    def _ev(self, t, typ, device, room, actor, attrs, sfile, quote):
        super()._ev(t, typ, device, room, actor, attrs, sfile, quote)  # keeps the baseline's own bookkeeping
        ev = EventSpec(type=typ, t=t, actor=actor, device=device, room=room, attrs=dict(attrs))
        self.records.append(Record(source=sfile, t=t, fields=parse_row(sfile, quote), events=[ev]))


@dataclass(frozen=True)
class FloorDay:
    person_id: str
    day: date
    arrive: datetime
    depart: datetime


@cache
def _run() -> tuple[tuple[Record, ...], tuple[FloorDay, ...]]:
    g = _RecordingGen()
    g.run()
    story_ids = mb._story_ids(g)
    cutoff = mb.INCIDENT_CUTOFF
    keep = []
    for r in g.records:
        ev = r.events[0]
        if ev.t >= cutoff and ev.t.date() == mb.INCIDENT_DAY and ev.actor["value"] in story_ids:
            continue  # same safety net as the fake baseline: the story owns this evening
        keep.append(r)
    badge_owner = {p["badge"]: p["person_id"] for p in g.people if p["badge"]}
    spans: dict[tuple[str, date], list[datetime]] = {}
    for r in keep:
        ev = r.events[0]
        if ev.type in ("badge_in", "badge_out"):
            pid = badge_owner[ev.actor["value"]]
            spans.setdefault((pid, ev.t.date()), []).append(ev.t)
    days = tuple(FloorDay(pid, d, min(v), max(v)) for (pid, d), v in sorted(spans.items()))
    return tuple(keep), days


def records() -> list[Record]:
    return list(_run()[0])


def floor_days() -> list[FloorDay]:
    """One entry per person per day they badged on the floor (background part only; story evening excluded)."""
    return list(_run()[1])


def check_against_fake_baseline() -> int:
    """Sanity check: the Records reproduce the fake baseline quotes exactly. Returns the number compared."""
    import json

    from .csv_writer import row_text

    fake = json.loads((mb.EVIDENCE / "fake" / "events_baseline.json").read_text(encoding="utf-8"))
    ours = sorted((ev.type, r.source, row_text(r.source, r.fields)) for r in records() for ev in r.events)
    want = sorted((e["type"], e["source"]["file"], e["source"]["quote"]) for e in fake)
    if ours != want:
        diff = set(ours) ^ set(want)
        raise AssertionError(f"presence records differ from the fake baseline, e.g. {sorted(diff)[:3]}")
    _ = parse_ts  # imported for callers that mix fake and generated times
    return len(want)
