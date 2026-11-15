"""Pipeline wiring. Calls each slice's run(case_id) in order and publishes progress for SSE."""
import threading
import time
from typing import Any

from app.registry import SLICES, STAGES
from app.shared.config import CASE_ID

_lock = threading.Lock()
state: dict[str, Any] = {"seq": 0, "running": False, "stage": None, "pct": 0, "msg": "idle"}


def _publish(**changes: Any) -> None:
    with _lock:
        state.update(changes)
        state["seq"] += 1


def _should_run(stages: list[str], from_idx: int) -> bool:
    if not stages:  # scene has no UI stage; it feeds analysis, so it reruns with evidence
        return from_idx <= STAGES.index("extract")
    return STAGES.index(stages[-1]) >= from_idx


# A rerun asked for while a run is in progress (e.g. the investigator uploads the parking log while the case-upload
# run is still going). It runs right after the current one, from the earliest stage asked for, so new evidence is
# never dropped; `running` stays true until the queued run is done too, so the UI waits for the run that uses it.
_pending: str | None = None


def _run_once(from_stage: str) -> None:
    from_idx = STAGES.index(from_stage)
    for i, (name, run, _, stages) in enumerate(SLICES):
        if not _should_run(stages, from_idx):
            continue
        _publish(stage=(stages or [name])[0], pct=int(100 * i / len(SLICES)), msg=f"running {name}")
        run(CASE_ID)
        time.sleep(0.2)  # placeholder pacing so progress is visible


def _run(from_stage: str) -> None:
    global _pending
    msg = "done"
    try:
        while True:
            _run_once(from_stage)
            with _lock:
                nxt, _pending = _pending, None
            if nxt is None:
                break
            from_stage = nxt
            _publish(msg="starting the queued rerun with the new evidence", pct=0)
    except Exception as exc:  # a failing slice must not leave the pipeline "running" forever
        msg = f"failed: {exc}"
        with _lock:
            _pending = None
        raise
    finally:
        _publish(running=False, stage="analyze", pct=100, msg=msg)


def start(from_stage: str = "ingest") -> bool:
    """Start a run from a stage on. Returns True if it started now. If a run is already in progress, returns False and
    queues the rerun: it starts as soon as the current run ends (from the earliest stage requested)."""
    global _pending
    if from_stage not in STAGES:
        raise ValueError(f"unknown stage {from_stage!r}; expected one of {STAGES}")
    with _lock:
        if state["running"]:
            if _pending is None or STAGES.index(from_stage) < STAGES.index(_pending):
                _pending = from_stage
            return False
        state["running"] = True
    _publish(msg="starting", pct=0)
    threading.Thread(target=_run, args=(from_stage,), daemon=True).start()
    return True
