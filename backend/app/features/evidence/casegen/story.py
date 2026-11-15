"""CASE.md story beats as Records.

story_spec.json holds every story event with its exact raw values (carried over from the finalized fakes, so fake
and real share wording, serials, paths and times) and its answer-key tags. This module turns it into:
  - csv_records():      Records for the CSV files (one per raw row; a CCTV row carries two events)
  - usb_records():      Records for endpoint/usbstor.txt (one per device block)
  - required_docs():    the email / chat / statement events the comms builder must place in its documents,
                        each with the exact quote_text the document has to contain
Records in the "extra" part (the parking log) are returned separately so build.py writes them to extra/.
"""
from __future__ import annotations

import json
from functools import cache

from .csv_writer import HEADERS, parse_row
from .records import EventSpec, Record
from .world import F_USB, STORY_SPEC, parse_ts


@cache
def spec() -> list[dict]:
    return json.loads(STORY_SPEC.read_text(encoding="utf-8"))


def _event(e: dict, with_quote: bool = False) -> EventSpec:
    return EventSpec(type=e["type"], t=parse_ts(e["t"]), actor=e["actor"], device=e["device"], room=e["room"],
                     attrs=dict(e["attrs"]), quote_text=e["quote"] if with_quote else None, tags=list(e["tags"]))


def csv_records(part: str = "story") -> list[Record]:
    """One Record per distinct raw CSV row of the given part ("story" or "extra")."""
    rows: dict[tuple[str, str], Record] = {}
    for e in spec():
        if e["part"] != part or e["source_file"] not in HEADERS:
            continue
        key = (e["source_file"], e["quote"])
        if key not in rows:
            rows[key] = Record(source=e["source_file"], t=parse_ts(e["t"]),
                               fields=parse_row(e["source_file"], e["quote"]), story=True)
        rec = rows[key]
        rec.events.append(_event(e))
        rec.t = min(rec.t, parse_ts(e["t"]))
    return list(rows.values())


def usb_records() -> list[Record]:
    """One usbstor block per story USB device. The block's bracketed time is the mount time (last write)."""
    out = []
    for e in spec():
        if e["source_file"] != F_USB:
            continue
        a = e["attrs"]
        fields = {
            "vendor": a["vendor"],
            "product": a["product"],
            "rev": "1.00",
            "serial": a["serial"],
            "friendly_name": f"{a['vendor']} {a['product'].replace('_', ' ')} USB Device",
            "first_install": parse_ts(a["first_seen"]),
            "last_write": parse_ts(e["t"]),
        }
        out.append(Record(source=F_USB, t=parse_ts(e["t"]), fields=fields, events=[_event(e)], story=True))
    return out


def required_docs() -> list[dict]:
    """Story events living in documents (email, chat, statement). The comms builder must create documents that
    contain each quote_text verbatim on its own line, using these exact t / actor / attrs / source_file values."""
    out = []
    for e in spec():
        if e["type"] in ("email", "chat", "statement"):
            out.append({"source_file": e["source_file"], "event": _event(e, with_quote=True)})
    return out
