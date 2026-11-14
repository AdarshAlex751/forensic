"""Background (noise) Records for four CSV sources: CCTV index, IT maintenance calendar, Hank's bank account and the
parking log.

The story rows for these files come from story.csv_records() and are written by build.py; everything here is the
ordinary activity around them and is built to agree with those rows (CCTV gaps, work-order numbers, the running bank
balance, the story-owned parking person-days). Each public function makes its own seeded rng, so the functions are
independent and every run gives the same Records.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from . import presence, story
from .csv_writer import HEADERS
from .records import EventSpec, Record
from .world import (F_CCTV, F_MAINT, F_PARKING, F_TXN, INCIDENT_DAY, SEED_SOURCES, at, days, devices, parse_ts,
                    people, person, ts)

CAMERAS = sorted(d for d, row in devices().items() if row["type"] == "camera")  # cam-01 .. cam-06

TXN_ACCOUNT = "CHK-7731"
TXN_OWNER = "p_hank"

# Person-days on 2026-03-04 that the story owns outright in the parking log.
STORY_PARKING_PEOPLE = ("p_alma", "p_hank", "p_maggie", "p_bg_17", "p_frederik")


def _rng(k: int) -> random.Random:
    return random.Random(SEED_SOURCES * 100 + k)


def _check(source: str, fields: dict[str, str]) -> dict[str, str]:
    assert list(fields) == HEADERS[source], (source, list(fields))
    return fields


# --------------------------------------------------------------------------------------------------- 1. CCTV index

def story_cctv_gaps() -> dict[tuple[str, date], list[tuple[datetime, datetime]]]:
    """(camera, day) -> the story's OFFLINE windows, read from story.csv_records()."""
    gaps: dict[tuple[str, date], list[tuple[datetime, datetime]]] = {}
    for r in story.csv_records():
        if r.source == F_CCTV and r.fields["status"] == "OFFLINE":
            s, e = parse_ts(r.fields["window_start"]), parse_ts(r.fields["window_end"])
            gaps.setdefault((r.fields["camera_id"], s.date()), []).append((s, e))
    return {k: sorted(v) for k, v in gaps.items()}


def _recording(cam: str, start: datetime, end: datetime) -> Record:
    fields = _check(F_CCTV, {
        "camera_id": cam,
        "window_start": ts(start),
        "window_end": ts(end),
        "status": "RECORDING",
        "clip_ref": f"clips/{cam}/{start.strftime('%Y%m%d_%H%M%S')}.mp4",
    })
    return Record(source=F_CCTV, t=start, fields=fields, events=[])


def cctv_records() -> list[Record]:
    """RECORDING windows for every camera and day, split around the story OFFLINE windows (which story owns)."""
    gaps = story_cctv_gaps()
    out = []
    for d in days():
        for cam in CAMERAS:
            cursor = at(d, 0, 0, 0)
            day_end = at(d, 23, 59, 59)
            for s, e in gaps.get((cam, d), []):
                if s > cursor:
                    out.append(_recording(cam, cursor, s))
                cursor = e
            if cursor < day_end:
                out.append(_recording(cam, cursor, day_end))
    out.sort(key=lambda r: (r.t, r.fields["camera_id"]))
    return out


# ----------------------------------------------------------------------------------------- 2. Maintenance calendar

_FREDERIK = "Frederik Mendelssohn"
_DANA = "Dana Whitlock (Facilities)"
_RAVI = "Ravi Castellanos (Facilities)"
_LENA = "Lena Marsh (Copier vendor)"

# (work_order, day, start h:m, end h:m, asset, technician, description). Numbers increase with date and interleave
# with the story's WO-3091 (02-24 13:00), WO-3098 (02-26 07:00) and WO-3117 (03-04 19:00); gaps are other floors.
# No camera work (story owns it) and nothing on lt-219 on 03-04. The 02-23 lt-219 window sits inside Frederik's own
# badge visit to room 219 that afternoon (presence baseline 13:01-14:41).
_WORK_ORDERS = [
    ("WO-3080", date(2026, 2, 23), (7, 0), (7, 30), "rdr-224", _DANA, "Badge reader battery replacement"),
    ("WO-3082", date(2026, 2, 23), (13, 15), (14, 30), "lt-219", _FREDERIK,
     "Monthly antivirus definition update (offline media)"),
    ("WO-3083", date(2026, 2, 23), (22, 0), (22, 40), "ap-2-01", _FREDERIK, "AP firmware upgrade to 8.10.2"),
    ("WO-3086", date(2026, 2, 24), (8, 0), (9, 0), "hvac-2-ahu2", _RAVI, "HVAC filter change on air handler 2"),
    ("WO-3093", date(2026, 2, 25), (6, 30), (7, 0), "rdr-212", _DANA, "Door strike adjustment"),
    ("WO-3095", date(2026, 2, 25), (22, 0), (22, 40), "ap-2-02", _FREDERIK, "AP firmware upgrade to 8.10.2"),
    ("WO-3100", date(2026, 2, 26), (12, 0), (13, 0), "av-lounge-2", _RAVI, "Lounge AV projector lamp replacement"),
    ("WO-3102", date(2026, 2, 26), (22, 0), (22, 40), "ap-2-03", _FREDERIK, "AP firmware upgrade to 8.10.2"),
    ("WO-3104", date(2026, 2, 27), (7, 0), (8, 0), "hvac-2-ahu2", _RAVI, "HVAC thermostat calibration"),
    ("WO-3106", date(2026, 2, 27), (15, 0), (15, 45), "prn-2-02", _LENA, "Printer service and drum replacement"),
    ("WO-3108", date(2026, 2, 28), (10, 0), (12, 0), "hvac-2-ahu1", _RAVI, "Weekend HVAC belt inspection"),
    ("WO-3110", date(2026, 3, 2), (6, 30), (7, 0), "rdr-227", _DANA, "Badge reader battery replacement"),
    ("WO-3111", date(2026, 3, 2), (22, 0), (22, 40), "ap-2-04", _FREDERIK, "AP firmware upgrade to 8.10.2"),
    ("WO-3113", date(2026, 3, 3), (9, 0), (10, 30), "av-lounge-2", _RAVI, "Lounge AV setup for summit week"),
    ("WO-3115", date(2026, 3, 4), (7, 0), (7, 30), "prn-2-01", _LENA, "Printer paper feed repair"),
    ("WO-3120", date(2026, 3, 5), (22, 0), (22, 40), "ap-2-05", _FREDERIK, "AP firmware upgrade to 8.10.2"),
    ("WO-3122", date(2026, 3, 6), (6, 30), (7, 0), "rdr-215", _DANA, "Door strike replacement"),
    ("WO-3124", date(2026, 3, 6), (14, 0), (14, 30), "av-lounge-2", _RAVI, "Lounge AV teardown after summit"),
    ("WO-3126", date(2026, 3, 7), (9, 0), (11, 0), "hvac-2-ahu1", _RAVI, "Weekend HVAC filter change on air handler 1"),
    ("WO-3128", date(2026, 3, 8), (22, 0), (22, 40), "ap-2-06", _FREDERIK, "AP firmware upgrade to 8.10.2"),
]


def maintenance_records() -> list[Record]:
    _rng(2)  # the calendar is hand-authored; seed reserved so adding jitter later stays independent
    out = []
    for wo, d, (sh, sm), (eh, em), asset, tech, desc in _WORK_ORDERS:
        start, end = at(d, sh, sm), at(d, eh, em)
        dev = asset if asset in devices() else None
        room = devices()[asset]["room"] if dev else None
        fields = _check(F_MAINT, {"work_order": wo, "asset": asset, "start": ts(start), "end": ts(end),
                                  "technician": tech, "description": desc})
        ev = EventSpec(type="maintenance_window", t=start, actor={"kind": "name", "value": tech}, device=dev,
                       room=room, attrs={"start": ts(start), "end": ts(end), "asset": asset, "work_order": wo,
                                         "technician": tech})
        out.append(Record(source=F_MAINT, t=start, fields=fields, events=[ev]))
    out.sort(key=lambda r: r.t)
    return out


# ------------------------------------------------------------------------------------------------ 3. Transactions

def _story_txns() -> list[Record]:
    return sorted((r for r in story.csv_records() if r.source == F_TXN), key=lambda r: r.t)


def _cents(text: str) -> int:
    sign = -1 if text.startswith("-") else 1
    whole, frac = text.lstrip("+-").split(".")
    return sign * (int(whole) * 100 + int(frac))


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    c = abs(cents)
    return f"{sign}{c // 100}.{c % 100:02d}"


def _txn_plan(rng: random.Random) -> list[tuple[datetime, str, str, int]]:
    """Hank's ordinary activity as (time, description, counterparty, cents). Nothing on 03-04 after the morning
    (no card alibi either way) and nothing between the bonus (03-06 10:42) and the exchange transfer (03-07 09:15),
    so the story balances follow directly from each other."""
    plan = []

    def add(d, h, m, desc, cp, lo, hi):
        plan.append((at(d, h, m), desc, cp, -rng.randint(int(lo * 100), int(hi * 100))))

    coffee = ["Bluebird Coffee Co", "Cobalt Bean Roasters"]
    for d in days():
        wd = d.weekday()
        if wd < 5:  # weekday morning coffee
            add(d, 7, rng.randint(30, 59), "DEBIT CARD PURCHASE", rng.choice(coffee), 3.75, 6.95)
        if wd < 5 and d != INCIDENT_DAY and rng.random() < 0.45:
            add(d, 12, rng.randint(5, 50), "DEBIT CARD PURCHASE", rng.choice(
                ["Lindqvist Deli", "Saffron Bowl Kitchen", "Harbor Street Tacos"]), 9.50, 17.80)
    for d, h in [(date(2026, 2, 23), 19), (date(2026, 2, 26), 19), (date(2026, 3, 1), 11), (date(2026, 3, 5), 19),
                 (date(2026, 3, 8), 10)]:
        add(d, h, rng.randint(0, 50), "DEBIT CARD PURCHASE", "Greenfield Market", 48.00, 142.00)
    for d in [date(2026, 2, 24), date(2026, 3, 2), date(2026, 3, 7)]:
        add(d, 18 if d.weekday() < 5 else 14, rng.randint(25, 55), "DEBIT CARD PURCHASE", "Route 1 Fuel Stop",
            38.00, 61.00)
    for d, cp in [(date(2026, 2, 27), "Corner Table Bistro"), (date(2026, 2, 28), "Old Mill Tavern"),
                  (date(2026, 3, 7), "Lantern Noodle House")]:
        add(d, 19, rng.randint(10, 50), "DEBIT CARD PURCHASE", cp, 34.00, 88.00)
    add(date(2026, 2, 24), 3, 12, "RECURRING SUBSCRIPTION", "Streamwave Media", 15.99, 15.99)
    add(date(2026, 3, 3), 3, 12, "RECURRING SUBSCRIPTION", "Tunebox Music", 10.99, 10.99)
    add(date(2026, 2, 25), 9, 0, "ONLINE BILL PAY", "Mercer Electric and Gas", 96.00, 148.00)
    add(date(2026, 3, 2), 9, 0, "ONLINE BILL PAY", "Riverbend Water Utility", 38.00, 54.00)
    add(date(2026, 3, 5), 9, 0, "ONLINE BILL PAY", "Kestrel Wireless", 72.40, 72.40)
    add(date(2026, 3, 1), 6, 0, "ACH RENT PAYMENT", "Elmwood Property Management", 2150.00, 2150.00)
    add(date(2026, 2, 28), 13, rng.randint(0, 40), "ATM WITHDRAWAL", "Lakeside Community Bank ATM", 100.00, 100.00)
    plan.append((at(date(2026, 2, 27), 6, 0), "DIRECT DEPOSIT PAYROLL", "Halvorsen Dynamics", 341255))
    plan.append((at(date(2026, 3, 6), 6, 0), "DIRECT DEPOSIT FINAL PAYROLL", "Halvorsen Dynamics", 287410))
    return plan


def opening_balance_cents() -> int:
    """Balance before the first row, derived backwards from the story: the balance right before the bonus."""
    st = _story_txns()
    bonus = st[0]
    before_bonus = _cents(bonus.fields["balance"]) - _cents(bonus.fields["amount"])
    spent = sum(c for t, _, _, c in _txn_plan(_rng(3)) if t < bonus.t)
    return before_bonus - spent


def transaction_records() -> list[Record]:
    st = _story_txns()
    bonus, xfer = st[0], st[-1]
    plan = sorted(_txn_plan(_rng(3)))
    for t, *_ in plan:
        assert not (bonus.t <= t <= xfer.t), f"noise transaction inside the story window: {t}"
    bal = opening_balance_cents()
    story_left = list(st)
    out = []
    for t, desc, cp, cents in plan:
        while story_left and story_left[0].t < t:  # pass the story rows in time order, checking they agree
            s = story_left.pop(0)
            bal += _cents(s.fields["amount"])
            assert bal == _cents(s.fields["balance"]), (s.fields, _money(bal))
        bal += cents
        assert bal > 0, f"overdrawn at {t}"
        fields = _check(F_TXN, {"timestamp": ts(t), "account": TXN_ACCOUNT, "description": desc,
                                "counterparty": cp, "amount": _money(cents), "balance": _money(bal)})
        ev = EventSpec(type="transaction", t=t, actor={"kind": "name", "value": person(TXN_OWNER)["name"]},
                       device=None, room=None, attrs={"account": TXN_ACCOUNT, "amount": round(cents / 100, 2),
                                                      "counterparty": cp, "description": desc})
        out.append(Record(source=F_TXN, t=t, fields=fields, events=[ev]))
    return out


# ------------------------------------------------------------------------------------------------- 4. Parking log

def story_parking_person_days() -> set[tuple[str, date]]:
    """(person_id, day) pairs whose parking rows the story owns."""
    by_permit = {p["parking_permit"]: p["person_id"] for p in people() if p["parking_permit"]}
    owned = {(pid, INCIDENT_DAY) for pid in STORY_PARKING_PEOPLE}
    for r in story.csv_records("extra"):
        if r.source == F_PARKING:
            owned.add((by_permit[r.fields["permit_id"]], parse_ts(r.fields["timestamp"]).date()))
    return owned


def _parking(t: datetime, lane: str, p: dict, direction: str) -> Record:
    fields = _check(F_PARKING, {"timestamp": ts(t), "lane": lane, "permit_id": p["parking_permit"],
                                "plate": p["plate"], "direction": direction})
    typ = "parking_entry" if direction == "IN" else "parking_exit"
    ev = EventSpec(type=typ, t=t, actor={"kind": "permit", "value": p["parking_permit"]}, device=None, room=None,
                   attrs={"plate": p["plate"], "lane": lane})
    return Record(source=F_PARKING, t=t, fields=fields, events=[ev])


def parking_records() -> list[Record]:
    rng = _rng(4)
    by_id = {p["person_id"]: p for p in people() if p["parking_permit"]}
    owned = story_parking_person_days()
    out = []
    for fd in presence.floor_days():
        p = by_id.get(fd.person_id)
        if p is None or (fd.person_id, fd.day) in owned:
            continue
        t_in = fd.arrive - timedelta(seconds=rng.randint(120, 720))
        t_out = fd.depart + timedelta(seconds=rng.randint(120, 600))
        out.append(_parking(t_in, rng.choice(["ENTRY-1", "ENTRY-2"]), p, "IN"))
        out.append(_parking(t_out, rng.choice(["EXIT-1", "EXIT-2"]), p, "OUT"))
    out.sort(key=lambda r: (r.t, r.fields["permit_id"]))
    return out


def all_records() -> list[Record]:
    return cctv_records() + maintenance_records() + transaction_records() + parking_records()

