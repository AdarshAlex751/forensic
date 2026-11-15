"""Evidence slice routes: case upload, upload removal, status and evidence release."""
from __future__ import annotations

import shutil
import stat
import tempfile
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, UploadFile

from app.features.evidence import release
from app.features.evidence.ingest import paths

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

MAX_UPLOAD_BYTES = 100 * 1024 * 1024        # the zip itself
MAX_UNPACKED_BYTES = 1024 * 1024 * 1024     # zip-bomb guard: total uncompressed size
MAX_ENTRIES = 20_000
CHUNK = 1024 * 1024


@router.get("/health")
def health() -> dict[str, str]:
    return {"slice": "evidence", "status": "placeholder"}


def _bad(msg: str) -> HTTPException:
    return HTTPException(status_code=400, detail=msg)


def _save_upload(file: UploadFile, dest: Path) -> None:
    """Copy the upload to disk in chunks, enforcing the size limit."""
    total = 0
    with dest.open("wb") as out:
        while True:
            chunk = file.file.read(CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise _bad(f"zip is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
            out.write(chunk)
    if total == 0:
        raise _bad("uploaded file is empty")


def _check_members(zf: zipfile.ZipFile) -> tuple[str, list[zipfile.ZipInfo]]:
    """Validate every entry (zip-slip, symlinks, size) and return (top-level folder, file entries)."""
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise _bad(f"zip has more than {MAX_ENTRIES} entries")
    tops: set[str] = set()
    files: list[zipfile.ZipInfo] = []
    unpacked = 0
    for info in infos:
        name = info.filename
        if not name or "\\" in name or ":" in name or "\x00" in name:
            raise _bad(f"unsafe path in zip: {name!r}")
        if name.startswith("/"):
            raise _bad(f"absolute path in zip: {name!r}")
        parts = PurePosixPath(name).parts
        if any(p in ("..", ".") for p in name.rstrip("/").split("/")):
            raise _bad(f"unsafe path in zip: {name!r}")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise _bad(f"symlink in zip: {name!r}")
        if info.is_dir():
            tops.add(parts[0])
            continue
        if len(parts) < 2:
            raise _bad(f"file outside the case folder: {name!r}; zip must contain one folder like CASE-1010F/")
        tops.add(parts[0])
        unpacked += info.file_size
        if unpacked > MAX_UNPACKED_BYTES:
            raise _bad("zip unpacks to more than 1 GB")
        files.append(info)
    if len(tops) != 1:
        found = ", ".join(sorted(tops)) or "none"
        raise _bad(f"zip must contain exactly one top-level folder (found: {found})")
    top = next(iter(tops))
    if not any(i.filename == f"{top}/manifest.csv" for i in files):
        raise _bad(f"{top}/manifest.csv is missing")
    return top, files


def _extract(zf: zipfile.ZipFile, files: list[zipfile.ZipInfo], dest: Path) -> None:
    root = dest.resolve()
    for info in files:
        target = (dest / info.filename).resolve()
        if root not in target.parents:
            raise _bad(f"unsafe path in zip: {info.filename!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as out:
            shutil.copyfileobj(src, out, CHUNK)


def _rename_with_retry(src: Path, dst: Path, attempts: int = 12, delay_s: float = 0.25) -> None:
    """Path.rename, retried on PermissionError. On Windows a folder of freshly written files is often held for a moment by
    antivirus or the indexer, and the rename answers WinError 5 until they let go."""
    for attempt in range(attempts):
        try:
            src.rename(dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay_s)


def _swap_in(new_dir: Path, final: Path) -> None:
    """Replace final with new_dir (rename old aside first; Windows cannot replace a directory).

    A rename that stays locked falls back to copying the folder into place, so a transient lock never turns an upload
    into a 500. The previous case is restored if nothing works."""
    old = None
    if final.exists():
        old = final.with_name(f".old-{uuid.uuid4().hex}")
        _rename_with_retry(final, old)
    try:
        try:
            _rename_with_retry(new_dir, final)
        except OSError:
            shutil.copytree(new_dir, final)  # still locked for renaming: copying only reads, so it gets through
    except OSError:
        shutil.rmtree(final, ignore_errors=True)  # drop a half-copied folder before putting the old case back
        if old is not None:
            old.rename(final)
        raise
    if old is not None:
        shutil.rmtree(old, ignore_errors=True)


def _start_pipeline() -> bool:
    from app import pipeline  # lazy: pipeline imports the registry, which imports this router

    return bool(pipeline.start("ingest"))


@router.post("/upload")
def upload(file: UploadFile) -> dict:
    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise _bad("upload must be a .zip file")
    work = paths.WORK_DIR
    work.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".upload-", dir=work))
    try:
        zip_path = staging / "upload.zip"
        _save_upload(file, zip_path)
        if not zipfile.is_zipfile(zip_path):
            raise _bad("upload is not a valid zip file")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                top, files = _check_members(zf)
                unpack = staging / "unpacked"
                unpack.mkdir()
                _extract(zf, files, unpack)
        except zipfile.BadZipFile as exc:
            raise _bad(f"zip is corrupt: {exc}") from exc
        zip_path.unlink()
        _swap_in(unpack / top, paths.UPLOADED_CASE_DIR)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    release.reset_released()  # a new case starts with nothing released
    started = _start_pipeline()
    case_id = top[5:] if top.upper().startswith("CASE-") else top
    return {
        "case_id": case_id,
        "filename": filename,
        "files": len(files),
        "case_dir": paths.UPLOADED_CASE_DIR.relative_to(paths.EVIDENCE).as_posix(),
        "pipeline_started": started,
        **({} if started else {"message": "a pipeline run is already in progress; rerun when it finishes"}),
    }


@router.delete("/upload")
def delete_upload() -> dict:
    existed = paths.UPLOADED_CASE_DIR.exists()
    if existed:
        shutil.rmtree(paths.UPLOADED_CASE_DIR)
    release.reset_released()
    return {"removed": existed, "case_dir": _rel(paths.active_case_dir())}


def _rel(p: Path) -> str:
    try:
        return p.relative_to(paths.EVIDENCE).as_posix()
    except ValueError:
        return p.as_posix()


@router.get("/status")
def status() -> dict:
    active = paths.active_case_dir()
    return {
        "case_dir": _rel(active),
        "uploaded": active == paths.UPLOADED_CASE_DIR,
        "released": release.released_files(),
    }


@router.post("/release/{request_id}")
def release_route(request_id: str) -> dict:
    return release.release_extra_evidence(request_id)
