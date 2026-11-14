import pytest

from app.features.investigator import inputs
from app.features.investigator.agent_tools import AgentTools, ToolContext, resolve_person
from app.features.investigator.approvals import Approvals

SRC = {"file": "f.csv", "line": 2, "quote": "q", "sha256": "s"}


def E(eid, t, typ, actor=None, **kw):
    return inputs.Event.from_dict({"id": eid, "t": t, "type": typ, "source": SRC | kw.pop("source", {}),
                                   **({"actor": actor} if actor else {}), **kw})


PERSONS = [
    inputs.Person("p_hank", "Hank Gibson", aliases=["hank.gibson@halvorsen.example", "badge:40388", "mac:02:1F:9A:10:00:02", "hgibson"]),
    inputs.Person("p_maggie", "Maggie Price", aliases=["badge:40392"]),
]


@pytest.fixture()
def tools():
    events = [
        E("e1", "2026-03-04T18:02:00-05:00", "badge_out", {"kind": "badge", "value": "40388"}, room="217"),
        E("e2", "2026-03-04T18:41:00-05:00", "wifi_disassoc", {"kind": "mac", "value": "02:1f:9a:10:00:02"}),
        E("e3", "2026-03-04T17:45:00-05:00", "badge_out", {"kind": "badge", "value": "40392"}),
        E("e4", "2026-03-04T17:30:00-05:00", "chat", {"kind": "slack", "value": "U1"}, source={"quote": "bring what you can"}),
        E("e5", "2026-03-05T09:00:00-05:00", "badge_in", {"kind": "badge", "value": "40388"}, person="p_hank"),
    ]
    ctx = ToolContext(events=events, persons=PERSONS,
                      contradictions=[inputs.Contradiction("c1", "temporal", ["e1", "e2"])],
                      edges=[inputs.Edge("p_hank", "rdr-217", "used", ["e1"])],
                      approvals=Approvals())
    return AgentTools(ctx)


def test_resolve_person_matches_badge_mac_account_and_name_case_insensitively():
    assert resolve_person(E("x", "t", "badge_in", {"kind": "badge", "value": "40388"}), PERSONS) == "p_hank"
    assert resolve_person(E("x", "t", "wifi_assoc", {"kind": "mac", "value": "02:1F:9A:10:00:02"}), PERSONS) == "p_hank"
    assert resolve_person(E("x", "t", "logon", {"kind": "account", "value": "HGibson"}), PERSONS) == "p_hank"
    assert resolve_person(E("x", "t", "statement", {"kind": "name", "value": "Maggie Price"}), PERSONS) == "p_maggie"
    assert resolve_person(E("x", "t", "badge_in", {"kind": "badge", "value": "99999"}), PERSONS) is None


def test_resolve_person_prefers_an_id_already_on_the_event():
    assert resolve_person(E("x", "t", "badge_in", {"kind": "badge", "value": "40392"}, person="p_hank"), PERSONS) == "p_hank"


def test_query_timeline_filters_by_person_and_window_and_sorts_by_time(tools):
    out = tools.query_timeline("p_hank", "2026-03-04T18:00:00-05:00", "2026-03-04T19:00:00-05:00")
    assert [e["id"] for e in out["events"]] == ["e1", "e2"]
    assert out["events"][0]["source"] == {"file": "f.csv", "line": 2}


def test_query_timeline_without_person_returns_everyone(tools):
    out = tools.query_timeline("", "2026-03-04T00:00:00-05:00", "2026-03-04T23:59:59-05:00")
    assert [e["id"] for e in out["events"]] == ["e4", "e3", "e1", "e2"]


def test_query_timeline_bad_time_is_a_readable_error_not_a_crash(tools):
    out = tools.query_timeline("p_hank", "tonight", "later")
    assert "ISO 8601" in out["error"]


def test_search_comms_finds_matching_text_only_in_messages(tools):
    out = tools.search_comms("bring what")
    assert [e["id"] for e in out["events"]] == ["e4"]
    assert tools.search_comms("nothing like this")["events"] == []


def test_graph_neighbors_returns_edges_with_event_ids(tools):
    out = tools.graph_neighbors("p_hank")
    assert out["neighbors"] == [{"node": "rdr-217", "type": "used", "events": ["e1"]}]


def test_request_evidence_creates_one_pending_request_and_is_idempotent(tools):
    a = tools.request_evidence("Pull the parking exit log, 18:10 to 18:45.", "Disproves h1 if the car left earlier.")
    b = tools.request_evidence("Pull the parking exit log, 18:10 to 18:45.", "again")
    assert a["id"] == b["id"] == "r1" and a["status"] == "pending"
    assert len(tools.ctx.approvals.requests) == 1


def test_scene_tools_pass_through_and_tag_their_source(tools):
    class Scene:
        walk_time = staticmethod(lambda a, b: {"seconds": 74, "path": [a, b]})
        ap_covers = staticmethod(lambda ap, room: True)
        camera_sees = staticmethod(lambda cam, room: False)

    tools.ctx.scene = Scene
    assert tools.walk_time("230", "219") == {"seconds": 74, "path": ["230", "219"], "source": "scene.tools.walk_time"}
    assert tools.ap_covers("ap-2-04", "219")["covers"] is True
    assert tools.camera_sees("cam-03", "219")["sees"] is False


def test_scene_tool_failure_becomes_an_error_result(tools):
    class Scene:
        @staticmethod
        def walk_time(a, b):
            raise RuntimeError("sweep graph not built")

    tools.ctx.scene = Scene
    assert "sweep graph not built" in tools.walk_time("230", "219")["error"]


def test_langchain_tool_list_exposes_named_documented_callables(tools):
    fns = tools.as_functions()
    names = {f.__name__ for f in fns}
    assert {"query_timeline", "search_comms", "graph_neighbors", "request_evidence", "walk_time", "ap_covers", "camera_sees"} <= names
    assert all(f.__doc__ for f in fns)
