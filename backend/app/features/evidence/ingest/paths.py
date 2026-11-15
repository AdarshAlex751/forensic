"""Where the evidence slice reads and writes. Shared by run.py, the upload route and release.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = ROOT / "data" / "evidence"

BUILTIN_CASE_DIR = EVIDENCE / "CASE-1010F"       # the generated case shipped in the repo
EXTRA_DIR = EVIDENCE / "extra"                   # withheld evidence (released on approval)
WORK_DIR = EVIDENCE / "work"                     # runtime: uploaded zips are unpacked here (gitignored)
UPLOADED_CASE_DIR = WORK_DIR / "CASE-1010F"
RELEASED_FILE = EVIDENCE / "released.json"       # runtime: which extra files are released (gitignored)

# Outputs (CONTRACTS.md: Person 1 writes these)
OUT_EVENTS = EVIDENCE / "events.json"
OUT_EVIDENCE = EVIDENCE / "evidence.json"
OUT_CASE = EVIDENCE / "case.json"


def active_case_dir() -> Path:
    """The uploaded case if one was uploaded, otherwise the built-in case (so reruns and the demo always work)."""
    if (UPLOADED_CASE_DIR / "manifest.csv").is_file():
        return UPLOADED_CASE_DIR
    return BUILTIN_CASE_DIR
