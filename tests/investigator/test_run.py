import json
import re
from pathlib import Path

import pytest

from app.features.investigator import inputs, run as run_mod
from app.features.investigator.approvals import Approvals
from app.features.investigator.trace import Trace
from app.shared import schema

BADGE = "access/badge_access.csv"


@pytest.fixture()
def env(case, monkeypatch):
    """A real-mode run against the fixture case folder, writing into a temp output dir."""
    out = case.root.parent / "out"
    out.mkdir()
    e1 = case.event("e1", "badge_out", "2026-03-04T18:16:10-05:00", BADGE, 2, actor={"kind": "badge", "value": "40420"})
    e2 = case.event("e2", "badge_in", "2026-03-04T18:16:40-05:00", BADGE, 3, actor={"kind": "badge", "value": "40420"})
    bad = case.event("e3", "badge_in", "2026-03-04T18:16:40-05:00", BADGE, 3, quote="not in the file", actor={"kind": "badge", "value": "40420"})
    snap = inputs.Inputs(
        case=inputs.CaseInfo("1010F", "Case"), evidence=inputs.parse_list(case.evidence, inputs.EvidenceFile, "e"),
        events=inputs.parse_list([e1, e2, bad], inputs.Event, "e"), persons=[], edges=[], devices=[], rooms=[],
        contradictions=[inputs.Contradiction("c1", "physical", ["e1", "e2"], 0.98, "Same badge, two rooms 30 s apart."),
                        inputs.Contradiction("c2", "temporal", ["e3"], 0.9, "Cites a rejected event.")],
    )
    snap.extra_event_ids = []
    monkeypatch.setattr(run_mod, "OUT_DIR", out)
    monkeypatch.setattr(run_mod, "_load_inputs", lambda include_extra: snap)
    monkeypatch.setattr(run_mod, "_case_files", lambda: inputs.CaseFiles(case.root))
    monkeypatch.setattr(run_mod, "approvals", Approvals())
    monkeypatch.setattr(run_mod, "trace", Trace())
    monkeypatch.setattr(run_mod, "_investigate", lambda ctx, trace: __import__("app.features.investigator.lead_agent", fromlist=["x"]).investigate(ctx, runner=lambda p: "nope", trace=trace))
    monkeypatch.setattr(run_mod, "_use_real", lambda: True)
    return out, snap


def read(out: Path, name: str):
    return json.loads((out / name).read_text(encoding="utf-8"))


def test_fake_mode_writes_nothing(env, monkeypatch):
    out, _ = env
    monkeypatch.setattr(run_mod, "_use_real", lambda: False)
    run_mod.run("1010F")
    assert list(out.iterdir()) == []


def test_real_mode_writes_the_four_files_matching_the_schema(env):
    out, _ = env
    run_mod.run("1010F")
    assert sorted(p.name for p in out.iterdir()) == ["hypotheses.json", "notes.json", "requests.json", "verification.json"]
    v = schema.Verification.model_validate(read(out, "verification.json"))
    assert v.verified_event_ids == ["e1", "e2"]
    assert (v.claims, v.verified, len(v.rejected)) == (5, 3, 2)  # 3 events + 2 contradictions; e3 and c2 rejected
    assert [schema.Hypothesis.model_validate(h).supports for h in read(out, "hypotheses.json")] == [["c1"]]
    [schema.Note.model_validate(n) for n in read(out, "notes.json")]
    [schema.Request.model_validate(r) for r in read(out, "requests.json")]


def test_agents_only_see_verified_facts(env, monkeypatch):
    seen = {}

    def spy(ctx, trace):
        seen["events"] = [e.id for e in ctx.events]
        seen["contradictions"] = [c.id for c in ctx.contradictions]
        from app.features.investigator.lead_agent import rules_result
        return rules_result(ctx)

    monkeypatch.setattr(run_mod, "_investigate", spy)
    run_mod.run("1010F")
    assert seen == {"events": ["e1", "e2"], "contradictions": ["c1"]}


def test_missing_case_folder_skips_the_run_instead_of_rejecting_everything(env, monkeypatch, tmp_path_factory=None):
    out, _ = env
    monkeypatch.setattr(run_mod, "_case_files", lambda: inputs.CaseFiles(out / "no-such-folder"))
    run_mod.run("1010F")
    assert list(out.iterdir()) == []


def test_approved_request_becomes_ingested_once_extra_events_are_present(env):
    out, snap = env
    run_mod.approvals.add_request("Pull the parking exit log.", "why")
    run_mod.approvals.approve("r1")
    snap.extra_event_ids = ["e9916"]
    run_mod.run("1010F")
    assert read(out, "requests.json")[0]["status"] == "ingested"


def test_approved_request_stays_approved_until_extra_events_arrive(env):
    out, _ = env
    run_mod.approvals.add_request("Pull the parking exit log.", "why")
    run_mod.approvals.approve("r1")
    run_mod.run("1010F")
    assert read(out, "requests.json")[0]["status"] == "approved"


def test_trace_starts_fresh_and_ends_done(env):
    run_mod.run("1010F")
    snap = run_mod.trace.snapshot()
    assert snap[0]["agent"] == "verifier" and snap[-1]["stage"] == "done"


def test_investigator_code_never_opens_the_answer_key_or_eval_file():
    pkg = Path(run_mod.__file__).parent
    pat = re.compile(r"(load|read_bytes|read_text|open)\([^)\n]*(answer_key|eval\.json)")
    offenders = [p.name for p in pkg.glob("*.py") if pat.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_the_agents_are_told_which_withheld_sources_can_be_requested(env, monkeypatch):
    seen = {}

    def spy(ctx, trace):
        seen["requestable"] = ctx.requestable
        from app.features.investigator.lead_agent import rules_result
        return rules_result(ctx)

    monkeypatch.setattr(run_mod, "_investigate", spy)
    monkeypatch.setattr(run_mod, "_withheld_sources", lambda: ["access/parking_exit.csv"])
    run_mod.run("1010F")
    assert seen["requestable"] == ["access/parking_exit.csv"]


def test_a_real_run_does_not_carry_over_pending_requests_learned_from_the_fake_file(env):
    out, _ = env
    run_mod.approvals.sync([{"id": "r1", "ask": "Pull the campus parking exit log (fake demo request)", "why": "y", "status": "pending"}])
    run_mod.run("1010F")
    assert read(out, "requests.json") == []


def test_a_real_run_keeps_requests_the_human_already_approved(env):
    out, _ = env
    run_mod.approvals.add_request("Pull the parking log", "why")
    run_mod.approvals.approve("r1")
    run_mod.run("1010F")
    assert [(r["id"], r["status"]) for r in read(out, "requests.json")] == [("r1", "approved")]


def test_an_approved_request_becomes_ingested_when_events_from_its_withheld_file_are_in_the_case(env, monkeypatch):
    """No baseline needed: the first run in a process may happen after the approval (server restarted, or run late)."""
    out, snap = env
    parking = inputs.parse_list([{"id": "e9", "t": "2026-03-04T18:44:00-05:00", "type": "parking_exit", "person": None,
                                  "device": None, "room": None, "actor": None, "attrs": {},
                                  "source": {"file": "access/parking_exit.csv", "line": 2, "quote": "q", "sha256": "s"}}],
                                inputs.Event, "e")
    snap.events = list(snap.events) + parking
    monkeypatch.setattr(run_mod, "_withheld_sources", lambda: ["access/parking_exit.csv"])
    run_mod._state["baseline_events"] = None
    run_mod.approvals.add_request("Pull the parking log", "why")
    run_mod.approvals.approve("r1")
    run_mod.run("1010F")
    assert read(out, "requests.json")[0]["status"] == "ingested"


def test_an_approved_request_stays_approved_while_its_withheld_file_has_no_events_yet(env, monkeypatch):
    out, _ = env
    monkeypatch.setattr(run_mod, "_withheld_sources", lambda: ["access/parking_exit.csv"])
    run_mod._state["baseline_events"] = None
    run_mod.approvals.add_request("Pull the parking log", "why")
    run_mod.approvals.approve("r1")
    run_mod.run("1010F")
    assert read(out, "requests.json")[0]["status"] == "approved"
