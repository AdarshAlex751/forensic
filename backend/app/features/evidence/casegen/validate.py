"""Independent validator of the generated Case 1010F files.

Reads only the RAW files on disk (case folder, extra folder, truth folder, plus the team source files
data/evidence/inventory.csv and layout_placeholder.json) and reports every way they disagree with CASE.md,
RAW_FORMATS.md and FORMAT.md. It never imports the generator's builders or in-memory data.

    validate(case_dir, extra_dir, truth_dir) -> list[str]     # empty list = valid
    python -m app.features.evidence.casegen.validate           # from backend/; PASS/FAIL per check, exit 1 on fail

Each check is a small function `check_<name>(ctx) -> list[str]`; every problem it returns starts with its name.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import mailbox
import re
import sys
from datetime import datetime
from email.utils import getaddresses
from functools import cached_property
from pathlib import Path
from typing import Callable

from . import world
from .csv_writer import HEADERS
from .world import (F_AUDIT, F_BADGE, F_CCTV, F_DEVICES, F_MAINT, F_MANIFEST, F_MBOX, F_PARKING, F_SEC,
                    F_SLACK_DIR, F_TXN, F_USB, F_WIFI, TAMPERED_FILE)

TS_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d-05:00$")
# Anything that looks like an ISO date-time (with or without seconds / offset) inside free text.
ISO_LIKE_RE = re.compile(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d)?(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z0-9-]+)")
URL_RE = re.compile(r"(?:https?://|www\.)([A-Za-z0-9.-]+)", re.I)
DOMAIN_RE = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+(?:com|org|net|edu|gov|io|co|ai|us|uk|de|info|biz|app|dev|me|ly|tv)\b",
                       re.I)
EVENT_ID_RE = re.compile(r"^e\d+$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

BINARY_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".zip"}
MANIFEST_HEADER = ["filename", "sha256", "collected_by", "collected_at"]
DEVICES_HEADER = ["device_id", "type", "room", "floor", "sweep"]
STATEMENTS = ["statements/hank_gibson.pdf", "statements/maggie_price.pdf", "statements/frederik_mendelssohn.pdf"]
SLACK_META = [f"{F_SLACK_DIR}/users.json", f"{F_SLACK_DIR}/channels.json", f"{F_SLACK_DIR}/dms.json"]
REQUIRED_CASE_FILES = [
    F_MANIFEST, world.F_BRIEF, F_DEVICES, F_BADGE, F_WIFI, F_USB, F_SEC, F_AUDIT, F_MBOX, F_TXN, F_CCTV, F_MAINT,
    *SLACK_META, *STATEMENTS,
]
SLACK_DAY_RE = re.compile(rf"^{F_SLACK_DIR}/[^/]+/\d{{4}}-\d\d-\d\d\.json$")
TRUTH_FILES = ["events_expected.json", "answer_key.json"]

# Time columns per CSV; the first one is the sort key.
TIME_COLS: dict[str, list[str]] = {
    F_BADGE: ["timestamp"], F_WIFI: ["timestamp"], F_SEC: ["TimeCreated"], F_AUDIT: ["timestamp"],
    F_CCTV: ["window_start", "window_end"], F_MAINT: ["start", "end"], F_TXN: ["timestamp"],
    F_PARKING: ["timestamp"],
}

HANK_BADGE, HANK_MAC, HANK_ACCOUNT, HANK_PERMIT = "40388", "02:1F:9A:10:00:02", "hgibson", "P-2088"
MAGGIE_BADGE, BG17_BADGE, FREDERIK_BADGE = "40392", "40417", "40455"
DAY = "2026-03-04"
TITAN = "C:\\Projects\\Titan\\"
HANK_STATEMENT, MAGGIE_STATEMENT = STATEMENTS[0], STATEMENTS[1]
MAX_REPORTED = 40  # per check and kind, so a systematic error does not print 8,000 lines


def _t(day: str, hms: str) -> str:
    return f"{day}T{hms}-05:00"


def _parse(text: str) -> datetime | None:
    if not isinstance(text, str) or not TS_RE.match(text):
        return None
    return datetime.fromisoformat(text)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cap(problems: list[str]) -> list[str]:
    if len(problems) <= MAX_REPORTED:
        return problems
    return problems[:MAX_REPORTED] + [f"{problems[0].split(':', 1)[0]}: ... and {len(problems) - MAX_REPORTED} more"]


class Ctx:
    """Lazy, cached readers over the raw files."""

    def __init__(self, case_dir: Path, extra_dir: Path, truth_dir: Path, evidence_dir: Path):
        self.case_dir, self.extra_dir, self.truth_dir = Path(case_dir), Path(extra_dir), Path(truth_dir)
        self.evidence_dir = Path(evidence_dir)
        self._text: dict[Path, str] = {}
        self._pdf: dict[Path, list[str]] = {}
        self._rows: dict[str, list[tuple[int, dict]]] = {}

    # ---------------------------------------------------------------- locating files
    def resolve(self, rel: str) -> Path | None:
        """Case-folder path -> file on disk: case folder first, then extra (extra sources use case paths)."""
        if not isinstance(rel, str) or not rel or rel.startswith("/") or ".." in rel.split("/"):
            return None
        for base in (self.case_dir, self.extra_dir):
            p = base / rel
            if p.is_file():
                return p
        return None

    def csv_path(self, rel: str) -> Path | None:
        base = self.extra_dir if rel in world.EXTRA_FILES else self.case_dir
        p = base / rel
        return p if p.is_file() else None

    @cached_property
    def case_files(self) -> list[str]:
        if not self.case_dir.is_dir():
            return []
        return sorted(p.relative_to(self.case_dir).as_posix() for p in self.case_dir.rglob("*") if p.is_file())

    def all_text_files(self) -> list[Path]:
        out = []
        for base in (self.case_dir, self.extra_dir, self.truth_dir):
            if base.is_dir():
                out += sorted(p for p in base.rglob("*") if p.is_file() and p.suffix.lower() not in BINARY_SUFFIXES)
        return out

    # ---------------------------------------------------------------- reading
    def text(self, path: Path) -> str:
        if path not in self._text:
            self._text[path] = path.read_bytes().decode("utf-8", errors="replace")
        return self._text[path]

    def lines(self, path: Path) -> list[str]:
        t = self.text(path)
        parts = t.split("\n")
        if t.endswith("\n"):
            parts = parts[:-1]
        return parts

    def pdf_lines(self, path: Path) -> list[str]:
        if path not in self._pdf:
            import pdfplumber

            with pdfplumber.open(str(path)) as pdf:
                text = "\n".join((page.extract_text() or "") for page in pdf.pages)
            self._pdf[path] = text.split("\n")
        return self._pdf[path]

    def doc_lines(self, path: Path) -> list[str]:
        return self.pdf_lines(path) if path.suffix.lower() == ".pdf" else self.lines(path)

    def rows(self, rel: str) -> list[tuple[int, dict]]:
        """(line number, {column: value}) for every data row of a CSV source; [] if missing."""
        if rel not in self._rows:
            p = self.csv_path(rel)
            out = []
            if p is not None:
                header = HEADERS[rel]
                for i, line in enumerate(self.lines(p)[1:], start=2):
                    if not line:
                        continue
                    vals = next(csv.reader([line]))
                    if len(vals) == len(header):
                        out.append((i, dict(zip(header, vals))))
            self._rows[rel] = out
        return self._rows[rel]

    def json(self, path: Path):
        return json.loads(self.text(path))

    @cached_property
    def answer_key(self) -> dict:
        p = self.truth_dir / "answer_key.json"
        try:
            d = self.json(p)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    @cached_property
    def events(self) -> list:
        p = self.truth_dir / "events_expected.json"
        try:
            d = self.json(p)
            return d if isinstance(d, list) else []
        except Exception:
            return []

    @cached_property
    def altered_lines(self) -> set[int]:
        tamper = self.answer_key.get("tamper") or {}
        lines = tamper.get("altered_lines") or []
        return {x for x in lines if isinstance(x, int)}

    @cached_property
    def inventory(self) -> list[dict]:
        with open(self.evidence_dir / "inventory.csv", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    @cached_property
    def layout(self) -> dict:
        return json.loads((self.evidence_dir / "layout_placeholder.json").read_text(encoding="utf-8"))

    @cached_property
    def manifest(self) -> list[list[str]]:
        p = self.case_dir / F_MANIFEST
        if not p.is_file():
            return []
        return list(csv.reader(io.StringIO(self.text(p), newline="")))

    @cached_property
    def mbox_messages(self) -> list:
        p = self.case_dir / F_MBOX
        if not p.is_file():
            return []
        box = mailbox.mbox(str(p), create=False)
        try:
            return list(box)
        finally:
            box.close()

    @cached_property
    def usb_devices(self) -> list[dict]:
        """RegRipper usbstor blocks: {line, header, serial, sn_line, sn_time, first_install}."""
        p = self.case_dir / F_USB
        if not p.is_file():
            return []
        devs: list[dict] = []
        cur = None
        for i, line in enumerate(self.lines(p), start=1):
            if line and not line[0].isspace() and "[" in line and line.rstrip().endswith("]"):
                cur = {"line": i, "header": line, "serial": None, "sn_line": None, "sn_time": None,
                       "first_install": None}
                devs.append(cur)
            elif cur is not None:
                s = line.strip()
                m = re.match(r"S/N:\s*(\S+)\s*\[([^\]]*)\]", s)
                if m:
                    cur["serial"], cur["sn_time"], cur["sn_line"] = m.group(1), m.group(2), i
                elif s.startswith("First InstallDate"):
                    cur["first_install"] = s.split(":", 1)[1].strip()
        return devs

    def statement_text(self, rel: str) -> str:
        p = self.case_dir / rel
        return "\n".join(self.pdf_lines(p)) if p.is_file() else ""

    def person_by(self, col: str, value: str) -> dict | None:
        return next((p for p in self.inventory if p.get(col) == value and value), None)


def quote_problem(ctx: Ctx, rel: str, line, quote) -> str | None:
    """None if `quote` is at `line` of case file `rel` under the FORMAT.md 3.2 rules, else why not."""
    path = ctx.resolve(rel)
    if path is None:
        return f"file {rel!r} not found in case or extra folder"
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        return f"{rel}: bad line {line!r}"
    lines = ctx.doc_lines(path)
    if line > len(lines):
        return f"{rel}:{line}: past end of file ({len(lines)} lines)"
    if quote is None:
        return None
    if not isinstance(quote, str) or not quote:
        return f"{rel}:{line}: bad quote {quote!r}"
    raw = lines[line - 1]
    suffix = path.suffix.lower()
    if suffix in (".mbox", ".json"):
        escaped = json.dumps(quote, ensure_ascii=False)[1:-1]
        ok = quote in raw or (suffix == ".json" and escaped in raw)
    else:  # csv, txt, pdf: whole line
        ok = raw == quote
    if not ok:
        return f"{rel}:{line}: quote {quote!r} != raw line {raw!r}"
    return None


# ===================================================================================================== checks

CHECKS: list[tuple[str, Callable[[Ctx], list[str]]]] = []


def check(fn):
    CHECKS.append((fn.__name__, fn))
    return fn


@check
def check_files_present(ctx: Ctx) -> list[str]:
    n = "check_files_present"
    out = []
    if not ctx.case_dir.is_dir():
        return [f"{n}: case folder {ctx.case_dir} missing"]
    for rel in REQUIRED_CASE_FILES:
        if not (ctx.case_dir / rel).is_file():
            out.append(f"{n}: missing case file {rel}")
    days = [f for f in ctx.case_files if SLACK_DAY_RE.match(f)]
    if not days:
        out.append(f"{n}: no Slack channel/day file under {F_SLACK_DIR}/<channel>/<YYYY-MM-DD>.json")
    if not (ctx.extra_dir / F_PARKING).is_file():
        out.append(f"{n}: missing extra file {F_PARKING} in {ctx.extra_dir}")
    if (ctx.case_dir / F_PARKING).exists():
        out.append(f"{n}: {F_PARKING} is inside the case folder (must be withheld in extra/)")
    case_res = ctx.case_dir.resolve()
    for label, d in (("extra", ctx.extra_dir), ("truth", ctx.truth_dir)):
        r = d.resolve()
        if r == case_res or case_res in r.parents:
            out.append(f"{n}: {label} folder {d} is inside the case folder")
    for name in TRUTH_FILES:
        if not (ctx.truth_dir / name).is_file():
            out.append(f"{n}: missing truth file {name}")
    for f in ctx.case_files:
        if f.rsplit("/", 1)[-1] in ("answer_key.json", "events_expected.json"):
            out.append(f"{n}: truth file {f} leaked into the case folder")
    allowed = set(REQUIRED_CASE_FILES)
    for f in ctx.case_files:
        if f in allowed or SLACK_DAY_RE.match(f) or re.match(r"^cctv/stills/[^/]+\.jpg$", f):
            continue
        out.append(f"{n}: unexpected file in case folder: {f}")
    return out


@check
def check_encoding(ctx: Ctx) -> list[str]:
    n = "check_encoding"
    out = []
    for p in ctx.all_text_files():
        b = p.read_bytes()
        if b.startswith(b"\xef\xbb\xbf"):
            out.append(f"{n}: {p}: has a UTF-8 BOM")
        try:
            b.decode("utf-8")
        except UnicodeDecodeError as e:
            out.append(f"{n}: {p}: not UTF-8 ({e})")
        crs = b.count(b"\r")
        if crs:
            out.append(f"{n}: {p}: contains {crs} CR (\\r) characters")
    return out


@check
def check_csv_headers(ctx: Ctx) -> list[str]:
    n = "check_csv_headers"
    out = []
    for rel, header in HEADERS.items():
        p = ctx.csv_path(rel)
        if p is None:
            out.append(f"{n}: {rel}: missing")
            continue
        lines = ctx.lines(p)
        if not lines or lines[0] != ",".join(header):
            out.append(f"{n}: {rel}: header {lines[0] if lines else ''!r} != {','.join(header)!r}")
        if not ctx.text(p).endswith("\n"):
            out.append(f"{n}: {rel}: does not end with a newline")
        bad = []
        for i, line in enumerate(lines[1:], start=2):
            if not line:
                bad.append(f"{n}: {rel}:{i}: empty line")
                continue
            vals = next(csv.reader([line]))
            if len(vals) != len(header):
                bad.append(f"{n}: {rel}:{i}: {len(vals)} columns, expected {len(header)}: {line!r}")
        out += _cap(bad)
        if len(lines) < 2:
            out.append(f"{n}: {rel}: no data rows")
    p = ctx.case_dir / F_DEVICES
    if p.is_file():
        lines = ctx.lines(p)
        if not lines or lines[0] != ",".join(DEVICES_HEADER):
            out.append(f"{n}: {F_DEVICES}: header {lines[0] if lines else ''!r} != {','.join(DEVICES_HEADER)!r}")
        src = ctx.evidence_dir / "devices.csv"
        if src.is_file():
            want = src.read_bytes().decode("utf-8").replace("\r\n", "\n")
            if ctx.text(p) != want:
                out.append(f"{n}: {F_DEVICES}: differs from data/evidence/devices.csv")
    return out


@check
def check_timestamps(ctx: Ctx) -> list[str]:
    n = "check_timestamps"
    out: list[str] = []
    bad: list[str] = []
    for rel, cols in TIME_COLS.items():
        for line, row in ctx.rows(rel):
            for c in cols:
                if not TS_RE.match(row[c]):
                    bad.append(f"{n}: {rel}:{line}: {c}={row[c]!r} is not YYYY-MM-DDTHH:MM:SS-05:00")
    out += _cap(bad)
    # free-text scan of every non-CSV text file (usbstor, mbox, Slack, manifest, truth)
    bad = []
    csv_paths = {ctx.csv_path(r) for r in HEADERS}
    for p in ctx.all_text_files():
        if p in csv_paths:
            continue
        for i, line in enumerate(ctx.lines(p), start=1):
            for m in ISO_LIKE_RE.finditer(line):
                if not TS_RE.match(m.group(0)):
                    bad.append(f"{n}: {p}:{i}: timestamp-like {m.group(0)!r} is not YYYY-MM-DDTHH:MM:SS-05:00")
    out += _cap(bad)
    # usbstor: every bracketed time and every InstallDate
    p = ctx.case_dir / F_USB
    if p.is_file():
        for i, line in enumerate(ctx.lines(p), start=1):
            for m in re.finditer(r"\[([^\]]*)\]", line):
                if m.group(1)[:1].isdigit() and not TS_RE.match(m.group(1)):
                    out.append(f"{n}: {F_USB}:{i}: bracket time {m.group(1)!r} bad")
            if "InstallDate" in line:
                v = line.split(":", 1)[1].strip() if ":" in line else ""
                if not TS_RE.match(v):
                    out.append(f"{n}: {F_USB}:{i}: InstallDate {v!r} bad")
    # mbox Date headers
    try:
        for msg in ctx.mbox_messages:
            d = msg.get("Date", "")
            if not str(d).rstrip().endswith("-0500"):
                out.append(f"{n}: {F_MBOX}: message {msg.get('Message-ID')} Date {d!r} does not end with -0500")
    except Exception as e:  # noqa: BLE001
        out.append(f"{n}: {F_MBOX}: cannot parse mbox ({e})")
    # Slack ts strings
    for f in ctx.case_files:
        if not SLACK_DAY_RE.match(f):
            continue
        try:
            msgs = ctx.json(ctx.case_dir / f)
        except Exception as e:  # noqa: BLE001
            out.append(f"{n}: {f}: not JSON ({e})")
            continue
        for m in msgs if isinstance(msgs, list) else []:
            if not isinstance(m, dict) or not re.match(r"^\d+\.\d{6}$", str(m.get("ts", ""))):
                out.append(f"{n}: {f}: message ts {m.get('ts') if isinstance(m, dict) else m!r} bad")
    return out


@check
def check_sorted(ctx: Ctx) -> list[str]:
    n = "check_sorted"
    out = []
    for rel, cols in TIME_COLS.items():
        prev = None
        for line, row in ctx.rows(rel):
            if rel == TAMPERED_FILE and line in ctx.altered_lines:
                continue
            t = _parse(row[cols[0]])
            if t is None:
                continue
            if prev is not None and t < prev[1]:
                out.append(f"{n}: {rel}:{line}: {cols[0]} {row[cols[0]]} is before line {prev[0]}")
            prev = (line, t)
    return _cap(out)


@check
def check_manifest(ctx: Ctx) -> list[str]:
    n = "check_manifest"
    rows = ctx.manifest
    if not rows:
        return [f"{n}: {F_MANIFEST} missing or empty"]
    out = []
    if rows[0] != MANIFEST_HEADER:
        out.append(f"{n}: header {rows[0]} != {MANIFEST_HEADER}")
    seen: dict[str, str] = {}
    for i, r in enumerate(rows[1:], start=2):
        if len(r) != 4:
            out.append(f"{n}: line {i}: {len(r)} columns: {r}")
            continue
        fname, sha, by, at = r
        if fname in seen:
            out.append(f"{n}: line {i}: duplicate row for {fname}")
        seen[fname] = sha
        if not SHA_RE.match(sha):
            out.append(f"{n}: line {i}: sha256 {sha!r} is not lowercase hex")
        if not by.strip():
            out.append(f"{n}: line {i}: empty collected_by")
        if not TS_RE.match(at):
            out.append(f"{n}: line {i}: collected_at {at!r} is not YYYY-MM-DDTHH:MM:SS-05:00")
        p = ctx.case_dir / fname
        if fname == F_MANIFEST:
            out.append(f"{n}: line {i}: manifest lists itself")
        elif not p.is_file():
            out.append(f"{n}: line {i}: {fname} listed but not in the case folder")
        else:
            disk = _sha(p)
            if fname == TAMPERED_FILE and disk == sha:
                out.append(f"{n}: {fname}: hash matches the manifest but must not (C8 tamper missing)")
            elif fname != TAMPERED_FILE and disk != sha:
                out.append(f"{n}: {fname}: sha256 on disk {disk} != manifest {sha}")
    for f in ctx.case_files:
        if f != F_MANIFEST and f not in seen:
            out.append(f"{n}: case file {f} has no manifest row")
    if TAMPERED_FILE not in seen:
        out.append(f"{n}: no manifest row for the tampered file {TAMPERED_FILE}")
    return out


@check
def check_truth_quotes(ctx: Ctx) -> list[str]:
    n = "check_truth_quotes"
    p = ctx.truth_dir / "events_expected.json"
    try:
        evs = ctx.json(p)
    except Exception as e:  # noqa: BLE001
        return [f"{n}: cannot read {p} ({e})"]
    if not isinstance(evs, list) or not evs:
        return [f"{n}: events_expected.json is not a non-empty array"]
    out: list[str] = []
    ids: set[str] = set()
    cited: set[tuple[Path, int]] = set()
    shas: dict[Path, str] = {}
    for k, e in enumerate(evs):
        if not isinstance(e, dict):
            out.append(f"{n}: event #{k} is not an object")
            continue
        eid = e.get("id")
        tag = f"event {eid!r}"
        if not isinstance(eid, str) or not EVENT_ID_RE.match(eid):
            out.append(f"{n}: {tag}: id is not e<number>")
        elif eid in ids:
            out.append(f"{n}: {tag}: duplicate id")
        ids.add(eid)
        if not TS_RE.match(str(e.get("t"))):
            out.append(f"{n}: {tag}: t {e.get('t')!r} is not YYYY-MM-DDTHH:MM:SS-05:00")
        src = e.get("source")
        if not isinstance(src, dict):
            out.append(f"{n}: {tag}: no source object")
            continue
        rel = src.get("file")
        path = ctx.resolve(rel)
        if path is None:
            out.append(f"{n}: {tag}: source.file {rel!r} not found in case or extra folder")
            continue
        if path not in shas:
            shas[path] = _sha(path)
        if src.get("sha256") != shas[path]:
            out.append(f"{n}: {tag}: source.sha256 of {rel} != sha256 of the file on disk")
        prob = quote_problem(ctx, rel, src.get("line"), src.get("quote"))
        if src.get("quote") is None:
            prob = prob or f"{rel}:{src.get('line')}: quote is null"
        if prob:
            out.append(f"{n}: {tag}: {prob}")
        if isinstance(src.get("line"), int):
            cited.add((path, src["line"]))
    # every CSV data row is cited by at least one event (cctv RECORDING rows excepted)
    uncited = []
    for rel in HEADERS:
        path = ctx.csv_path(rel)
        if path is None:
            continue
        for line, row in ctx.rows(rel):
            if rel == F_CCTV and row["status"] == "RECORDING":
                continue
            if (path, line) not in cited:
                uncited.append(f"{n}: {rel}:{line}: row not cited by any expected event")
    return _cap(out) + _cap(uncited)


@check
def check_answer_key(ctx: Ctx) -> list[str]:
    n = "check_answer_key"
    p = ctx.truth_dir / "answer_key.json"
    try:
        key = ctx.json(p)
    except Exception as e:  # noqa: BLE001
        return [f"{n}: cannot read {p} ({e})"]
    if not isinstance(key, dict):
        return [f"{n}: answer_key.json is not an object"]
    out = []
    if key.get("case_id") != "1010F":
        out.append(f"{n}: case_id {key.get('case_id')!r} != '1010F'")
    person_ids = {r["person_id"] for r in ctx.inventory}
    planted = key.get("planted") or []
    ids = [c.get("id") for c in planted if isinstance(c, dict)]
    want = [f"C{i}" for i in range(1, 9)]
    for cid in want:
        if ids.count(cid) != 1:
            out.append(f"{n}: {cid} appears {ids.count(cid)} times (expected exactly once)")
    for cid in ids:
        if cid not in want:
            out.append(f"{n}: unexpected planted id {cid!r}")
    for c in planted:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if c.get("kind") not in ("physical", "temporal", "statement", "custody"):
            out.append(f"{n}: {cid}: kind {c.get('kind')!r} invalid")
        for pid in c.get("persons") or []:
            if pid not in person_ids:
                out.append(f"{n}: {cid}: person {pid!r} not in inventory.csv")
        sources = c.get("sources") or []
        if not sources:
            out.append(f"{n}: {cid}: no sources")
        for s in sources:
            if not isinstance(s, dict):
                out.append(f"{n}: {cid}: source {s!r} is not an object")
                continue
            rel, line, quote = s.get("file"), s.get("line"), s.get("quote")
            if line is None and quote is None:  # file-level source (C8)
                if ctx.resolve(rel) is None:
                    out.append(f"{n}: {cid}: file {rel!r} not found")
                continue
            prob = quote_problem(ctx, rel, line, quote)
            if prob:
                out.append(f"{n}: {cid}: {prob}")
    fa = key.get("false_alarm_persons") or []
    for pid in ("p_frederik", "p_bg_17"):
        if pid not in fa:
            out.append(f"{n}: false_alarm_persons lacks {pid}")
    tamper = key.get("tamper") or {}
    if tamper.get("file") != TAMPERED_FILE:
        out.append(f"{n}: tamper.file {tamper.get('file')!r} != {TAMPERED_FILE!r}")
    if not isinstance(tamper.get("seed"), int):
        out.append(f"{n}: tamper.seed {tamper.get('seed')!r} is not an int")
    altered = tamper.get("altered_lines")
    if not isinstance(altered, list) or not altered:
        out.append(f"{n}: tamper.altered_lines is empty")
        altered = []
    if any(not isinstance(x, int) or isinstance(x, bool) or x < 2 for x in altered):
        out.append(f"{n}: tamper.altered_lines {altered} has non-data line numbers")
    logon = [ln for ln, r in ctx.rows(F_SEC) if r["EventID"] == "4624" and r["TargetUserName"] == HANK_ACCOUNT
             and r["TimeCreated"].startswith(DAY)]
    if not logon:
        out.append(f"{n}: Hank's {DAY} 4624 logon row is missing from {F_SEC}")
    for ln in logon:
        if ln in altered:
            out.append(f"{n}: tamper.altered_lines includes Hank's {DAY} logon row (line {ln})")
    return out


def _person_reads(ctx: Ctx, badge: str, day: str) -> list[tuple[int, dict]]:
    return [(ln, r) for ln, r in ctx.rows(F_BADGE) if r["badge_id"] == badge and r["timestamp"].startswith(day)]


def _has_row(ctx: Ctx, rel: str, **want) -> bool:
    return any(all(r[k] == v for k, v in want.items()) for _, r in ctx.rows(rel))


@check
def check_C1(ctx: Ctx) -> list[str]:
    n = "check_C1"
    out = []
    reads = _person_reads(ctx, HANK_BADGE, DAY)
    out_t = _t(DAY, "18:02:00")
    disc_t = _t(DAY, "18:41:00")
    if not reads:
        return [f"{n}: no badge {HANK_BADGE} reads on {DAY}"]
    last = reads[-1][1]
    if (last["timestamp"], last["reader_id"], last["direction"]) != (out_t, "rdr-217", "OUT"):
        out.append(f"{n}: last {DAY} read of {HANK_BADGE} is {last} (expected OUT rdr-217 {out_t})")
    wifi = [r for _, r in ctx.rows(F_WIFI) if r["client_mac"] == HANK_MAC and r["timestamp"].startswith(DAY)]
    after = [r for r in wifi if out_t < r["timestamp"] < disc_t]
    if not after:
        out.append(f"{n}: no Wi-Fi events of {HANK_MAC} between {out_t} and {disc_t}")
    if not any(r["timestamp"] == disc_t and r["event"] == "DISASSOC" for r in wifi):
        out.append(f"{n}: no DISASSOC of {HANK_MAC} at {disc_t}")
    later = [r for r in wifi if r["timestamp"] > disc_t]
    if later:
        out.append(f"{n}: {len(later)} Wi-Fi events of {HANK_MAC} after {disc_t} (first {later[0]['timestamp']})")
    between = [r for _, r in reads if out_t < r["timestamp"] <= disc_t]
    if between:
        out.append(f"{n}: badge {HANK_BADGE} read between {out_t} and {disc_t}: {between[0]}")
    return out


@check
def check_C2(ctx: Ctx) -> list[str]:
    n = "check_C2"
    out = []
    for hms, rdr in (("18:16:10", "rdr-230"), ("18:16:40", "rdr-219")):
        if not _has_row(ctx, F_BADGE, timestamp=_t(DAY, hms), badge_id=BG17_BADGE, reader_id=rdr, direction="IN"):
            out.append(f"{n}: no badge {BG17_BADGE} IN at {rdr} {_t(DAY, hms)}")
    walk = (ctx.layout.get("walk_s") or {}).get("230-219")
    if not isinstance(walk, (int, float)) or walk <= 30:
        out.append(f"{n}: layout walk_s['230-219'] = {walk!r}, must be > 30 s")
    return out


@check
def check_C3(ctx: Ctx) -> list[str]:
    n = "check_C3"
    out = []
    if not _has_row(ctx, F_PARKING, timestamp=_t(DAY, "18:44:00"), permit_id=HANK_PERMIT, direction="OUT"):
        out.append(f"{n}: extra {F_PARKING} has no {HANK_PERMIT} OUT at {_t(DAY, '18:44:00')}")
    if "I went straight home at six." not in ctx.statement_text(HANK_STATEMENT):
        out.append(f"{n}: {HANK_STATEMENT} lacks 'I went straight home at six.'")
    return out


@check
def check_C4(ctx: Ctx) -> list[str]:
    n = "check_C4"
    out = []
    reads = _person_reads(ctx, MAGGIE_BADGE, DAY)
    want = (_t(DAY, "17:45:00"), "rdr-217", "OUT")
    if not reads or (reads[-1][1]["timestamp"], reads[-1][1]["reader_id"], reads[-1][1]["direction"]) != want:
        out.append(f"{n}: last {DAY} read of {MAGGIE_BADGE} is {reads[-1][1] if reads else None} (expected {want})")
    if "Hank and I left together around 6:30." not in ctx.statement_text(MAGGIE_STATEMENT):
        out.append(f"{n}: {MAGGIE_STATEMENT} lacks 'Hank and I left together around 6:30.'")
    return out


def _body(msg) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    out = []
    for part in parts:
        if part.get_content_maintype() == "text":
            raw = part.get_payload(decode=True) or b""
            out.append(raw.decode(part.get_content_charset() or "utf-8", errors="replace"))
    return "\n".join(out)


@check
def check_C5(ctx: Ctx) -> list[str]:
    n = "check_C5"
    out = []
    hank, alma = "hank.gibson@halvorsen.example", "alma.imhoff@halvorsen.example"
    found = False
    for msg in ctx.mbox_messages:
        frm = [a.lower() for _, a in getaddresses([str(msg.get("From", ""))])]
        to = [a.lower() for _, a in getaddresses([str(v) for v in msg.get_all("To", [])])]
        if hank in frm and alma in to and "I never touched the Titan folder." in _body(msg):
            found = True
    if not found:
        out.append(f"{n}: no email from {hank} to {alma} containing 'I never touched the Titan folder.'")
    lo, hi = _t(DAY, "18:16:00"), _t(DAY, "18:32:00")
    copies = [r for _, r in ctx.rows(F_AUDIT) if r["user"] == HANK_ACCOUNT and r["action"] == "COPY"
              and r["path"].startswith(TITAN) and r["target_volume"] == "E:" and lo <= r["timestamp"] <= hi]
    if not copies:
        out.append(f"{n}: {F_AUDIT} has no {HANK_ACCOUNT} COPY of {TITAN}* to E: between {lo} and {hi}")
    sec = [r for _, r in ctx.rows(F_SEC) if r["EventID"] == "4663" and r["TargetUserName"] == HANK_ACCOUNT
           and r["ObjectName"].startswith(TITAN) and r["TimeCreated"].startswith(DAY)
           and r["TimeCreated"] >= _t(DAY, "17:00:00")]
    if not sec:
        out.append(f"{n}: {F_SEC} has no {HANK_ACCOUNT} 4663 on {TITAN}* on the evening of {DAY}")
    return out


@check
def check_C6(ctx: Ctx) -> list[str]:
    n = "check_C6"
    out = []
    planted = ("cam-03", _t(DAY, "18:05:00"), _t(DAY, "18:30:00"))
    offline = [(ln, r) for ln, r in ctx.rows(F_CCTV) if r["status"] == "OFFLINE"]
    if not any((r["camera_id"], r["window_start"], r["window_end"]) == planted for _, r in offline):
        out.append(f"{n}: {F_CCTV} has no cam-03 OFFLINE {planted[1]}..{planted[2]}")
    orders = [r for _, r in ctx.rows(F_MAINT)]
    for r in orders:
        if r["asset"] == "cam-03":
            out.append(f"{n}: {F_MAINT} has work order {r['work_order']} for cam-03")
    for ln, r in offline:
        if (r["camera_id"], r["window_start"], r["window_end"]) == planted:
            continue
        covered = any(w["asset"] == r["camera_id"] and w["start"] <= r["window_start"]
                      and r["window_end"] <= w["end"] for w in orders)
        if not covered:
            out.append(f"{n}: {F_CCTV}:{ln}: {r['camera_id']} OFFLINE {r['window_start']}..{r['window_end']}"
                       " is not inside a work order for that camera")
    return out


@check
def check_C7(ctx: Ctx) -> list[str]:
    n = "check_C7"
    out = []
    devs = ctx.usb_devices
    if not devs:
        return [f"{n}: no devices parsed from {F_USB}"]
    for d in devs:
        if not d["serial"] or not d["first_install"]:
            out.append(f"{n}: {F_USB}:{d['line']}: block without S/N or First InstallDate")
    serials = [d["serial"] for d in devs if d["serial"]]
    for s in sorted({s for s in serials if serials.count(s) > 1}):
        out.append(f"{n}: serial {s} appears in more than one block")
    night = [d for d in devs if (d["first_install"] or "").startswith(DAY)]
    if len(night) != 1:
        out.append(f"{n}: {len(night)} devices first installed on {DAY} (expected exactly 1)")
    elif night[0]["sn_time"] != _t(DAY, "18:17:30"):
        out.append(f"{n}: the {DAY} device's S/N time is {night[0]['sn_time']!r}, expected {_t(DAY, '18:17:30')}")
    if not any((d["first_install"] or "").startswith("2025-") for d in devs):
        out.append(f"{n}: no device first installed in 2025")
    if "IT gave me that drive last year." not in ctx.statement_text(HANK_STATEMENT):
        out.append(f"{n}: {HANK_STATEMENT} lacks 'IT gave me that drive last year.'")
    return out


@check
def check_C8(ctx: Ctx) -> list[str]:
    n = "check_C8"
    out = []
    listed = {r[0]: r[1] for r in ctx.manifest[1:] if len(r) == 4}
    p = ctx.case_dir / TAMPERED_FILE
    if TAMPERED_FILE not in listed or not p.is_file():
        out.append(f"{n}: {TAMPERED_FILE} missing from manifest or case folder")
    elif _sha(p) == listed[TAMPERED_FILE]:
        out.append(f"{n}: {TAMPERED_FILE} hash matches the manifest (no custody break)")
    c8 = [c for c in ctx.answer_key.get("planted") or [] if isinstance(c, dict) and c.get("id") == "C8"]
    if c8 and not any(isinstance(s, dict) and s.get("file") == TAMPERED_FILE for s in c8[0].get("sources") or []):
        out.append(f"{n}: answer key C8 does not cite {TAMPERED_FILE}")
    return out


@check
def check_red_herrings(ctx: Ctx) -> list[str]:
    n = "check_red_herrings"
    out = []
    start, end = _t(DAY, "19:00:00"), _t(DAY, "21:30:00")
    if not _has_row(ctx, F_MAINT, asset="lt-219", start=start, end=end, technician="Frederik Mendelssohn"):
        out.append(f"{n}: {F_MAINT} has no lt-219 work order {start}..{end} by Frederik Mendelssohn")
    reads = [r for _, r in _person_reads(ctx, FREDERIK_BADGE, DAY) if r["reader_id"] == "rdr-219"]

    def near(r, target, direction):
        t, tt = _parse(r["timestamp"]), _parse(target)
        return r["direction"] == direction and t is not None and abs((t - tt).total_seconds()) <= 15 * 60

    if not any(near(r, start, "IN") for r in reads):
        out.append(f"{n}: no badge {FREDERIK_BADGE} IN at rdr-219 within 15 min of {start}")
    if not any(near(r, end, "OUT") for r in reads):
        out.append(f"{n}: no badge {FREDERIK_BADGE} OUT at rdr-219 within 15 min of {end}")
    return out


@check
def check_access_rules(ctx: Ctx) -> list[str]:
    n = "check_access_rules"
    out = []
    by_badge = {p["badge"]: p for p in ctx.inventory if p["badge"]}
    readers = set()
    p = ctx.case_dir / F_DEVICES
    if p.is_file():
        readers = {line.split(",")[0] for line in ctx.lines(p)[1:] if line.split(",")[1:2] == ["badge_reader"]}
    for ln, r in ctx.rows(F_BADGE):
        person = by_badge.get(r["badge_id"])
        if person is None:
            out.append(f"{n}: {F_BADGE}:{ln}: badge {r['badge_id']} not in inventory.csv")
            continue
        if readers and r["reader_id"] not in readers:
            out.append(f"{n}: {F_BADGE}:{ln}: reader {r['reader_id']} not in {F_DEVICES}")
        rooms = set(filter(None, person["authorized_rooms"].split(";")))
        if r["reader_id"] == "rdr-219" and "219" not in rooms:
            out.append(f"{n}: {F_BADGE}:{ln}: badge {r['badge_id']} ({person['person_id']}) at rdr-219 "
                       "but 219 is not in its authorized_rooms")
        for rev in filter(None, person["revoked"].split(";")):
            room, _, when = rev.partition("@")
            if r["reader_id"] == f"rdr-{room}" and r["timestamp"] > when:
                out.append(f"{n}: {F_BADGE}:{ln}: badge {r['badge_id']} ({person['person_id']}) at rdr-{room} "
                           f"after its revocation {when}")
    if not any(rev.startswith("219@2026-03-02T17:00:00-05:00")
               for rev in (ctx.person_by("badge", HANK_BADGE) or {}).get("revoked", "").split(";")):
        out.append(f"{n}: inventory.csv lacks Hank's 219@2026-03-02T17:00:00-05:00 revocation")
    return _cap(out)


@check
def check_badge_wifi_consistency(ctx: Ctx) -> list[str]:
    n = "check_badge_wifi_consistency"
    out = []
    by_badge = {p["badge"]: p["person_id"] for p in ctx.inventory if p["badge"]}
    by_mac = {p["laptop_mac"]: p["person_id"] for p in ctx.inventory if p["laptop_mac"]}
    span: dict[tuple[str, str], list] = {}
    for _, r in ctx.rows(F_BADGE):
        pid = by_badge.get(r["badge_id"])
        if pid is None:
            continue
        s = span.setdefault((pid, r["timestamp"][:10]), [None, None])
        if r["direction"] == "IN" and (s[0] is None or r["timestamp"] < s[0]):
            s[0] = r["timestamp"]
        if r["direction"] == "OUT" and (s[1] is None or r["timestamp"] > s[1]):
            s[1] = r["timestamp"]
    hank_lo, hank_hi = _t(DAY, "18:02:00"), _t(DAY, "18:41:00")
    for ln, r in ctx.rows(F_WIFI):
        pid = by_mac.get(r["client_mac"])
        t = r["timestamp"]
        if pid is None:
            out.append(f"{n}: {F_WIFI}:{ln}: MAC {r['client_mac']} not in inventory.csv")
            continue
        if pid == "p_hank" and hank_lo < t <= hank_hi:
            continue  # planted C1
        first_in, last_out = span.get((pid, t[:10]), [None, None])
        if first_in is None or last_out is None:
            out.append(f"{n}: {F_WIFI}:{ln}: {pid} on Wi-Fi at {t} but has no badge IN/OUT that day")
        elif not first_in <= t <= last_out:
            out.append(f"{n}: {F_WIFI}:{ln}: {pid} on Wi-Fi at {t} outside badge span {first_in}..{last_out}")
    return _cap(out)


@check
def check_no_real_domains(ctx: Ctx) -> list[str]:
    n = "check_no_real_domains"
    out = []
    sources: list[tuple[str, str]] = []
    for base in (ctx.case_dir, ctx.extra_dir):
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            if p.suffix.lower() == ".pdf":
                try:
                    sources.append((str(p), "\n".join(ctx.pdf_lines(p))))
                except Exception as e:  # noqa: BLE001
                    out.append(f"{n}: {p}: cannot read PDF ({e})")
            elif p.suffix.lower() not in BINARY_SUFFIXES:
                sources.append((str(p), ctx.text(p)))
    for name, text in sources:
        bad = set()
        for m in EMAIL_RE.finditer(text):
            if not m.group(1).lower().endswith(".example"):
                bad.add(m.group(0))
        for m in URL_RE.finditer(text):
            if not m.group(1).lower().rstrip(".").endswith(".example"):
                bad.add(m.group(0))
        for m in DOMAIN_RE.finditer(text):
            bad.add(m.group(0))
        for b in sorted(bad):
            out.append(f"{n}: {name}: non-.example address/domain {b!r}")
    return _cap(out)


# ===================================================================================================== API


def run_checks(case_dir: Path = world.CASE_DIR, extra_dir: Path = world.EXTRA_DIR,
               truth_dir: Path = world.TRUTH_DIR, evidence_dir: Path = world.EVIDENCE) -> list[tuple[str, list[str]]]:
    ctx = Ctx(case_dir, extra_dir, truth_dir, evidence_dir)
    results = []
    for name, fn in CHECKS:
        try:
            probs = fn(ctx)
        except Exception as e:  # noqa: BLE001 - a crash is a problem with the files, not with the caller
            probs = [f"{name}: crashed: {type(e).__name__}: {e}"]
        results.append((name, probs))
    return results


def validate(case_dir: Path = world.CASE_DIR, extra_dir: Path = world.EXTRA_DIR,
             truth_dir: Path = world.TRUTH_DIR, evidence_dir: Path = world.EVIDENCE) -> list[str]:
    """Every problem found in the raw files; empty list = the case is valid."""
    return [p for _, probs in run_checks(case_dir, extra_dir, truth_dir, evidence_dir) for p in probs]


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Validate the generated Case 1010F raw files.")
    ap.add_argument("--case", type=Path, default=world.CASE_DIR)
    ap.add_argument("--extra", type=Path, default=world.EXTRA_DIR)
    ap.add_argument("--truth", type=Path, default=world.TRUTH_DIR)
    args = ap.parse_args(argv)
    total = 0
    for name, probs in run_checks(args.case, args.extra, args.truth):
        print(f"{'PASS' if not probs else 'FAIL'}  {name}" + (f"  ({len(probs)} problems)" if probs else ""))
        for p in probs:
            print(f"      {p}")
        total += len(probs)
    print(f"\n{'VALID' if not total else 'INVALID'}: {total} problems")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
