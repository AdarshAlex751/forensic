"""Analysis slice tests: stages 3 (resolve), 4 (graph), 6 (anomaly), 7 (contradictions).

Unit tests use tiny inline events in the FORMAT.md shape. The fake-data tests run on Person 1's
fakes in data/evidence/fake/ and find events by type/time/device, never by e# or line (FORMAT.md 9).
Never reads answer_key.json.
"""
import json

import pytest

from app.features.analysis import entity_resolution, fact_graph, files, timeutil
from app.features.analysis.run import analyze, run

INVENTORY = [
    {"person_id": "p_hank", "name": "Hank Gibson", "home_room": "217", "badge": "40388",
     "laptop_mac": "02:1F:9A:10:00:02", "local_account": "hgibson", "parking_permit": "P-2088"},
    {"person_id": "p_bg_17", "name": "Rina Okafor", "home_room": "217", "badge": "40417"},
]


def ev(id, t, type, room=None, device=None, actor=None, attrs=None):
    kind, value = actor.split(":", 1) if actor else (None, None)
    return {"id": id, "t": f"2026-03-04T{t}-05:00", "type": type, "person": None, "room": room, "device": device,
            "actor": {"kind": kind, "value": value} if actor else None, "attrs": attrs or {},
            "source": {"file": "f", "line": 1, "quote": "q", "sha256": "x"}}


def resolve(events):
    idx = entity_resolution.build_alias_index(INVENTORY)
    return entity_resolution.resolve_events(events, idx, entity_resolution.build_persons(INVENTORY))


# ---------- unit ----------

def test_spoken_time_is_est():
    assert timeutil.spoken(timeutil.parse("2026-03-04T18:02:00-05:00")) == "6:02 pm"


def test_identifiers_normalize_and_resolve():
    out = resolve([
        ev("e1", "18:16:40", "badge_in", "219", "rdr-219", "badge:40417"),
        ev("e2", "18:41:00", "wifi_disassoc", actor="mac:02-1f-9a-10-00-02"),
        ev("e3", "18:17:05", "logon", "219", "lt-219", "account:LT-219\\hgibson", {"host": "lt-219"}),
        ev("e4", "09:00:00", "statement", actor="name:hank gibson"),
        ev("e5", "09:00:00", "chat", actor="slack:nobody"),
    ])
    assert [e["person"] for e in out] == ["p_bg_17", "p_hank", "p_hank", "p_hank", None]


def test_usb_mount_goes_to_logged_on_account_only_during_session():
    out = resolve([
        ev("e1", "18:17:05", "logon", "219", "lt-219", "account:hgibson", {"host": "lt-219"}),
        ev("e2", "18:17:30", "usb_mount", "219", "lt-219", None, {"host": "lt-219", "serial": "S1"}),
        ev("e3", "18:31:20", "logoff", "219", "lt-219", "account:hgibson", {"host": "lt-219"}),
        ev("e4", "19:05:00", "usb_mount", "219", "lt-219", None, {"host": "lt-219", "serial": "S2"}),
    ])
    assert out[1]["person"] == "p_hank" and out[1]["person_via"] == "host_session"
    assert out[3]["person"] is None


def test_bank_account_resolves_transactions():
    inv = [{**INVENTORY[0], "bank_account": "CHK-7731"}]
    idx = entity_resolution.build_alias_index(inv)
    [t] = entity_resolution.resolve_events([ev("e1", "10:42:00", "transaction", actor="account:CHK-7731")], idx, [])
    assert t["person"] == "p_hank"


def test_email_lines_link_once_per_message():
    msg = {"from": "hank.gibson@x.example", "to": ["a@x.example"], "message_id": "<m1>"}
    lines = [ev(f"e{i}", "10:14:00", "email", actor="email:hank.gibson@x.example", attrs=msg) for i in (1, 2, 3)]
    for e in lines:
        e["person"] = "p_hank"
    g = fact_graph.build_graph(lines, entity_resolution.build_persons(INVENTORY), [], {})
    [edge] = [x for x in fact_graph.export_edges(g) if x["type"] == "sent"]
    assert edge["events"] == ["e1"]


def test_graph_edges_and_kinds():
    events = resolve([
        ev("e1", "18:02:00", "badge_out", "217", "rdr-217", "badge:40388"),
        ev("e2", "18:20:00", "file_copy", "219", "lt-219", "account:hgibson", {"host": "lt-219", "path": "C:\\T\\a.step"}),
        ev("e3", "09:00:00", "transaction", actor="name:Hank Gibson", attrs={"amount": 25000.0, "counterparty": "Northline"}),
    ])
    idx = entity_resolution.build_alias_index(INVENTORY)
    g = fact_graph.build_graph(events, entity_resolution.build_persons(INVENTORY),
                               [{"device_id": "rdr-217", "room": "217"}, {"device_id": "lt-219", "room": "219"}], idx)
    edges = {(x["from"], x["to"], x["type"]): x for x in fact_graph.export_edges(g)}
    assert edges[("p_hank", "rdr-217", "used")]["events"] == ["e1"]
    assert edges[("p_hank", "file:C:\\T\\a.step", "accessed")]["to_kind"] == "file"
    assert ("org:Northline", "p_hank", "paid") in edges
    assert ("rdr-217", "room:217", "located_in") in edges


# ---------- Person 1's fakes ----------

@pytest.fixture(scope="module")
def result():
    return analyze(files.load_inputs())


def _find(events, type, t=None, **kw):
    hits = [e for e in events if e["type"] == type and (t is None or e["t"].startswith(t))
            and all(e.get(k) == v for k, v in kw.items())]
    assert hits, f"no {type} at {t} {kw}"
    return hits


def test_fakes_every_internal_actor_resolves(result):
    """Only outside identities (not in inventory.csv, e.g. the summit organizer's email) may stay unresolved."""
    left = [e["actor"] for e in result["events"] if e.get("actor") and not e.get("person")]
    assert all(a["kind"] in ("email", "slack") and "halvorsen.example" not in a["value"] for a in left), left
    edges = {(x["from"], x["type"]) for x in result["edges"]}
    assert ("email:events@jrr-aisummit.example", "sent") in edges


def test_fakes_story_identities(result):
    evs = result["events"]
    assert _find(evs, "badge_out", "2026-03-04T18:02:00", room="217")[0]["person"] == "p_hank"
    # Both C2 badge reads resolve to the card holder: a fact about the card, not who held it.
    assert _find(evs, "badge_in", "2026-03-04T18:16:10", room="230")[0]["person"] == "p_bg_17"
    assert _find(evs, "badge_in", "2026-03-04T18:16:40", room="219")[0]["person"] == "p_bg_17"
    assert _find(evs, "usb_mount", "2026-03-04T18:17:30")[0]["person"] == "p_hank"
    assert _find(evs, "wifi_disassoc", "2026-03-04T18:41:00")[0]["person"] == "p_hank"
    assert _find(evs, "maintenance_window", "2026-03-04T19:00:00")[0]["person"] == "p_frederik"
    speakers = {e["attrs"]["speaker"]: e["person"] for e in evs if e["type"] == "statement"}
    assert speakers == {"Hank Gibson": "p_hank", "Maggie Price": "p_maggie", "Frederik Mendelssohn": "p_frederik"}


def test_fakes_hank_aliases_merge(result):
    hank = next(p for p in result["persons"] if p["id"] == "p_hank")
    for alias in ("badge:40388", "mac:02:1F:9A:10:00:02", "account:hgibson", "permit:P-2088", "email:hank.gibson@halvorsen.example"):
        assert alias in hank["aliases"]


def test_fakes_graph_links_hank_to_titan_kim_and_northline(result):
    edges = {(x["from"], x["to"], x["type"]) for x in result["edges"]}
    assert any(f == "p_hank" and t.startswith("file:") and "Titan" in t for f, t, _ in edges)
    assert any(f == "p_hank" and t.startswith("usb:") for f, t, _ in edges)
    chats = {f for f, t, ty in edges if ty == "sent" and t.startswith("channel:")}
    assert {"p_hank", "p_kim"} <= chats
    assert any(f.startswith("org:Northline") and t == "p_hank" and ty == "paid" for f, t, ty in edges)


def test_fakes_every_edge_event_exists(result):
    ids = {e["id"] for e in result["events"]}
    for edge in result["edges"]:
        assert set(edge["events"]) <= ids


def test_run_writes_the_three_outputs(tmp_path):
    run("1010F", out_dir=tmp_path, use_nli=False)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["contradictions.json", "edges.json", "persons.json"]
    persons = json.loads((tmp_path / "persons.json").read_text(encoding="utf-8"))
    assert all({"id", "name", "aliases", "community", "centrality"} <= p.keys() for p in persons)


# ---------- stage 6: anomaly ----------

def walk_realistic(a, b):
    """Stand-in until Person 2's real walk_time: 230 <-> 219 is the far walk (CASE.md), neighbours are close."""
    far = {frozenset({"230", "219"}): 74}
    return {"seconds": far.get(frozenset({a, b}), 10), "path": [a, b]}


@pytest.fixture(scope="module")
def full():
    return analyze(files.load_inputs(), walk=walk_realistic)


def _person(r, pid):
    return next(p for p in r["persons"] if p["id"] == pid)


def test_anomaly_scores_in_range_and_hank_tops(full):
    scores = {p["id"]: p["anomaly"] for p in full["persons"]}
    assert all(0.0 <= v <= 1.0 for v in scores.values())
    assert max(scores, key=scores.get) == "p_hank"
    assert _person(full, "p_hank")["features"]["usb_mounts"] >= 1


def test_frederik_flagged_but_work_order_covers_it(full):
    """Red herring: high after-hours score, and the features carry the fact that clears him:
    most of his late time sits inside his own work order (fakes ~68%, real case ~97%)."""
    f = _person(full, "p_frederik")
    assert f["anomaly"] >= 0.5
    assert f["features"]["after_hours_in_work_order_minutes"] >= 0.5 * f["features"]["after_hours_minutes"]


# ---------- stage 7: contradictions ----------

from app.features.analysis import rules  # noqa: E402


@pytest.mark.parametrize("quote,expected", [
    ("I went straight home at six.", (18, 0, 10)),
    ("Hank and I left together around 6:30.", (18, 30, 20)),
    ("I left at 9:15 am", (9, 15, 10)),
    ("I copied two files.", None),
])
def test_claimed_time(quote, expected):
    got = rules.claimed_time(quote)
    assert (got and (got[0], got[1], got[2].seconds // 60)) == expected or got == expected


def _by_rule(r):
    out = {}
    for c in r["contradictions"]:
        out.setdefault(c["rule"], []).append(c)
    return out


def _cited(r, c):
    by_id = {e["id"]: e for e in r["events"]}
    return [by_id[x] for x in c["events"]]


def test_focus_day_comes_from_the_logs(full):
    assert full["focus_days"] == ["2026-03-04"]


def test_c2_only_the_far_badge_pair(full):
    [c2] = _by_rule(full)["impossible_travel"]
    rooms = [e["room"] for e in _cited(full, c2)]
    assert rooms == ["230", "219"] and c2["gap_s"] == 30 and c2["walk_s"] == 74


def test_tampered_file_is_cited_once_and_used_nowhere_else(full):
    tainted = "endpoint/security_log.csv"
    for c in full["contradictions"]:
        files_cited = {s["file"] for s in c["sources"]}
        assert (tainted in files_cited) == (c["rule"] == "custody_mismatch")


def test_c1_c6_c8(full):
    by = _by_rule(full)
    [c1] = by["wifi_after_last_badge"]
    assert [e["type"] for e in _cited(full, c1)] == ["badge_out", "wifi_disassoc"]
    [c6] = by["camera_gap_without_work_order"]
    assert "cam-03" in c6["explanation"]  # cam-02 / cam-05 outages have work orders
    [c8] = by["custody_mismatch"]
    assert c8["file"] == "endpoint/security_log.csv"


def test_c4_maggie_and_hank_leave_claims(full):
    claims = {_cited(full, c)[0]["attrs"]["speaker"]: c for c in _by_rule(full)["leave_time_claim"]}
    assert set(claims) == {"Hank Gibson", "Maggie Price"}
    maggie_cited = {(e["type"], e["t"][11:19]) for e in _cited(full, claims["Maggie Price"])}
    assert ("badge_out", "17:45:00") in maggie_cited


def test_c3_parking_exit_after_evidence_is_released():
    import json as _json
    from app.shared.config import DATA_DIR

    inputs = files.load_inputs()
    inputs["events"] += _json.loads((DATA_DIR / "evidence" / "fake" / "events_extra.json").read_text(encoding="utf-8"))
    r = analyze(inputs, use_nli=False, walk=walk_realistic)
    hank = [c for c in _by_rule(r)["leave_time_claim"] if _cited(r, c)[0]["attrs"]["speaker"] == "Hank Gibson"]
    assert [(e["type"], e["t"][11:19]) for e in _cited(r, hank[0])][-1] == ("parking_exit", "18:44:00")


def test_c7_drive_first_seen_that_night(full):
    [c7] = _by_rule(full)["drive_history_claim"]
    assert _cited(full, c7)[1]["attrs"]["first_seen"].startswith("2026-03-04")


def test_c5_nli_titan_and_no_false_alarm_on_frederik(full):
    nli_hits = _by_rule(full).get("nli", [])
    if not nli_hits:
        pytest.skip("NLI model not available")
    assert [_cited(full, c)[0]["source"]["quote"] for c in nli_hits] == ["I never touched the Titan folder."]


def test_no_contradiction_targets_red_herrings(full):
    """Accusing Frederik, or anyone other than the card holder in C2, counts as a false alarm (CASE.md)."""
    for c in full["contradictions"]:
        assert "p_frederik" not in c.get("persons", [])
        if c["rule"] != "impossible_travel":
            assert "p_bg_17" not in c.get("persons", [])
        assert c["sources"] and all({"file", "line", "quote", "sha256"} <= s.keys() for s in c["sources"])


# ---------- page fields (views.py): red flags page and contradictions page ----------

def test_red_flags_page_ranks_and_cites_events(full):
    ranked = sorted((p for p in full["persons"] if p["anomaly_rank"]), key=lambda p: p["anomaly_rank"])
    assert ranked[0]["id"] == "p_hank" and ranked[0]["anomaly_rank"] == 1
    ids = {e["id"] for e in full["events"]}
    flags = {f["feature"]: f for f in ranked[0]["red_flags"]}
    assert flags["usb_mounts"]["events"] and set(flags["usb_mounts"]["events"]) <= ids
    assert all(f["value"] > f["baseline"] for f in ranked[0]["red_flags"])


def test_red_flags_page_shows_frederiks_work_order(full):
    [ctx] = _person(full, "p_frederik")["context"]
    assert ctx["kind"] == "work_order" and ctx["events"]


def test_contradiction_cards_have_sides_and_chain(full):
    for c in full["contradictions"]:
        assert c["title"] and len(c["sides"]) == 2
        assert [x["event"] for x in c["chain"]] == c["events"]
        assert all(x["source"]["sha256"] for x in c["chain"])
    [c5] = _by_rule(full).get("nli", [None])[:1] or [None]
    if c5:
        assert c5["sides"][0]["label"] == "Said" and c5["sides"][0]["quotes"] == ["I never touched the Titan folder."]


def test_release_keeps_ids_and_marks_the_parking_finding():
    """Rerun after the parking log is released: ids stay, Hank's leave claim is marked updated and is `latest`."""
    import json as _json
    from app.features.analysis import views
    from app.shared.config import DATA_DIR

    inputs = files.load_inputs()
    before = analyze(inputs, use_nli=False, walk=walk_realistic)["contradictions"]
    inputs["events"] += _json.loads((DATA_DIR / "evidence" / "fake" / "events_extra.json").read_text(encoding="utf-8"))
    after = analyze(inputs, use_nli=False, walk=walk_realistic, previous=before)["contradictions"]

    assert {c["key"]: c["id"] for c in before}.items() <= {c["key"]: c["id"] for c in after}.items()
    changed = [c for c in after if c["change"]]
    assert changed and all(c["rule"] == "leave_time_claim" for c in changed)
    latest = next(c for c in after if c["id"] == views.latest_change(after))
    assert latest["chain"][-1]["type"] == "parking_exit"


def test_released_unlisted_file_is_trusted_only_hash_mismatch_is_not():
    evidence = [
        {"file": "manifest.csv", "manifest_match": False, "manifest_sha256": None},
        {"file": "endpoint/security_log.csv", "manifest_match": False, "manifest_sha256": "abc"},
        {"file": "access/parking_exit.csv", "manifest_match": False, "manifest_sha256": None},  # released from extra/
    ]
    assert rules.untrusted_files(evidence) == {"endpoint/security_log.csv"}
    assert [c["file"] for c in rules.custody_mismatch([], evidence)] == ["endpoint/security_log.csv"]


def test_left_the_room_is_not_checked_against_the_parking_exit():
    """Frederik: 'left the room' at 21:30 matches his badge-out; his car leaving 11 min later is not a conflict."""
    import datetime as _dt
    persons = [{"id": "p_frederik", "name": "Frederik Mendelssohn"}]

    def stmt(quote):
        e = ev("e1", "16:30:00", "statement", actor="name:Frederik Mendelssohn", attrs={"speaker": "Frederik Mendelssohn"})
        e["source"] = {**e["source"], "quote": quote}
        return e

    records = [ev("e2", "21:30:12", "badge_out", "219", "rdr-219"), ev("e3", "21:41:03", "parking_exit")]
    for e in records:
        e["person"] = "p_frederik"
    day = {_dt.date(2026, 3, 4)}
    room = stmt("I logged off shortly before 21:30 and left the room.")
    room["person"] = "p_frederik"
    assert rules.leave_time_claims([room, *records], persons, day) == []
    home = stmt("I went home at 21:30.")
    home["person"] = "p_frederik"
    assert len(rules.leave_time_claims([home, *records], persons, day)) == 1
