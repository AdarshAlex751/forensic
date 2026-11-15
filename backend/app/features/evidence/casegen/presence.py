"""Background behaviour of everyone on the floor, 02-23 to 03-08, as Records.

Reuses the simulation in fakes/make_baseline.py (same seed), so the generated case has exactly the background
behaviour the fakes already describe, for everyone except Frederik. The story people's 03-04 evening is left out
here; story.py supplies it.

Frederik (IT contractor) is not on the floor at random: his visits are driven by his work orders. The baseline's
random Frederik visits are dropped (the simulation still runs them, so the shared rng and everyone else's records
are untouched) and replaced by one visit per physical work order assigned to him (sources.maintenance_records() plus
the story's work orders). Remote work (AP firmware, anything starting at 22:00 or later) needs no presence. His
03-04 evening patch window belongs to story.py.

Also derives each person's day on the floor (first arrival, last departure), which other builders use for parking,
email timing and so on.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cache

from ..fakes import make_baseline as mb
from .csv_writer import parse_row
from .records import EventSpec, Record
from .world import F_MAINT, INCIDENT_DAY, LAB_HOST, SEED_PRESENCE, devices, layout, parse_ts, person

FREDERIK = "p_frederik"
FREDERIK_NAME = "Frederik Mendelssohn"
LOBBY_AP = "ap-2-02"                       # covers lobby-2: where anyone without a badge read enters the floor
PHYSICAL_TYPES = {"camera", "laptop", "badge_reader", "printer"}
REMOTE_FROM_HOUR = 22                      # night work orders are done remotely


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


@dataclass(frozen=True)
class WorkOrder:
    work_order: str
    asset: str
    start: datetime
    end: datetime
    description: str


def _frederik_ids() -> set[str]:
    p = person(FREDERIK)
    return {v for v in (p["badge"], p["laptop_mac"], p["local_account"]) if v}


def frederik_work_orders() -> list[WorkOrder]:
    """Every work order assigned to Frederik: the noise calendar plus the story rows, in time order."""
    from . import sources, story  # lazy: sources imports this module

    out = []
    for r in sources.maintenance_records() + [r for r in story.csv_records() if r.source == F_MAINT]:
        f = r.fields
        if f["technician"] != FREDERIK_NAME:
            continue
        out.append(WorkOrder(f["work_order"], f["asset"], parse_ts(f["start"]), parse_ts(f["end"]),
                             f["description"]))
    return sorted(out, key=lambda w: w.start)


def _asset_type(asset: str) -> str | None:
    if asset in devices():
        return devices()[asset]["type"]
    if asset.startswith("prn-"):
        return "printer"
    return None


def is_physical(wo: WorkOrder) -> bool:
    """On-site work: cameras, lt-219, printers, badge readers, during the day. AP / controller / night work is remote."""
    return _asset_type(wo.asset) in PHYSICAL_TYPES and wo.start.hour < REMOTE_FROM_HOUR


def _asset_ap(asset: str) -> str:
    """The AP covering the asset's room or corridor (first in id order); printers and unknowns: the lobby AP."""
    room = devices()[asset]["room"] if asset in devices() else None
    for ap, spaces in sorted(layout()["ap_coverage"].items()):
        if room in spaces:
            return ap
    return LOBBY_AP


_AV_PATHS = [
    ("C:\\Patches\\AV\\{ym}\\mpam-fe_x64.exe", 150_000_000, 175_000_000),
    ("C:\\Patches\\AV\\{ym}\\nis_full_x64.exe", 2_000_000, 4_500_000),
    ("C:\\Patches\\AV\\{ym}\\offline_update_readme.txt", 3_000, 9_000),
    ("C:\\ProgramData\\Microsoft\\Windows Defender\\Support\\MPLog-{ymd}.log", 400_000, 2_500_000),
]
_PATCH_PATHS = [
    ("C:\\Patches\\{ym}\\windows11.0-x64-cumulative.msu", 380_000_000, 460_000_000),
    ("C:\\Patches\\{ym}\\patch_manifest.txt", 2_000, 8_000),
    ("C:\\Windows\\Logs\\CBS\\CBS.log", 8_000_000, 24_000_000),
]


def _frederik_visit(g: _RecordingGen, wo: WorkOrder) -> None:
    """One on-site visit: arrive 10-25 min before the window, leave 5-20 min after it."""
    rng = g.rng
    p = person(FREDERIK)
    badge, mac, acct = p["badge"], p["laptop_mac"], p["local_account"]
    arrive = wo.start - g.sec(10 * 60, 25 * 60)
    depart = wo.end + g.sec(5 * 60, 20 * 60)
    target_ap = _asset_ap(wo.asset)
    g.wifi(arrive, mac, LOBBY_AP, "ASSOC")
    at_asset = arrive + g.sec(70, 200)
    if target_ap != LOBBY_AP:
        g.wifi(at_asset, mac, target_ap, "ROAM")
    leave_asset = depart - g.sec(70, 200)
    if wo.asset == LAB_HOST:
        b_in = at_asset + g.sec(15, 60)
        b_out = wo.end + g.sec(60, 4 * 60)
        if b_out >= leave_asset:
            leave_asset = b_out + g.sec(20, 60)
        g.badge(b_in, badge, mb.LAB_ROOM, "IN")
        on = b_in + g.sec(40, 120)
        off = b_out - g.sec(30, 100)
        g.logon(on, acct)
        templ = _AV_PATHS if "antivirus" in wo.description.lower() else _PATCH_PATHS
        picks = rng.sample(templ, min(len(templ), rng.randint(3, 4)))
        lo_t = max(on + timedelta(seconds=90), wo.start)   # the reads fall inside the work-order window
        hi_t = min(off - timedelta(seconds=90), wo.end)
        span = int((hi_t - lo_t).total_seconds())
        offsets = sorted(rng.sample(range(0, span), len(picks)))
        ym, ymd = wo.start.strftime("%Y-%m"), wo.start.strftime("%Y%m%d")
        for (path, lo, hi), o in zip(picks, offsets):
            g.file_read(lo_t + timedelta(seconds=o), acct, path.format(ym=ym, ymd=ymd), rng.randint(lo, hi))
        g.logoff(off, acct)
        g.badge(b_out, badge, mb.LAB_ROOM, "OUT")
    if target_ap != LOBBY_AP:
        g.wifi(leave_asset, mac, LOBBY_AP, "ROAM")
    g.wifi(depart, mac, LOBBY_AP, "DISASSOC")


def _frederik_records() -> list[Record]:
    g = _RecordingGen()
    g.rng = random.Random(SEED_PRESENCE * 100 + 4)  # own stream: never touches the baseline simulation
    for wo in frederik_work_orders():
        if wo.start.date() == INCIDENT_DAY or not is_physical(wo):
            continue  # 03-04 evening: story.py; remote work: no presence
        _frederik_visit(g, wo)
    return g.records


@cache
def _baseline() -> tuple[Record, ...]:
    """The fake baseline's records exactly (same filters as make_baseline.main())."""
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
    return tuple(keep)


@cache
def _run() -> tuple[tuple[Record, ...], tuple[FloorDay, ...]]:
    fred = _frederik_ids()
    keep = [r for r in _baseline() if r.events[0].actor["value"] not in fred] + _frederik_records()
    owner = {}
    for p in mb.load_inputs()[1]:
        for k in ("badge", "laptop_mac"):
            if p[k]:
                owner[p[k]] = p["person_id"]
    spans: dict[tuple[str, date], list[datetime]] = {}
    for r in keep:
        ev = r.events[0]
        if ev.type.startswith("badge_") or ev.type.startswith("wifi_"):
            pid = owner[ev.actor["value"]]
            spans.setdefault((pid, ev.t.date()), []).append(ev.t)
    days = tuple(FloorDay(pid, d, min(v), max(v)) for (pid, d), v in sorted(spans.items()))
    return tuple(keep), days


def records() -> list[Record]:
    return list(_run()[0])


def floor_days() -> list[FloorDay]:
    """One entry per person per day they were on the floor: first..last of their badge and Wi-Fi events
    (background part only; story evening excluded). Wi-Fi counts, so Frederik's camera visits (no badge) appear."""
    return list(_run()[1])


def check_against_fake_baseline() -> int:
    """Sanity check: every non-Frederik Record reproduces the fake baseline quotes exactly (Frederik is rebuilt from
    his work orders). Returns the number compared."""
    import json

    from .csv_writer import row_text

    fred = _frederik_ids()
    fake = json.loads((mb.EVIDENCE / "fake" / "events_baseline.json").read_text(encoding="utf-8"))
    ours = sorted((ev.type, r.source, row_text(r.source, r.fields)) for r in records() for ev in r.events
                  if ev.actor["value"] not in fred)
    want = sorted((e["type"], e["source"]["file"], e["source"]["quote"]) for e in fake
                  if e["actor"]["value"] not in fred)
    if ours != want:
        diff = set(ours) ^ set(want)
        raise AssertionError(f"presence records differ from the fake baseline, e.g. {sorted(diff)[:3]}")
    return len(want)
