"""Stage 8: the verifier. Code, not an LLM.

Re-checks every claim against the real case file it cites:
  1. the cited file exists and its bytes hash to the cited sha256;
  2. the cited line exists and contains the cited quote (whitespace-normalized);
  3. for CSV rows, the event time and actor identifier appear in that row;
  4. custody: a file whose hash does not match manifest.csv is not trusted (checked first, for every event citing
     it, even if the quote no longer matches). Its events are left out of
     verified_event_ids with the reason "custody: hash mismatch" (the quote may be perfectly accurate; we just
     cannot trust the file). The same fact is reported from a trusted source when one exists (file_audit.csv).
A contradiction is verified only if every event it cites is verified (custody contradictions are about the
file itself, so they may cite the unverified event).
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from app.features.investigator.inputs import Contradiction, EvidenceFile, Event

log = logging.getLogger(__name__)

CUSTODY_REASON = "custody: hash mismatch"
_ACTOR_KINDS_IN_ROW = {"badge", "mac", "account", "permit"}


class _Files(Protocol):
    def read_bytes(self, rel: str) -> bytes | None: ...


@dataclass
class Rejection:
    claim: str
    reason: str


@dataclass
class VerificationResult:
    claims: int = 0
    verified: int = 0
    rejected: list[Rejection] = field(default_factory=list)
    verified_event_ids: list[str] = field(default_factory=list)
    # events held back for custody -> ids of verified events that state the same fact from a trusted file
    corroborated_by: dict[str, list[str]] = field(default_factory=dict)
    custody_failed_event_ids: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        """Exactly the shape of schema.Verification (verified_event_ids is the documented extra field)."""
        return {
            "claims": self.claims,
            "verified": self.verified,
            "rejected": [{"claim": r.claim, "reason": r.reason} for r in self.rejected],
            "verified_event_ids": list(self.verified_event_ids),
        }


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _claim_text(e: Event) -> str:
    q = _norm(e.source.quote)
    shown = q if len(q) <= 70 else q[:70] + "..."
    return f"{e.id}: {e.type} at {e.t}, \"{shown}\""


class _Reader:
    """Reads each cited file once and exposes its physical lines (PDFs: the text pdfplumber extracts)."""

    def __init__(self, files: _Files) -> None:
        self._files = files
        self._bytes: dict[str, bytes | None] = {}
        self._lines: dict[str, list[str]] = {}

    def bytes(self, rel: str) -> bytes | None:
        if rel not in self._bytes:
            self._bytes[rel] = self._files.read_bytes(rel)
        return self._bytes[rel]

    def lines(self, rel: str) -> list[str]:
        if rel not in self._lines:
            data = self.bytes(rel) or b""
            self._lines[rel] = self._pdf_lines(data) if rel.lower().endswith(".pdf") else self._text_lines(data)
        return self._lines[rel]

    @staticmethod
    def _text_lines(data: bytes) -> list[str]:
        return data.decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n")

    @staticmethod
    def _pdf_lines(data: bytes) -> list[str]:
        try:
            import pdfplumber  # lazy: only needed when a statement is cited

            with pdfplumber.open(io.BytesIO(data)) as pdf:
                text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        except Exception as exc:  # noqa: BLE001 - a corrupt PDF just means the claim cannot be verified
            log.warning("cannot extract PDF text (%s)", exc)
            return []
        return text.split("\n")


def _quote_in_line(rel: str, line: str, quote: str) -> bool:
    q, l = _norm(quote), _norm(line)
    if not q:
        return False
    if rel.lower().endswith(".csv"):
        return q == l  # a CSV quote is the whole raw row
    if q in l:
        return True
    if rel.lower().endswith(".json"):  # Slack: the line holds a JSON-escaped string
        m = re.search(r'"text"\s*:\s*(".*")', line)
        if m:
            try:
                return q in _norm(json.loads(m.group(1)))
            except ValueError:
                return False
    return False


def _row_fields_match(e: Event) -> bool:
    row = e.source.quote
    if e.t and e.t not in row:
        return False
    if e.actor and e.actor.kind in _ACTOR_KINDS_IN_ROW and e.actor.value.lower() not in row.lower():
        return False
    return True


def _check_source(e: Event, reader: _Reader) -> str | None:
    """Return None if the cited source checks out, otherwise the reason it does not."""
    src = e.source
    data = reader.bytes(src.file)
    if data is None:
        return "cited file not found"
    if hashlib.sha256(data).hexdigest() != src.sha256.lower():
        return "sha256 does not match the cited file"
    lines = reader.lines(src.file)
    if src.line < 1 or src.line > len(lines):
        return "cited line not in file"
    if not _quote_in_line(src.file, lines[src.line - 1], src.quote):
        return "quote not found"
    if src.file.lower().endswith(".csv") and not _row_fields_match(e):
        return "field mismatch in cited row"
    return None


def _same_fact(a: Event, b: Event) -> bool:
    """Do two events from different files state the same thing (same account and path, same moment)?"""
    path_a, path_b = a.attrs.get("path"), b.attrs.get("path")
    same_actor = a.actor is not None and b.actor is not None and a.actor.value.lower() == b.actor.value.lower()
    return bool(path_a and path_a == path_b and same_actor and a.t == b.t)


def verify_events(events: Iterable[Event], evidence: Iterable[EvidenceFile], files: _Files) -> VerificationResult:
    events = list(events)
    reader = _Reader(files)
    # Custody fails only when the manifest lists the file and its hash differs. A file the manifest never listed
    # (released extra evidence) is "not listed", not "tampered": it is checked against its own bytes like any other.
    untrusted = {
        f.file for f in evidence
        if not f.not_in_manifest
        and (not f.manifest_match or (f.manifest_sha256 is not None and f.manifest_sha256.lower() != f.sha256.lower()))
    }
    result = VerificationResult(claims=len(events))
    held_back: list[Event] = []

    for e in events:
        # A file that failed custody is untrusted whatever its rows say: an altered row no longer matches the quote
        # taken as collected, and an event may cite the hash of the file as collected. Both are custody problems.
        if e.source.file in untrusted and reader.bytes(e.source.file) is not None:
            held_back.append(e)
            result.custody_failed_event_ids.append(e.id)
            continue
        reason = _check_source(e, reader)
        if reason is None:
            result.verified_event_ids.append(e.id)
        else:
            result.rejected.append(Rejection(_claim_text(e), reason))

    trusted = {e.id: e for e in events if e.id in set(result.verified_event_ids)}
    for e in held_back:
        twins = [t.id for t in trusted.values() if t.source.file != e.source.file and _same_fact(e, t)]
        reason = CUSTODY_REASON
        if twins:
            result.corroborated_by[e.id] = twins
            files_used = sorted({trusted[t].source.file for t in twins})
            reason += f" (same fact verified from {', '.join(files_used)}: {', '.join(twins)})"
        result.rejected.append(Rejection(_claim_text(e), reason))

    result.verified = len(result.verified_event_ids)
    return result


def verify_contradictions(contradictions: Iterable[Contradiction], base: VerificationResult,
                          known_event_ids: Iterable[str] | None = None) -> VerificationResult:
    """Add one claim per contradiction. A contradiction stands only if all the events it cites are verified."""
    verified = set(base.verified_event_ids)
    known = set(known_event_ids) if known_event_ids is not None else verified | set(base.custody_failed_event_ids) | {
        r.claim.split(":")[0] for r in base.rejected
    }
    out = VerificationResult(
        claims=base.claims, verified=base.verified, rejected=list(base.rejected),
        verified_event_ids=list(base.verified_event_ids), corroborated_by=dict(base.corroborated_by),
        custody_failed_event_ids=list(base.custody_failed_event_ids),
    )
    for c in contradictions:
        out.claims += 1
        claim = f"{c.id}: {c.kind} contradiction, {c.explanation[:80]}".rstrip(", ")
        problem = None
        for eid in c.events:
            if eid not in known:
                problem = f"cites unknown event {eid}"
                break
            if eid not in verified and c.kind != "custody":
                problem = f"cites event {eid} that is not verified"
                break
        if problem:
            out.rejected.append(Rejection(claim, problem))
        else:
            out.verified += 1
    return out
