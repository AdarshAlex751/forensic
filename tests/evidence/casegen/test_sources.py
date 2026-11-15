"""Background records for CCTV, maintenance, transactions and parking (casegen/sources.py)."""
from datetime import timedelta

import pytest

from app.features.evidence.casegen import csv_writer, presence, sources, story, world
from app.features.evidence.casegen.world import F_CCTV, F_MAINT, F_PARKING, F_TXN, parse_ts

FUNCS = [sources.cctv_records, sources.maintenance_records, sources.transaction_records, sources.parking_records]
SRC = {sources.cctv_records: F_CCTV, sources.maintenance_records: F_MAINT, sources.transaction_records: F_TXN,
       sources.parking_records: F_PARKING}
STORY_WOS = {"WO-3091", "WO-3098", "WO-3117"}


def _cents(s):
    return round(float(s) * 100)


@pytest.mark.parametrize("fn", FUNCS, ids=lambda f: f.__name__)
def test_deterministic_and_well_formed(fn):
    a, b = fn(), fn()
    assert a == b and a
    for r in a:
        assert r.source == SRC[fn]
        assert list(r.fields) == csv_writer.HEADERS[r.source]
        assert all(isinstance(v, str) for v in r.fields.values())
        csv_writer.row_text(r.source, r.fields)
        assert not r.story
        for ev in r.events:
            assert ev.t.utcoffset() == timedelta(hours=-5)


def test_all_records_is_concatenation():
    assert sources.all_records() == sum((f() for f in FUNCS), [])


def test_cctv_covers_every_camera_day_without_overlap():
    story_rows = [r for r in story.csv_records() if r.source == F_CCTV]
    gaps = [(r.fields["camera_id"], parse_ts(r.fields["window_start"]), parse_ts(r.fields["window_end"]))
            for r in story_rows]
    ours = sources.cctv_records()
    assert all(r.fields["status"] == "RECORDING" and r.events == [] for r in ours)
    assert all(r.t == parse_ts(r.fields["window_start"]) for r in ours)
    for r in ours:
        s = parse_ts(r.fields["window_start"])
        assert r.fields["clip_ref"] == f"clips/{r.fields['camera_id']}/{s:%Y%m%d_%H%M%S}.mp4"
        e = parse_ts(r.fields["window_end"])
        for cam, gs, ge in gaps:
            if cam == r.fields["camera_id"]:
                assert e <= gs or s >= ge, (r.fields, gs, ge)
    cams = sorted(d for d, v in world.devices().items() if v["type"] == "camera")
    assert cams == [f"cam-0{i}" for i in range(1, 7)]
    windows = {}
    for r in ours + story_rows:
        windows.setdefault(r.fields["camera_id"], []).append(
            (parse_ts(r.fields["window_start"]), parse_ts(r.fields["window_end"])))
    for cam in cams:
        for d in world.days():
            ws = sorted(w for w in windows[cam] if w[0].date() == d)
            assert ws[0][0] == world.at(d, 0, 0, 0) and ws[-1][1] == world.at(d, 23, 59, 59)
            for (s1, e1), (s2, e2) in zip(ws, ws[1:]):
                assert e1 == s2, (cam, d, e1, s2)  # contiguous, no overlap, no hole
    assert len(ours) == 6 * len(list(world.days())) + len(story_rows)


def test_maintenance():
    recs = sources.maintenance_records()
    assert 15 <= len(recs) <= 25
    wos = [r.fields["work_order"] for r in recs]
    assert len(set(wos)) == len(wos) and not set(wos) & STORY_WOS
    for r in recs:
        f, (ev,) = r.fields, r.events
        assert not f["asset"].startswith("cam-")
        assert not (f["asset"] == world.LAB_HOST and parse_ts(f["start"]).date() == world.INCIDENT_DAY)
        assert parse_ts(f["start"]) < parse_ts(f["end"])
        assert ev.type == "maintenance_window" and ev.actor == {"kind": "name", "value": f["technician"]}
        assert ev.attrs == {"start": f["start"], "end": f["end"], "asset": f["asset"], "work_order": f["work_order"],
                            "technician": f["technician"]}
        dev = world.devices().get(f["asset"])
        assert ev.device == (f["asset"] if dev else None) and ev.room == (dev["room"] if dev else None)
    # work-order numbers increase with date, story rows included
    every = sorted(recs + [r for r in story.csv_records() if r.source == F_MAINT], key=lambda r: r.t)
    nums = [int(r.fields["work_order"].split("-")[1]) for r in every]
    assert nums == sorted(nums)


def test_transactions_running_balance():
    ours = sources.transaction_records()
    st = [r for r in story.csv_records() if r.source == F_TXN]
    assert [r.fields["balance"] for r in sorted(st, key=lambda r: r.t)] == ["31842.17", "13842.17"]
    rows = sorted(ours + st, key=lambda r: r.t)
    bal = _cents(rows[0].fields["balance"]) - _cents(rows[0].fields["amount"])
    assert bal == sources.opening_balance_cents() > 0
    for r in rows:
        bal += _cents(r.fields["amount"])
        assert _cents(r.fields["balance"]) == bal, r.fields
        assert bal > 0
    for r in ours:
        f, (ev,) = r.fields, r.events
        assert f["account"] == "CHK-7731"
        assert f["amount"].lstrip("-").count(".") == 1 and len(f["amount"].split(".")[1]) == 2
        assert len(f["balance"].split(".")[1]) == 2
        assert "Northline" not in f["counterparty"] and "coin" not in f["counterparty"].lower()
        assert ev.actor == {"kind": "account", "value": "CHK-7731"} and ev.device is None and ev.room is None
        assert ev.attrs == {"account": "CHK-7731", "amount": float(f["amount"]), "counterparty": f["counterparty"],
                            "description": f["description"]}
        assert world.START <= r.t.date() <= world.END


def test_parking():
    ours = sources.parking_records()
    by_permit = {p["parking_permit"]: p for p in world.people() if p["parking_permit"]}
    days = {(fd.person_id, fd.day): fd for fd in presence.floor_days()}
    owned = {(by_permit[r.fields["permit_id"]]["person_id"], parse_ts(r.fields["timestamp"]).date())
             for r in story.csv_records("extra") if r.source == F_PARKING}
    for pid in ("p_alma", "p_hank", "p_maggie", "p_bg_17", "p_frederik"):
        owned.add((pid, world.INCIDENT_DAY))
    seen = set()
    for r in ours:
        f, (ev,) = r.fields, r.events
        p = by_permit[f["permit_id"]]
        assert f["plate"] == p["plate"]
        key = (p["person_id"], r.t.date())
        assert key not in owned
        fd = days[key]
        if f["direction"] == "IN":
            assert ev.type == "parking_entry" and f["lane"] in ("ENTRY-1", "ENTRY-2")
            assert timedelta(minutes=2) <= fd.arrive - r.t <= timedelta(minutes=12)
        else:
            assert ev.type == "parking_exit" and f["lane"] in ("EXIT-1", "EXIT-2")
            assert timedelta(minutes=2) <= r.t - fd.depart <= timedelta(minutes=10)
        assert ev.actor == {"kind": "permit", "value": f["permit_id"]}
        assert ev.attrs == {"plate": f["plate"], "lane": f["lane"]} and ev.device is None and ev.room is None
        seen.add((key, f["direction"]))
    expected = {k for k in days if k[0] in {p["person_id"] for p in by_permit.values()} and k not in owned}
    assert seen == {(k, d) for k in expected for d in ("IN", "OUT")}


def test_written_quotes_match_file_lines(tmp_path):
    recs = sorted(sources.all_records(), key=lambda r: (r.source, r.t))
    written = csv_writer.write_csv(recs, tmp_path)
    assert len(written) == sum(len(r.events) for r in recs)
    cache = {}
    for w in written:
        lines = cache.setdefault(w.record.source,
                                 (tmp_path / w.record.source).read_text(encoding="utf-8").split("\n"))
        assert lines[w.line - 1] == w.quote
    for src in (F_CCTV, F_MAINT, F_TXN, F_PARKING):
        text = (tmp_path / src).read_bytes()
        assert text.startswith(",".join(csv_writer.HEADERS[src]).encode() + b"\n") and b"\r" not in text
