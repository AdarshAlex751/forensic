from app.features.investigator.trace import Trace


def test_emit_assigns_increasing_seq_and_keeps_latest_todos():
    t = Trace()
    t.emit("lead", "plan", "Planning", todos=[{"text": "a", "status": "doing"}])
    t.emit("physics", "delegate", "Checking walk times")
    snap = t.snapshot()
    assert [e["seq"] for e in snap] == [1, 2]
    assert snap[1]["todos"] == [{"text": "a", "status": "doing"}]


def test_snapshot_after_returns_only_newer_events_and_reset_clears():
    t = Trace()
    t.emit("lead", "plan", "x")
    t.emit("lead", "rank", "y")
    assert [e["msg"] for e in t.snapshot(after=1)] == ["y"]
    t.reset()
    assert t.snapshot() == []


def test_is_done_after_a_done_event():
    t = Trace()
    assert not t.is_done()
    t.emit("lead", "done", "finished")
    assert t.is_done()
