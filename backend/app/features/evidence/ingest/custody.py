"""Chain of custody: hash every case file and compare it with manifest.csv (stage 1, the MISMATCH stamp)."""
from __future__ import annotations

import csv
from pathlib import Path

from .base import sha256_file

PARSER_BY_SUFFIX = {".csv": "csv", ".txt": "text", ".mbox": "mbox", ".json": "slack_json", ".pdf": "pdf",
                    ".jpg": "image", ".jpeg": "image", ".png": "image"}


def manifest_hashes(case_dir: Path) -> dict[str, str]:
    p = case_dir / "manifest.csv"
    if not p.is_file():
        return {}
    with open(p, encoding="utf-8", newline="") as f:
        return {r["filename"]: r["sha256"] for r in csv.DictReader(f)}


def evidence_row(rel: str, path: Path, manifest: dict[str, str], records: int) -> dict:
    sha = sha256_file(path)
    expected = manifest.get(rel)
    return {
        "file": rel,
        "sha256": sha,
        "manifest_sha256": expected,
        "manifest_match": expected is not None and sha == expected,
        "parser": PARSER_BY_SUFFIX.get(path.suffix.lower(), "text"),
        "records": records,
    }
