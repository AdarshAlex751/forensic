import json

import pytest

from app.features.investigator import inputs
from app.features.investigator.agent_tools import AgentTools, ToolContext
from app.features.investigator.approvals import Approvals
from app.features.investigator.lead_agent import build_brief, investigate, sanitize_hypotheses
from app.features.investigator.subagents import build_subagents
from app.features.investigator.trace import Trace

SRC = {"file": "f.csv", "line": 2, "quote": "q", "sha256": "s"}


def make_ctx():
    events = [inputs.Event.from_dict({"id": f"e{i}", "t": f"2026-03-04T18:0{i}:00-05:00", "type": "badge_in", "source": SRC})
              for i in range(1, 4)]
    cons = [
        inputs.Contradiction("c1", "physical", ["e1", "e2"], 0.98, "Same badge read 30 s apart in rooms 74 s apart.", walk_s=74, gap_s=30),
        inputs.Contradiction("c2", "statement", ["e3"], 0.94, "Statement conflicts with a Wi-Fi record."),
    ]
    return ToolContext(events=events, contradictions=cons, approvals=Approvals(), persons=[inputs.Person("p1", "Alex Doe", anomaly=0.9)])


def good_json():
    return json.dumps({
        "hypotheses": [
            {"text": "Two records place one badge in two rooms too far apart.", "confidence": 0.8, "supports": ["c1"],
             "disproved_by": "A second badge holder."},
            {"text": "A statement conflicts with a log.", "confidence": 0.9, "supports": ["c2", "c1"], "disproved_by": "A corrected statement."},
        ],
        "notes": [{"text": "Check the lobby camera.", "kind": "check_next"}, {"text": "odd kind", "kind": "weird"}],
    })


def test_sanitize_ranks_by_confidence_renumbers_and_keeps_only_known_supports():
    out, warns = sanitize_hypotheses(json.loads(good_json())["hypotheses"] + [
        {"text": "Unsupported.", "confidence": 0.5, "supports": ["c99"], "disproved_by": "x"}], {"c1", "c2"})
    assert [h["id"] for h in out] == ["h1", "h2"]
    assert out[0]["confidence"] == 0.9 and out[0]["supports"] == ["c2", "c1"]
    assert any("c99" in w for w in warns)


def test_sanitize_drops_hypotheses_that_label_a_person_or_lack_a_disproof():
    raw = [
        {"text": "Alex Doe is the culprit.", "confidence": 0.9, "supports": ["c1"], "disproved_by": "x"},
        {"text": "Records conflict.", "confidence": 0.9, "supports": ["c1"], "disproved_by": ""},
        {"text": "Records conflict.", "confidence": 7, "supports": ["c1"], "disproved_by": "A second holder."},
    ]
    out, warns = sanitize_hypotheses(raw, {"c1"})
    assert len(out) == 1 and out[0]["confidence"] == 1.0
    assert len(warns) == 2


def test_investigate_uses_the_llm_answer_when_it_is_valid():
    res = investigate(make_ctx(), runner=lambda prompt: "Here you go:\n```json\n" + good_json() + "\n```")
    assert res.engine == "llm" and [h["id"] for h in res.hypotheses] == ["h1", "h2"]
    assert [n["kind"] for n in res.notes] == ["check_next", "check_next"]


def test_investigate_falls_back_to_rules_when_the_runner_raises():
    def boom(prompt):
        raise RuntimeError("groq down")

    res = investigate(make_ctx(), runner=boom)
    assert res.engine == "rules" and res.warnings
    assert all(h["disproved_by"] and h["supports"] for h in res.hypotheses)
    assert res.hypotheses[0]["supports"] == ["c1"]


def test_investigate_falls_back_to_rules_on_invalid_json():
    res = investigate(make_ctx(), runner=lambda p: "I could not decide.")
    assert res.engine == "rules"


def test_without_a_groq_key_or_runner_the_rules_engine_runs(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert investigate(make_ctx()).engine == "rules"


def test_a_429_from_the_runner_is_retried(monkeypatch):
    monkeypatch.setattr("app.shared.llm_client.time.sleep", lambda s: None)
    calls = {"n": 0}

    def flaky(prompt):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("Error code: 429 rate limit")
        return good_json()

    assert investigate(make_ctx(), runner=flaky).engine == "llm" and calls["n"] == 3


def test_rules_confidence_comes_from_the_contradiction_score_and_never_names_a_role():
    res = investigate(make_ctx(), runner=lambda p: "nope")
    assert [h["confidence"] for h in res.hypotheses] == sorted((h["confidence"] for h in res.hypotheses), reverse=True)
    assert all(0 < h["confidence"] <= 0.95 for h in res.hypotheses)


def test_brief_contains_only_verified_facts_and_approved_context():
    ctx = make_ctx()
    ctx.approvals.add_request("Pull the parking log.", "why")
    brief = build_brief(ctx)
    assert "c1" in brief and "Same badge read 30 s apart" in brief and "Alex Doe" in brief
    assert "Pull the parking log." in brief


def test_trace_events_are_emitted_in_order():
    t = Trace()
    investigate(make_ctx(), runner=lambda p: good_json(), trace=t)
    stages = [e["stage"] for e in t.snapshot()]
    assert stages[0] == "plan" and stages[-1] == "done" and "rank" in stages
    assert [e["seq"] for e in t.snapshot()] == sorted(e["seq"] for e in t.snapshot())


def test_subagent_specs_have_the_four_roles_and_only_the_tools_they_need():
    specs = build_subagents(AgentTools(make_ctx()))
    by = {s["name"]: s for s in specs}
    assert set(by) == {"timeline", "physics", "comms", "money"}
    names = lambda s: {f.__name__ for f in s["tools"]}  # noqa: E731
    assert {"walk_time", "ap_covers", "camera_sees"} <= names(by["physics"])
    assert "search_comms" in names(by["comms"]) and "walk_time" not in names(by["comms"])
    assert "request_evidence" not in set().union(*(names(s) for s in specs))
    assert all("fact" in s["system_prompt"].lower() and s["description"] for s in specs)
