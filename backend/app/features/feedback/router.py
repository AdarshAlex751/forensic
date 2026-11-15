"""Feedback routes: the critic's checked questions (data/feedback/feedback.json) and a trigger to regenerate them.
Questions point at gaps and alternatives in the analysis; they never state a verdict."""
from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException

from app.features.feedback import check, contract

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

CASE_ID = "1010F"


def _current() -> dict:
    fb = check.load_current(contract.OUT_FILE)   # read at call time so tests can point OUT_FILE elsewhere
    if fb is None:
        raise HTTPException(404, "no feedback yet: POST /api/feedback/regenerate to generate it")
    return fb


@router.get("/health")
def health() -> dict[str, str]:
    return {"slice": "feedback", "status": "ok"}


@router.get("")
def feedback() -> dict:
    return _current()


@router.get("/questions")
def questions(kind: str | None = None, focus: str | None = None) -> dict:
    """Kept questions, optionally filtered by kind and/or focus id (a contradiction or person id)."""
    qs = _current().get("questions", [])
    if kind:
        qs = [q for q in qs if q.get("kind") == kind]
    if focus:
        qs = [q for q in qs if q.get("focus") == focus]
    return {"questions": qs, "count": len(qs)}


@router.post("/regenerate")
def regenerate() -> dict:
    try:
        from app.features.feedback.run import run
    except ImportError:
        raise HTTPException(503, "feedback run not available yet")
    threading.Thread(target=run, args=(CASE_ID,), name="feedback-regenerate", daemon=True).start()
    return {"started": True}
