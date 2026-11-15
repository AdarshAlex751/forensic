"""Every real event's quote must appear verbatim on the cited line of the real raw case file.

Reads data/evidence/events.json (Person 1's real ingest) and data/evidence/CASE-1010F/ (read-only), plus extra/ for
released evidence. If a quote does not match, this test reports file, line, expected quote and found text; it never
edits another person's file. PDFs use pdfplumber extract_text() lines, all pages joined by a newline (FORMAT.md).
"""
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "data" / "evidence" / "CASE-1010F"
EVENTS = ROOT / "data" / "evidence" / "events.json"
EXTRA = ROOT / "data" / "evidence" / "extra"

pytestmark = pytest.mark.skipif(not (CASE.is_dir() and EVENTS.is_file()), reason="raw case files or real events.json not present")


def _lines(rel: str) -> list[str] | None:
    path = CASE / rel
    if not path.is_file():
        path = EXTRA / rel  # released extra evidence is never copied into the case folder
    if not path.is_file():
        return None
    data = path.read_bytes()
    if rel.lower().endswith(".pdf"):
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages).split("\n")
    return data.decode("utf-8").split("\n")  # not splitlines(): that also splits on odd unicode separators


def test_every_event_quote_is_on_its_cited_line_of_the_raw_file():
    events = json.loads(EVENTS.read_text(encoding="utf-8"))
    assert events, "no events found"
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
