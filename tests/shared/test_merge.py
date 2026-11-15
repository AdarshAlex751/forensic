from app.shared import merge

SRC = {"file": "f.csv", "line": 2, "quote": "q", "sha256": "s"}
HANK = {"id": "p_hank", "aliases": ["badge:40388", "account:hgibson", "mac:02:1F:9A:10:00:02", "name:Hank Gibson", "email:hank@x.example"]}
MAGGIE = {"id": "p_maggie", "aliases": ["badge:40392", "account:mprice"]}


def ev(eid, kind=None, value=None, person=None):
    return {"id": eid, "t": "2026-03-04T18:00:00-05:00", "type": "badge_in", "person": person, "device": None, "room": None,
            "actor": {"kind": kind, "value": value} if kind else None, "attrs": {}, "source": SRC}


def test_person_is_filled_from_the_alias_that_matches_the_actor():
    out = merge.fill_persons([ev("e1", "badge", "40388"), ev("e2", "account", "hgibson"), ev("e3", "mac", "02:1f:9a:10:00:02")], [HANK, MAGGIE])
    assert [e["person"] for e in out] == ["p_hank", "p_hank", "p_hank"]


def test_matching_ignores_case_and_requires_the_same_kind():
    out = merge.fill_persons([ev("e1", "account", "HGibson"), ev("e2", "badge", "hgibson")], [HANK])
    assert [e["person"] for e in out] == ["p_hank", None]


def test_an_existing_person_is_never_overwritten():
    out = merge.fill_persons([ev("e1", "badge", "40388", person="p_maggie")], [HANK, MAGGIE])
    assert out[0]["person"] == "p_maggie"


def test_an_ambiguous_alias_is_left_unresolved():
    twin = {"id": "p_twin", "aliases": ["badge:40388"]}
    assert merge.fill_persons([ev("e1", "badge", "40388")], [HANK, twin])[0]["person"] is None


def test_events_without_an_actor_or_a_match_keep_a_null_person():
    out = merge.fill_persons([ev("e1"), ev("e2", "badge", "99999")], [HANK])
    assert [e["person"] for e in out] == [None, None]


def test_the_input_events_are_not_mutated_and_missing_fields_are_tolerated():
    original = ev("e1", "badge", "40388")
    out = merge.fill_persons([original, {"id": "e2"}], [HANK, {"id": "p_x"}, {"aliases": ["badge:1"]}])
    assert original["person"] is None and out[0]["person"] == "p_hank" and "person" not in out[1] or out[1].get("person") is None


def test_build_findings_fills_person_and_keeps_verified(monkeypatch):
    data = {
        ("evidence", "events.json"): [ev("e1", "badge", "40388")],
        ("investigator", "verification.json"): {"verified_event_ids": ["e1"]},
        ("analysis", "persons.json"): [HANK],
    }
    monkeypatch.setattr(merge, "load", lambda s, f: data.get((s, f), []))
    f = merge.build_findings()
    assert f["events"][0]["person"] == "p_hank" and f["events"][0]["verified"] is True
