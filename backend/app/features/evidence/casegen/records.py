"""The contract between record builders and file writers.

A Record is one unit a writer renders: one CSV row, one email, one Slack message, one USB device block, one PDF.
Each Record carries the events it produces (EventSpec, in the data/evidence/FORMAT.md shape minus id/source).

A writer has the signature   write(records, out_dir) -> list[Written]
It writes its file(s) under out_dir at each record's `source` path and returns one Written per EventSpec, with the
exact 1-based line number and the exact text it wrote there. Nothing else in the generator numbers lines or
builds quotes: the writer that wrote the line is the only source of truth for where it is.

Writer rules:
  - UTF-8, no BOM, LF line endings, deterministic output (same records -> same bytes).
  - Records for one file are written in the order given (builders sort them; CSV rows by time).
  - CSV and text lines: quote = the whole line without its newline.
  - Documents (mbox, Slack, PDF): EventSpec.quote_text must appear on exactly one written line (for PDFs: one line
    of the text pdfplumber extracts, all pages joined with "\n"); line = that line, quote = quote_text.
    A writer must raise if quote_text is missing or would be split across lines.

`fields` per source (keys a writer may rely on):
  CSV files       column name -> raw string value, exactly the RAW_FORMATS.md header columns
  usbstor.txt     vendor, product, rev, serial, friendly_name, first_install (datetime), last_write (datetime)
  mailbox.mbox    message_id, from_name, from_addr, to (list of addresses), cc (list), subject, date (datetime),
                  in_reply_to (str or None), body (list of lines, no newlines)
  slack           channel (folder name, e.g. "general" or a DM id "D0HANKKIM"), user (handle), text, ts (datetime)
                  source = f"comms/slack_export/{channel}/{YYYY-MM-DD}.json"
  statement PDFs  title, case_id, speaker, role, interviewer, date (datetime), location, paragraphs (list of str);
                  each statement EventSpec.quote_text must equal one whole paragraph or one sentence on its own line
  brief.pdf       title, case_id, author, date (datetime), paragraphs (list of str); no events
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


@dataclass
class EventSpec:
    type: str
    t: datetime
    actor: dict | None
    device: str | None
    room: str | None
    attrs: dict[str, Any]
    quote_text: str | None = None          # documents only: the exact text to quote
    tags: list[str] = field(default_factory=list)  # answer-key tags, e.g. ["C2"]; story events only


@dataclass
class Record:
    source: str                            # case-folder path, e.g. "access/badge_access.csv"
    t: datetime                            # sort key inside its file
    fields: dict[str, Any]
    events: list[EventSpec] = field(default_factory=list)
    story: bool = False                    # True for CASE.md story records (never dropped or altered by noise)


@dataclass
class Written:
    event: EventSpec
    record: Record
    line: int
    quote: str


Writer = Callable[[list[Record], "Path"], list[Written]]  # noqa: F821
