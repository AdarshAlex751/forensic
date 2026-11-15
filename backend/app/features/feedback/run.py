"""Feedback slice entry point: run(case_id) writes data/feedback/feedback.json.

context.build_bundle()  ->  critic.ask(bundle)  ->  check.validate(raw, bundle)  ->  check.write(feedback)

Runs last in the pipeline (CONTRACTS.md "Pipeline order"), after analysis, so the questions always describe the
current analysis, including after released evidence. If the analysis has not changed (same bundle fingerprint) and
the last run came from Groq, the previous questions are kept instead of calling Groq again (saves the free tier and
keeps the page stable). A failing Groq call never breaks the pipeline: the critic falls back to the recorded reply.
"""
from __future__ import annotations

import logging

from . import check, context, critic

log = logging.getLogger(__name__)


def run(case_id: str, force: bool = False) -> dict:
    bundle = context.build_bundle()
    fingerprint = context.bundle_fingerprint(bundle)
    previous = check.load_current()
    if (not force and previous and previous.get("input_fingerprint") == fingerprint
            and previous.get("source") == "groq"):
        log.info("feedback %s: analysis unchanged, keeping %d questions", case_id, len(previous["questions"]))
        return previous
    raw = critic.ask(bundle)
    feedback = check.validate(raw, bundle, fingerprint=fingerprint)
    check.write(feedback)
    log.info("feedback %s: %d kept, %d rejected (source %s)", case_id, feedback["counts"]["kept"],
             feedback["counts"]["rejected"], feedback["source"])
    return feedback
