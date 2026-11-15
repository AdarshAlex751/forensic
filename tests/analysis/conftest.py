import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


import pytest  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _analysis_tests_run_on_the_fakes():
    """These tests assert on the fake case (data/*/fake). Pin every slice to fake mode so they do not change with the
    USE_REAL_* flags in the developer's .env (with real data, outside names legitimately stay unresolved)."""
    mp = pytest.MonkeyPatch()
    for slice_name in ("EVIDENCE", "SCENE", "ANALYSIS", "INVESTIGATOR"):
        mp.setenv(f"USE_REAL_{slice_name}", "false")
    yield
    mp.undo()
