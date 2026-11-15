"""The parser contract.

A parser is a function   parse(ctx: FileCtx) -> list[dict]
It returns one event dict per event in the file, built with make_event(), in any order. ingest.py sorts them and
assigns ids. Rules (data/evidence/FORMAT.md sections 2-3):
  - t: ISO 8601 EST with -05:00 and seconds (use est_ts()).
  - person is always None; actor is the raw identifier in the record ({"kind", "value"}) or None.
  - device / room come from the case's own facilities/devices.csv (ctx.device_room(), ctx.host_device()).
  - source.line is 1-based on ctx.lines (file split on "\n"; a CSV header is line 1); source.quote is the exact
    text, never stripped (the usbstor S/N line keeps its two leading spaces).
  - attrs keys exactly as FORMAT.md section 3.1 for that type.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import cached_property
from pathlib import Path
from typing import Any, Callable

EST = timezone(timedelta(hours=-5))


def read_lines(path: Path) -> list[str]:
    """The one way to number a text file's lines (shared with the verifier): UTF-8, split on \\n, no stripping.
    A trailing newline does not create an extra line."""
    text = path.read_bytes().decode("utf-8")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def est_ts(t: datetime) -> str:
    """2026-03-04T18:16:40-05:00"""
    if t.tzinfo is None:
        raise ValueError(f"naive datetime {t!r}")
    return t.astimezone(EST).isoformat(timespec="seconds")


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text)


@dataclass
class FileCtx:
    rel: str              # path relative to the case (or extra) folder, forward slashes: "access/badge_access.csv"
    path: Path            # absolute path on disk
    sha256: str
    case_dir: Path        # the case folder (for facilities/devices.csv and sibling files like slack users.json)
    devices: dict[str, dict] = field(repr=False, default_factory=dict)

    @cached_property
    def lines(self) -> list[str]:
        return read_lines(self.path)

    def device_room(self, device_id: str | None) -> str | None:
        d = self.devices.get(device_id or "")
        return d["room"] if d else None

    def host_device(self, host_raw: str) -> str | None:
        """Log host name (LT-219) -> device id (lt-219) if it is in the device map."""
        d = (host_raw or "").lower()
        return d if d in self.devices else None


def make_event(ctx: FileCtx, line: int, quote: str, *, t: str, type: str, device: str | None, room: str | None,
               actor: dict | None, attrs: dict[str, Any]) -> dict:
    return {
        "id": None,
        "t": t,
        "type": type,
        "person": None,
        "device": device,
        "room": room,
        "actor": actor,
        "attrs": attrs,
        "source": {"file": ctx.rel, "line": line, "quote": quote, "sha256": ctx.sha256},
    }


def load_devices(case_dir: Path) -> dict[str, dict]:
    p = case_dir / "facilities" / "devices.csv"
    if not p.is_file():
        return {}
    with open(p, encoding="utf-8", newline="") as f:
        return {r["device_id"]: r for r in csv.DictReader(f)}


Parser = Callable[[FileCtx], list[dict]]
