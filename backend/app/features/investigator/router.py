import asyncio
import json
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.features.investigator.approvals import approvals
from app.features.investigator.trace import trace
from app.shared.merge import load as _merge_load

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/investigator", tags=["investigator"])


def _load_requests() -> list[dict[str, Any]]:
    """The requests the pipeline currently serves (fake/ or real, per USE_REAL_INVESTIGATOR)."""
    try:
        data = _merge_load("investigator", "requests.json")
        return data if isinstance(data, list) else []
    except Exception as exc:  # noqa: BLE001 - an unreadable file means "no known requests", not a 500
        log.warning("cannot read requests.json (%s)", exc)
        return []


def release_extra(request_id: str) -> dict[str, Any]:
    """Ask the evidence slice (Person 1) to release the withheld files for an approved request.

    Person 1 provides `release_extra_evidence(request_id)` in app.features.evidence.release. Until it exists this is a
    stub, so approval still works and the rerun still starts; the new evidence just does not appear yet.
    """
    try:
        from app.features.evidence.release import release_extra_evidence  # type: ignore[import-not-found]
    except ImportError:
        log.warning("evidence.release.release_extra_evidence not provided yet; stub used for %s", request_id)
        return {"released": [], "stub": True}
    return release_extra_evidence(request_id)


def _start_rerun() -> bool:
    from app import pipeline  # lazy: pipeline imports the registry, which imports this router

    return pipeline.start("extract")


@router.get("/health")
def health() -> dict[str, str]:
    return {"slice": "investigator", "status": "ok"}


@router.get("/requests")
def list_requests() -> list[dict[str, Any]]:
    """Requests with their current status (approvals live in memory, so findings.json can lag behind a click)."""
    return approvals.overlay(_load_requests())


@router.post("/requests/{request_id}/approve")
def approve(request_id: str) -> dict[str, Any]:
    """Approve a request: release its withheld evidence, then rerun the pipeline.

    If nothing was released (the release function failed or returned nothing) the approval is undone and a 502 says
    why, so the card never shows "approved" for evidence that did not arrive.
    """
    approvals.sync(_load_requests())
    if approvals.approve(request_id) is None:
        raise HTTPException(404, f"unknown request {request_id}")
    try:
        result = release_extra(request_id)
        released = list(result.get("released") or []) if isinstance(result, dict) else []
        problem = None if released else "Nothing was released: the evidence slice returned no files for this request."
    except Exception as exc:  # noqa: BLE001 - reported to the caller below
        released, problem = [], f"Releasing the evidence failed: {exc}"
        log.error("releasing extra evidence for %s failed: %s", request_id, exc)
    if problem:
        approvals.revoke(request_id)
        log.warning("approval of %s undone: %s", request_id, problem)
        raise HTTPException(502, problem)
    started = _start_rerun()
    return {"request_id": request_id, "status": "approved", "released": released,
            "rerun": "started" if started else "already running"}


async def _trace_stream() -> AsyncIterator[str]:
    last = 0
    idle_ticks = 0
    while True:
        fresh = trace.snapshot(after=last)
        for ev in fresh:
            last = ev["seq"]
            idle_ticks = 0
            yield f"data: {json.dumps(ev)}\n\n"
        if trace.is_done() and not trace.snapshot(after=last):
            return
        idle_ticks += 1
        if idle_ticks % 60 == 0:  # about every 15 s, keep proxies from closing an idle stream
            yield ": keep-alive\n\n"
        await asyncio.sleep(0.25)


@router.get("/stream")
async def stream() -> StreamingResponse:
    """Server-Sent Events: what the lead investigator and its subagents are doing, in order."""
    return StreamingResponse(_trace_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
