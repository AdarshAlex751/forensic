"""CSV parsers against the answer sheet (data/evidence/truth/events_expected.json).

The truth file is read by the tests only; the parsers work from the case folder alone.
"""
import json
from pathlib import Path

import pytest

from app.features.evidence.ingest import csv_parsers as cp
from app.features.evidence.ingest.base import FileCtx, load_devices, sha256_file

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "data" / "evidence"
CASE = EVIDENCE / "CASE-1010F"
EXTRA = EVIDENCE / "extra"
TRUTH = EVIDENCE / "truth" / "events_expected.json"

FILES = [
    ("access/badge_access.csv", CASE, cp.parse_badge),
    ("network/wifi_ap_logs.csv", CASE, cp.parse_wifi),
    ("endpoint/security_log.csv", CASE, cp.parse_security_log),
    ("endpoint/file_audit.csv", CASE, cp.parse_file_audit),
    ("cctv/index.csv", CASE, cp.parse_cctv),
    ("it/maintenance_calendar.csv", CASE, cp.parse_maintenance),
    ("financial/transactions.csv", CASE, cp.parse_transactions),
    ("access/parking_exit.csv", EXTRA, cp.parse_parking),
]


@pytest.fixture(scope="module")
def truth():
    if not TRUTH.is_file():
        pytest.skip("no generated case")
    return json.loads(TRUTH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def devices():
    return load_devices(CASE)


def _ctx(rel: str, base: Path, devices: dict, path: Path | None = None) -> FileCtx:
    p = path or base / rel
    return FileCtx(rel=rel, path=p, sha256=sha256_file(p), case_dir=CASE, devices=devices)


def _key(e: dict) -> tuple:
    return (e["t"], e["source"]["line"], e["type"])


def _strip(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "id"}


def _typed(x):
    """Make int vs float vs str visible to ==: 1 == 1.0 == True in plain Python."""
    if isinstance(x, dict):
        return {k: _typed(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_typed(v) for v in x]
    return (type(x).__name__, x)


@pytest.mark.parametrize("rel,base,fn", FILES, ids=[f[0] for f in FILES])
def test_matches_truth(rel, base, fn, truth, devices):
    if not (base / rel).is_file():
        pytest.skip(f"missing {rel}")
    got = sorted((_strip(e) for e in fn(_ctx(rel, base, devices))), key=_key)
    want = sorted((_strip(e) for e in truth if e["source"]["file"] == rel), key=_key)
    assert want, f"truth has no events for {rel}"
    diffs = [(g, w) for g, w in zip(got, want) if _typed(g) != _typed(w)]
    msg = [f"{rel}: got {len(got)} events, expected {len(want)}; {len(diffs)} differ"]
    for g, w in diffs[:3]:
        msg.append("  got:  " + json.dumps(g, sort_keys=True))
        msg.append("  want: " + json.dumps(w, sort_keys=True))
    assert len(got) == len(want) and not diffs, "\n".join(msg)


@pytest.mark.parametrize("rel,base,fn", FILES, ids=[f[0] for f in FILES])
def test_quotes_are_raw_lines(rel, base, fn, devices):
    if not (base / rel).is_file():
        pytest.skip(f"missing {rel}")
    ctx = _ctx(rel, base, devices)
    events = fn(ctx)
    assert events
    for e in events:
        assert e["source"]["quote"] == ctx.lines[e["source"]["line"] - 1]
        assert e["source"]["line"] >= 2
        assert e["person"] is None and e["id"] is None


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "f.csv"
    p.write_bytes(text.encode("utf-8"))
    return p


def test_wrong_column_count_raises(tmp_path, devices):
    p = _write(tmp_path, "timestamp,badge_id,reader_id,direction,result\n"
                         "2026-03-04T18:16:40-05:00,40417,rdr-219,IN,GRANTED\n"
                         "2026-03-04T18:17:40-05:00,40417,rdr-219,IN\n")
    with pytest.raises(ValueError, match=r"access/badge_access\.csv:3"):
        cp.parse_badge(_ctx("access/badge_access.csv", CASE, devices, p))


def test_wrong_header_raises(tmp_path, devices):
    p = _write(tmp_path, "timestamp,lane,permit,plate,direction\n"
                         "2026-02-23T08:04:32-05:00,ENTRY-1,P-2219,N13-SUV,IN\n")
    with pytest.raises(ValueError, match=r"access/parking_exit\.csv:1"):
        cp.parse_parking(_ctx("access/parking_exit.csv", EXTRA, devices, p))


def test_bad_value_raises(tmp_path, devices):
    p = _write(tmp_path, "timestamp,ap_id,client_mac,event,rssi,ssid\n"
                         "2026-03-04T18:41:00-05:00,ap-2-03,02:1F:9A:10:00:02,DISASSOC,strong,JRR2-SECURE\n")
    with pytest.raises(ValueError, match=r"network/wifi_ap_logs\.csv:2"):
        cp.parse_wifi(_ctx("network/wifi_ap_logs.csv", CASE, devices, p))
