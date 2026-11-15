"""Release of withheld evidence and the case upload routes. All paths point at tmp_path."""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import pipeline  # noqa: E402
from app.features.evidence import release  # noqa: E402
from app.features.evidence.ingest import paths  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def ev(tmp_path, monkeypatch):
    """Point every evidence path at tmp_path; stub the pipeline so no run happens."""
    evidence = tmp_path / "evidence"
    builtin = evidence / "CASE-1010F"
    builtin.mkdir(parents=True)
    (builtin / "manifest.csv").write_text("path\n", encoding="utf-8")
    extra = evidence / "extra"
    (extra / "access").mkdir(parents=True)
    (extra / "access" / "parking_exit.csv").write_text("a,b\n", encoding="utf-8")
    work = evidence / "work"
    monkeypatch.setattr(paths, "EVIDENCE", evidence)
    monkeypatch.setattr(paths, "BUILTIN_CASE_DIR", builtin)
    monkeypatch.setattr(paths, "EXTRA_DIR", extra)
    monkeypatch.setattr(paths, "WORK_DIR", work)
    monkeypatch.setattr(paths, "UPLOADED_CASE_DIR", work / "CASE-1010F")
    monkeypatch.setattr(paths, "RELEASED_FILE", evidence / "released.json")
    calls: list[str] = []
    monkeypatch.setattr(pipeline, "start", lambda stage="ingest": calls.append(stage) or True)
    return {"root": evidence, "builtin": builtin, "extra": extra, "work": work, "calls": calls}


@pytest.fixture
def client():
    return TestClient(app)


def make_zip(entries: dict[str, bytes | None], symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            if data is None:
                zf.writestr(zipfile.ZipInfo(name), b"")
            else:
                zf.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (0o120777 << 16)
            zf.writestr(info, "../../etc/passwd")
    return buf.getvalue()


GOOD = {
    "CASE-1010F/": None,
    "CASE-1010F/manifest.csv": b"path,sha256\n",
    "CASE-1010F/access/badge.csv": b"t,who\n",
    "CASE-1010F/docs/memo.txt": b"hello\n",
}


def post_zip(client, data: bytes, name: str = "case.zip"):
    return client.post("/api/evidence/upload", files={"file": (name, data, "application/zip")})


# ---------------------------------------------------------------- release

def test_release_is_idempotent_and_any_id_works(ev):
    first = release.release_extra_evidence("r1")
    assert first == {"released": ["access/parking_exit.csv"]}
    assert release.release_extra_evidence("r1") == first
    assert release.release_extra_evidence("whatever-id") == first
    data = json.loads(paths.RELEASED_FILE.read_text(encoding="utf-8"))
    assert data == {"released": ["access/parking_exit.csv"], "requests": ["r1", "whatever-id"]}
    assert release.released_files() == ["access/parking_exit.csv"]


def test_release_file_is_valid_json_lf_and_no_temp_left(ev):
    release.release_extra_evidence("r1")
    raw = paths.RELEASED_FILE.read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"\n")
    json.loads(raw.decode("utf-8"))
    leftovers = [p.name for p in paths.RELEASED_FILE.parent.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_release_sorted_nested_files(ev):
    (ev["extra"] / "b.csv").write_text("x", encoding="utf-8")
    (ev["extra"] / "access" / "deep").mkdir()
    (ev["extra"] / "access" / "deep" / "a.csv").write_text("x", encoding="utf-8")
    got = release.release_extra_evidence("r2")["released"]
    assert got == ["access/deep/a.csv", "access/parking_exit.csv", "b.csv"]


def test_release_missing_or_empty_extra_dir(ev, monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "EXTRA_DIR", tmp_path / "nope")
    assert release.release_extra_evidence("r1") == {"released": []}
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(paths, "EXTRA_DIR", empty)
    assert release.release_extra_evidence("r1") == {"released": []}
    assert release.released_files() == []


def test_reset_and_unreadable_file(ev):
    release.reset_released()  # nothing to delete: no error
    release.release_extra_evidence("r1")
    release.reset_released()
    assert not paths.RELEASED_FILE.exists()
    assert release.released_files() == []
    paths.RELEASED_FILE.write_text("{not json", encoding="utf-8")
    assert release.released_files() == []


def test_release_never_touches_case_dirs(ev):
    before = sorted(p.as_posix() for p in ev["builtin"].rglob("*"))
    release.release_extra_evidence("r1")
    assert sorted(p.as_posix() for p in ev["builtin"].rglob("*")) == before
    assert not paths.UPLOADED_CASE_DIR.exists()


def test_release_route(ev, client):
    r = client.post("/api/evidence/release/r9")
    assert r.status_code == 200
    assert r.json() == {"released": ["access/parking_exit.csv"]}


# ---------------------------------------------------------------- upload

def test_upload_happy_path_then_status_then_delete(ev, client):
    release.release_extra_evidence("r1")
    r = post_zip(client, make_zip(GOOD))
    assert r.status_code == 200, r.text
    assert r.json() == {
        "case_id": "1010F",
        "filename": "case.zip",
        "files": 3,
        "case_dir": "work/CASE-1010F",
        "pipeline_started": True,
    }
    assert ev["calls"] == ["ingest"]
    up = paths.UPLOADED_CASE_DIR
    assert (up / "manifest.csv").is_file() and (up / "docs" / "memo.txt").read_bytes() == b"hello\n"
    assert paths.active_case_dir() == up
    assert not paths.RELEASED_FILE.exists()  # new case: nothing released
    assert [p.name for p in ev["work"].iterdir()] == ["CASE-1010F"]  # no staging leftovers

    s = client.get("/api/evidence/status").json()
    assert s == {"case_dir": "work/CASE-1010F", "uploaded": True, "released": []}
    assert not ev["extra"].exists()  # a new case also drops any extra evidence uploaded for the old one
    release.add_uploaded_evidence("r1", "parking_exit.csv", PARKING_CSV)
    assert client.get("/api/evidence/status").json()["released"] == ["access/parking_exit.csv"]

    d = client.delete("/api/evidence/upload")
    assert d.status_code == 200
    assert not up.exists()
    assert paths.active_case_dir() == ev["builtin"]
    assert client.get("/api/evidence/status").json() == {
        "case_dir": "CASE-1010F", "uploaded": False, "released": []}


def test_upload_replaces_previous_upload(ev, client):
    assert post_zip(client, make_zip(GOOD)).status_code == 200
    second = {"CASE-1010F/manifest.csv": b"path\n", "CASE-1010F/new.txt": b"n"}
    r = post_zip(client, make_zip(second))
    assert r.status_code == 200 and r.json()["files"] == 2
    names = sorted(p.relative_to(paths.UPLOADED_CASE_DIR).as_posix()
                   for p in paths.UPLOADED_CASE_DIR.rglob("*"))
    assert names == ["manifest.csv", "new.txt"]


def test_upload_reports_pipeline_busy(ev, client, monkeypatch):
    monkeypatch.setattr(pipeline, "start", lambda stage="ingest": False)
    r = post_zip(client, make_zip(GOOD))
    assert r.status_code == 200
    assert r.json()["pipeline_started"] is False


@pytest.mark.parametrize("bad_name", ["../x", "/x", "C:\\x", "C:/x", "CASE-1010F/../../x",
                                      "CASE-1010F\\..\\x"])
def test_upload_rejects_zip_slip(ev, client, bad_name):
    entries = dict(GOOD)
    entries[bad_name] = b"evil"
    r = post_zip(client, make_zip(entries))
    assert r.status_code == 400, r.text
    assert not paths.UPLOADED_CASE_DIR.exists()
    assert not (ev["root"].parent / "x").exists()


def test_upload_rejects_raw_backslash_name(ev, client):
    # ZipInfo turns backslashes into '/' on Windows, so set the raw name after construction.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CASE-1010F/manifest.csv", b"x")
        info = zipfile.ZipInfo("placeholder")
        info.filename = "CASE-1010F\\..\\..\\x"
        zf.writestr(info, b"evil")
    r = post_zip(client, buf.getvalue())
    assert r.status_code == 400 and "unsafe" in r.json()["detail"]


def test_upload_rejects_symlink(ev, client):
    r = post_zip(client, make_zip(GOOD, symlink="CASE-1010F/link"))
    assert r.status_code == 400 and "symlink" in r.json()["detail"]


def test_upload_rejects_non_zip(ev, client):
    assert post_zip(client, b"not a zip at all", name="case.zip").status_code == 400
    assert post_zip(client, make_zip(GOOD), name="case.tar").status_code == 400


def test_upload_rejects_missing_manifest(ev, client):
    r = post_zip(client, make_zip({"CASE-1010F/docs/memo.txt": b"x"}))
    assert r.status_code == 400 and "manifest.csv" in r.json()["detail"]


def test_upload_rejects_two_top_level_folders(ev, client):
    entries = dict(GOOD)
    entries["OTHER/manifest.csv"] = b"x"
    r = post_zip(client, make_zip(entries))
    assert r.status_code == 400 and "exactly one top-level folder" in r.json()["detail"]


def test_upload_rejects_top_level_file(ev, client):
    entries = dict(GOOD)
    entries["readme.txt"] = b"x"
    assert post_zip(client, make_zip(entries)).status_code == 400


def test_failed_upload_keeps_previous_upload(ev, client):
    assert post_zip(client, make_zip(GOOD)).status_code == 200
    assert post_zip(client, make_zip({"../x": b"e"})).status_code == 400
    assert (paths.UPLOADED_CASE_DIR / "manifest.csv").is_file()
    assert [p.name for p in ev["work"].iterdir()] == ["CASE-1010F"]


def test_upload_too_large(ev, client, monkeypatch):
    from app.features.evidence import router as ev_router
    monkeypatch.setattr(ev_router, "MAX_UPLOAD_BYTES", 10)
    r = post_zip(client, make_zip(GOOD))
    assert r.status_code == 400 and "larger" in r.json()["detail"]


# ---------------------------------------------------------------- extra evidence uploaded for a request

PARKING_CSV = b"timestamp,lane,permit_id,plate,direction\n2026-03-04T18:44:00-05:00,EXIT-1,P-2088,W26-VCU,OUT\n"


def test_uploaded_parking_log_is_saved_where_the_parser_expects_and_released(ev):
    got = release.add_uploaded_evidence("r1", "my_parking_export.csv", b"\xef\xbb\xbf" + PARKING_CSV)  # BOM is fine
    assert got == {"released": ["access/parking_exit.csv"], "file": "access/parking_exit.csv"}
    assert (ev["extra"] / "access" / "parking_exit.csv").read_bytes().endswith(PARKING_CSV)
    assert release.released_files() == ["access/parking_exit.csv"]


@pytest.mark.parametrize("name,data", [
    ("parking.csv", b""),
    ("parking.txt", PARKING_CSV),
    ("other.csv", b"when,who\n1,2\n"),
])
def test_wrong_uploads_are_rejected_and_nothing_is_released(ev, name, data):
    import shutil
    shutil.rmtree(ev["extra"])
    with pytest.raises(release.UploadRejected):
        release.add_uploaded_evidence("r1", name, data)
    assert release.released_files() == [] and not (ev["extra"] / "access" / "parking_exit.csv").exists()


def test_swap_in_retries_while_windows_briefly_locks_the_new_folder(tmp_path, monkeypatch):
    """A just-unpacked folder can be locked for a moment (antivirus scan): the rename is retried, not failed."""
    from app.features.evidence import router as ev_router

    new, final = tmp_path / "new", tmp_path / "final"
    new.mkdir()
    (new / "a.txt").write_text("x")
    real_rename, fails = Path.rename, {"n": 2}

    def flaky(self, target):
        if self == new and fails["n"]:
            fails["n"] -= 1
            raise PermissionError(5, "Access is denied")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky)
    monkeypatch.setattr(ev_router.time, "sleep", lambda s: None)
    ev_router._swap_in(new, final)
    assert (final / "a.txt").read_text() == "x" and fails["n"] == 0
