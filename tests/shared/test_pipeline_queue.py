"""A rerun asked for during a run is queued, not dropped (parking log uploaded while the case-upload run is going)."""
import threading
import time

from app import pipeline


def test_rerun_requested_during_a_run_is_queued_and_runs_after(monkeypatch):
    gate, calls = threading.Event(), []

    def slow(case_id):
        calls.append("evidence")
        if len(calls) == 1:
            gate.wait(5)  # hold the first run open while the second request comes in

    monkeypatch.setattr(pipeline, "SLICES", [("evidence", slow, None, ["ingest", "extract"])])
    monkeypatch.setattr(pipeline, "STAGES", ["ingest", "extract"])
    monkeypatch.setattr(pipeline, "state", {"seq": 0, "running": False, "stage": None, "pct": 0, "msg": "idle"})
    monkeypatch.setattr(pipeline, "_pending", None)

    assert pipeline.start("ingest") is True
    while not calls:
        time.sleep(0.01)
    assert pipeline.start("ingest") is False  # in progress: queued
    assert pipeline.state["running"] is True
    gate.set()
    deadline = time.monotonic() + 10
    while pipeline.state["running"] and time.monotonic() < deadline:
        time.sleep(0.02)
    assert calls == ["evidence", "evidence"] and pipeline.state["msg"] == "done"


def test_a_failing_slice_does_not_leave_the_pipeline_running(monkeypatch):
    def boom(case_id):
        raise RuntimeError("parser crashed")

    monkeypatch.setattr(pipeline, "SLICES", [("evidence", boom, None, ["ingest", "extract"])])
    monkeypatch.setattr(pipeline, "STAGES", ["ingest", "extract"])
    monkeypatch.setattr(pipeline, "state", {"seq": 0, "running": False, "stage": None, "pct": 0, "msg": "idle"})
    monkeypatch.setattr(pipeline, "_pending", None)
    monkeypatch.setattr(threading, "excepthook", lambda args: None)  # the thread's error is expected here
    assert pipeline.start("ingest") is True
    deadline = time.monotonic() + 10
    while pipeline.state["running"] and time.monotonic() < deadline:
        time.sleep(0.02)
    assert pipeline.state["running"] is False and pipeline.state["msg"].startswith("failed")
