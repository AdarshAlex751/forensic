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


def _run(from_stage: str) -> None:
    from_idx = STAGES.index(from_stage)
    for i, (name, run, _, stages) in enumerate(SLICES):
        if not _should_run(stages, from_idx):
            continue
        _publish(stage=(stages or [name])[0], pct=int(100 * i / len(SLICES)), msg=f"running {name}")
        run(CASE_ID)
        time.sleep(0.2)  # placeholder pacing so progress is visible
    _publish(running=False, stage="analyze", pct=100, msg="done")


def start(from_stage: str = "ingest") -> bool:
    """Start a run from a stage on. Returns False if a run is already in progress."""
    if from_stage not in STAGES:
        raise ValueError(f"unknown stage {from_stage!r}; expected one of {STAGES}")
    with _lock:
        if state["running"]:
            return False
        state["running"] = True
    _publish(msg="starting", pct=0)
    threading.Thread(target=_run, args=(from_stage,), daemon=True).start()
    return True
