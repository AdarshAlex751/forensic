"""Checks the evidence slice's output files against data/evidence/FORMAT.md.

Runs on two locations:
  * fake  -> data/evidence/fake/  (events.json, events_extra.json, events_baseline.json, evidence.json, case.json)
  * real  -> data/evidence/       (events.json, evidence.json, case.json)
Missing files are skipped, so the same test runs on the fakes now and on the real output later.
devices.csv and inventory.csv are checked directly in data/evidence/, the fake answer key in data/evidence/fake/.

Every test collects all problems and reports the first few, so one failure shows many bad items.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

# --------------------------------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "data" / "evidence"
FAKE_DIR = EVIDENCE_DIR / "fake"
CASE_DIR = EVIDENCE_DIR / "CASE-1010F"

DEVICES_CSV = EVIDENCE_DIR / "devices.csv"
INVENTORY_CSV = EVIDENCE_DIR / "inventory.csv"
ANSWER_KEY_JSON = EVIDENCE_DIR / "fake" / "answer_key.json"  # the fake key; the real key (data/evidence/answer_key.json) is checked by casegen/validate.py

# name -> (folder, event files in that folder, event files that count toward evidence.json records)
LOCATIONS: dict[str, dict[str, Any]] = {
    "fake": {
        "dir": FAKE_DIR,
        "event_files": ["events.json", "events_baseline.json", "events_extra.json"],
        "record_files": ["events.json", "events_baseline.json"],
    },
    "real": {
        "dir": EVIDENCE_DIR,
        "event_files": ["events.json"],
        "record_files": ["events.json"],
    },
}
LOCATION_NAMES = list(LOCATIONS)

# Files that may be cited by events but be missing from evidence.json until released.
MAY_BE_UNRELEASED = {"access/parking_exit.csv"}

MAX_REPORT = 10

# --------------------------------------------------------------------------------------------------
# FORMAT.md tables as Python data
# --------------------------------------------------------------------------------------------------

EVENT_KEYS = {"id", "t", "type", "person", "device", "room", "actor", "attrs", "source"}
SOURCE_KEYS = {"file", "line", "quote", "sha256"}
ACTOR_KINDS = {"badge", "mac", "account", "email", "slack", "permit", "name"}

# FORMAT.md 3.1: type -> (source file or prefix, expected actor.kind or None, attrs keys)
EVENT_TYPES: dict[str, tuple[str, str | None, set[str]]] = {
    "badge_in": ("access/badge_access.csv", "badge", {"reader", "result"}),
    "badge_out": ("access/badge_access.csv", "badge", {"reader", "result"}),
    "wifi_assoc": ("network/wifi_ap_logs.csv", "mac", {"ap", "rssi", "ssid"}),
    "wifi_disassoc": ("network/wifi_ap_logs.csv", "mac", {"ap", "rssi", "ssid"}),
    "wifi_roam": ("network/wifi_ap_logs.csv", "mac", {"ap", "rssi", "ssid"}),
    "logon": ("endpoint/security_log.csv", "account", {"event_id", "logon_type", "host"}),
    "logoff": ("endpoint/security_log.csv", "account", {"event_id", "host"}),
    "file_access": ("endpoint/security_log.csv", "account", {"event_id", "path", "access_mask", "host"}),
    "file_read": ("endpoint/file_audit.csv", "account", {"path", "bytes", "target_volume", "host"}),
    "file_copy": ("endpoint/file_audit.csv", "account", {"path", "bytes", "target_volume", "host"}),
    "usb_mount": ("endpoint/usbstor.txt", None, {"serial", "vendor", "product", "first_seen", "host"}),
    "camera_offline": ("cctv/index.csv", None, {"camera", "clip_ref"}),
    "camera_online": ("cctv/index.csv", None, {"camera", "clip_ref"}),
    "maintenance_window": (
        "it/maintenance_calendar.csv",
        "name",
        {"start", "end", "asset", "work_order", "technician"},
    ),
    "email": ("comms/mailbox.mbox", "email", {"from", "to", "subject", "message_id"}),
    "chat": ("comms/slack_export/", "slack", {"channel", "ts"}),
    "statement": ("statements/", "name", {"speaker", "page"}),
    "transaction": (
        "financial/transactions.csv",
        "account",
        {"account", "amount", "counterparty", "description"},
    ),
    "parking_entry": ("access/parking_exit.csv", "permit", {"plate", "lane"}),
    "parking_exit": ("access/parking_exit.csv", "permit", {"plate", "lane"}),
}

EVIDENCE_KEYS = {"file", "sha256", "manifest_sha256", "manifest_match", "parser", "records"}
PARSERS = {"csv", "text", "mbox", "slack_json", "pdf", "image"}

CASE_KEYS = {"id", "title", "address", "summary", "costar_property_id", "matterport_model_id"}

DEVICES_HEADER = ["device_id", "type", "room", "floor", "sweep"]
DEVICE_TYPES = {"badge_reader", "wifi_ap", "camera", "laptop"}

INVENTORY_HEADER = (
    "person_id,name,role,home_room,email,badge,laptop_mac,parking_permit,plate,"
    "local_account,bank_account,slack_handle,authorized_rooms,revoked"
).split(",")

CONTRADICTION_KINDS = {"physical", "temporal", "statement", "custody"}
PLANTED_IDS = [f"C{i}" for i in range(1, 9)]

TIME_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d-05:00$")
EVENT_ID_RE = re.compile(r"^e\d+$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

# Raw CSV headers (RAW_FORMATS.md), used to read quote fields by name.
RAW_CSV_HEADERS: dict[str, list[str]] = {
    "access/badge_access.csv": ["timestamp", "badge_id", "reader_id", "direction", "result"],
    "network/wifi_ap_logs.csv": ["timestamp", "ap_id", "client_mac", "event", "rssi", "ssid"],
    "endpoint/security_log.csv": [
        "TimeCreated", "EventID", "Computer", "TargetUserName", "LogonType",
        "ObjectName", "AccessMask", "ProcessName",
    ],
    "endpoint/file_audit.csv": ["timestamp", "host", "user", "action", "path", "bytes", "target_volume"],
    "cctv/index.csv": ["camera_id", "window_start", "window_end", "status", "clip_ref"],
    "it/maintenance_calendar.csv": ["work_order", "asset", "start", "end", "technician", "description"],
    "financial/transactions.csv": ["timestamp", "account", "description", "counterparty", "amount", "balance"],
    "access/parking_exit.csv": ["timestamp", "lane", "permit_id", "plate", "direction"],
}

# --------------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------------


def load_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        pytest.skip(f"{path.relative_to(REPO_ROOT)} does not exist yet")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        pytest.fail(f"{path.relative_to(REPO_ROOT)} is not valid JSON: {exc}")


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Return (header, rows) with rows as dicts. Skips the test if the file is missing."""
    if not path.exists():
        pytest.skip(f"{path.relative_to(REPO_ROOT)} does not exist yet")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        rows = [dict(zip(header, r)) for r in reader if r]
    return header, rows


def split_csv_line(line: str) -> list[str]:
    return next(csv.reader(io.StringIO(line)), [])


def report(problems: list[str], what: str) -> None:
    __tracebackhide__ = True
    if problems:
        shown = "\n  ".join(problems[:MAX_REPORT])
        more = f"\n  ... and {len(problems) - MAX_REPORT} more" if len(problems) > MAX_REPORT else ""
        pytest.fail(f"{len(problems)} problem(s) in {what}:\n  {shown}{more}")


def ev_label(fname: str, idx: int, ev: Any) -> str:
    eid = ev.get("id") if isinstance(ev, dict) else None
    return f"{fname}[{idx}] id={eid!r}"


def location_event_files(loc: str) -> dict[str, list[Any]]:
    """{file name: list of events} for the event files that exist in this location; skip if none."""
    info = LOCATIONS[loc]
    out: dict[str, list[Any]] = {}
    for name in info["event_files"]:
        path = info["dir"] / name
        if not path.exists():
            continue
        data = load_json(path)
        if not isinstance(data, list):
            pytest.fail(f"{path.relative_to(REPO_ROOT)} top level must be an array, got {type(data).__name__}")
        out[name] = data
    if not out:
        pytest.skip(f"no event files in {loc} location yet")
    return out


def iter_events(files: dict[str, list[Any]]):
    for fname, events in files.items():
        for idx, ev in enumerate(events):
            yield fname, idx, ev


def iter_dict_events(files: dict[str, list[Any]]):
    for fname, idx, ev in iter_events(files):
        if isinstance(ev, dict):
            yield fname, idx, ev


def get_source(ev: dict) -> dict:
    src = ev.get("source")
    return src if isinstance(src, dict) else {}


def device_rows() -> list[dict[str, str]]:
    if not DEVICES_CSV.exists():
        return []
    return load_csv(DEVICES_CSV)[1]


def device_ids() -> set[str]:
    return {r.get("device_id", "") for r in device_rows()}


def room_ids() -> set[str]:
    return {r.get("room", "") for r in device_rows() if r.get("room")}


def is_csv(file: str) -> bool:
    return file.lower().endswith(".csv")


# --------------------------------------------------------------------------------------------------
# Encoding (section 2)
# --------------------------------------------------------------------------------------------------

def _all_output_files() -> list[Path]:
    files = [DEVICES_CSV, INVENTORY_CSV, ANSWER_KEY_JSON]
    for info in LOCATIONS.values():
        d = info["dir"]
        files += [d / n for n in info["event_files"]] + [d / "evidence.json", d / "case.json"]
    return files


@pytest.mark.parametrize("path", _all_output_files(), ids=lambda p: str(p.relative_to(EVIDENCE_DIR)))
def test_utf8_no_bom(path: Path):
    if not path.exists():
        pytest.skip(f"{path.relative_to(REPO_ROOT)} does not exist yet")
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{path.name} starts with a UTF-8 BOM"
    raw.decode("utf-8")


# --------------------------------------------------------------------------------------------------
# events (section 3)
# --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_keys(loc):
    files = location_event_files(loc)
    problems = []
    for fname, idx, ev in iter_events(files):
        if not isinstance(ev, dict):
            problems.append(f"{fname}[{idx}] is not an object")
            continue
        keys = set(ev)
        if "verified" in keys:
            problems.append(f"{ev_label(fname, idx, ev)}: 'verified' must be absent (merge step sets it)")
        missing = EVENT_KEYS - keys
        extra = keys - EVENT_KEYS - {"verified"}
        if missing or extra:
            problems.append(f"{ev_label(fname, idx, ev)}: missing={sorted(missing)} extra={sorted(extra)}")
    report(problems, f"{loc} event keys")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_ids(loc):
    files = location_event_files(loc)
    problems = []
    seen: dict[str, str] = {}
    for fname, idx, ev in iter_dict_events(files):
        eid = ev.get("id")
        if not isinstance(eid, str) or not EVENT_ID_RE.match(eid):
            problems.append(f"{ev_label(fname, idx, ev)}: id does not match ^e\\d+$")
            continue
        if eid in seen:
            problems.append(f"{ev_label(fname, idx, ev)}: duplicate id, first seen in {seen[eid]}")
        else:
            seen[eid] = f"{fname}[{idx}]"
    report(problems, f"{loc} event ids (unique across {sorted(files)})")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_time_format(loc):
    files = location_event_files(loc)
    problems = [
        f"{ev_label(f, i, ev)}: t={ev.get('t')!r}"
        for f, i, ev in iter_dict_events(files)
        if not isinstance(ev.get("t"), str) or not TIME_RE.match(ev["t"])
    ]
    report(problems, f"{loc} event t format (YYYY-MM-DDTHH:MM:SS-05:00)")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_type(loc):
    files = location_event_files(loc)
    problems = [
        f"{ev_label(f, i, ev)}: type={ev.get('type')!r}"
        for f, i, ev in iter_dict_events(files)
        if ev.get("type") not in EVENT_TYPES
    ]
    report(problems, f"{loc} event type (FORMAT.md 3.1 list)")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_type_matches_source_file(loc):
    files = location_event_files(loc)
    problems = []
    for f, i, ev in iter_dict_events(files):
        spec = EVENT_TYPES.get(ev.get("type"))
        sfile = get_source(ev).get("file")
        if not spec or not isinstance(sfile, str):
            continue
        expected = spec[0]
        ok = sfile.startswith(expected) if expected.endswith("/") else sfile == expected
        if not ok:
            problems.append(f"{ev_label(f, i, ev)}: type {ev['type']} expects source {expected}, got {sfile}")
    report(problems, f"{loc} event type vs source.file")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_attrs_keys(loc):
    files = location_event_files(loc)
    problems = []
    for f, i, ev in iter_dict_events(files):
        attrs = ev.get("attrs")
        if not isinstance(attrs, dict):
            problems.append(f"{ev_label(f, i, ev)}: attrs must be an object, got {type(attrs).__name__}")
            continue
        spec = EVENT_TYPES.get(ev.get("type"))
        if spec is None:
            continue
        if set(attrs) != spec[2]:
            problems.append(
                f"{ev_label(f, i, ev)} ({ev['type']}): attrs keys {sorted(attrs)} != {sorted(spec[2])}"
            )
    report(problems, f"{loc} event attrs keys")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_attrs_types(loc):
    """Value types stated in FORMAT.md 3.1 (int, list, null, time, device id)."""
    files = location_event_files(loc)
    devs = device_ids()
    problems = []

    def bad(f, i, ev, msg):
        problems.append(f"{ev_label(f, i, ev)} ({ev.get('type')}): {msg}")

    for f, i, ev in iter_dict_events(files):
        a = ev.get("attrs")
        typ = ev.get("type")
        if not isinstance(a, dict):
            continue

        def is_int(k):
            return isinstance(a.get(k), int) and not isinstance(a.get(k), bool)

        if typ in ("badge_in", "badge_out") and "result" in a and a["result"] not in ("GRANTED", "DENIED"):
            bad(f, i, ev, f"result={a['result']!r} not GRANTED/DENIED")
        if typ and typ.startswith("wifi_") and "rssi" in a and not is_int("rssi"):
            bad(f, i, ev, f"rssi={a['rssi']!r} not int")
        if typ in ("logon", "logoff", "file_access") and "event_id" in a:
            want = {"logon": 4624, "logoff": 4634, "file_access": 4663}[typ]
            if not is_int("event_id") or a["event_id"] != want:
                bad(f, i, ev, f"event_id={a['event_id']!r}, expected int {want}")
        if typ == "logon" and "logon_type" in a and not is_int("logon_type"):
            bad(f, i, ev, f"logon_type={a['logon_type']!r} not int")
        if typ in ("file_read", "file_copy") and "bytes" in a and not is_int("bytes"):
            bad(f, i, ev, f"bytes={a['bytes']!r} not int")
        if typ == "file_read" and "target_volume" in a and a["target_volume"] is not None:
            bad(f, i, ev, f"target_volume={a['target_volume']!r} must be null")
        if typ == "file_copy" and "target_volume" in a and not (isinstance(a["target_volume"], str) and a["target_volume"]):
            bad(f, i, ev, f"target_volume={a['target_volume']!r} must be a non-empty string")
        if typ == "usb_mount" and "first_seen" in a and not (isinstance(a["first_seen"], str) and TIME_RE.match(a["first_seen"])):
            bad(f, i, ev, f"first_seen={a['first_seen']!r} not a -05:00 time")
        if typ == "camera_offline" and "clip_ref" in a and a["clip_ref"] is not None:
            bad(f, i, ev, f"clip_ref={a['clip_ref']!r} must be null")
        if typ == "maintenance_window":
            for k in ("start", "end"):
                if k in a and not (isinstance(a[k], str) and TIME_RE.match(a[k])):
                    bad(f, i, ev, f"{k}={a[k]!r} not a -05:00 time")
        if typ == "email" and "to" in a and not (isinstance(a["to"], list) and all(isinstance(x, str) for x in a["to"])):
            bad(f, i, ev, f"to={a['to']!r} must be a list of strings")
        if typ == "chat" and "ts" in a and not isinstance(a["ts"], str):
            bad(f, i, ev, f"ts={a['ts']!r} must be a string")
        if typ == "statement" and "page" in a and not is_int("page"):
            bad(f, i, ev, f"page={a['page']!r} not int")
        if typ == "transaction" and "amount" in a and (
            isinstance(a["amount"], bool) or not isinstance(a["amount"], (int, float))
        ):
            bad(f, i, ev, f"amount={a['amount']!r} not a number")
        if "host" in a and devs and a["host"] not in devs:
            bad(f, i, ev, f"host={a['host']!r} not a device_id in devices.csv")
        for k, v in a.items():
            if v == "":
                bad(f, i, ev, f"attrs.{k} is \"\" (missing scalars must be null)")
    report(problems, f"{loc} event attrs value types")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_actor(loc):
    files = location_event_files(loc)
    problems = []
    for f, i, ev in iter_dict_events(files):
        actor = ev.get("actor", "<absent>")
        spec = EVENT_TYPES.get(ev.get("type"))
        expected_kind = spec[1] if spec else "<unknown type>"
        if actor is None:
            if spec and expected_kind is not None:
                problems.append(f"{ev_label(f, i, ev)} ({ev['type']}): actor is null, expected kind {expected_kind}")
            continue
        if not isinstance(actor, dict) or set(actor) != {"kind", "value"}:
            problems.append(f"{ev_label(f, i, ev)}: actor must be null or {{kind, value}}, got {actor!r}")
            continue
        if actor["kind"] not in ACTOR_KINDS:
            problems.append(f"{ev_label(f, i, ev)}: actor.kind={actor['kind']!r} not in {sorted(ACTOR_KINDS)}")
        if not isinstance(actor["value"], str) or not actor["value"]:
            problems.append(f"{ev_label(f, i, ev)}: actor.value={actor['value']!r} must be a non-empty string")
        if spec and actor["kind"] != expected_kind:
            problems.append(
                f"{ev_label(f, i, ev)} ({ev['type']}): actor.kind={actor['kind']!r}, expected {expected_kind!r}"
            )
    report(problems, f"{loc} event actor")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_person_is_null(loc):
    files = location_event_files(loc)
    problems = [
        f"{ev_label(f, i, ev)}: person={ev.get('person')!r}"
        for f, i, ev in iter_dict_events(files)
        if ev.get("person") is not None
    ]
    report(problems, f"{loc} event person (always null in evidence output)")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_device_and_room(loc):
    files = location_event_files(loc)
    devs, rooms = device_ids(), room_ids()
    if not devs:
        pytest.skip("devices.csv missing")
    problems = []
    for f, i, ev in iter_dict_events(files):
        dev, room = ev.get("device"), ev.get("room")
        if dev is not None and dev not in devs:
            problems.append(f"{ev_label(f, i, ev)}: device={dev!r} not in devices.csv")
        if room is not None and (not isinstance(room, str) or room not in rooms):
            problems.append(f"{ev_label(f, i, ev)}: room={room!r} not a room in devices.csv")
    report(problems, f"{loc} event device/room")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_source_shape(loc):
    files = location_event_files(loc)
    problems = []
    for f, i, ev in iter_dict_events(files):
        src = ev.get("source")
        lab = ev_label(f, i, ev)
        if not isinstance(src, dict):
            problems.append(f"{lab}: source must be an object")
            continue
        if set(src) != SOURCE_KEYS:
            problems.append(f"{lab}: source keys {sorted(src)} != {sorted(SOURCE_KEYS)}")
        sfile, line, quote, sha = src.get("file"), src.get("line"), src.get("quote"), src.get("sha256")
        if not isinstance(sfile, str) or not sfile or "\\" in sfile or sfile.startswith("/"):
            problems.append(f"{lab}: source.file={sfile!r} must be a relative path with forward slashes")
        min_line = 2 if isinstance(sfile, str) and is_csv(sfile) else 1
        if not isinstance(line, int) or isinstance(line, bool) or line < min_line:
            problems.append(f"{lab}: source.line={line!r} must be int >= {min_line}")
        if not isinstance(quote, str) or not quote:
            problems.append(f"{lab}: source.quote must be a non-empty string")
        elif "\n" in quote or "\r" in quote:
            problems.append(f"{lab}: source.quote contains a newline")
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            problems.append(f"{lab}: source.sha256={sha!r} is not 64 lowercase hex chars")
    report(problems, f"{loc} event source")


def _check_csv_quote(ev: dict) -> list[str]:
    """Compare a CSV quote's fields with the event. Returns problem strings (without label)."""
    src = get_source(ev)
    sfile, quote = src.get("file"), src.get("quote")
    if not isinstance(sfile, str) or not isinstance(quote, str) or not is_csv(sfile):
        return []
    fields = split_csv_line(quote)
    header = RAW_CSV_HEADERS.get(sfile)
    t, typ = ev.get("t"), ev.get("type")
    actor = ev.get("actor") if isinstance(ev.get("actor"), dict) else {}
    attrs = ev.get("attrs") if isinstance(ev.get("attrs"), dict) else {}
    out: list[str] = []

    if header is None:
        # Unknown CSV: first field should be the time.
        if fields and fields[0] != t:
            out.append(f"quote first field {fields[0]!r} != t {t!r}")
        return out
    if len(fields) != len(header):
        return [f"quote has {len(fields)} fields, {sfile} has {len(header)} columns: {quote!r}"]
    row = dict(zip(header, fields))

    def eq(label, got, want):
        if got != want:
            out.append(f"{label}: quote has {got!r}, event has {want!r}")

    if sfile == "access/badge_access.csv":
        eq("timestamp vs t", row["timestamp"], t)
        eq("badge_id vs actor.value", row["badge_id"], actor.get("value"))
        eq("reader_id vs device", row["reader_id"], ev.get("device"))
        if "reader" in attrs:
            eq("reader_id vs attrs.reader", row["reader_id"], attrs["reader"])
        if "result" in attrs:
            eq("result vs attrs.result", row["result"], attrs["result"])
        want_dir = {"badge_in": "IN", "badge_out": "OUT"}.get(typ)
        if want_dir:
            eq("direction vs type", row["direction"], want_dir)
    elif sfile == "network/wifi_ap_logs.csv":
        eq("timestamp vs t", row["timestamp"], t)
        eq("client_mac vs actor.value", row["client_mac"], actor.get("value"))
        if "ap" in attrs:
            eq("ap_id vs attrs.ap", row["ap_id"], attrs["ap"])
        want_evt = {"wifi_assoc": "ASSOC", "wifi_disassoc": "DISASSOC", "wifi_roam": "ROAM"}.get(typ)
        if want_evt:
            eq("event vs type", row["event"], want_evt)
    elif sfile == "endpoint/security_log.csv":
        eq("TimeCreated vs t", row["TimeCreated"], t)
        eq("TargetUserName vs actor.value", row["TargetUserName"], actor.get("value"))
        if "event_id" in attrs:
            eq("EventID vs attrs.event_id", row["EventID"], str(attrs["event_id"]))
    elif sfile == "endpoint/file_audit.csv":
        eq("timestamp vs t", row["timestamp"], t)
        eq("user vs actor.value", row["user"], actor.get("value"))
        want_act = {"file_read": "READ", "file_copy": "COPY"}.get(typ)
        if want_act:
            eq("action vs type", row["action"], want_act)
    elif sfile == "cctv/index.csv":
        col = {"camera_offline": "window_start", "camera_online": "window_end"}.get(typ, "window_start")
        eq(f"{col} vs t", row[col], t)
        if "camera" in attrs:
            eq("camera_id vs attrs.camera", row["camera_id"], attrs["camera"])
    elif sfile == "it/maintenance_calendar.csv":
        eq("start vs t", row["start"], t)
        for k in ("start", "end", "asset", "work_order", "technician"):
            if k in attrs:
                eq(f"{k} vs attrs.{k}", row[k], attrs[k])
    elif sfile == "financial/transactions.csv":
        eq("timestamp vs t", row["timestamp"], t)
        if "account" in attrs:
            eq("account vs attrs.account", row["account"], attrs["account"])
    elif sfile == "access/parking_exit.csv":
        eq("timestamp vs t", row["timestamp"], t)
        eq("permit_id vs actor.value", row["permit_id"], actor.get("value"))
        want_dir = {"parking_entry": "IN", "parking_exit": "OUT"}.get(typ)
        if want_dir:
            eq("direction vs type", row["direction"], want_dir)
    return out


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_csv_quote_consistent(loc):
    files = location_event_files(loc)
    problems = []
    for f, i, ev in iter_dict_events(files):
        for p in _check_csv_quote(ev):
            problems.append(f"{ev_label(f, i, ev)} ({ev.get('type')}): {p}")
    report(problems, f"{loc} CSV quote vs event fields")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_sorted(loc):
    """Section 2: sorted by t, then source.file, then source.line (checked within each event file)."""
    files = location_event_files(loc)
    problems = []
    for fname, events in files.items():
        prev = None
        for idx, ev in enumerate(events):
            if not isinstance(ev, dict):
                continue
            src = get_source(ev)
            key = (str(ev.get("t")), str(src.get("file")), src.get("line") if isinstance(src.get("line"), int) else 0)
            if prev is not None and key < prev[0]:
                problems.append(f"{ev_label(fname, idx, ev)}: {key} comes after {prev[1]} {prev[0]}")
            prev = (key, ev_label(fname, idx, ev))
    report(problems, f"{loc} event ordering")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_same_line_same_quote(loc):
    files = location_event_files(loc)
    first: dict[tuple, tuple[str, str]] = {}
    problems = []
    for f, i, ev in iter_dict_events(files):
        src = get_source(ev)
        key = (src.get("file"), src.get("line"))
        q = src.get("quote")
        if key in first and first[key][0] != q:
            problems.append(
                f"{ev_label(f, i, ev)}: {key} quote {q!r} differs from {first[key][1]} quote {first[key][0]!r}"
            )
        first.setdefault(key, (q, ev_label(f, i, ev)))
    report(problems, f"{loc} (file, line) -> quote consistency")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_events_same_file_same_sha(loc):
    files = location_event_files(loc)
    first: dict[str, tuple[str, str]] = {}
    problems = []
    for f, i, ev in iter_dict_events(files):
        src = get_source(ev)
        sfile, sha = src.get("file"), src.get("sha256")
        if sfile in first and first[sfile][0] != sha:
            problems.append(f"{ev_label(f, i, ev)}: {sfile} sha256 differs from {first[sfile][1]}")
        first.setdefault(sfile, (sha, ev_label(f, i, ev)))
    report(problems, f"{loc} file -> sha256 consistency")


def test_real_events_match_case_files():
    """Real output only: each source line/quote/sha256 matches the raw file in CASE-1010F/ (or extra/)."""
    path = EVIDENCE_DIR / "events.json"
    if not path.exists():
        pytest.skip("real events.json does not exist yet")
    if not CASE_DIR.exists():
        pytest.skip("CASE-1010F/ does not exist yet")
    events = load_json(path)
    cache: dict[str, tuple[str, list[str]] | None] = {}
    problems = []
    for idx, ev in enumerate(events):
        if not isinstance(ev, dict):
            continue
        src = get_source(ev)
        sfile = src.get("file")
        if not isinstance(sfile, str):
            continue
        if sfile not in cache:
            raw_path = next(
                (p for p in (CASE_DIR / sfile, EVIDENCE_DIR / "extra" / sfile) if p.exists()), None
            )
            if raw_path is None:
                cache[sfile] = None
            else:
                raw = raw_path.read_bytes()
                lines = raw.decode("utf-8", errors="replace").split("\n")
                cache[sfile] = (hashlib.sha256(raw).hexdigest(), lines)
        entry = cache[sfile]
        lab = ev_label("events.json", idx, ev)
        if entry is None:
            problems.append(f"{lab}: source.file {sfile} not found in CASE-1010F/ or extra/")
            continue
        sha, lines = entry
        if src.get("sha256") != sha:
            problems.append(f"{lab}: sha256 does not match {sfile}")
        if sfile.lower().endswith(".pdf"):
            continue  # line refers to pdfplumber text, not raw bytes
        line, quote = src.get("line"), src.get("quote")
        if not isinstance(line, int) or not 1 <= line <= len(lines):
            problems.append(f"{lab}: line {line!r} out of range for {sfile}")
            continue
        raw_line = lines[line - 1].rstrip("\r")
        # CSV: the whole raw line. Text, mbox, Slack: a substring of the line.
        ok = raw_line == quote if is_csv(sfile) else isinstance(quote, str) and quote in raw_line
        if not ok:
            problems.append(f"{lab}: quote {quote!r} does not match {sfile}:{line} {raw_line!r}")
    report(problems, "real events vs raw case files")


# --------------------------------------------------------------------------------------------------
# evidence.json (section 4)
# --------------------------------------------------------------------------------------------------

def _load_evidence(loc: str) -> list[Any]:
    data = load_json(LOCATIONS[loc]["dir"] / "evidence.json")
    if not isinstance(data, list):
        pytest.fail(f"{loc} evidence.json must be an array")
    return data


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_evidence_shape(loc):
    items = _load_evidence(loc)
    problems = []
    seen = set()
    for idx, it in enumerate(items):
        lab = f"evidence.json[{idx}] file={it.get('file') if isinstance(it, dict) else None!r}"
        if not isinstance(it, dict):
            problems.append(f"{lab}: not an object")
            continue
        if set(it) != EVIDENCE_KEYS:
            problems.append(f"{lab}: keys {sorted(it)} != {sorted(EVIDENCE_KEYS)}")
        if not isinstance(it.get("file"), str) or not it["file"] or "\\" in it["file"]:
            problems.append(f"{lab}: file must be a forward-slash path")
        elif it["file"] in seen:
            problems.append(f"{lab}: duplicate file entry")
        else:
            seen.add(it["file"])
        sha, msha = it.get("sha256"), it.get("manifest_sha256")
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            problems.append(f"{lab}: sha256={sha!r} not 64 lowercase hex")
        if msha is not None and (not isinstance(msha, str) or not SHA_RE.match(msha)):
            problems.append(f"{lab}: manifest_sha256={msha!r} must be null or 64 lowercase hex")
        if it.get("manifest_match") is not (sha == msha):
            problems.append(f"{lab}: manifest_match={it.get('manifest_match')!r} but sha256==manifest_sha256 is {sha == msha}")
        if it.get("parser") not in PARSERS:
            problems.append(f"{lab}: parser={it.get('parser')!r} not in {sorted(PARSERS)}")
        rec = it.get("records")
        if not isinstance(rec, int) or isinstance(rec, bool) or rec < 0:
            problems.append(f"{lab}: records={rec!r} must be int >= 0")
    report(problems, f"{loc} evidence.json")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_evidence_covers_event_sources(loc):
    items = _load_evidence(loc)
    files = location_event_files(loc)
    by_file = {it.get("file"): it for it in items if isinstance(it, dict)}
    problems = []
    reported = set()
    for f, i, ev in iter_dict_events(files):
        src = get_source(ev)
        sfile = src.get("file")
        if sfile in reported:
            continue
        if sfile not in by_file:
            if sfile not in MAY_BE_UNRELEASED:
                problems.append(f"{ev_label(f, i, ev)}: source.file {sfile!r} missing from evidence.json")
                reported.add(sfile)
        elif by_file[sfile].get("sha256") != src.get("sha256"):
            problems.append(f"{ev_label(f, i, ev)}: sha256 for {sfile} differs from evidence.json")
            reported.add(sfile)
    report(problems, f"{loc} evidence.json coverage of event sources")


@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_evidence_records_count(loc):
    items = _load_evidence(loc)
    info = LOCATIONS[loc]
    counts: Counter = Counter()
    found_any = False
    for name in info["record_files"]:
        path = info["dir"] / name
        if not path.exists():
            continue
        found_any = True
        data = load_json(path)
        for ev in data if isinstance(data, list) else []:
            if isinstance(ev, dict):
                counts[get_source(ev).get("file")] += 1
    if not found_any:
        pytest.skip(f"no event files counted toward records in {loc} yet")
    problems = []
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        want = counts.get(it.get("file"), 0)
        if it.get("records") != want:
            problems.append(f"evidence.json[{idx}] {it.get('file')}: records={it.get('records')!r}, events cite it {want} time(s)")
    report(problems, f"{loc} evidence.json records (counted over {info['record_files']})")


# --------------------------------------------------------------------------------------------------
# case.json (section 5)
# --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("loc", LOCATION_NAMES)
def test_case_json(loc):
    data = load_json(LOCATIONS[loc]["dir"] / "case.json")
    assert isinstance(data, dict), "case.json must be an object"
    problems = []
    if set(data) != CASE_KEYS:
        problems.append(f"keys {sorted(data)} != {sorted(CASE_KEYS)}")
    for k in CASE_KEYS & set(data):
        if not isinstance(data[k], str):
            problems.append(f"{k} must be a string, got {type(data[k]).__name__}")
    if data.get("id") != "1010F":
        problems.append(f"id={data.get('id')!r}, expected '1010F'")
    report(problems, f"{loc} case.json")


# --------------------------------------------------------------------------------------------------
# devices.csv (section 6)
# --------------------------------------------------------------------------------------------------

def test_devices_csv():
    header, rows = load_csv(DEVICES_CSV)
    problems = []
    if header != DEVICES_HEADER:
        problems.append(f"header {header} != {DEVICES_HEADER}")
    ids = Counter(r.get("device_id") for r in rows)
    for did, n in ids.items():
        if n > 1:
            problems.append(f"device_id {did!r} appears {n} times")
    for line_no, r in enumerate(rows, start=2):
        if r.get("type") not in DEVICE_TYPES:
            problems.append(f"line {line_no} {r.get('device_id')!r}: type={r.get('type')!r}")
        if not r.get("room"):
            problems.append(f"line {line_no} {r.get('device_id')!r}: room is empty")
        if not (r.get("floor") or "").isdigit():
            problems.append(f"line {line_no} {r.get('device_id')!r}: floor={r.get('floor')!r} not an int")
    required = [f"rdr-{n}" for n in range(210, 231)] + ["lt-219", "cam-03"]
    for did in required:
        if did not in ids:
            problems.append(f"required device {did} missing")
    report(problems, "devices.csv")


# --------------------------------------------------------------------------------------------------
# inventory.csv (section 7)
# --------------------------------------------------------------------------------------------------

REVOKED_RE = re.compile(r"^([^@;]+)@(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d-05:00)$")


def test_inventory_csv():
    header, rows = load_csv(INVENTORY_CSV)
    rooms = room_ids()
    problems = []
    if header != INVENTORY_HEADER:
        problems.append(f"header {header} != {INVENTORY_HEADER}")
    for col in ("person_id", "badge", "laptop_mac", "parking_permit"):
        counts = Counter(r.get(col) for r in rows if r.get(col))
        for val, n in counts.items():
            if n > 1:
                problems.append(f"{col} {val!r} appears {n} times")
    for line_no, r in enumerate(rows, start=2):
        pid = r.get("person_id")
        if not pid:
            problems.append(f"line {line_no}: empty person_id")
        auth = r.get("authorized_rooms") or ""
        for room in filter(None, auth.split(";")):
            if rooms and room not in rooms:
                problems.append(f"line {line_no} {pid}: authorized room {room!r} not in devices.csv")
        rev = r.get("revoked") or ""
        for entry in filter(None, rev.split(";")):
            m = REVOKED_RE.match(entry)
            if not m:
                problems.append(f"line {line_no} {pid}: revoked entry {entry!r} not room@YYYY-MM-DDTHH:MM:SS-05:00")
            elif rooms and m.group(1) not in rooms:
                problems.append(f"line {line_no} {pid}: revoked room {m.group(1)!r} not in devices.csv")
    report(problems, "inventory.csv")


# --------------------------------------------------------------------------------------------------
# answer_key.json (section 8)
# --------------------------------------------------------------------------------------------------

def _known_quotes() -> set[tuple]:
    """(file, line, quote) of every event in the fake event files (plus real events.json if present)."""
    out = set()
    paths = [FAKE_DIR / n for n in LOCATIONS["fake"]["event_files"]] + [EVIDENCE_DIR / "events.json"]
    for p in paths:
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for ev in data if isinstance(data, list) else []:
            if isinstance(ev, dict):
                s = get_source(ev)
                out.add((s.get("file"), s.get("line"), s.get("quote")))
    return out


def test_answer_key():
    data = load_json(ANSWER_KEY_JSON)
    assert isinstance(data, dict), "answer_key.json must be an object"
    problems = []
    want_keys = {"case_id", "planted", "false_alarm_persons", "tamper"}
    if set(data) != want_keys:
        problems.append(f"keys {sorted(data)} != {sorted(want_keys)}")
    if data.get("case_id") != "1010F":
        problems.append(f"case_id={data.get('case_id')!r}, expected '1010F'")

    person_ids: set[str] = set()
    if INVENTORY_CSV.exists():
        person_ids = {r["person_id"] for r in load_csv(INVENTORY_CSV)[1]}
    quotes = _known_quotes()

    planted = data.get("planted")
    if not isinstance(planted, list):
        problems.append("planted must be an array")
        planted = []
    ids = Counter(p.get("id") for p in planted if isinstance(p, dict))
    for cid in PLANTED_IDS:
        if ids.get(cid, 0) != 1:
            problems.append(f"planted {cid} appears {ids.get(cid, 0)} time(s), expected exactly 1")
    for extra in set(ids) - set(PLANTED_IDS):
        problems.append(f"unexpected planted id {extra!r}")

    for pi, p in enumerate(planted):
        if not isinstance(p, dict):
            problems.append(f"planted[{pi}] not an object")
            continue
        lab = f"planted[{pi}] {p.get('id')}"
        for k in ("id", "kind", "sources", "persons"):
            if k not in p:
                problems.append(f"{lab}: missing {k}")
        if p.get("kind") not in CONTRADICTION_KINDS:
            problems.append(f"{lab}: kind={p.get('kind')!r} not in {sorted(CONTRADICTION_KINDS)}")
        if "events" in p:
            problems.append(f"{lab}: has 'events' (old k1 shape); match by sources, never event id")
        sources = p.get("sources")
        if not isinstance(sources, list) or not sources:
            problems.append(f"{lab}: sources must be a non-empty array")
            sources = []
        for si, s in enumerate(sources):
            slab = f"{lab}.sources[{si}]"
            if not isinstance(s, dict) or not isinstance(s.get("file"), str) or not s.get("file"):
                problems.append(f"{slab}: needs a file string")
                continue
            line = s.get("line", "<absent>")
            file_level_ok = p.get("id") == "C8" and line is None
            if not file_level_ok and (not isinstance(line, int) or isinstance(line, bool) or line < 1):
                problems.append(f"{slab}: line={line!r} must be int >= 1 (only C8 may use null)")
            if "quote" in s and s["quote"] is not None:
                if (s["file"], line, s["quote"]) not in quotes:
                    problems.append(f"{slab}: ({s['file']}, {line}, {s['quote']!r}) matches no fake event")
        persons = p.get("persons", [])
        if not isinstance(persons, list):
            problems.append(f"{lab}: persons must be an array")
            persons = []
        for pid in persons:
            if person_ids and pid not in person_ids:
                problems.append(f"{lab}: person {pid!r} not in inventory.csv")

    fap = data.get("false_alarm_persons")
    if not isinstance(fap, list):
        problems.append("false_alarm_persons must be an array")
    else:
        for pid in fap:
            if person_ids and pid not in person_ids:
                problems.append(f"false_alarm_persons: {pid!r} not in inventory.csv")

    tamper = data.get("tamper")
    if not isinstance(tamper, dict):
        problems.append("tamper must be an object")
    else:
        if not isinstance(tamper.get("file"), str):
            problems.append("tamper.file must be a string")
        if not isinstance(tamper.get("seed"), int):
            problems.append("tamper.seed must be an int")
        al = tamper.get("altered_lines")
        if not isinstance(al, list) or not all(isinstance(x, int) and x >= 1 for x in al):
            problems.append("tamper.altered_lines must be a list of ints >= 1")
    report(problems, "answer_key.json")
