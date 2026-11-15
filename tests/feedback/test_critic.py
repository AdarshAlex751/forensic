"""Tests for the feedback critic. No real Groq calls: the LLM is always a fake or the key is blanked."""
import json
import re
from pathlib import Path

import pytest

from app.features.feedback import contract, critic, prompts

ROOT = Path(__file__).resolve().parents[2]


class FakeMsg:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    model_name = "fake-model"

    def __init__(self, content=None, exc=None):
        self.content, self.exc, self.calls = content, exc, []

    def invoke(self, messages):
        self.calls.append(messages)
        if self.exc:
            raise self.exc
        return FakeMsg(self.content)


@pytest.fixture
def bundle():
    return {
        "case": {"id": "T1", "title": "test"},
        "contradictions": [
            {"id": "c1", "kind": "custody", "rule": "custody_mismatch", "title": "hash", "file": "x/log.csv",
             "explanation": "x/log.csv does not match its manifest hash", "score": 1.0, "events": ["e1"]},
            {"id": "c2", "kind": "physical", "rule": "impossible_travel", "title": "two rooms",
             "explanation": "The same badge (p_b) is in room 1 and room 2 30 s apart", "score": 0.9,
             "events": ["e2", "e3", "e999"]},
            {"id": "c3", "kind": "temporal", "rule": "wifi_after_last_badge", "title": "wifi",
             "explanation": "p_a laptop on wifi after badge out", "score": 0.8, "events": ["e4", "e5"]},
            {"id": "c4", "kind": "statement", "rule": "leave_time_claim", "title": "said six",
             "explanation": "p_a said six", "score": 0.7, "events": ["e5"]},
        ],
        "persons": [
            {"id": "p_a", "name": "A", "role": "eng", "anomaly": 1.0, "anomaly_rank": 1,
             "red_flags": [{"text": "usb", "events": ["e4", "e404"]}], "context": [], "links": {}},
            {"id": "p_b", "name": "B", "role": "ops", "anomaly": 0.3, "anomaly_rank": 2,
             "red_flags": [], "context": [], "links": {}},
        ],
        "events": {f"e{i}": {"t": "2026-03-04T18:00:00-05:00", "type": "badge", "person": "p_a",
                             "file": "f.csv", "line": i, "quote": "q"} for i in range(1, 6)},
        "untrusted_files": ["x/log.csv"],
        "notes": [],
        "budget": {"approx_tokens": 500, "dropped": {"persons": 0, "events": 0}},
    }


@pytest.fixture
def no_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "FALLBACK_FILE", tmp_path / "missing.json")


GOOD = {"questions": [{"kind": "assumption", "question": "Who held the badge in c2?", "why": "Two reads 30 s apart.",
                       "cites": {"events": ["e2"], "contradictions": ["c2"], "persons": ["p_b"]}, "focus": "c2"}]}


def test_valid_json_parsed(bundle):
    llm = FakeLLM(json.dumps(GOOD))
    r = critic.ask(bundle, llm=llm)
    assert r["source"] == "groq" and r["error"] is None and r["model"] == "fake-model"
    assert r["questions"][0]["cites"]["contradictions"] == ["c2"]
    assert r["questions"][0]["focus"] == "c2"
    roles = [m[0] for m in llm.calls[0]]
    assert roles == ["system", "human"]


def test_fenced_json_parsed(bundle):
    text = "Here you go:\n```json\n" + json.dumps(GOOD, indent=2) + "\n```\n"
    r = critic.ask(bundle, llm=FakeLLM(text))
    assert r["source"] == "groq"
    assert r["questions"][0]["kind"] == "assumption"


def test_garbage_falls_back_to_mock(bundle, no_fallback):
    r = critic.ask(bundle, llm=FakeLLM("I cannot help with that."))
    assert r["source"] == "mock" and r["error"]
    assert 3 <= len(r["questions"]) <= 6


def test_garbage_uses_fallback_file(bundle, tmp_path, monkeypatch):
    fb = tmp_path / "fb.json"
    monkeypatch.setattr(contract, "FALLBACK_FILE", fb)
    critic.save_fallback({**GOOD, "source": "groq", "model": "m"})
    r = critic.ask(bundle, llm=FakeLLM("{not json"))
    assert r["source"] == "fallback" and r["error"]
    assert r["questions"] == critic._questions(GOOD)
    r2 = critic.ask(bundle, llm=FakeLLM("{not json"), use_fallback=False)
    assert r2["source"] == "mock"


def test_llm_exception_does_not_raise(bundle, no_fallback):
    r = critic.ask(bundle, llm=FakeLLM(exc=TimeoutError("timed out")))
    assert r["source"] == "mock" and "TimeoutError" in r["error"]


def test_missing_key_no_real_call(bundle, no_fallback, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    r = critic.ask(bundle)
    assert r["source"] == "mock" and "GROQ_API_KEY" in r["error"]


def test_error_message_redacts_key(bundle, no_fallback, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_secretvalue123")
    r = critic.ask(bundle, llm=FakeLLM(exc=RuntimeError("bad key gsk_secretvalue123")))
    assert "secretvalue" not in r["error"]


def test_mock_reply_cites_only_bundle_ids(bundle):
    r = critic.mock_reply(bundle)
    assert r["source"] == "mock"
    assert 3 <= len(r["questions"]) <= 6
    ev, cs, ps = set(bundle["events"]), {c["id"] for c in bundle["contradictions"]}, {p["id"] for p in bundle["persons"]}
    kinds = set()
    for q in r["questions"]:
        assert q["kind"] in contract.KINDS
        kinds.add(q["kind"])
        assert set(q["cites"]["events"]) <= ev
        assert set(q["cites"]["contradictions"]) <= cs
        assert set(q["cites"]["persons"]) <= ps
        assert q["focus"] is None or q["focus"] in cs | ps
        assert len(q["question"].split()) <= 40
        text = (q["question"] + " " + q["why"]).lower()
        assert not [w for w in contract.FORBIDDEN if w in text]
    assert {"assumption", "weak_evidence", "confirm_or_disprove"} <= kinds
    assert r == critic.mock_reply(bundle)  # deterministic


def test_mock_reply_empty_bundle():
    r = critic.mock_reply({})
    assert 3 <= len(r["questions"]) <= 6
    assert all(not any(q["cites"].values()) for q in r["questions"])


def test_system_prompt_rules():
    sp = prompts.SYSTEM_PROMPT
    low = sp.lower()
    assert "only ask questions" in low and "never answer them" in low
    assert "never give a verdict" in low
    assert "never put a label" in low
    assert "an unusual day" in low
    assert "cite only ids" in low
    assert str(contract.MAX_QUESTIONS) in sp
    for k in contract.KINDS:
        assert k in sp
    # forbidden words appear only in the single "never use" line, never anywhere else
    assert prompts.FORBIDDEN_LINE in sp
    rest = sp.replace(prompts.FORBIDDEN_LINE, "").lower()
    assert not [w for w in contract.FORBIDDEN if w in rest]
    assert prompts.FORBIDDEN_LINE.startswith("Never use")


def _realistic_bundle():
    contras = json.loads((ROOT / "data/analysis/contradictions.json").read_text(encoding="utf-8"))
    persons = json.loads((ROOT / "data/analysis/persons.json").read_text(encoding="utf-8"))
    ev_path = ROOT / "data/evidence/events.json"
    all_events = {e["id"]: e for e in json.loads(ev_path.read_text(encoding="utf-8"))} if ev_path.exists() else {}
    cited = []
    out_c = []
    for c in contras:
        e = c.get("events", [])[:8]
        cited += e
        out_c.append({"id": c["id"], "kind": c["kind"], "rule": c.get("rule"), "title": c.get("title"),
                      "explanation": c.get("explanation"), "score": c.get("score"), "events": e})
    top = sorted(persons, key=lambda p: -(p.get("anomaly") or 0))[:12]
    out_p = []
    for p in top:
        flags = [{"text": f["text"], "events": f.get("events", [])[:4]} for f in p.get("red_flags", [])]
        cited += [e for f in flags for e in f["events"]]
        out_p.append({"id": p["id"], "name": p["name"], "role": p.get("role"), "anomaly": p.get("anomaly"),
                      "anomaly_rank": p.get("anomaly_rank"), "red_flags": flags, "context": []})
    events = {}
    for eid in dict.fromkeys(cited):
        e = all_events.get(eid, {})
        src = e.get("source") or {}
        events[eid] = {"t": e.get("t"), "type": e.get("type"), "person": e.get("person"), "room": e.get("room"),
                       "file": src.get("file"), "line": src.get("line"), "quote": (src.get("quote") or "")[:160]}
    return {"case": {"id": "1010F", "title": "case"}, "contradictions": out_c, "persons": out_p,
            "events": events, "untrusted_files": ["endpoint/security_log.csv"], "notes": [],
            "budget": {"approx_tokens": 0, "dropped": {"persons": 0, "events": 0}}}


def test_user_message_embeds_bundle_and_fits_budget():
    if not (ROOT / "data/analysis/contradictions.json").exists():
        pytest.skip("analysis data not present")
    b = _realistic_bundle()
    msgs = critic.build_messages(b)
    user = msgs[1][1]
    assert prompts.bundle_json(b) in user
    # the message actually sent is built from context.build_bundle(), which applies the budget
    from app.features.feedback import context
    sent = critic.build_messages(context.build_bundle())[1][1]
    assert len(sent) <= contract.MAX_BUNDLE_TOKENS * 4 + 4000
    # mock on the realistic bundle also stays in-bundle
    ids = set(b["events"]) | {c["id"] for c in b["contradictions"]} | {p["id"] for p in b["persons"]}
    for q in critic.mock_reply(b)["questions"]:
        assert set(sum(q["cites"].values(), [])) <= ids


def test_parse_json_variants():
    assert critic.parse_json('noise {"questions": []} trailing')["questions"] == []
    with pytest.raises(ValueError):
        critic.parse_json("no json here")
