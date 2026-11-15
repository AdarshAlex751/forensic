"""Ingest a case folder (plus any released extra evidence) into events and evidence rows.

ingest(case_dir, extra_dir, released) -> IngestResult
  1. custody: hash every file in case_dir and compare with manifest.csv
  2. parse: run the registered parser on every file (registry.py)
  3. order: events sorted by (t, source.file, source.line, type), ids e1.. ; events from released extra files are
     numbered after the case events (append-only, as after an approval)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .base import FileCtx, load_devices, sha256_file
from .custody import evidence_row, manifest_hashes
from .registry import parser_for


@dataclass
class IngestResult:
    events: list[dict]
    evidence: list[dict]
    problems: list[str] = field(default_factory=list)   # files that failed to parse (reported, not raised)


def _files(base: Path) -> list[str]:
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())


def _order(e: dict) -> tuple:
    return (e["t"], e["source"]["file"], e["source"]["line"], e["type"])


def _parse_dir(base: Path, rels: list[str], case_dir: Path, devices: dict, problems: list[str],
               progress: Callable[[str], None] | None) -> tuple[list[dict], dict[str, int]]:
    events: list[dict] = []
    counts: dict[str, int] = {}
    for rel in rels:
        fn = parser_for(rel)
        if progress:
            progress(rel)
        if fn is None:
            counts[rel] = 0
            continue
        ctx = FileCtx(rel=rel, path=base / rel, sha256=sha256_file(base / rel), case_dir=case_dir, devices=devices)
        try:
            got = fn(ctx)
        except Exception as exc:  # one bad file must not stop the rest of the case
            problems.append(f"{rel}: {type(exc).__name__}: {exc}")
            got = []
        counts[rel] = len(got)
        events.extend(got)
    return events, counts


def ingest(case_dir: Path, extra_dir: Path | None = None, released: list[str] | None = None,
           progress: Callable[[str], None] | None = None) -> IngestResult:
    case_dir = Path(case_dir)
    devices = load_devices(case_dir)
    problems: list[str] = []
    manifest = manifest_hashes(case_dir)

    rels = _files(case_dir)
    events, counts = _parse_dir(case_dir, rels, case_dir, devices, problems, progress)
    evidence = [evidence_row(r, case_dir / r, manifest, counts[r]) for r in rels]

    extra_events: list[dict] = []
    for rel in sorted(released or []):
        if extra_dir is None or not (Path(extra_dir) / rel).is_file():
            problems.append(f"released file not found in extra/: {rel}")
            continue
        got, c = _parse_dir(Path(extra_dir), [rel], case_dir, devices, problems, progress)
        extra_events.extend(got)
        evidence.append(evidence_row(rel, Path(extra_dir) / rel, manifest, c[rel]))

    events.sort(key=_order)
    extra_events.sort(key=_order)
    for i, e in enumerate(events + extra_events, start=1):
        e["id"] = f"e{i}"
    return IngestResult(events=events + extra_events, evidence=evidence, problems=problems)
