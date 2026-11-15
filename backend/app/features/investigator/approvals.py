"""In-memory request/approval state for the investigator.

Fake mode (USE_REAL_INVESTIGATOR=false) keeps approvals here only: they reset on restart and leave nothing to
commit. Real mode also writes the status into requests.json on the next run, but this overlay is what
GET /api/investigator/requests returns, so the UI is correct immediately after a click.
"""
from __future__ import annotations

import re
import threading
from typing import Any


def _key(ask: str) -> str:
    return re.sub(r"\s+", " ", ask).strip().lower()


class Approvals:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests: list[dict[str, Any]] = []
        self._approved: set[str] = set()

    def _next_id(self) -> str:
        nums = [int(m.group(1)) for r in self.requests if (m := re.fullmatch(r"r(\d+)", r["id"]))]
        return f"r{max(nums, default=0) + 1}"

    def add_request(self, ask: str, why: str) -> dict[str, Any]:
        """Create a pending request, or return the existing one with the same ask (idempotent)."""
        with self._lock:
            for r in self.requests:
                if _key(r["ask"]) == _key(ask):
                    return dict(r)
            r = {"id": self._next_id(), "ask": ask.strip(), "why": why.strip(), "status": "pending"}
            self.requests.append(r)
            return dict(r)

    def sync(self, records: list[dict[str, Any]]) -> None:
        """Learn requests that exist only in requests.json (e.g. the fake file) so they can be approved."""
        with self._lock:
            known = {r["id"] for r in self.requests}
            for rec in records:
                if isinstance(rec, dict) and rec.get("id") and rec["id"] not in known:
                    self.requests.append({"id": str(rec["id"]), "ask": str(rec.get("ask", "")),
                                          "why": str(rec.get("why", "")), "status": str(rec.get("status", "pending"))})

    def approve(self, request_id: str) -> str | None:
        with self._lock:
            for r in self.requests:
                if r["id"] == request_id:
                    if r["status"] != "ingested":
                        r["status"] = "approved"
                    self._approved.add(request_id)
                    return "approved"
        return None

    def revoke(self, request_id: str) -> None:
        """Undo an approval whose evidence could not be released (an ingested request is never downgraded)."""
        with self._lock:
            self._approved.discard(request_id)
            for r in self.requests:
                if r["id"] == request_id and r["status"] == "approved":
                    r["status"] = "pending"

    def mark_ingested(self) -> None:
        """The released evidence is now part of the case: approved requests become ingested."""
        with self._lock:
            for r in self.requests:
                if r["id"] in self._approved:
                    r["status"] = "ingested"

    def approved_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._approved)

    def any_approved(self) -> bool:
        with self._lock:
            return bool(self._approved)

    def overlay(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Records from a file with their status replaced by the in-memory one (never downgrading 'ingested')."""
        self.sync(records)
        with self._lock:
            live = {r["id"]: r["status"] for r in self.requests}
        out = []
        for rec in records:
            rec = dict(rec)
            if rec.get("status") != "ingested" and rec.get("id") in live:
                rec["status"] = live[rec["id"]]
            out.append(rec)
        known = {r["id"] for r in out}
        with self._lock:
            out += [dict(r) for r in self.requests if r["id"] not in known]
        return out


approvals = Approvals()
