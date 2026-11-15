"""The fixed world of Case 1010F: paths, clock, dates, seeds, people, devices and the placeholder layout.

Everything here comes from CASE.md, data/evidence/devices.csv, inventory.csv and layout_placeholder.json.
Other modules import from here instead of re-reading files or re-typing constants.
"""
import csv
import json
from datetime import date, datetime, timedelta, timezone
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = ROOT / "data" / "evidence"
CASE_DIR = EVIDENCE / "CASE-1010F"      # the case folder (zipped for upload)
EXTRA_DIR = EVIDENCE / "extra"          # withheld until the evidence request is approved
TRUTH_DIR = EVIDENCE / "truth"          # generator truth: expected events + answer key (never read by the system)
STORY_SPEC = Path(__file__).with_name("story_spec.json")

# One clock for the whole case: EST, fixed -05:00 (CASE.md section 1, CONTRACTS rule 7).
EST = timezone(timedelta(hours=-5))
START = date(2026, 2, 23)
END = date(2026, 3, 8)
INCIDENT_DAY = date(2026, 3, 4)
COLLECTED_AT = datetime(2026, 3, 9, 17, 30, 0, tzinfo=EST)
COLLECTED_BY = "Alma Imhoff (Halvorsen security) and R. Castell (forensic examiner)"

# Seeds: one per module so changing one source never reshuffles another.
SEED_PRESENCE = 1010   # same seed as the fake baseline, so the background behaviour is identical
SEED_SOURCES = 1011
SEED_COMMS = 1012
SEED_TAMPER = 1010

SSID = "JRR2-SECURE"
LAB_HOST = "lt-219"
LAB_HOST_RAW = "LT-219"
TAMPERED_FILE = "endpoint/security_log.csv"
EXTRA_FILES = {"access/parking_exit.csv"}

# Case-folder paths of every source file (CASE.md section 10).
F_BADGE = "access/badge_access.csv"
F_WIFI = "network/wifi_ap_logs.csv"
F_SEC = "endpoint/security_log.csv"
F_AUDIT = "endpoint/file_audit.csv"
F_USB = "endpoint/usbstor.txt"
F_CCTV = "cctv/index.csv"
F_MAINT = "it/maintenance_calendar.csv"
F_TXN = "financial/transactions.csv"
F_PARKING = "access/parking_exit.csv"
F_MBOX = "comms/mailbox.mbox"
F_SLACK_DIR = "comms/slack_export"
F_STATEMENTS_DIR = "statements"
F_BRIEF = "brief.pdf"
F_DEVICES = "facilities/devices.csv"
F_MANIFEST = "manifest.csv"


def ts(t: datetime) -> str:
    """The one timestamp format used in every file: 2026-03-04T18:16:40-05:00."""
    return t.astimezone(EST).isoformat(timespec="seconds")


def parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(EST)


def at(day: date, h: int, m: int = 0, s: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, h, m, s, tzinfo=EST)


def days():
    d = START
    while d <= END:
        yield d
        d += timedelta(days=1)


@cache
def devices() -> dict[str, dict]:
    with open(EVIDENCE / "devices.csv", encoding="utf-8", newline="") as f:
        return {r["device_id"]: r for r in csv.DictReader(f)}


@cache
def people() -> list[dict]:
    with open(EVIDENCE / "inventory.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def person(pid: str) -> dict:
    return next(p for p in people() if p["person_id"] == pid)


@cache
def layout() -> dict:
    return json.loads((EVIDENCE / "layout_placeholder.json").read_text(encoding="utf-8"))


def slack_user_id(handle: str) -> str:
    """Stable Slack-style user ID for a handle (U + 10 chars), same on every run."""
    import hashlib

    return "U" + hashlib.sha256(handle.encode()).hexdigest()[:10].upper()
