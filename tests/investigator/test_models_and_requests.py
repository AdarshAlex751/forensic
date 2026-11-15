from app.features.investigator import inputs
from app.features.investigator.agent_tools import ToolContext
from app.features.investigator.approvals import Approvals
from app.features.investigator.lead_agent import pick_model, rules_result

SRC = {"file": "f.csv", "line": 2, "quote": "q", "sha256": "s"}


def ev(i, etype="badge_in"):
    return inputs.Event.from_dict({"id": f"e{i}", "t": f"2026-03-04T18:0{i}:00-05:00", "type": etype, "source": SRC})


def ctx_with(cons, events=None, approvals=None):
    return ToolContext(events=events or [ev(1), ev(2)], contradictions=cons, approvals=approvals or Approvals())


STATEMENT = inputs.Contradiction("c5", "statement", ["e1", "e2"], 0.95,
                                 'The person said "I went straight home at six." Their last badge read was OUT of room 217 at 6:02 pm.')
PHYSICAL = inputs.Contradiction("c2", "physical", ["e1", "e2"], 0.98, "The same badge was read in two rooms 30 s apart.")


# ---- model choice ----
def test_pick_model_takes_the_first_candidate_the_account_has():
    assert pick_model(["a", "b", "c"], available={"b", "c"}) == "b"


def test_pick_model_keeps_the_first_candidate_when_the_model_list_is_unknown():
    assert pick_model(["a", "b"], available=None) == "a"


def test_pick_model_returns_none_when_no_candidate_exists_so_the_rules_engine_runs():
    assert pick_model(["a", "b"], available={"z"}) is None


# ---- the fallback still raises the evidence request that the demo needs ----
def test_rules_request_the_parking_log_when_a_statement_hinges_on_when_someone_left():
    c = ctx_with([STATEMENT, PHYSICAL])
    res = rules_result(c)
    assert len(res.requests) == 1
    r = res.requests[0]
    assert r["status"] == "pending" and "parking" in r["ask"].lower() and "c5" in r["why"]
    assert any("Waiting for approval" in n["text"] for n in res.notes)


def test_rules_request_nothing_for_conflicts_that_do_not_concern_leaving():
    assert rules_result(ctx_with([PHYSICAL])).requests == []


def test_rules_do_not_ask_again_once_parking_records_are_part_of_the_case():
    c = ctx_with([STATEMENT], events=[ev(1), ev(2, "parking_exit")])
    assert rules_result(c).requests == []


def test_rules_do_not_duplicate_a_request_that_already_exists():
    a = Approvals()
    first = rules_result(ctx_with([STATEMENT], approvals=a)).requests
    second = rules_result(ctx_with([STATEMENT], approvals=a)).requests
    assert len(first) == len(second) == 1


# ---- the investigator reports what the records show, never intent, motive, deception or fault ----
from app.features.investigator.agent_tools import AgentTools  # noqa: E402
from app.features.investigator.lead_agent import LEAD_PROMPT, build_brief, sanitize_hypotheses  # noqa: E402

INTENT_PHRASES = [
    "Camera cam-03 was deliberately taken offline to conceal activity.",
    "The USB drive was introduced, indicating a false statement or tampering.",
    "The badge records were spoofed, so nobody could have been in both rooms.",
    "Hank remained in the building, possibly to access data.",
    "Her statement is false; she left earlier.",
    "He lied about the drive.",
    "Files were exfiltrated to the drive.",
    "The records show a cover-up.",
]


def test_hypotheses_that_speak_of_intent_or_deception_are_not_kept_as_written():
    raw = [{"text": t, "confidence": 0.8, "supports": ["c2"], "disproved_by": "A corrected record."} for t in INTENT_PHRASES]
    out, warns = sanitize_hypotheses(raw, {"c2"})
    assert out == [] and len(warns) == len(INTENT_PHRASES)


def test_a_banned_hypothesis_is_replaced_by_neutral_wording_for_the_same_contradiction():
    raw = [{"text": "The camera was deliberately taken offline to conceal activity.", "confidence": 0.7,
            "supports": ["c4"], "disproved_by": "A work order covering the outage."}]
    out, warns = sanitize_hypotheses(raw, {"c4"}, neutral={"c4": "The records conflict: cam-03 was offline with no work order."})
    assert [h["text"] for h in out] == ["The records conflict: cam-03 was offline with no work order."]
    assert out[0]["confidence"] == 0.7 and out[0]["supports"] == ["c4"]
    assert any("neutral" in w for w in warns)


def test_neutral_factual_wording_passes_untouched():
    text = "The badge record and the laptop log cannot both describe the same hour."
    out, _ = sanitize_hypotheses([{"text": text, "confidence": 0.8, "supports": ["c2"], "disproved_by": "A clock error."}], {"c2"})
    assert [h["text"] for h in out] == [text]


def test_the_prompt_tells_the_model_to_describe_records_not_intent():
    p = LEAD_PROMPT.lower()
    assert "intent" in p and "motive" in p and "conceal" in p


# ---- evidence requests are limited to what can really be released ----
def test_a_request_for_a_source_that_is_not_obtainable_is_refused_and_lists_what_is():
    c = ctx_with([STATEMENT])
    c.requestable = ["access/parking_exit.csv"]
    r = AgentTools(c).request_evidence("Provide motion sensor logs for the hallway.", "to test c2")
    assert "error" in r and "parking_exit.csv" in r["error"]
    assert c.approvals.requests == []


def test_a_request_matching_a_withheld_source_is_accepted():
    c = ctx_with([STATEMENT])
    c.requestable = ["access/parking_exit.csv"]
    r = AgentTools(c).request_evidence("Pull the campus parking exit log for 2026-03-04.", "tests c5")
    assert r["id"] == "r1" and r["status"] == "pending"


def test_exit_camera_footage_is_not_mistaken_for_the_parking_exit_log():
    c = ctx_with([STATEMENT])
    c.requestable = ["access/parking_exit.csv"]
    assert "error" in AgentTools(c).request_evidence("Exit camera footage for 6:02 pm.", "tests c5")


def test_with_no_known_withheld_sources_requests_stay_unrestricted_for_backward_compatibility():
    c = ctx_with([STATEMENT])  # requestable is None
    assert AgentTools(c).request_evidence("Anything.", "why")["status"] == "pending"


def test_an_empty_withheld_list_means_nothing_more_can_be_requested():
    c = ctx_with([STATEMENT])
    c.requestable = []
    assert "error" in AgentTools(c).request_evidence("Pull the parking log.", "why")


def test_the_brief_names_the_withheld_sources_a_human_can_release():
    c = ctx_with([STATEMENT])
    c.requestable = ["access/parking_exit.csv"]
    assert "parking_exit.csv" in build_brief(c)


# ---- the parking request does not depend on the language model choosing to ask ----
import json as _json  # noqa: E402

from app.features.investigator.lead_agent import investigate  # noqa: E402

NO_REQUEST_JSON = _json.dumps({
    "hypotheses": [{"text": "The statement is not supported by the badge record.", "confidence": 0.8, "supports": ["c5"],
                    "disproved_by": "A later badge read."}],
    "notes": [],
})


def test_with_the_llm_the_parking_request_is_still_raised_when_the_model_did_not_ask():
    c = ctx_with([STATEMENT])
    c.requestable = ["access/parking_exit.csv"]
    res = investigate(c, runner=lambda prompt: NO_REQUEST_JSON, trace=__import__("app.features.investigator.trace", fromlist=["x"]).Trace())
    assert res.engine == "llm" and [r["status"] for r in res.requests] == ["pending"]
    assert "parking" in res.requests[0]["ask"].lower()


def test_no_request_is_raised_when_nothing_can_be_released():
    c = ctx_with([STATEMENT])
    c.requestable = []
    assert rules_result(c).requests == []


def test_the_rules_request_respects_the_obtainable_list():
    c = ctx_with([STATEMENT])
    c.requestable = ["access/parking_exit.csv"]
    assert len(rules_result(c).requests) == 1


def test_the_safety_net_does_not_add_a_second_request_for_a_source_the_model_already_asked_for():
    c = ctx_with([STATEMENT])
    c.requestable = ["access/parking_exit.csv"]
    c.approvals.add_request("Please provide access/parking_exit.csv", "tests c5")  # the model's own wording
    res = rules_result(c)
    assert [r["ask"] for r in res.requests] == ["Please provide access/parking_exit.csv"]


def test_a_source_that_was_already_requested_and_approved_is_not_requested_again():
    c = ctx_with([STATEMENT])
    c.requestable = ["access/parking_exit.csv"]
    c.approvals.add_request("Pull the parking exit log", "tests c5")
    c.approvals.approve("r1")
    assert len(rules_result(c).requests) == 1


# ---- request text never cites hypothesis ids: the ranking renumbers them, so "H2" would point at the wrong card ----
import re as _re  # noqa: E402

import pytest  # noqa: E402

HYP_ID = _re.compile(r"\bh\d+\b", _re.I)


@pytest.mark.parametrize("why", [
    "To verify whether Hank exited before 6:00 pm, which would disprove hypotheses H2 and H3 about them remaining on premises.",
    "These logs could confirm the 74 s distance, thereby disproving hypothesis H1 about impossible movement.",
    "Tests h2: an exit after 18:16 conflicts with the statement.",
    "A parking record would weaken the timing (h3) of the badge reads.",
    "Would disprove H1, H2 & H4.",
])
def test_request_text_never_cites_hypothesis_ids(why):
    c = ctx_with([STATEMENT])
    AgentTools(c).request_evidence("Pull the parking log. It tests H2.", why)
    r = c.approvals.requests[0]
    assert not HYP_ID.search(r["why"]) and not HYP_ID.search(r["ask"])
    assert r["why"].strip() and "  " not in r["why"]


def test_contradiction_ids_are_kept_because_they_are_stable():
    c = ctx_with([STATEMENT])
    AgentTools(c).request_evidence("Pull the parking log.", "Tests whether c5 holds, which would disprove hypothesis H2.")
    assert "c5" in c.approvals.requests[0]["why"]


def test_ordinary_words_that_look_like_ids_are_left_alone():
    c = ctx_with([STATEMENT])
    AgentTools(c).request_evidence("Pull the parking log.", "Records from 2H and the H-wing lobby, room H12a, are not involved.")
    assert c.approvals.requests[0]["why"] == "Records from 2H and the H-wing lobby, room H12a, are not involved."


# ---- the same wording rule applies to "what would disprove it" and to the model's evidence requests ----
def test_a_disproof_that_speaks_of_intent_is_replaced_by_the_kind_default():
    raw = [{"text": "The camera was offline with no work order.", "confidence": 0.6, "supports": ["c4"],
            "disproved_by": "Work-order logs confirming the camera was intentionally taken offline for a known reason."}]
    out, warns = sanitize_hypotheses(raw, {"c4"}, disproof_for={"c4": "A work order covering the outage."})
    assert [h["disproved_by"] for h in out] == ["A work order covering the outage."]
    assert any("disproof" in w for w in warns)


def test_a_disproof_with_banned_wording_and_no_default_drops_the_hypothesis():
    raw = [{"text": "The camera was offline.", "confidence": 0.6, "supports": ["c4"], "disproved_by": "Proof he hid it."}]
    out, _ = sanitize_hypotheses(raw, {"c4"})
    assert out == []


def test_an_evidence_request_that_speaks_of_intent_is_refused_so_the_model_can_reword_it():
    c = ctx_with([STATEMENT])
    r = AgentTools(c).request_evidence("Pull the parking log.", "To show he deliberately left late to conceal the copying.")
    assert "error" in r and c.approvals.requests == []
