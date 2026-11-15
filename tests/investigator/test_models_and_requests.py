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
