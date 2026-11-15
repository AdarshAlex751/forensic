import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.investigator import router as router_mod
from app.features.investigator.approvals import Approvals
from app.features.investigator.trace import Trace

FILE_REQUESTS = [{"id": "r1", "ask": "Pull the parking exit log.", "why": "why", "status": "pending"}]


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router_mod.router)
    monkeypatch.setattr(router_mod, "approvals", Approvals())
    monkeypatch.setattr(router_mod, "trace", Trace())
    monkeypatch.setattr(router_mod, "_load_requests", lambda: FILE_REQUESTS)
    calls = {"release": [], "rerun": []}
    monkeypatch.setattr(router_mod, "release_extra", lambda rid: calls["release"].append(rid) or {"released": ["x"]})
    monkeypatch.setattr(router_mod, "_start_rerun", lambda: calls["rerun"].append("extract") or True)
    c = TestClient(app)
    c.calls = calls
    return c


def test_health_still_works(client):
    assert client.get("/api/investigator/health").status_code == 200


def test_get_requests_returns_file_records_with_live_status(client):
    assert client.get("/api/investigator/requests").json()[0]["status"] == "pending"
    client.post("/api/investigator/requests/r1/approve")
    assert client.get("/api/investigator/requests").json()[0]["status"] == "approved"


def test_approve_releases_the_evidence_then_starts_the_rerun(client):
    r = client.post("/api/investigator/requests/r1/approve")
    assert r.status_code == 200
    assert r.json() == {"request_id": "r1", "status": "approved", "released": ["x"], "rerun": "started"}
    assert client.calls == {"release": ["r1"], "rerun": ["extract"]}


def test_approve_unknown_request_is_404_and_does_nothing(client):
    r = client.post("/api/investigator/requests/r404/approve")
    assert r.status_code == 404 and "r404" in r.json()["detail"]
    assert client.calls == {"release": [], "rerun": []}


def test_approve_reports_when_a_run_is_already_in_progress(client, monkeypatch):
    monkeypatch.setattr(router_mod, "_start_rerun", lambda: False)
    assert client.post("/api/investigator/requests/r1/approve").json()["rerun"] == "already running"


def _status(client):
    return client.get("/api/investigator/requests").json()[0]["status"]


def test_approve_reports_what_was_released(client):
    assert client.post("/api/investigator/requests/r1/approve").json()["released"] == ["x"]


def test_a_failing_release_is_reported_and_the_request_stays_pending(client, monkeypatch):
    def boom(rid):
        raise RuntimeError("disk full")

    monkeypatch.setattr(router_mod, "release_extra", boom)
    r = client.post("/api/investigator/requests/r1/approve")
    assert r.status_code == 502 and "disk full" in r.json()["detail"]
    assert _status(client) == "pending"
    assert client.calls["rerun"] == []


def test_a_release_of_nothing_is_reported_and_the_request_stays_pending(client, monkeypatch):
    monkeypatch.setattr(router_mod, "release_extra", lambda rid: {"released": []})
    r = client.post("/api/investigator/requests/r1/approve")
    assert r.status_code == 502 and "nothing was released" in r.json()["detail"].lower()
    assert _status(client) == "pending"
    assert client.calls["rerun"] == []


def test_a_release_result_without_a_released_list_counts_as_nothing_released(client, monkeypatch):
    monkeypatch.setattr(router_mod, "release_extra", lambda rid: None)
    assert client.post("/api/investigator/requests/r1/approve").status_code == 502


def test_a_failed_release_can_be_retried_and_then_succeeds(client, monkeypatch):
    monkeypatch.setattr(router_mod, "release_extra", lambda rid: {"released": []})
    assert client.post("/api/investigator/requests/r1/approve").status_code == 502
    monkeypatch.setattr(router_mod, "release_extra", lambda rid: {"released": ["access/parking_exit.csv"]})
    assert client.post("/api/investigator/requests/r1/approve").status_code == 200
    assert _status(client) == "approved"


def test_release_calls_the_evidence_slice_function_when_it_exists(monkeypatch):
    import sys
    import types

    seen = []
    fake = types.ModuleType("app.features.evidence.release")
    fake.release_extra_evidence = lambda rid: seen.append(rid) or {"released": ["access/parking_exit.csv"]}
    monkeypatch.setitem(sys.modules, "app.features.evidence.release", fake)
    assert router_mod.release_extra("r1") == {"released": ["access/parking_exit.csv"]}
    assert seen == ["r1"]


def test_release_falls_back_to_the_stub_when_the_evidence_function_is_missing(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "app.features.evidence.release", None)  # makes the import raise ImportError
    out = router_mod.release_extra("r1")
    assert out["released"] == [] and out["stub"] is True


def test_stream_replays_a_finished_trace_as_sse_and_ends(client):
    router_mod.trace.emit("lead", "plan", "Planning")
    router_mod.trace.emit("lead", "done", "Finished")
    r = client.get("/api/investigator/stream")
    assert r.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert [e["stage"] for e in events] == ["plan", "done"]
    assert {"seq", "agent", "stage", "msg", "todos"} <= set(events[0])


def test_the_rerun_starts_from_ingest_so_released_events_land_in_events_json(monkeypatch):
    from app import pipeline

    seen = []
    monkeypatch.setattr(pipeline, "start", lambda stage: seen.append(stage) or True)
    assert router_mod._start_rerun() is True
    assert seen == ["ingest"]


# ---------- upload the requested file (replaces Approve in the UI) ----------

PARKING = b"timestamp,lane,permit_id,plate,direction\n2026-03-04T18:44:00-05:00,EXIT-1,P-2088,W26-VCU,OUT\n"


def _evidence_upload(monkeypatch, fn):
    from app.features.evidence import release
    monkeypatch.setattr(release, "add_uploaded_evidence", fn)


def test_upload_adds_the_file_approves_and_starts_the_rerun(client, monkeypatch):
    seen = []
    _evidence_upload(monkeypatch, lambda rid, name, data: seen.append((rid, name, data))
                     or {"released": ["access/parking_exit.csv"], "file": "access/parking_exit.csv"})
    r = client.post("/api/investigator/requests/r1/upload", files={"file": ("parking.csv", PARKING, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json() == {"request_id": "r1", "status": "approved", "released": ["access/parking_exit.csv"],
                        "file": "access/parking_exit.csv", "rerun": "started"}
    assert seen == [("r1", "parking.csv", PARKING)] and client.calls["rerun"] == ["extract"]
    assert client.get("/api/investigator/requests").json()[0]["status"] == "approved"


def test_a_rejected_upload_is_400_and_the_request_stays_pending(client, monkeypatch):
    from app.features.evidence.release import UploadRejected

    def reject(rid, name, data):
        raise UploadRejected("This file is not a parking exit log.")
    _evidence_upload(monkeypatch, reject)
    r = client.post("/api/investigator/requests/r1/upload", files={"file": ("x.csv", b"a,b\n", "text/csv")})
    assert r.status_code == 400 and "not a parking exit log" in r.json()["detail"]
    assert client.get("/api/investigator/requests").json()[0]["status"] == "pending"
    assert client.calls["rerun"] == []


def test_upload_for_an_unknown_request_is_404(client):
    r = client.post("/api/investigator/requests/nope/upload", files={"file": ("p.csv", PARKING, "text/csv")})
    assert r.status_code == 404
