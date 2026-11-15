"""Parsers for the text and document evidence: usbstor.txt, mailbox.mbox, Slack day files, statement PDFs, and the
brief (case.json fields).

Contract: base.py and data/evidence/FORMAT.md sections 2-3. Every parser works from the case folder only.

Conventions (from FORMAT.md / RAW_FORMATS.md, and checked against the parser tests):
  - usbstor: `serial` is the S/N value exactly as printed, including the `&0` instance suffix; `vendor` / `product`
    come from the `Disk&Ven_<v>&Prod_<p>&Rev_<r>` key line, underscores kept (`DataTraveler_3.0`). The host is the
    machine the registry hive was imaged from. usbstor output does not name it, so it is taken from the case's
    devices.csv: the single device of type `laptop` (lt-219 in CASE-1010F). With zero or several laptops it is None.
  - mbox: `to` holds the `To:` header addresses only (`Cc:` is not included). Body lines are every line between the
    blank line ending the headers and the next `From ` separator; "non-empty" means not blank after strip().
  - statements: a page's lines are numbered in the text of all pages joined with "\\n"; `page` is the 1-based page
    that line came from.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path

from .base import EST, FileCtx, est_ts, make_event, parse_iso

# --------------------------------------------------------------------------------------------------- usbstor

_USB_KEY = re.compile(r"^Disk&Ven_(?P<vendor>[^&]*)&Prod_(?P<product>[^&]*)&Rev_(?P<rev>[^\s\[]*)\s*\[(?P<ts>[^\]]+)\]")
_USB_SN = re.compile(r"^\s+S/N:\s*(?P<serial>\S+)\s*\[(?P<ts>[^\]]+)\]\s*$")
_USB_FIRST = re.compile(r"^\s+First InstallDate\s*:\s*(?P<ts>\S+)\s*$")


def _laptop_host(ctx: FileCtx) -> str | None:
    laptops = [d for d, row in ctx.devices.items() if (row.get("type") or "").strip() == "laptop"]
    return laptops[0] if len(laptops) == 1 else None


def parse_usbstor(ctx: FileCtx) -> list[dict]:
    host = _laptop_host(ctx)
    room = ctx.device_room(host)
    events: list[dict] = []
    block: dict | None = None

    def flush() -> None:
        if block and "sn_line" in block:
            events.append(make_event(
                ctx, block["sn_line"], block["sn_quote"], t=est_ts(parse_iso(block["sn_ts"])), type="usb_mount",
                device=host, room=room, actor=None,
                attrs={"serial": block["serial"], "vendor": block["vendor"], "product": block["product"],
                       "first_seen": est_ts(parse_iso(block["first"])) if block.get("first") else None,
                       "host": host}))

    for n, line in enumerate(ctx.lines, 1):
        m = _USB_KEY.match(line)
        if m:
            flush()
            block = {"vendor": m["vendor"], "product": m["product"]}
            continue
        if block is None:
            continue
        m = _USB_SN.match(line)
        if m:
            block.update(sn_line=n, sn_quote=line, serial=m["serial"], sn_ts=m["ts"])
            continue
        m = _USB_FIRST.match(line)
        if m:
            block["first"] = m["ts"]
    flush()
    return events


# ------------------------------------------------------------------------------------------------------ mbox

def _is_separator(lines: list[str], i: int) -> bool:
    return lines[i].startswith("From ") and (i == 0 or lines[i - 1] == "")


def parse_mbox(ctx: FileCtx) -> list[dict]:
    lines = ctx.lines
    starts = [i for i in range(len(lines)) if _is_separator(lines, i)]
    events: list[dict] = []
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        # headers (with folded continuation lines) up to the first blank line
        headers: dict[str, str] = {}
        last = None
        i = start + 1
        while i < end and lines[i] != "":
            h = lines[i]
            if h[:1] in (" ", "\t") and last:
                headers[last] += " " + h.strip()
            elif ":" in h:
                name, _, value = h.partition(":")
                last = name.strip().lower()
                headers.setdefault(last, value.strip())
            i += 1
        body_start = i + 1
        frm = parseaddr(headers.get("from", ""))[1] or None
        to = [a for _, a in getaddresses([headers.get("to", "")]) if a]
        t = est_ts(parsedate_to_datetime(headers["date"]))
        attrs = {"from": frm, "to": to, "subject": headers.get("subject"), "message_id": headers.get("message-id")}
        actor = {"kind": "email", "value": frm} if frm else None
        for j in range(body_start, end):
            if lines[j].strip():
                events.append(make_event(ctx, j + 1, lines[j], t=t, type="email", device=None, room=None,
                                         actor=actor, attrs=dict(attrs, to=list(to))))
    return events


# ----------------------------------------------------------------------------------------------------- slack

_TEXT_LINE = re.compile(r'^\s*"text"\s*:')


def _slack_users(case_dir: Path) -> dict[str, str]:
    p = case_dir / "comms" / "slack_export" / "users.json"
    if not p.is_file():
        return {}
    return {u["id"]: u.get("name") for u in json.loads(p.read_text(encoding="utf-8"))}


def parse_slack_day(ctx: FileCtx) -> list[dict]:
    parts = ctx.rel.split("/")
    channel = parts[-2]
    users = _slack_users(ctx.case_dir)
    messages = json.loads("\n".join(ctx.lines))
    # The export is pretty-printed with one key per line, so the n-th top-level "text" key line is message n's.
    # Message objects are flat (type/user/text/ts), so every "text" line belongs to a message.
    text_lines = [n for n, line in enumerate(ctx.lines, 1) if _TEXT_LINE.match(line)]
    if len(text_lines) != len(messages):
        raise ValueError(f"{ctx.rel}: {len(messages)} messages but {len(text_lines)} text lines")
    events = []
    for msg, n in zip(messages, text_lines):
        handle = users.get(msg.get("user"), msg.get("user"))
        ts = msg["ts"]
        t = est_ts(datetime.fromtimestamp(float(ts), tz=EST))
        events.append(make_event(ctx, n, msg["text"], t=t, type="chat", device=None, room=None,
                                 actor={"kind": "slack", "value": handle} if handle else None,
                                 attrs={"channel": channel, "ts": ts}))
    return events


# ------------------------------------------------------------------------------------------------------- pdf

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"], 1)}
_INTERVIEW_TIME = re.compile(r"^Date / time:\s*(?:\w+,\s*)?(\d{1,2})\s+(\w+)\s+(\d{4}),\s*(\d{1,2}):(\d{2})")
_SPEAKER = re.compile(r"^Statement of:\s*(.+?)\s*\(")


def _pdf_lines(path: Path) -> list[tuple[str, int]]:
    """[(line, page)] of the pdfplumber text, all pages joined with \\n."""
    import pdfplumber

    texts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or "")
    out: list[tuple[str, int]] = []
    for p, text in enumerate(texts, 1):
        for line in text.split("\n"):
            out.append((line, p))
    return out


def parse_statement(ctx: FileCtx) -> list[dict]:
    lines = _pdf_lines(ctx.path)
    speaker = None
    t = None
    for line, _ in lines:
        m = _SPEAKER.match(line)
        if m and speaker is None:
            speaker = m.group(1)
        m = _INTERVIEW_TIME.match(line)
        if m and t is None:
            day, month, year, hh, mm = m.groups()
            t = est_ts(datetime(int(year), _MONTHS[month.lower()], int(day), int(hh), int(mm), tzinfo=EST))
    if t is None:
        raise ValueError(f"{ctx.rel}: no 'Date / time:' line")
    actor = {"kind": "name", "value": speaker} if speaker else None

    events = []
    started = False
    in_note = False
    for n, (line, page) in enumerate(lines, 1):
        if not started:
            if line.startswith("Q:"):
                started = True
            continue
        if line.startswith("I confirm that this statement"):
            break
        if in_note:
            if line.rstrip().endswith("]"):
                in_note = False
            continue
        if line.startswith("["):
            in_note = not line.rstrip().endswith("]")
            continue
        if line.startswith("Q:") or not line.strip():
            continue
        events.append(make_event(ctx, n, line, t=t, type="statement", device=None, room=None, actor=actor,
                                 attrs={"speaker": speaker, "page": page}))
    return events


# ----------------------------------------------------------------------------------------------------- brief

_LABEL = re.compile(r"^([A-Z][A-Za-z ]{0,40})\.\s+(.*)$")
_BUILDING = re.compile(r"\b(?:of|in|at) the ((?:[A-Z][\w.-]*\s)+Building)\b")


def brief_case_info(case_dir: Path) -> dict:
    """case.json fields from brief.pdf. Deterministic and simple:
    id = 'Case number', title = the brief's header (organisation + document title), address = the building the
    brief names (else its 'Location:' line, else ''), summary = its first two labelled paragraphs, labels removed."""
    lines = [line for line, _ in _pdf_lines(Path(case_dir) / "brief.pdf")]
    case_id = ""
    for line in lines:
        m = re.match(r"^Case number:\s*(\S+)", line)
        if m:
            case_id = m.group(1)
            break
    header = [line.strip() for line in lines[:2] if line.strip()]
    # "Incident brief: The Titan Files" -> the case name after the colon; otherwise organisation + document title
    doc_title = header[1] if len(header) > 1 else ""
    title = doc_title.partition(": ")[2] if ": " in doc_title else ": ".join(header)

    # paragraphs: start at a 'Label. text' line after the header block, continue until the next label line
    paragraphs: list[tuple[str, list[str]]] = []   # (label, lines)
    body_started = False
    for line in lines:
        if not body_started:
            if line.startswith("Date:"):
                body_started = True
            continue
        m = _LABEL.match(line)
        if m:
            paragraphs.append((m.group(1), [m.group(2)]))
        elif paragraphs:
            paragraphs[-1][1].append(line)
    labelled = [(label, " ".join(s.strip() for s in p)) for label, p in paragraphs]
    paras = [text for label, text in labelled if label != "Location"]
    summary = " ".join(paras[:2])

    text = " ".join(lines)
    address = next((t for label, t in labelled if label == "Location"), "")
    m = _BUILDING.search(text)
    if address:
        pass
    elif m:
        address = m.group(1)
    else:
        for line in lines:
            if line.startswith("Location:"):
                address = line.partition(":")[2].strip()
                break
    return {"id": case_id, "title": title, "address": address, "summary": summary,
            "costar_property_id": "", "matterport_model_id": ""}
