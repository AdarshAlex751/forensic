"""Writers for the text and document case files: usbstor.txt, mailbox.mbox, the Slack export and the PDFs.

Each writer follows records.py: write(records, out_dir) -> list[Written], one Written per EventSpec with the exact
1-based line and quote, UTF-8 without BOM, LF endings, byte-identical output for the same records.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path

from .records import Record, Written
from .world import EST, F_BRIEF, F_MBOX, F_SLACK_DIR, F_STATEMENTS_DIR, F_USB, people, slack_user_id, ts

ORG = "Halvorsen Dynamics - Security Office"

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DAYS_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                "November", "December"]


def _write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _no_newline(where: str, value: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError(f"{where}: value contains a newline: {value!r}")
    return value


# --------------------------------------------------------------------------------------------- usbstor.txt

USBSTOR_HEADER = [
    "usbstor v.20200515",
    "(System) Get USBStor key info",
    "",
    "USBStor",
    "ControlSet001\\Enum\\USBStor",
    "",
]


def write_usbstor(records: list[Record], out_dir: Path) -> list[Written]:
    """RegRipper `usbstor` output: one block per record, blank line between blocks. Event line = the S/N line."""
    lines = list(USBSTOR_HEADER)
    written: list[Written] = []
    for i, r in enumerate(records):
        if r.source != F_USB:
            raise ValueError(f"not the usbstor source: {r.source}")
        f = r.fields
        vals = {k: _no_newline(f"usbstor {k}", str(f[k])) for k in
                ("vendor", "product", "rev", "serial", "friendly_name")}
        last = ts(f["last_write"])
        if i:
            lines.append("")
        lines.append(f"Disk&Ven_{vals['vendor']}&Prod_{vals['product']}&Rev_{vals['rev']} [{last}]")
        sn = f"  S/N: {vals['serial']} [{last}]"
        lines.append(sn)
        sn_line = len(lines)
        lines.append(f"  FriendlyName  : {vals['friendly_name']}")
        lines.append(f"  First InstallDate : {ts(f['first_install'])}")
        for ev in r.events:
            written.append(Written(event=ev, record=r, line=sn_line, quote=sn))
    _write_lines(out_dir / F_USB, lines)
    return written


# --------------------------------------------------------------------------------------------- mailbox.mbox

def _asctime(dt: datetime) -> str:
    """mbox separator date, locale-independent: 'Wed Mar  4 17:30:00 2026'."""
    dt = dt.astimezone(EST)
    return f"{_DAYS[dt.weekday()]} {_MONTHS[dt.month - 1]} {dt.day:2d} {dt:%H:%M:%S} {dt.year}"


def write_mbox(records: list[Record], out_dir: Path) -> list[Written]:
    """Standard mbox, messages in the given order. Bytes are written directly so no library re-wraps lines."""
    lines: list[str] = []
    written: list[Written] = []
    for i, r in enumerate(records):
        if r.source != F_MBOX:
            raise ValueError(f"not the mbox source: {r.source}")
        f = r.fields
        mid = f.get("message_id", "?")
        from_addr = _no_newline("mbox from_addr", f["from_addr"])
        if " " in from_addr or not from_addr:
            raise ValueError(f"mbox {mid}: bad from_addr {from_addr!r}")
        date = f["date"].astimezone(EST)
        if i:
            lines.append("")
        lines.append(f"From {from_addr} {_asctime(date)}")
        headers = [("From", f'"{f["from_name"]}" <{from_addr}>'), ("To", ", ".join(f["to"]))]
        if f.get("cc"):
            headers.append(("Cc", ", ".join(f["cc"])))
        headers += [("Subject", f["subject"]), ("Date", format_datetime(date)), ("Message-ID", f["message_id"])]
        if f.get("in_reply_to"):
            headers.append(("In-Reply-To", f["in_reply_to"]))
        headers += [("MIME-Version", "1.0"), ("Content-Type", "text/plain; charset=utf-8"),
                    ("Content-Transfer-Encoding", "8bit")]
        for name, value in headers:
            lines.append(f"{name}: {_no_newline(f'mbox {mid} {name}', str(value))}")
        lines.append("")
        body_start = len(lines) + 1  # file line number of body line 0
        body = list(f["body"])
        for bl in body:
            if "\r" in bl or "\n" in bl:
                raise ValueError(f"mbox {mid}: body line contains a newline or CR: {bl!r}")
            if bl.startswith("From "):
                raise ValueError(f"mbox {mid}: body line starts with 'From ' (mbox would escape it): {bl!r}")
            lines.append(bl)
        for ev in r.events:
            if ev.quote_text is not None:
                hits = [j for j, bl in enumerate(body) if ev.quote_text in bl]
                if len(hits) != 1:
                    raise ValueError(f"mbox {mid}: quote {ev.quote_text!r} is on {len(hits)} body lines, need 1")
                written.append(Written(event=ev, record=r, line=body_start + hits[0], quote=ev.quote_text))
            else:
                j = next((j for j, bl in enumerate(body) if bl.strip()), None)
                if j is None:
                    raise ValueError(f"mbox {mid}: empty body, nothing to quote")
                written.append(Written(event=ev, record=r, line=body_start + j, quote=body[j]))
    _write_lines(out_dir / F_MBOX, lines)
    return written


# --------------------------------------------------------------------------------------------- Slack export

_DM_ID = re.compile(r"^D[0-9A-Z]+$")


def _is_dm(channel: str) -> bool:
    return bool(_DM_ID.match(channel))


def _channel_id(name: str) -> str:
    return "C" + hashlib.sha256(name.encode()).hexdigest()[:10].upper()


def _check_slack_text(text: str) -> str:
    if any(c in text for c in '"\\') or any(ord(c) < 0x20 for c in text):
        raise ValueError(f"slack text has a quote, backslash or control char (JSON would escape it): {text!r}")
    return text


def write_slack(records: list[Record], out_dir: Path) -> list[Written]:
    """Slack export: users.json, channels.json, dms.json and one <channel>/<YYYY-MM-DD>.json per record source.

    Message ts = f"{epoch}.{n:06d}" with n = 100, 200, ... per message within the same second of one file, unless
    fields['ts_str'] gives it explicitly. The ts is also stored in each event's attrs['ts'] (set if missing,
    must match if present).
    """
    root = out_dir / F_SLACK_DIR
    by_file: dict[str, list[tuple[int, Record]]] = {}
    for i, r in enumerate(records):
        if not r.source.startswith(F_SLACK_DIR + "/"):
            raise ValueError(f"not a Slack source: {r.source}")
        by_file.setdefault(r.source, []).append((i, r))

    written: list[Written] = []
    chan_posters: dict[str, set[str]] = {}
    chan_first: dict[str, int] = {}
    for source in sorted(by_file):
        entries = []
        per_second: dict[int, int] = {}
        for i, r in by_file[source]:
            f = r.fields
            channel, dt = f["channel"], f["ts"].astimezone(EST)
            expected = f"{F_SLACK_DIR}/{channel}/{dt:%Y-%m-%d}.json"
            if r.source != expected:
                raise ValueError(f"slack record source {r.source!r} != {expected!r}")
            text = _check_slack_text(f["text"])
            if f.get("ts_str"):
                ts_str = f["ts_str"]
            else:
                sec = int(dt.timestamp())
                per_second[sec] = per_second.get(sec, 0) + 1
                ts_str = f"{sec}.{per_second[sec] * 100:06d}"
            entries.append((float(ts_str), i, ts_str, r, text))
            chan_posters.setdefault(channel, set()).add(f["user"])
            chan_first[channel] = min(chan_first.get(channel, int(dt.timestamp())), int(dt.timestamp()))
        entries.sort(key=lambda e: (e[0], e[1]))
        stamps = [e[2] for e in entries]
        if len(set(stamps)) != len(stamps):
            raise ValueError(f"{source}: duplicate Slack ts")
        msgs = [{"type": "message", "user": slack_user_id(e[3].fields["user"]), "text": e[4], "ts": e[2]}
                for e in entries]
        out = json.dumps(msgs, indent=2, ensure_ascii=False)
        out_lines = out.split("\n")
        for k, (_, _, ts_str, r, text) in enumerate(entries):
            line = 5 + 6 * k  # "[", "  {", type, user, text
            if out_lines[line - 1] != f'    "text": "{text}",':
                raise ValueError(f"{source}: text line {line} not where expected")
            for ev in r.events:
                if ev.quote_text is not None and ev.quote_text != text:
                    raise ValueError(f"{source}: chat quote_text {ev.quote_text!r} != message text {text!r}")
                if ev.attrs.get("ts", ts_str) != ts_str:
                    raise ValueError(f"{source}: event attrs ts {ev.attrs['ts']!r} != written ts {ts_str!r}")
                ev.attrs["ts"] = ts_str
                written.append(Written(event=ev, record=r, line=line, quote=text))
        _write_lines(out_dir / source, out_lines)

    users = []
    for p in people():
        h = p.get("slack_handle") or ""
        if h:
            users.append({"id": slack_user_id(h), "name": h, "real_name": p["name"], "deleted": False,
                          "is_bot": False, "profile": {"real_name": p["name"], "display_name": h,
                                                       "title": p.get("role", "")}})
    handles = {u["name"] for u in users}
    for h in sorted(set().union(*chan_posters.values()) if chan_posters else set()):
        if h not in handles:
            raise ValueError(f"slack handle {h!r} is not in inventory.csv")
    channels = [{"id": _channel_id(c), "name": c, "created": chan_first[c], "is_general": c == "general",
                 "members": sorted(slack_user_id(h) for h in chan_posters[c])}
                for c in sorted(chan_posters) if not _is_dm(c)]
    dms = [{"id": c, "created": chan_first[c], "members": sorted(slack_user_id(h) for h in chan_posters[c])}
           for c in sorted(chan_posters) if _is_dm(c)]
    for name, data in (("users.json", users), ("channels.json", channels), ("dms.json", dms)):
        _write_lines(root / name, json.dumps(data, indent=2, ensure_ascii=False).split("\n"))
    return written


# --------------------------------------------------------------------------------------------- PDFs

PAGE_W, PAGE_H = 612.0, 792.0  # US Letter
MARGIN = 57.6  # 0.8 in; leaves 496.8 pt so every story quote fits one line
TEXT_W = PAGE_W - 2 * MARGIN
FONT, FONT_B, SIZE, LEADING = "Helvetica", "Helvetica-Bold", 11, 15
PARA_GAP = 8
FOOT_Y = 40.0


def _long_date(dt: datetime, with_time: bool) -> str:
    dt = dt.astimezone(EST)
    s = f"{_DAYS_LONG[dt.weekday()]}, {dt.day} {_MONTHS_LONG[dt.month - 1]} {dt.year}"
    return s + f", {dt:%H:%M} EST" if with_time else s


def _width(text: str, font: str = FONT, size: float = SIZE) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    return stringWidth(text, font, size)


def max_line_width() -> float:
    """Width in points available to one body line (a quote must fit in it)."""
    return TEXT_W


def _wrap(text: str) -> list[str]:
    from reportlab.lib.utils import simpleSplit

    text = " ".join(text.split())
    return simpleSplit(text, FONT, SIZE, TEXT_W) if text else []


def _para_lines(para: str, quotes: list[str], where: str) -> list[str]:
    """Body lines for one paragraph; each quote it contains gets a line of its own and never wraps."""
    spans = []
    for q in quotes:
        k = para.find(q)
        if k < 0:
            continue
        if para.find(q, k + 1) >= 0:
            raise ValueError(f"{where}: quote appears twice in one paragraph: {q!r}")
        spans.append((k, k + len(q), q))
    spans.sort()
    for a, b in zip(spans, spans[1:]):
        if b[0] < a[1]:
            raise ValueError(f"{where}: overlapping quotes {a[2]!r} / {b[2]!r}")
    out, pos = [], 0
    for a, b, q in spans:
        out += _wrap(para[pos:a])
        if _width(q) > TEXT_W:
            raise ValueError(f"{where}: quote is too long for one PDF line ({_width(q):.0f} > {TEXT_W:.0f} pt): {q!r}")
        out.append(q)
        pos = b
    out += _wrap(para[pos:])
    return out


class _Doc:
    def __init__(self, path: Path, title: str, author: str, subject: str, footer: str):
        from reportlab.pdfgen import canvas

        path.parent.mkdir(parents=True, exist_ok=True)
        self.c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H), invariant=1, pageCompression=0)
        self.c.setTitle(title)
        self.c.setAuthor(author)
        self.c.setSubject(subject)
        self.c.setCreator("Halvorsen Dynamics Security Office")
        self.c.setProducer("ReportLab PDF Library")
        self.c.setKeywords("")
        self.footer = footer
        self.page = 1
        self.y = PAGE_H - MARGIN

    def _footer(self):
        self.c.setFont(FONT, 8)
        self.c.drawString(MARGIN, FOOT_Y, f"{self.footer} - Page {self.page}")

    def need(self, h: float):
        if self.y - h < FOOT_Y + 30:
            self._footer()
            self.c.showPage()
            self.page += 1
            self.y = PAGE_H - MARGIN

    def line(self, text: str, font: str = FONT, size: float = SIZE, leading: float = LEADING):
        self.need(leading)
        self.y -= leading
        self.c.setFont(font, size)
        self.c.drawString(MARGIN, self.y, text)

    def gap(self, h: float):
        self.y -= h

    def rule(self):
        self.need(10)
        self.y -= 6
        self.c.setLineWidth(0.6)
        self.c.line(MARGIN, self.y, PAGE_W - MARGIN, self.y)
        self.y -= 4

    def save(self):
        self._footer()
        self.c.showPage()
        self.c.save()


def _extract_lines(path: Path) -> list[str]:
    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return [ln.rstrip(" ") for ln in text.split("\n")]


def _render_pdf(r: Record, out_dir: Path) -> list[Written]:
    f = r.fields
    is_brief = r.source == F_BRIEF
    for k in (("title", "case_id", "author", "date", "paragraphs") if is_brief else
              ("title", "case_id", "speaker", "role", "interviewer", "date", "location", "paragraphs")):
        if k not in f:
            raise ValueError(f"{r.source}: missing field {k!r}")
    quotes = []
    for ev in r.events:
        if not ev.quote_text:
            raise ValueError(f"{r.source}: event {ev.type} has no quote_text")
        quotes.append(ev.quote_text)
    # Helvetica (standard PDF font) only round-trips plain ASCII reliably through pdfplumber.
    for text in [str(f.get(k, "")) for k in ("title", "speaker", "role", "interviewer", "location", "author")] + \
            list(f["paragraphs"]):
        bad = sorted({c for c in text if ord(c) > 126 or (ord(c) < 32)})
        if bad:
            raise ValueError(f"{r.source}: non-ASCII characters {bad!r} would not extract cleanly: {text[:60]!r}")

    path = out_dir / r.source
    author = f["author"] if is_brief else f["interviewer"]
    subject = f"Case {f['case_id']}" + ("" if is_brief else f" - statement of {f['speaker']}")
    doc = _Doc(path, f["title"], author, subject, f"{ORG} - Case {f['case_id']} - CONFIDENTIAL")

    doc.line(ORG, FONT_B, 14, 18)
    doc.line(f["title"], FONT_B, 12, 18)
    doc.gap(4)
    if is_brief:
        meta = [("Case number", f["case_id"]), ("Prepared by", f["author"]), ("Date", _long_date(f["date"], False))]
    else:
        meta = [("Case number", f["case_id"]), ("Statement of", f"{f['speaker']} ({f['role']})"),
                ("Date / time", _long_date(f["date"], True)), ("Location", f["location"]),
                ("Interviewer", f["interviewer"])]
    for k, v in meta:
        doc.line(f"{k}: {_no_newline(r.source, str(v))}", FONT, 10, 14)
    doc.rule()
    doc.gap(4)

    used = set()
    for n, para in enumerate(f["paragraphs"]):
        _no_newline(r.source, para)
        here = [q for q in quotes if q in para]
        used.update(here)
        plines = _para_lines(para, here, r.source)
        if n:
            doc.gap(PARA_GAP)
        for pl in plines:
            doc.line(pl)
    missing = [q for q in quotes if q not in used]
    if missing:
        raise ValueError(f"{r.source}: quote not in any paragraph: {missing[0]!r}")

    doc.gap(30)
    if is_brief:
        doc.line(f"{f['author']}", FONT_B, 10, 14)
        doc.line(ORG, FONT, 10, 14)
    else:
        doc.line("I confirm that this statement is true to the best of my knowledge and belief.", FONT, 10, 14)
        doc.gap(24)
        doc.line("Signature: ______________________________          Date: ________________", FONT, 10, 14)
        doc.line(f"Statement taken by: {f['interviewer']}", FONT, 10, 14)
    doc.save()

    lines = _extract_lines(path)
    written = []
    for ev in r.events:
        hits = [i for i, ln in enumerate(lines) if ln == ev.quote_text]
        if len(hits) != 1:
            near = [ln for ln in lines if ev.quote_text[:20] in ln]
            raise ValueError(f"{r.source}: quote {ev.quote_text!r} found on {len(hits)} extracted lines "
                             f"(missing, split or duplicated); near: {near[:3]!r}")
        written.append(Written(event=ev, record=r, line=hits[0] + 1, quote=ev.quote_text))
    return written


def write_pdfs(records: list[Record], out_dir: Path) -> list[Written]:
    """statements/<name>.pdf and brief.pdf, one PDF per record, deterministic (reportlab invariant mode)."""
    written: list[Written] = []
    seen = set()
    for r in records:
        if not (r.source == F_BRIEF or (r.source.startswith(F_STATEMENTS_DIR + "/") and r.source.endswith(".pdf"))):
            raise ValueError(f"not a PDF source: {r.source}")
        if r.source in seen:
            raise ValueError(f"two records for one PDF: {r.source}")
        seen.add(r.source)
        written += _render_pdf(r, out_dir)
    return written


# --------------------------------------------------------------------------------------------- dispatch

def _kind(source: str) -> str:
    if source == F_USB:
        return "usb"
    if source == F_MBOX:
        return "mbox"
    if source.startswith(F_SLACK_DIR + "/"):
        return "slack"
    if source == F_BRIEF or source.startswith(F_STATEMENTS_DIR + "/"):
        return "pdf"
    raise ValueError(f"no document writer for {source}")


WRITERS = {"usb": write_usbstor, "mbox": write_mbox, "slack": write_slack, "pdf": write_pdfs}


def write_all(records: list[Record], out_dir: Path) -> list[Written]:
    """Dispatch records to the four document writers (order inside each writer is kept)."""
    groups: dict[str, list[Record]] = {k: [] for k in WRITERS}
    for r in records:
        groups[_kind(r.source)].append(r)
    written: list[Written] = []
    for k, recs in groups.items():
        if recs:
            written += WRITERS[k](recs, out_dir)
    return written


__all__ = ["write_usbstor", "write_mbox", "write_slack", "write_pdfs", "write_all", "max_line_width", "ORG"]
