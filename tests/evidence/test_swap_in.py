"""Swapping an uploaded case into place must survive Windows' transient locks (antivirus or the indexer holding a
handle on a folder of freshly written files): WinError 5 on rename used to make the upload answer 500."""
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest  # noqa: E402

from app.features.evidence import router  # noqa: E402


@pytest.fixture
def dirs(monkeypatch):
    monkeypatch.setattr(router.time, "sleep", lambda s: None)  # no real waiting in tests
    with tempfile.TemporaryDirectory(prefix="swap-") as d:
        base = Path(d)
        new = base / "unpacked" / "CASE-1010F"
        new.mkdir(parents=True)
        (new / "manifest.csv").write_text("new", encoding="utf-8")
        yield new, base / "work" / "CASE-1010F"


def lock_rename_of(monkeypatch, src: Path, times: int):
    """Make Path.rename(src -> anything) raise PermissionError the first `times` calls, then behave normally."""
    real, left = Path.rename, {"n": times}

    def fake(self, target):
        if self == src and left["n"] > 0:
            left["n"] -= 1
            raise PermissionError(5, "Access is denied")
        return real(self, target)

    monkeypatch.setattr(Path, "rename", fake)
    return left


def test_a_fresh_install_with_no_previous_case(dirs):
    new, final = dirs
    final.parent.mkdir(parents=True)
    router._swap_in(new, final)
    assert (final / "manifest.csv").read_text() == "new"


def test_a_transient_lock_on_the_new_folder_is_retried(dirs, monkeypatch):
    new, final = dirs
    final.parent.mkdir(parents=True)
    left = lock_rename_of(monkeypatch, new, times=3)
    router._swap_in(new, final)
    assert left["n"] == 0 and (final / "manifest.csv").read_text() == "new"


def test_a_lock_that_never_clears_falls_back_to_copying(dirs, monkeypatch):
    new, final = dirs
    final.parent.mkdir(parents=True)
    lock_rename_of(monkeypatch, new, times=10_000)
    router._swap_in(new, final)
    assert (final / "manifest.csv").read_text() == "new"


def test_the_previous_case_is_replaced_and_its_leftovers_removed(dirs, monkeypatch):
    new, final = dirs
    final.mkdir(parents=True)
    (final / "manifest.csv").write_text("old", encoding="utf-8")
    lock_rename_of(monkeypatch, new, times=2)
    router._swap_in(new, final)
    assert (final / "manifest.csv").read_text() == "new"
    assert [p.name for p in final.parent.iterdir()] == ["CASE-1010F"]  # no .old-* directory left behind


def test_a_lock_on_the_previous_case_is_retried_too(dirs, monkeypatch):
    new, final = dirs
    final.mkdir(parents=True)
    (final / "manifest.csv").write_text("old", encoding="utf-8")
    left = lock_rename_of(monkeypatch, final, times=3)
    router._swap_in(new, final)
    assert left["n"] == 0 and (final / "manifest.csv").read_text() == "new"
