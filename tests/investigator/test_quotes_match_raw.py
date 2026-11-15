"""Every story event's quote must appear verbatim on the cited line of the real raw case file.

Reads data/evidence/fake/events.json (the 75 story events) and data/evidence/CASE-1010F/ (read-only). It does not read
events_baseline.json. If a quote does not match, this test reports file, line, expected quote and found text; it never
edits another person's file. PDFs use pdfplumber extract_text() lines, all pages joined by a newline (FORMAT.md).
"""
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "data" / "evidence" / "CASE-1010F"
EVENTS = ROOT / "data" / "evidence" / "fake" / "events.json"

pytestmark = pytest.mark.skipif(not CASE.is_dir(), reason="raw case files (data/evidence/CASE-1010F) not present")


def _lines(rel: str) -> list[str] | None:
    path = CASE / rel
    if not path.is_file():
        return None
    data = path.read_bytes()
    if rel.lower().endswith(".pdf"):
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages).split("\n")
    return data.decode("utf-8").split("\n")  # not splitlines(): that also splits on odd unicode separators


@pytest.mark.xfail(
    strict=True,
    reason="data/evidence/fake/events.json was written against the earlier mini files: most quotes are in the real "
    "files on other lines, some are not there at all. Run with -rx to list them. Remove this mark once Person 1 "
    "regenerates the fakes (strict: it fails the suite the moment the quotes all match, as a reminder).",
)
def test_every_story_event_quote_is_on_its_cited_line_of_the_raw_file():
    events = json.loads(EVENTS.read_text(encoding="utf-8"))
    assert events, "no story events found"
    cache: dict[str, list[str] | None] = {}
    problems: list[str] = []
    for e in events:
        src = e["source"]
        rel, n, quote = src["file"], src["line"], src["quote"]
        lines = cache.setdefault(rel, _lines(rel))
        if lines is None:
            problems.append(f"{e['id']}: {rel} does not exist in CASE-1010F")
        elif not 1 <= n <= len(lines):
            problems.append(f"{e['id']}: {rel} has {len(lines)} lines, event cites line {n}")
        elif quote not in lines[n - 1]:
            problems.append(f"{e['id']}: {rel}:{n}\n    expected: {quote!r}\n    found:    {lines[n - 1]!r}")
    assert not problems, f"{len(problems)} of {len(events)} quotes do not match the raw files:\n" + "\n".join(problems)
