"""Consistency of the background presence simulation with the story spec (no overlapping visits, Frederik driven
by his work orders, lt-219 sessions inside badge visits, USB mounts inside sessions, C7 and tags intact)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

import pytest

from app.features.evidence.casegen import presence, story
from app.features.evidence.casegen.csv_writer import HEADERS, parse_row, row_text
from app.features.evidence.casegen.world import (F_BADGE, F_CCTV, F_MAINT, F_PARKING, F_SEC, F_USB, F_WIFI,
                                                 INCIDENT_DAY, parse_ts, people, person)

DAY = INCIDENT_DAY
CLONE_BADGE = "40417"                      # Hank's copy of p_bg_17's badge, read at 219 during the theft
CLONE_IN = parse_ts("2026-03-04T18:16:40-05:00")
CLONE_OUT = parse_ts("2026-03-04T18:31:40-05:00")
FRED = person("p_frederik")
FRED_IDS = {FRED["badge"], FRED["laptop_mac"], FRED["local_account"]}


def _all_csv():
    return presence.records() + story.csv_records("story")


def _events(source: str):
    out = []
    for r in _all_csv():
        if r.source == source:
            for ev in r.events:
                out.append(ev)
    return sorted(out, key=lambda e: e.t)


def _is_clone(ev) -> bool:
    return ev.actor["value"] == CLONE_BADGE and ev.room == "219" and CLONE_IN <= ev.t <= CLONE_OUT


def _visits(room: str) -> dict[str, list[tuple[datetime, datetime]]]:
    """badge -> [(IN, OUT)] at the given room, the clone read pair kept apart under key 'clone'."""
    opened: dict[str, datetime] = {}
    out: dict[str, list] = defaultdict(list)
    for ev in _events(F_BADGE):
        if ev.room != room:
            continue
        key = "clone" if _is_clone(ev) else ev.actor["value"]
        if ev.type == "badge_in":
            opened[key] = ev.t
        else:
            out[key].append((opened.pop(key), ev.t))
    return out


def _sessions() -> list[tuple[str, datetime, datetime]]:
    opened: dict[str, datetime] = {}
    out = []
    for ev in _events(F_SEC):
        if ev.type == "logon":
            assert ev.actor["value"] not in opened, f"nested logon {ev}"
            opened[ev.actor["value"]] = ev.t
        elif ev.type == "logoff":
            out.append((ev.actor["value"], opened.pop(ev.actor["value"]), ev.t))
    assert not opened, opened
    return out


def test_never_badged_into_two_rooms():
    state: dict[tuple[str, object], str | None] = {}
    for ev in _events(F_BADGE):
        if _is_clone(ev):
            continue  # the planted incident: a second card, not the holder (C2)
        k = (ev.actor["value"], ev.t.date())
        cur = state.get(k)
        if ev.type == "badge_in":
            assert cur is None, f"{k}: IN {ev.room} at {ev.t} while still in {cur}"
            state[k] = ev.room
        else:
            assert cur == ev.room, f"{k}: OUT {ev.room} at {ev.t} while in {cur}"
            state[k] = None


def test_lab_sessions_inside_rdr219_visits():
    acct_badge = {p["local_account"]: p["badge"] for p in people() if p["local_account"]}
    visits = _visits("219")
    sessions = _sessions()
    assert sessions
    for acct, on, off in sessions:
        cands = visits.get(acct_badge[acct], [])
        if acct == "hgibson" and on.date() == DAY:
            cands = visits["clone"]
        assert any(a <= on and off <= b for a, b in cands), f"{acct} session {on}..{off} outside any 219 visit"


def test_usb_mounts_inside_lab_sessions():
    sessions = _sessions()
    for r in story.usb_records():
        t = r.events[0].t
        assert any(on < t < off for _, on, off in sessions), f"usb_mount {r.fields['serial']} at {t} outside session"
        assert r.fields["first_install"] <= t


def test_no_story_lab_session_overlay():
    """The background owns every lab session before 03-04; the story spec adds none."""
    for e in story.spec():
        if e["type"] in ("logon", "logoff", "badge_in", "badge_out") and e["source_file"] in (F_SEC, F_BADGE):
            assert e["t"][:10] == "2026-03-04", e


def _fred_events():
    return [ev for r in _all_csv() for ev in r.events if ev.actor and ev.actor["value"] in FRED_IDS]


def test_frederik_only_with_work_orders():
    wo_days = {w.start.date() for w in presence.frederik_work_orders() if presence.is_physical(w)}
    assert {w.work_order for w in presence.frederik_work_orders() if presence.is_physical(w)} == {
        "WO-3082", "WO-3091", "WO-3098", "WO-3117"}
    days = {ev.t.date() for ev in _fred_events()}
    assert days and days <= wo_days, days - wo_days
    assert days == wo_days
    fd = {f.day for f in presence.floor_days() if f.person_id == "p_frederik"}
    assert fd == wo_days - {DAY}


def test_frederik_02_23_antivirus_visit():
    evs = sorted((e for e in _fred_events() if e.t.date().isoformat() == "2026-02-23"), key=lambda e: e.t)
    types = Counter(e.type for e in evs)
    assert types["badge_in"] == 1 and types["badge_out"] == 1
    assert types["logon"] == 1 and types["logoff"] == 1 and types["file_read"] >= 2
    assert all(e.room == "219" for e in evs if e.type.startswith("badge_"))
    b_in = next(e.t for e in evs if e.type == "badge_in")
    b_out = next(e.t for e in evs if e.type == "badge_out")
    start, end = parse_ts("2026-02-23T13:15:00-05:00"), parse_ts("2026-02-23T14:30:00-05:00")
    assert start - timedelta(minutes=25) <= evs[0].t <= start - timedelta(minutes=10)
    assert end + timedelta(minutes=5) <= evs[-1].t <= end + timedelta(minutes=20)
    assert b_in < start and b_out > end
    for e in evs:
        if e.type == "file_read":
            assert b_in < e.t < b_out and start <= e.t <= end
            assert "\\Patches\\AV\\" in e.attrs["path"] or "Windows Defender" in e.attrs["path"]


def test_frederik_badge_only_at_219():
    for ev in _fred_events():
        if ev.type.startswith("badge_"):
            assert ev.room == "219", ev


@pytest.mark.parametrize("cam", ["cam-02", "cam-05"])
def test_frederik_covers_camera_offline(cam):
    off = [r for r in story.csv_records() if r.source == F_CCTV and r.fields["camera_id"] == cam
           and r.fields["status"] == "OFFLINE"]
    assert len(off) == 1
    s, e = parse_ts(off[0].fields["window_start"]), parse_ts(off[0].fields["window_end"])
    wifi = sorted((ev for ev in _fred_events() if ev.type.startswith("wifi_") and ev.t.date() == s.date()),
                  key=lambda ev: ev.t)
    assert wifi[0].type == "wifi_assoc" and wifi[-1].type == "wifi_disassoc"
    assert wifi[0].t < s and wifi[-1].t > e
    ap = presence._asset_ap(cam)
    at_ap = [ev for ev in wifi if ev.attrs["ap"] == ap]
    assert at_ap and at_ap[0].t < s and wifi[wifi.index(at_ap[0]) + 1].t > e
    assert not any(ev.type.startswith("badge_") and ev.t.date() == s.date() for ev in _fred_events())


def test_frederik_evening():
    evs = sorted((e for e in _fred_events() if e.t.date() == DAY), key=lambda e: e.t)
    assert [e.type for e in evs if e.type in ("logon", "logoff")] == ["logon", "logoff", "logon", "logoff"]
    assert evs[1].type == "wifi_assoc" and evs[1].attrs["ap"] == "ap-2-04"
    assert evs[-2].type == "wifi_disassoc" and evs[-1].type == "badge_out"


def test_story_quotes_parse_and_match_t():
    for e in story.spec():
        sf, q, t = e["source_file"], e["quote"], e["t"]
        if sf in HEADERS:
            f = parse_row(sf, q)
            assert row_text(sf, f) == q
            if sf == F_CCTV:
                assert t in (f["window_start"], f["window_end"]), e
            elif sf == F_MAINT:
                assert f["start"] == t == e["attrs"]["start"] and f["end"] == e["attrs"]["end"], e
            else:
                assert f[HEADERS[sf][0]] == t, e
        elif sf == F_USB:
            assert q == f"  S/N: {e['attrs']['serial']} [{t}]", e


def test_c7():
    devs = story.usb_records()
    serials = [r.fields["serial"] for r in devs]
    assert len(serials) == len(set(serials))
    night = [r for r in devs if r.fields["first_install"].date() == DAY]
    assert len(night) == 1
    assert night[0].fields["serial"] == "4C530001230918112443&0"
    assert night[0].fields["last_write"] == parse_ts("2026-03-04T18:17:30-05:00")
    assert "C7" in night[0].events[0].tags
    assert any(r.fields["first_install"].year == 2025 for r in devs)
    reused = [r for r in devs if r.fields["last_write"] == parse_ts("2026-03-04T19:03:10-05:00")]
    assert len(reused) == 1 and reused[0].fields["vendor"] == "Kingston"
    assert reused[0].fields["first_install"].year == 2025
    assert "07A1B2C3D4E5F6" not in " ".join(serials)


def test_tags_present():
    tags = Counter(t for e in story.spec() for t in e["tags"])
    for t in ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "RH_frederik", "RH_bg17"]:
        assert tags[t] >= 1, t


def test_parking_entry_before_exit():
    rows = defaultdict(list)
    for r in story.csv_records("extra"):
        assert r.source == F_PARKING
        rows[r.fields["permit_id"]].append((parse_ts(r.fields["timestamp"]), r.fields["direction"]))
    for permit, v in rows.items():
        v.sort()
        assert v[0][1] == "IN", permit
        assert any(d == "OUT" for _, d in v), permit
    first_badge = {}
    for ev in _events(F_BADGE):
        if ev.t.date() == DAY:
            first_badge.setdefault(ev.actor["value"], ev.t)
    for pid in ("p_bg_04", "p_bg_22"):
        p = person(pid)
        t_in = rows[p["parking_permit"]][0][0]
        gap = first_badge[p["badge"]] - t_in
        assert timedelta(minutes=2) <= gap <= timedelta(minutes=12), (pid, gap)


def test_bank_and_slack_ids():
    for e in story.spec():
        if e["type"] == "transaction":
            assert e["actor"] == {"kind": "account", "value": "CHK-7731"}
        if e["type"] == "chat":
            assert e["attrs"]["channel"] == "D07Q3K9L2MZ"
            assert e["source_file"].startswith("comms/slack_export/D07Q3K9L2MZ/")


def test_non_frederik_records_match_fake_baseline():
    assert presence.check_against_fake_baseline() > 9000


def test_deterministic():
    a = [(r.source, row_text(r.source, r.fields)) for r in presence.records()]
    fd = presence.floor_days()
    presence._run.cache_clear()
    presence._baseline.cache_clear()
    assert [(r.source, row_text(r.source, r.fields)) for r in presence.records()] == a
    assert presence.floor_days() == fd


def test_wifi_rows_well_formed():
    for r in presence.records():
        if r.source == F_WIFI:
            assert r.fields["ssid"] == "JRR2-SECURE"
