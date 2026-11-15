"""The whole ingest pipeline against the answer sheet (data/evidence/truth/events_expected.json).

Ingesting the built-in case with the parking log released must reproduce every expected event exactly, ids included.
Without the release, the result must be exactly the case part (the extra events are numbered after it).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend")) if str(ROOT / "backend") not in sys.path else None
EVIDENCE = ROOT / "data" / "evidence"
TRUTH = EVIDENCE / "truth" / "events_expected.json"

pytest.importorskip("app.features.evidence.ingest.csv_parsers")
pytest.importorskip("app.features.evidence.ingest.doc_parsers")
from app.features.evidence.ingest.ingest import ingest  # noqa: E402

EXTRA = "access/parking_exit.csv"


@pytest.fixture(scope="module")
def truth():
    if not TRUTH.is_file():
        pytest.skip("no generated case")
    return json.loads(TRUTH.read_text(encoding="utf-8"))


def _diff(got, want, n=5):
    out = []
    for g, w in zip(got, want):
        if g != w:
            out.append(f"\n got: {json.dumps(g)[:400]}\nwant: {json.dumps(w)[:400]}")
            if len(out) >= n:
                break
    return "".join(out)


def test_full_case_with_release_matches_truth_exactly(truth):
    res = ingest(EVIDENCE / "CASE-1010F", EVIDENCE / "extra", [EXTRA])
    assert res.problems == []
    assert len(res.events) == len(truth), f"{len(res.events)} events, expected {len(truth)}"
    assert res.events == truth, _diff(res.events, truth)


def test_case_without_release_is_the_case_part(truth):
    res = ingest(EVIDENCE / "CASE-1010F", EVIDENCE / "extra", [])
    case_part = [e for e in truth if e["source"]["file"] != EXTRA]
    assert res.problems == []
    assert res.events == case_part, _diff(res.events, case_part)


def test_evidence_rows_and_custody(truth):
    res = ingest(EVIDENCE / "CASE-1010F", EVIDENCE / "extra", [EXTRA])
    rows = {r["file"]: r for r in res.evidence}
    assert rows["endpoint/security_log.csv"]["manifest_match"] is False          # C8: the tampered file
    mismatched = [f for f, r in rows.items() if r["manifest_sha256"] and not r["manifest_match"]]
    assert mismatched == ["endpoint/security_log.csv"]
    counts = {}
    for e in truth:
        counts[e["source"]["file"]] = counts.get(e["source"]["file"], 0) + 1
    for f, n in counts.items():
        assert rows[f]["records"] == n, f
    assert rows[EXTRA]["manifest_sha256"] is None   # released later; not in the original manifest
