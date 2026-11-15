"""Evidence slice entry point: run(case_id) ingests the active case and writes data/evidence/{events,evidence,case}.json.

The active case is the uploaded one (data/evidence/work/CASE-1010F/) if a zip was uploaded, otherwise the built-in
data/evidence/CASE-1010F/. Extra evidence is parsed only once the investigator has uploaded it (release.py, saved
under data/evidence/work/extra/), and its events are numbered after the case events.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes((json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    os.replace(tmp, path)


def run(case_id: str) -> None:
    from .ingest import doc_parsers, paths
    from .ingest.ingest import ingest
    from .release import released_files

    case_dir = paths.active_case_dir()
    result = ingest(case_dir, paths.EXTRA_DIR, released_files())
    for p in result.problems:
        log.warning("ingest: %s", p)
    _write_json(paths.OUT_EVENTS, result.events)
    _write_json(paths.OUT_EVIDENCE, result.evidence)
    _write_json(paths.OUT_CASE, doc_parsers.brief_case_info(case_dir))
    log.info("ingest %s: %d events, %d files, %d problems from %s", case_id, len(result.events),
             len(result.evidence), len(result.problems), case_dir)
