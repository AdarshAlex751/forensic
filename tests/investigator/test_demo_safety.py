"""The demo must survive Groq failing: every failure ends on the rules fallback, which still raises the parking-log
request and still produces hypotheses, and nothing hangs."""
import json
import threading
import time

import pytest

from app.features.investigator import inputs, lead_agent
from app.features.investigator.agent_tools import ToolContext
from app.features.investigator.approvals import Approvals
from app.features.investigator.lead_agent import investigate
from app.features.investigator.trace import Trace
from app.shared import llm_client, schema

SRC = {"file": "f.csv", "line": 2, "quote": "q", "sha256": "s"}
LEAVING = inputs.Contradiction("c5", "statement", ["e1", "e2"], 0.95,
                               'The person said "I went straight home at six." Their last badge read was OUT at 6:02 pm.')
OTHER = inputs.Contradiction("c2", "physical", ["e1", "e2"], 0.98, "The same badge was read in two rooms 30 s apart.")
GOOD = json.dumps({"hypotheses": [{"text": "The statement is not supported by the badge record.", "confidence": 0.8,
                                   "supports": ["c5"], "disproved_by": "A later badge read."}], "notes": []})


def ctx():
    events = [inputs.Event.from_dict({"id": f"e{i}", "t": f"2026-03-04T18:0{i}:00-05:00", "type": "badge_in", "source": SRC}) for i in (1, 2)]
    c = ToolContext(events=events, contradictions=[LEAVING, OTHER], approvals=Approvals())
    c.requestable = ["access/parking_exit.csv"]
    return c


def assert_demo_still_works(res):
    assert res.engine == "rules"
    assert res.hypotheses, "the memo needs hypotheses"
    for h in res.hypotheses:
        schema.Hypothesis.model_validate(h)
    assert [r["status"] for r in res.requests] == ["pending"] and "parking" in res.requests[0]["ask"].lower()


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)  # the backoff must not make the tests wait


# (a) no key
def test_a_empty_groq_key_runs_the_rules_engine(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert_demo_still_works(investigate(ctx(), trace=Trace()))


def test_a_missing_groq_key_runs_the_rules_engine(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert_demo_still_works(investigate(ctx(), trace=Trace()))


# (b) invalid key: Groq answers 401 on the first call
def test_b_an_invalid_key_falls_back_to_rules():
    class AuthenticationError(Exception):
        pass

    def runner(prompt):
        raise AuthenticationError("Error code: 401 - {'error': {'message': 'Invalid API Key', 'code': 'invalid_api_key'}}")

    assert_demo_still_works(investigate(ctx(), runner=runner, trace=Trace()))


# (c) rate limited (429) on every attempt
def test_c_a_429_that_never_clears_falls_back_to_rules_after_the_retries():
    calls = []

    def runner(prompt):
        calls.append(1)
        raise RuntimeError("Error code: 429 - rate limit reached")

    res = investigate(ctx(), runner=runner, trace=Trace())
    assert len(calls) == 6  # the first try plus five backoff retries, then give up
    assert_demo_still_works(res)


def test_c_a_429_that_clears_is_retried_and_the_model_answer_is_used():
    calls = []

    def runner(prompt):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("429 rate limit")
        return GOOD

    res = investigate(ctx(), runner=runner, trace=Trace())
    assert res.engine == "llm" and len(calls) == 3
    assert [r["status"] for r in res.requests] == ["pending"]  # the parking request is raised for the model too


# a call that never returns must not hang the pipeline
def test_a_hung_model_call_is_cut_off_and_falls_back_to_rules(monkeypatch):
    monkeypatch.setenv("INVESTIGATOR_LLM_BUDGET_S", "0.3")

    def runner(prompt):
        threading.Event().wait(30)  # blocks for real (time.sleep is patched out in this module)
        return GOOD

    t = time.monotonic()
    res = investigate(ctx(), runner=runner, trace=Trace())
    assert time.monotonic() - t < 5
    assert_demo_still_works(res)
    assert any("timed out" in w.lower() or "time" in w.lower() for w in res.warnings)


def test_the_model_clients_get_a_60_second_request_timeout():
    assert lead_agent.LLM_REQUEST_TIMEOUT_S == 60


# ---- Groq rejects an answer the model wrapped in a call to a tool named "json" (400 tool_use_failed), but the whole
# ---- answer is inside the error (failed_generation). It is recovered instead of thrown away.
ANSWER = {"hypotheses": [{"text": "The statement is not supported by the badge record.", "confidence": 0.8,
                          "supports": ["c5"], "disproved_by": "A later badge read."}], "notes": []}


class BadRequestError(Exception):
    def __init__(self, failed_generation: str, as_body: bool = True):
        self.body = {"message": "Tool call validation failed", "type": "invalid_request_error", "code": "tool_use_failed",
                     "failed_generation": failed_generation} if as_body else None
        super().__init__("Error code: 400 - " + repr({"error": {"message": "Tool call validation failed", "code": "tool_use_failed",
                                                              "failed_generation": failed_generation}}))


def test_an_answer_wrapped_in_a_json_tool_call_is_recovered_from_the_error_body():
    wrapped = json.dumps({"name": "json", "arguments": ANSWER})

    def runner(prompt):
        raise BadRequestError(wrapped)

    res = investigate(ctx(), runner=runner, trace=Trace())
    assert res.engine == "llm" and [h["supports"] for h in res.hypotheses] == [["c5"]]


def test_the_answer_is_recovered_from_the_error_text_when_there_is_no_body():
    wrapped = json.dumps({"name": "json", "arguments": ANSWER})

    def runner(prompt):
        raise BadRequestError(wrapped, as_body=False)

    assert investigate(ctx(), runner=runner, trace=Trace()).engine == "llm"


def test_arguments_given_as_a_json_string_are_recovered_too():
    wrapped = json.dumps({"name": "json", "arguments": json.dumps(ANSWER)})

    def runner(prompt):
        raise BadRequestError(wrapped)

    assert investigate(ctx(), runner=runner, trace=Trace()).engine == "llm"


def test_a_recovered_answer_still_goes_through_the_wording_filter():
    bad = dict(ANSWER, hypotheses=[dict(ANSWER["hypotheses"][0], text="She deliberately hid the badge to conceal the copying.")])

    def runner(prompt):
        raise BadRequestError(json.dumps({"name": "json", "arguments": bad}))

    res = investigate(ctx(), runner=runner, trace=Trace())
    assert res.engine == "llm" and "deliberately" not in json.dumps(res.hypotheses)


def test_an_unrecoverable_400_still_falls_back_to_rules():
    def runner(prompt):
        raise BadRequestError("not json at all")

    assert_demo_still_works(investigate(ctx(), runner=runner, trace=Trace()))
