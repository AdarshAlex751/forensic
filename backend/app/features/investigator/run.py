"""Investigator slice entry point: run(case_id). The only thing pipeline.py calls.

1. Verify every claim against the real case files (stage 8).
2. Hand only VERIFIED events and contradictions to the lead investigator (stage 9).
3. Write data/investigator/{verification,hypotheses,requests,notes}.json (real mode only).

USE_REAL_INVESTIGATOR=false (the default): write nothing; shared merge.load() serves data/investigator/fake/.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.features.investigator import inputs
from app.features.investigator.agent_tools import ToolContext
from app.features.investigator.approvals import approvals
from app.features.investigator.lead_agent import LeadResult, investigate
from app.features.investigator.trace import Trace, trace
from app.features.investigator.verifier import verify_contradictions, verify_events
from app.shared import schema
from app.shared.config import DATA_DIR, use_real

log = logging.getLogger(__name__)

OUT_DIR: Path = DATA_DIR / "investigator"
_state: dict[str, int | None] = {"baseline_events": None}  # event count before any approval, to detect ingestion


# thin seams so tests can swap them
def _use_real() -> bool:
    return use_real("investigator")


def _load_inputs(include_extra: bool) -> inputs.Inputs:
    return inputs.load_inputs(include_extra=include_extra)


def _case_files() -> inputs.CaseFiles:
    return inputs.CaseFiles()


def _withheld_sources() -> list[str]:
    return inputs.withheld_sources()


def _investigate(ctx: ToolContext, tr: Trace) -> LeadResult:
    return investigate(ctx, trace=tr)


def _write(name: str, data: Any) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_DIR / f".{name}.tmp"
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, OUT_DIR / name)


def run(case_id: str) -> None:
    trace.reset()
    if not _use_real():
        log.info("USE_REAL_INVESTIGATOR is false; serving data/investigator/fake/ (nothing written)")
        trace.emit("lead", "done", "Fake mode: showing the stored demo result")
        return

    files = _case_files()
    if not files.root.is_dir():
        log.error("case folder %s not found; skipping verification so we do not reject every claim", files.root)
        trace.emit("verifier", "verify", "Case folder not found; verification skipped")
        trace.emit("lead", "done", "Nothing to investigate until the case files exist")
        return

    approvals.reset_pending()  # only the human's decisions carry over; the agents re-raise what is still justified
    trace.emit("verifier", "verify", "Re-checking every claim against the case files")
    snap = _load_inputs(include_extra=approvals.any_approved())
    result = verify_events(snap.events, snap.evidence, files)
    result = verify_contradictions(snap.contradictions, result, known_event_ids={e.id for e in snap.events})
    trace.emit("verifier", "verify", f"{result.verified} of {result.claims} claims verified, {len(result.rejected)} rejected")

    verified_ids = set(result.verified_event_ids)
    verified_contradictions = [c for c in snap.contradictions
                               if c.id not in {r.claim.split(":")[0] for r in result.rejected}]
    ctx = ToolContext(
        events=[e for e in snap.events if e.id in verified_ids],
        persons=snap.persons,
        contradictions=verified_contradictions,
        edges=snap.edges,
        approvals=approvals,
        requestable=_withheld_sources(),
    )

    if _state["baseline_events"] is None and not approvals.any_approved():
        _state["baseline_events"] = len(snap.events)
    grew = _state["baseline_events"] is not None and len(snap.events) > _state["baseline_events"]
    if approvals.any_approved() and (snap.extra_event_ids or grew):
        approvals.mark_ingested()

    lead = _investigate(ctx, trace)
    if approvals.any_approved() and (snap.extra_event_ids or grew):
        approvals.mark_ingested()  # a request made during this run cannot be ingested yet; this is a no-op then

    schema.Verification.model_validate(result.to_json())
    _write("verification.json", result.to_json())
    _write("hypotheses.json", [schema.Hypothesis.model_validate(h).model_dump() for h in lead.hypotheses])
    _write("notes.json", [schema.Note.model_validate(n).model_dump() for n in lead.notes])
    _write("requests.json", [schema.Request.model_validate(r).model_dump() for r in approvals.overlay(lead.requests)])
    for w in lead.warnings:
        log.warning("lead investigator: %s", w)
