"""Release of withheld evidence (data/evidence/extra/) once an investigator request is approved.

Person 4's approve route calls release_extra_evidence(request_id) and then reruns the pipeline.
Any request id releases everything currently in EXTRA_DIR. The released set is recorded in
RELEASED_FILE so the ingest stage (and GET /api/evidence/status) can see it.

Paths are read from the paths module at call time, so tests can monkeypatch
app.features.evidence.ingest.paths.EXTRA_DIR / RELEASED_FILE to tmp_path.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from app.features.evidence.ingest import paths


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


def released_files() -> list[str]:
    """The released paths (relative to EXTRA_DIR, forward slashes); empty if nothing was released."""
    return sorted(_read(paths.RELEASED_FILE)["released"])


def reset_released() -> None:
    """Forget every release (fresh demo run or newly uploaded case)."""
    try:
        paths.RELEASED_FILE.unlink()
    except FileNotFoundError:
        pass
