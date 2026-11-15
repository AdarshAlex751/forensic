"""Extra evidence uploaded by the investigator after an evidence request (e.g. the parking exit log).

Person 4's upload route calls add_uploaded_evidence(request_id, filename, data): the file is recognized by its
header, saved under EXTRA_DIR (data/evidence/work/extra/, runtime and gitignored) at the path its parser expects,
and recorded in RELEASED_FILE so the ingest stage (and GET /api/evidence/status) sees it; then the pipeline reruns.
release_extra_evidence(request_id) marks everything already uploaded as released (idempotent).

Paths are read from the paths module at call time, so tests can monkeypatch
app.features.evidence.ingest.paths.EXTRA_DIR / RELEASED_FILE to tmp_path.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from app.features.evidence.ingest import paths
from app.features.evidence.ingest.csv_parsers import PARKING_HEADER

# Header row -> path inside the case that the parser registry knows (ingest/registry.py).
UPLOADABLE = {tuple(PARKING_HEADER): "access/parking_exit.csv"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class UploadRejected(ValueError):
    """The uploaded file is not a kind of extra evidence this case can take."""


def _extra_files(extra_dir: Path) -> list[str]:
    if not extra_dir.is_dir():
        return []
    return sorted(p.relative_to(extra_dir).as_posix() for p in extra_dir.rglob("*") if p.is_file())


def _read(released_file: Path) -> dict:
    try:
        data = json.loads(released_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"released": [], "requests": []}
    if not isinstance(data, dict):
        return {"released": [], "requests": []}
    released = [x for x in data.get("released", []) if isinstance(x, str)]
    requests = [x for x in data.get("requests", []) if isinstance(x, str)]
    return {"released": released, "requests": requests}


def _write_atomic(target: Path, data: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".released-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def release_extra_evidence(request_id: str) -> dict:
    """Release all withheld evidence. Idempotent; any request id works. Returns {"released": [...]}."""
    released_file = paths.RELEASED_FILE
    current = _read(released_file)
    released = sorted(set(current["released"]) | set(_extra_files(paths.EXTRA_DIR)))
    requests = sorted(set(current["requests"]) | {str(request_id)})
    if released or released_file.exists():
        _write_atomic(released_file, {"released": released, "requests": requests})
    return {"released": released}


def _header(data: bytes) -> tuple[str, ...]:
    first = data.decode("utf-8-sig", errors="replace").splitlines()[0] if data else ""
    return tuple(col.strip().lower() for col in first.split(","))


def add_uploaded_evidence(request_id: str, filename: str, data: bytes) -> dict:
    """Save one uploaded extra-evidence file and mark it released. Returns {"released": [...], "file": <path>}.

    Raises UploadRejected for an empty, oversized or unrecognized file (nothing is saved then)."""
    if not data:
        raise UploadRejected("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected("The uploaded file is larger than 20 MB.")
    if not filename.lower().endswith(".csv"):
        raise UploadRejected("Upload the log as a .csv file.")
    rel = UPLOADABLE.get(_header(data))
    if rel is None:
        raise UploadRejected("This file is not a parking exit log (expected columns: " + ", ".join(PARKING_HEADER) + ").")
    target = paths.EXTRA_DIR / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".upload-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {**release_extra_evidence(request_id), "file": rel}


def clear_uploaded_evidence() -> None:
    """Delete every uploaded extra file (a new case starts with none)."""
    shutil.rmtree(paths.EXTRA_DIR, ignore_errors=True)


def released_files() -> list[str]:
    """The released paths (relative to EXTRA_DIR, forward slashes); empty if nothing was released."""
    return sorted(_read(paths.RELEASED_FILE)["released"])


def reset_released() -> None:
    """Forget every release (fresh demo run or newly uploaded case)."""
    try:
        paths.RELEASED_FILE.unlink()
    except FileNotFoundError:
        pass
