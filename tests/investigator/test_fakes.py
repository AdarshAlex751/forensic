import json
from pathlib import Path

from app.shared import schema

FAKE = Path(__file__).resolve().parents[2] / "data" / "investigator" / "fake"
EVIDENCE_FAKE = Path(__file__).resolve().parents[2] / "data" / "evidence" / "fake"


def load(name):
    return json.loads((FAKE / name).read_text(encoding="utf-8"))


def test_fake_outputs_match_the_shared_schema():
    schema.Verification.model_validate(load("verification.json"))
    for h in load("hypotheses.json"):
        schema.Hypothesis.model_validate(h)
    for n in load("notes.json"):
        schema.Note.model_validate(n)
    for r in load("requests.json"):
        schema.Request.model_validate(r)


def test_fake_verification_counts_add_up_and_cite_real_fake_events():
    v = load("verification.json")
    ids = {e["id"] for e in json.loads((EVIDENCE_FAKE / "events.json").read_text(encoding="utf-8"))}
    assert set(v["verified_event_ids"]) <= ids
    assert v["claims"] - v["verified"] == len(v["rejected"])
    assert all(r["reason"].startswith("custody:") for r in v["rejected"])


def test_every_fake_hypothesis_says_what_would_disprove_it_and_labels_no_one():
    for h in load("hypotheses.json"):
        assert h["disproved_by"].strip() and h["supports"]
        assert not any(w in h["text"].lower() for w in ("guilty", "culprit", "perpetrator", "thief"))
