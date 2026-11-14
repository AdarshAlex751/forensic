"""Live agent trace: what the lead investigator and its subagents are doing. In memory, streamed over SSE."""
from __future__ import annotations

import threading
from typing import Any


class Trace:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._seq = 0
        self._todos: list[dict[str, str]] = []

    def emit(self, agent: str, stage: str, msg: str, todos: list[dict[str, str]] | None = None) -> dict[str, Any]:
        with self._lock:
            if todos is not None:
                self._todos = [dict(t) for t in todos]
            self._seq += 1
            ev = {"seq": self._seq, "agent": agent, "stage": stage, "msg": msg, "todos": [dict(t) for t in self._todos]}
            self._events.append(ev)
            return dict(ev)

    def snapshot(self, after: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self._events if e["seq"] > after]

    def is_done(self) -> bool:
        with self._lock:
            return bool(self._events) and self._events[-1]["stage"] == "done"

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._todos = []
            self._seq = 0


trace = Trace()
