"""doc_parsers against the answer sheet: for every text/document file in CASE-1010F, the parser output must equal the
expected events with that source.file exactly (all fields, types included; ids aside)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend")) if str(ROOT / "backend") not in sys.path else None
EVIDENCE = ROOT / "data" / "evidence"
CASE = EVIDENCE / "CASE-1010F"
TRUTH = EVIDENCE / "truth" / "events_expected.json"

from app.features.evidence.ingest import doc_parsers as d  # noqa: E402
from app.features.evidence.ingest.base import FileCtx, load_devices, sha256_file  # noqa: E402

if not CASE.is_dir() or not TRUTH.is_file():
    pytest.skip("no generated case", allow_module_level=True)


def _rels(pattern: str) -> list[str]:
    return sorted(p.relative_to(CASE).as_posix() for p in CASE.glob(pattern))


SLACK_DAYS = [r for r in _rels("comms/slack_export/*/*.json")]
STATEMENTS = _rels("statements/*.pdf")
CASES = ([("endpoint/usbstor.txt", d.parse_usbstor), ("comms/mailbox.mbox", d.parse_mbox)]
         + [(r, d.parse_slack_day) for r in SLACK_DAYS]
         + [(r, d.parse_statement) for r in STATEMENTS])


@pytest.fixture(scope="module")
def truth_by_file():
    out: dict[str, list[dict]] = {}
    for e in json.loads(TRUTH.read_text(encoding="utf-8")):
        out.setdefault(e["source"]["file"], []).append(e)
    return out


@pytest.fixture(scope="module")
def devices():
    return load_devices(CASE)


def _norm(events):
    out = [{k: v for k, v in e.items() if k != "id"} for e in events]
    return sorted(out, key=lambda e: (e["t"], e["source"]["line"], e["type"]))


def test_found_files():
    assert SLACK_DAYS and STATEMENTS


@pytest.mark.parametrize("rel,parser", CASES, ids=[c[0] for c in CASES])
def test_parser_matches_truth(rel, parser, truth_by_file, devices):
    path = CASE / rel
    ctx = FileCtx(rel=rel, path=path, sha256=sha256_file(path), case_dir=CASE, devices=devices)
    got = _norm(parser(ctx))
    want = _norm(truth_by_file.get(rel, []))
    if got != want:
        diffs = [(i, g, w) for i, (g, w) in enumerate(zip(got, want)) if g != w][:3]
        msg = [f"{rel}: got {len(got)} events, want {len(want)}"]
        for i, g, w in diffs:
            msg.append(f"#{i}\n got:  {json.dumps(g, ensure_ascii=False)}\n want: {json.dumps(w, ensure_ascii=False)}")
        if not diffs:
            extra = got[len(want):] or want[len(got):]
            msg.append(f"first unmatched: {json.dumps(extra[0], ensure_ascii=False)}")
        print("\n".join(msg))
        pytest.fail("\n".join(msg))
    assert got == want


def test_brief_case_info():
    info = d.brief_case_info(CASE)
    assert set(info) == {"id", "title", "address", "summary", "costar_property_id", "matterport_model_id"}
    assert all(isinstance(v, str) for v in info.values())
    assert info["id"] == "1010F"
    assert info["title"] and info["summary"] and info["address"]
    assert info["costar_property_id"] == "" and info["matterport_model_id"] == ""
    assert info == d.brief_case_info(CASE)  # deterministic
