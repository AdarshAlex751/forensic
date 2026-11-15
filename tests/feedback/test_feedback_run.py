"""End to end: real Person 3 analysis + real evidence -> run() with the mock critic -> feedback.json + route.
No Groq call is made here."""
import json

import pytest

from app.features.feedback import check, contract, critic, run as run_mod


@pytest.fixture
def real_inputs(monkeypatch, tmp_path):
    monkeypatch.setenv("USE_REAL_ANALYSIS", "true")
    monkeypatch.setenv("USE_REAL_EVIDENCE", "true")
    out = tmp_path / "feedback.json"
    monkeypatch.setattr(contract, "OUT_FILE", out)
    monkeypatch.setattr(check, "OUT_FILE", out, raising=False)
    monkeypatch.setattr(critic, "ask", lambda bundle, **kw: critic.mock_reply(bundle))
    return out


def test_run_writes_valid_feedback(real_inputs):
    fb = run_mod.run("1010F", force=True)
    assert real_inputs.is_file()
    on_disk = json.loads(real_inputs.read_text(encoding="utf-8"))
    assert on_disk["questions"] == fb["questions"]
    assert fb["case_id"] == "1010F" and fb["source"] == "mock"
    assert fb["counts"]["kept"] >= 3 and fb["counts"]["rejected"] == 0
    for q in fb["questions"]:
        assert q["kind"] in contract.KINDS and q["question"].endswith("?")
        assert any(q["cites"].values())


def test_unchanged_analysis_keeps_previous_groq_questions(real_inputs, monkeypatch):
    fb = run_mod.run("1010F", force=True)
    fb["source"] = "groq"
    check.write(fb, real_inputs)
    called = []
    monkeypatch.setattr(critic, "ask", lambda bundle, **kw: called.append(1) or critic.mock_reply(bundle))
    again = run_mod.run("1010F")
    assert called == [] and again["input_fingerprint"] == fb["input_fingerprint"]


def test_slice_is_registered_last():
    from app.registry import SLICES, STAGES
    assert SLICES[-1][0] == "feedback" and STAGES[-1] == "critique"
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app).get("/api/feedback/health")
    assert r.status_code == 200 and r.json() == {"slice": "feedback", "status": "ok"}
