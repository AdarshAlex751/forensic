import json
import sys
import threading
import time
import types
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.feedback import check, contract
from app.features.feedback.contract import KIND_LABELS, MAX_QUESTIONS

NOW = datetime(2026, 3, 9, 14, 30, 5)


def make_bundle():
    return {
        "case": {"id": "1010F", "title": "Test case"},
        "contradictions": [
            {"id": "c1", "kind": "presence", "title": "Badge vs camera", "events": ["e1", "e2"]},
            {"id": "c2", "kind": "custody", "title": "Log gap", "events": ["e3"]},
        ],
        "persons": [
            {"id": "p_a", "name": "Ana", "role": "staff"},
            {"id": "p_b", "name": "Ben", "role": "guard"},
        ],
        "events": {
            "e1": {"t": "2026-03-01T09:00:00-05:00", "type": "badge", "person": "p_a", "file": "badge.csv",
                   "line": 4, "quote": "Ana badged into R2"},
            "e2": {"t": "2026-03-01T09:05:00-05:00", "type": "camera", "person": "p_a", "file": "cam.csv",
                   "line": 9, "quote": "R5 camera shows Ana"},
            "e3": {"t": "2026-03-01T10:00:00-05:00", "type": "log", "person": "p_b", "file": "sec.csv",
                   "line": 12, "quote": "log rotated"},
            "e4": {"t": "2026-03-01T11:00:00-05:00", "type": "chat", "person": "p_b", "file": "chat.txt",
                   "line": 2, "quote": "see you at noon"},
        },
    }


def q(question="Could the badge clock be offset from the camera clock?", kind="alternative",
      why="Both records come from different systems.", cites=None, focus=None):
    return {"kind": kind, "question": question, "why": why,
            "cites": {"events": ["e1", "e2"], "contradictions": ["c1"], "persons": []} if cites is None else cites,
            "focus": focus}


def raw(*questions):
    return {"questions": list(questions), "source": "mock", "model": "test-model", "error": None}


def reasons(fb):
    return [r["reason"] for r in fb["rejected"]]


def test_good_question_kept_with_quotes():
    b = make_bundle()
    fb = check.validate(raw(q(focus="c1")), b, now=NOW)
    assert fb["counts"] == {"asked": 1, "kept": 1, "rejected": 0}
    k = fb["questions"][0]
    assert k["id"] == "q1"
    assert k["kind_label"] == KIND_LABELS["alternative"]
    assert k["focus"] == "c1"
    assert k["quotes"] == [
        {"event": "e1", "file": "badge.csv", "line": 4, "quote": "Ana badged into R2"},
        {"event": "e2", "file": "cam.csv", "line": 9, "quote": "R5 camera shows Ana"},
    ]
    assert fb["case_id"] == "1010F"
    assert fb["source"] == "mock" and fb["model"] == "test-model"
    assert fb["generated_at"] == "2026-03-09T14:30:05-05:00"
    assert fb["input_fingerprint"] == check.bundle_fingerprint(b)
    assert len(fb["input_fingerprint"]) == 64


@pytest.mark.parametrize("bad, expected", [
    (q(kind="verdict"), "unknown kind"),
    (q(question="   "), "empty question"),
    (q(question="The clocks may differ."), "does not end with '?'"),
    (q(question=" ".join(["word"] * 61) + "?"), "longer than 60 words"),
    (q(why=""), "missing 'why'"),
    ({**q(), "cites": None}, "missing cites"),
    (q(cites={"events": [], "contradictions": [], "persons": []}), "cites no ids"),
    (q(cites={"events": ["e99"]}), "cites unknown events id(s): e99"),
    (q(cites={"contradictions": ["c9"]}), "cites unknown contradictions id(s): c9"),
    (q(cites={"persons": ["p_zz"]}), "cites unknown persons id(s): p_zz"),
    (q(question="Is Ana the culprit here?"), "forbidden phrase 'culprit' in question"),
    (q(question="Is Ben GUILTY of this?"), "forbidden phrase 'guilty' in question"),
    (q(why="Ana is   lying about R2."), "forbidden phrase 'is lying' in why"),
    (q(why="Ben was responsible for the logs."), "forbidden phrase 'responsible for' in why"),
    ("just a string", "not an object"),
])
def test_rejections(bad, expected):
    fb = check.validate(raw(bad), make_bundle(), now=NOW)
    assert fb["questions"] == []
    assert fb["counts"] == {"asked": 1, "kept": 0, "rejected": 1}
    assert expected in fb["rejected"][0]["reason"]


def test_forbidden_is_word_boundary_aware():
    # "lied" inside "applied", "framed" inside "reframed" must not trigger.
    good = q(question="Was the policy applied to the reframed timeline?", why="The supplied log is partial.")
    fb = check.validate(raw(good), make_bundle(), now=NOW)
    assert fb["counts"]["kept"] == 1, fb["rejected"]


def test_near_duplicates_rejected():
    a = q(question="Could the badge clock be offset from the camera clock?")
    b = q(question="Could the camera clock be offset from the badge clock, really?")   # Jaccard 9/10
    c = q(question="Who else had access to R2 between 09:00 and 09:05?", kind="gap")
    fb = check.validate(raw(a, b, c), make_bundle(), now=NOW)
    assert [k["id"] for k in fb["questions"]] == ["q1", "q2"]
    assert fb["questions"][1]["kind"] == "gap"
    assert reasons(fb) == ["near-duplicate of a kept question"]


def test_cap_preserves_order(monkeypatch):
    monkeypatch.setattr(check, "MAX_PER_POINT", 10**6)   # this test is about the cap, not the same-point rule
    # distinct (citations, kind) per question, so only the cap applies
    qs = [q(question=f"Does record number {i} {'x' * i} match the camera feed?", kind=check.KINDS[i % len(check.KINDS)],
            cites={"contradictions": [f"c{1 + (i // 4) % 2}"], "events": [f"e{1 + i % 4}"]})
          for i in range(MAX_QUESTIONS + 3)]
    fb = check.validate(raw(*qs), make_bundle(), now=NOW)
    assert fb["counts"] == {"asked": MAX_QUESTIONS + 3, "kept": MAX_QUESTIONS, "rejected": 3}
    assert [k["id"] for k in fb["questions"]] == [f"q{i + 1}" for i in range(MAX_QUESTIONS)]
    assert fb["questions"][0]["question"].startswith("Does record number 0 ")
    assert all("cap" in r for r in reasons(fb))


def test_focus_kept_or_nulled():
    a = q(focus="p_b")
    b = q(question="What would show the log gap was routine maintenance?", kind="confirm_or_disprove",
          cites={"contradictions": ["c2"], "events": ["e3"]}, focus="p_unknown")
    fb = check.validate(raw(a, b), make_bundle(), now=NOW)
    assert [k["focus"] for k in fb["questions"]] == ["p_b", None]


def test_quotes_capped_at_four():
    many = q(cites={"events": ["e1", "e2", "e3", "e4", "e1"]})
    fb = check.validate(raw(many), make_bundle(), now=NOW)
    assert [x["event"] for x in fb["questions"][0]["quotes"]] == ["e1", "e2", "e3", "e4"]


def test_deterministic_and_fingerprint_override():
    b = make_bundle()
    r = raw(q(), q(question="Who else had access to R2?", kind="gap"))
    assert check.validate(r, b, now=NOW) == check.validate(r, b, now=NOW)
    assert check.validate(r, b, now=NOW, fingerprint="abc")["input_fingerprint"] == "abc"
    # fingerprint ignores key order
    reordered = dict(reversed(list(b.items())))
    assert check.bundle_fingerprint(reordered) == check.bundle_fingerprint(b)


def test_write_atomic_lf_json(tmp_path):
    out = tmp_path / "sub" / "feedback.json"
    fb = check.validate(raw(q(why="Ünïcode — kept as is.")), make_bundle(), now=NOW)
    check.write(fb, out)
    data = out.read_bytes()
    assert b"\r\n" not in data
    assert "Ünïcode -".encode("utf-8") in data   # letters kept; typographic dash normalised to ASCII
    assert json.loads(data.decode("utf-8")) == fb
    assert check.load_current(out) == fb
    assert [p.name for p in out.parent.iterdir()] == ["feedback.json"]   # no temp file left behind
    check.write({**fb, "case_id": "X"}, out)
    assert check.load_current(out)["case_id"] == "X"
    assert check.load_current(tmp_path / "missing.json") is None


# ------------------------------------------------------------------ routes

@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.features.feedback.router import router
    out = tmp_path / "feedback" / "feedback.json"
    monkeypatch.setattr(contract, "OUT_FILE", out)
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    c.out = out
    return c


def test_routes(client):
    assert client.get("/api/feedback/health").json() == {"slice": "feedback", "status": "ok"}
    r = client.get("/api/feedback")
    assert r.status_code == 404 and "no feedback yet" in r.json()["detail"]
    assert client.get("/api/feedback/questions").status_code == 404

    fb = check.validate(raw(
        q(focus="c1"),
        q(question="Who else had access to R2 between 09:00 and 09:05?", kind="gap", focus="p_a"),
        q(question="Is the rotated security log a reliable source here?", kind="weak_evidence",
          cites={"events": ["e3"]}, focus="c1"),
    ), make_bundle(), now=NOW)
    check.write(fb, client.out)

    r = client.get("/api/feedback")
    assert r.status_code == 200 and r.json() == fb
    assert client.get("/api/feedback/questions").json()["count"] == 3
    assert [x["id"] for x in client.get("/api/feedback/questions", params={"kind": "gap"}).json()["questions"]] == ["q2"]
    assert [x["id"] for x in client.get("/api/feedback/questions", params={"focus": "c1"}).json()["questions"]] == ["q1", "q3"]
    both = client.get("/api/feedback/questions", params={"kind": "weak_evidence", "focus": "c1"}).json()
    assert [x["id"] for x in both["questions"]] == ["q3"]
    assert client.get("/api/feedback/questions", params={"focus": "p_b"}).json()["count"] == 0


def test_regenerate_unavailable(client, monkeypatch):
    monkeypatch.setitem(sys.modules, "app.features.feedback.run", None)   # makes the import raise ImportError
    r = client.post("/api/feedback/regenerate")
    assert r.status_code == 503 and r.json()["detail"] == "feedback run not available yet"


def test_regenerate_starts_without_blocking(client, monkeypatch):
    release, called = threading.Event(), threading.Event()
    seen = []

    def slow_run(case_id):
        seen.append(case_id)
        called.set()
        release.wait(5)

    fake = types.ModuleType("app.features.feedback.run")
    fake.run = slow_run
    monkeypatch.setitem(sys.modules, "app.features.feedback.run", fake)
    t0 = time.monotonic()
    r = client.post("/api/feedback/regenerate")
    elapsed = time.monotonic() - t0
    release.set()
    assert r.status_code == 200 and r.json() == {"started": True}
    assert elapsed < 2
    assert called.wait(2) and seen == ["1010F"]
