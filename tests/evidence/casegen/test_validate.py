"""Tests for casegen/validate.py: a tiny hand-built valid case passes; each broken copy fails the right check."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from pathlib import Path

import pdfplumber
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.features.evidence.casegen import world
from app.features.evidence.casegen.validate import validate

HANK = "02:1F:9A:10:00:02"
BG17 = "02:1F:9A:00:00:11"
TS = "-05:00"

CSV_FILES = {
    "access/badge_access.csv": ["timestamp,badge_id,reader_id,direction,result",
        f"2026-03-02T09:00:00{TS},40388,rdr-217,IN,GRANTED",
        f"2026-03-02T10:00:00{TS},40388,rdr-219,IN,GRANTED",
        f"2026-03-02T10:30:00{TS},40388,rdr-219,OUT,GRANTED",
        f"2026-03-02T16:00:00{TS},40388,rdr-217,OUT,GRANTED",
        f"2026-03-04T08:50:00{TS},40388,rdr-217,IN,GRANTED",
        f"2026-03-04T09:00:00{TS},40392,rdr-217,IN,GRANTED",
        f"2026-03-04T09:10:00{TS},40417,rdr-217,IN,GRANTED",
        f"2026-03-04T17:45:00{TS},40392,rdr-217,OUT,GRANTED",
        f"2026-03-04T18:02:00{TS},40388,rdr-217,OUT,GRANTED",
        f"2026-03-04T18:16:10{TS},40417,rdr-230,IN,GRANTED",
        f"2026-03-04T18:16:40{TS},40417,rdr-219,IN,GRANTED",
        f"2026-03-04T18:31:40{TS},40417,rdr-219,OUT,GRANTED",
        f"2026-03-04T18:52:00{TS},40417,rdr-230,OUT,GRANTED",
        f"2026-03-04T19:00:30{TS},40455,rdr-219,IN,GRANTED",
        f"2026-03-04T21:29:10{TS},40455,rdr-219,OUT,GRANTED"],
    "network/wifi_ap_logs.csv": ["timestamp,ap_id,client_mac,event,rssi,ssid",
        f"2026-03-02T09:01:00{TS},ap-2-03,{HANK},ASSOC,-55,JRR2-SECURE",
        f"2026-03-02T15:59:00{TS},ap-2-03,{HANK},DISASSOC,-58,JRR2-SECURE",
        f"2026-03-04T08:52:00{TS},ap-2-03,{HANK},ASSOC,-55,JRR2-SECURE",
        f"2026-03-04T09:12:00{TS},ap-2-03,{BG17},ASSOC,-50,JRR2-SECURE",
        f"2026-03-04T18:12:00{TS},ap-2-04,{HANK},ROAM,-60,JRR2-SECURE",
        f"2026-03-04T18:17:00{TS},ap-2-07,{BG17},ROAM,-52,JRR2-SECURE",
        f"2026-03-04T18:41:00{TS},ap-2-03,{HANK},DISASSOC,-61,JRR2-SECURE",
        f"2026-03-04T18:50:00{TS},ap-2-07,{BG17},DISASSOC,-57,JRR2-SECURE"],
    "endpoint/security_log.csv": [
        "TimeCreated,EventID,Computer,TargetUserName,LogonType,ObjectName,AccessMask,ProcessName",
        f"2026-03-04T18:17:05{TS},4624,LT-219,hgibson,2,,,C:\\Windows\\System32\\winlogon.exe",
        f"2026-03-04T18:18:02{TS},4663,LT-219,hgibson,,C:\\Projects\\Titan\\thruster_v4.step,0x1,C:\\Windows\\explorer.exe",
        f"2026-03-04T16:01:44{TS},4663,LT-219,hgibson,,C:\\Projects\\Titan\\nozzle.step,0x1,C:\\Windows\\explorer.exe",
        f"2026-03-04T18:31:20{TS},4634,LT-219,hgibson,2,,,",
        f"2026-03-04T19:05:00{TS},4624,LT-219,fmendelssohn,2,,,C:\\Windows\\System32\\winlogon.exe"],
    "endpoint/file_audit.csv": ["timestamp,host,user,action,path,bytes,target_volume",
        f"2026-03-04T18:17:50{TS},LT-219,hgibson,READ,C:\\Projects\\Titan\\thruster_v4.step,48211968,",
        f"2026-03-04T18:18:02{TS},LT-219,hgibson,COPY,C:\\Projects\\Titan\\thruster_v4.step,48211968,E:"],
    "cctv/index.csv": ["camera_id,window_start,window_end,status,clip_ref",
        f"cam-02,2026-02-24T13:05:00{TS},2026-02-24T13:22:00{TS},OFFLINE,",
        f"cam-01,2026-03-04T18:00:00{TS},2026-03-04T19:00:00{TS},RECORDING,clip-cam01-0304-18",
        f"cam-03,2026-03-04T18:05:00{TS},2026-03-04T18:30:00{TS},OFFLINE,"],
    "it/maintenance_calendar.csv": ["work_order,asset,start,end,technician,description",
        f"WO-3091,cam-02,2026-02-24T13:00:00{TS},2026-02-24T13:30:00{TS},Frederik Mendelssohn,Camera firmware update",
        f"WO-3117,lt-219,2026-03-04T19:00:00{TS},2026-03-04T21:30:00{TS},Frederik Mendelssohn,"
        "Monthly security patching (offline media)"],
    "financial/transactions.csv": ["timestamp,account,description,counterparty,amount,balance",
        f"2026-03-06T10:42:00{TS},CHK-7731,SIGNING BONUS,Northline Systems Inc,25000.00,31842.17"],
}
PARKING = ["timestamp,lane,permit_id,plate,direction",
           f"2026-03-04T08:40:00{TS},EXIT-1,P-2088,W26-VCU,IN",
           f"2026-03-04T18:44:00{TS},EXIT-1,P-2088,W26-VCU,OUT"]
TAMPERED_LINE = 4
ORIGINAL_SEC_ROW = (f"2026-03-04T18:20:00{TS},4663,LT-219,hgibson,,C:\\Projects\\Titan\\nozzle.step,0x1,"
                    "C:\\Windows\\explorer.exe")

USBSTOR = [
    "usbstor v.20200515", "(System) Get USBStor key info", "", "USBStor", "ControlSet001\\Enum\\USBStor", "",
    f"Disk&Ven_Kingston&Prod_DataTraveler_3.0&Rev_1.00 [2026-02-25T10:03:41{TS}]",
    f"  S/N: 07A1B2C3D4E5F601&0 [2026-02-25T10:03:41{TS}]",
    "  FriendlyName  : Kingston DataTraveler 3.0 USB Device",
    f"  First InstallDate : 2025-06-12T14:22:09{TS}",
    "",
    f"Disk&Ven_SanDisk&Prod_Ultra&Rev_1.00 [2026-03-04T18:17:30{TS}]",
    f"  S/N: 4C530001230918112443&0 [2026-03-04T18:17:30{TS}]",
    "  FriendlyName  : SanDisk Ultra USB Device",
    f"  First InstallDate : 2026-03-04T18:17:30{TS}",
]

MBOX = [
    "From sofia.marchetti@halvorsen.example Wed Mar  4 10:00:00 2026",
    'From: "Sofia Marchetti" <sofia.marchetti@halvorsen.example>',
    "To: all@halvorsen.example",
    "Subject: Summit welcome reception",
    "Date: Wed, 04 Mar 2026 10:00:00 -0500",
    "Message-ID: <20260304100000.a1@halvorsen.example>",
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=utf-8",
    "Content-Transfer-Encoding: 8bit",
    "",
    "The welcome reception starts at 18:15 in the lounge.",
    "",
    "From hank.gibson@halvorsen.example Mon Mar  9 09:30:00 2026",
    'From: "Hank Gibson" <hank.gibson@halvorsen.example>',
    "To: alma.imhoff@halvorsen.example",
    "Subject: Re: Titan access",
    "Date: Mon, 09 Mar 2026 09:30:00 -0500",
    "Message-ID: <20260309093000.b2@halvorsen.example>",
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=utf-8",
    "Content-Transfer-Encoding: 8bit",
    "",
    "Alma,",
    "I never touched the Titan folder.",
    "Hank",
]
MBOX_QUOTES = ["The welcome reception starts at 18:15 in the lounge.", "I never touched the Titan folder."]

SLACK_DM = "comms/slack_export/D0HANKKIM/2026-03-04.json"
SLACK_TEXT = "Thanks. Still wrapping up a few things here before I'm out."

STATEMENTS = {
    "statements/hank_gibson.pdf": ["Interview statement, case 1010F", "Speaker: Hank Gibson",
                                   "I went straight home at six.", "IT gave me that drive last year."],
    "statements/maggie_price.pdf": ["Interview statement, case 1010F", "Speaker: Maggie Price",
                                    "Hank and I left together around 6:30."],
    "statements/frederik_mendelssohn.pdf": ["Interview statement, case 1010F", "Speaker: Frederik Mendelssohn",
                                            "I patched lt-219 from 19:00 to 21:30 as scheduled."],
    "brief.pdf": ["Incident summary, case 1010F", "Titan files may have left the lab on 4 March."],
}
STATEMENT_QUOTES = ["I went straight home at six.", "IT gave me that drive last year.",
                    "Hank and I left together around 6:30.", "I patched lt-219 from 19:00 to 21:30 as scheduled."]


def _write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def _lines_text(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def _pdf(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter, invariant=1)
    y = 720
    for line in lines:
        c.drawString(72, y, line)
        y -= 24
    c.save()


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _pdf_lines(p: Path) -> list[str]:
    with pdfplumber.open(str(p)) as pdf:
        return "\n".join((pg.extract_text() or "") for pg in pdf.pages).split("\n")


def _find(lines: list[str], quote: str, whole: bool) -> int:
    for i, line in enumerate(lines, start=1):
        if (line == quote) if whole else (quote in line):
            return i
    raise AssertionError(f"quote {quote!r} not in fixture")


def build_case(root: Path) -> tuple[Path, Path, Path]:
    case, extra, truth = root / "CASE-1010F", root / "extra", root / "truth"
    for rel, lines in CSV_FILES.items():
        _write(case / rel, _lines_text(lines))
    _write(extra / "access/parking_exit.csv", _lines_text(PARKING))
    _write(case / "facilities/devices.csv",
           (world.EVIDENCE / "devices.csv").read_bytes().decode("utf-8").replace("\r\n", "\n"))
    _write(case / "endpoint/usbstor.txt", _lines_text(USBSTOR))
    _write(case / "comms/mailbox.mbox", _lines_text(MBOX))
    sl = case / "comms/slack_export"
    _write(sl / "users.json", json.dumps([{"id": "U1", "name": "hank.gibson"}, {"id": "U2", "name": "kim.sayers"}],
                                         indent=2) + "\n")
    _write(sl / "channels.json", json.dumps([{"id": "C1", "name": "general", "members": ["U1"]}], indent=2) + "\n")
    _write(sl / "dms.json", json.dumps([{"id": "D0HANKKIM", "members": ["U1", "U2"]}], indent=2) + "\n")
    _write(case / SLACK_DM, json.dumps([{"type": "message", "user": "U1", "text": SLACK_TEXT,
                                         "ts": "1772665200.000100"}], indent=2) + "\n")
    for rel, lines in STATEMENTS.items():
        _pdf(case / rel, lines)

    # truth: one event per cited line
    events = []

    def add(rel: str, line: int, quote: str, t: str):
        p = case / rel if (case / rel).exists() else extra / rel
        events.append({"id": f"e{len(events) + 1}", "t": t, "type": "x", "person": None, "device": None,
                       "room": None, "actor": None, "attrs": {},
                       "source": {"file": rel, "line": line, "quote": quote, "sha256": _sha(p)}})

    for rel, lines in [*CSV_FILES.items(), ("access/parking_exit.csv", PARKING)]:
        for i, row in enumerate(lines[1:], start=2):
            if ",RECORDING," in row:
                continue
            t = next(v for v in row.split(",") if v.endswith(TS))
            add(rel, i, row, t)
    for i, line in enumerate(USBSTOR, start=1):
        if "S/N:" in line:
            add("endpoint/usbstor.txt", i, line, line.split("[")[1].rstrip("]"))
    for q in MBOX_QUOTES:
        add("comms/mailbox.mbox", _find(MBOX, q, False), q, f"2026-03-04T10:00:00{TS}")
    slack_lines = (case / SLACK_DM).read_text(encoding="utf-8").split("\n")
    add(SLACK_DM, _find(slack_lines, SLACK_TEXT, False), SLACK_TEXT, f"2026-03-04T18:00:00{TS}")
    pdf_lines = {rel: _pdf_lines(case / rel) for rel in STATEMENTS}
    for q in STATEMENT_QUOTES:
        rel = next(r for r, ls in pdf_lines.items() if q in ls)
        add(rel, _find(pdf_lines[rel], q, True), q, f"2026-03-09T11:00:00{TS}")

    def src(rel: str, quote: str) -> dict:
        if rel.endswith(".pdf"):
            return {"file": rel, "line": _find(pdf_lines[rel], quote, True), "quote": quote}
        p = case / rel if (case / rel).exists() else extra / rel
        lines = p.read_text(encoding="utf-8").split("\n")
        return {"file": rel, "line": _find(lines, quote, not rel.endswith(".mbox")), "quote": quote}

    b, w = "access/badge_access.csv", "network/wifi_ap_logs.csv"
    planted = [
        ("C1", "temporal", [src(b, CSV_FILES[b][9]), src(w, CSV_FILES[w][7])], ["p_hank"]),
        ("C2", "physical", [src(b, CSV_FILES[b][10]), src(b, CSV_FILES[b][11])], ["p_bg_17"]),
        ("C3", "statement", [src("statements/hank_gibson.pdf", STATEMENT_QUOTES[0]),
                             src("access/parking_exit.csv", PARKING[2])], ["p_hank"]),
        ("C4", "statement", [src("statements/maggie_price.pdf", STATEMENT_QUOTES[2]), src(b, CSV_FILES[b][8])],
         ["p_maggie"]),
        ("C5", "statement", [src("comms/mailbox.mbox", MBOX_QUOTES[1]),
                             src("endpoint/file_audit.csv", CSV_FILES["endpoint/file_audit.csv"][2])], ["p_hank"]),
        ("C6", "temporal", [src("cctv/index.csv", CSV_FILES["cctv/index.csv"][3])], []),
        ("C7", "statement", [src("statements/hank_gibson.pdf", STATEMENT_QUOTES[1]),
                             src("endpoint/usbstor.txt", USBSTOR[12])], ["p_hank"]),
        ("C8", "custody", [{"file": "endpoint/security_log.csv", "line": None, "quote": None}], []),
    ]
    key = {"case_id": "1010F",
           "planted": [{"id": i, "kind": k, "detector": "rule", "sources": s, "persons": p}
                       for i, k, s, p in planted],
           "false_alarm_persons": ["p_frederik", "p_bg_17"],
           "tamper": {"file": "endpoint/security_log.csv", "seed": 1010, "altered_lines": [TAMPERED_LINE]}}
    _write(truth / "events_expected.json", json.dumps(events, indent=2) + "\n")
    _write(truth / "answer_key.json", json.dumps(key, indent=2) + "\n")

    # manifest: hash of the original (untampered) security log
    sec = list(CSV_FILES["endpoint/security_log.csv"])
    sec[TAMPERED_LINE - 1] = ORIGINAL_SEC_ROW
    original_sec = hashlib.sha256(_lines_text(sec).encode("utf-8")).hexdigest()
    buf = io.StringIO()
    wr = csv.writer(buf, lineterminator="\n")
    wr.writerow(["filename", "sha256", "collected_by", "collected_at"])
    for p in sorted(x for x in case.rglob("*") if x.is_file()):
        rel = p.relative_to(case).as_posix()
        sha = original_sec if rel == "endpoint/security_log.csv" else _sha(p)
        wr.writerow([rel, sha, world.COLLECTED_BY, f"2026-03-09T17:30:00{TS}"])
    _write(case / "manifest.csv", buf.getvalue())
    return case, extra, truth


@pytest.fixture(scope="session")
def pristine(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("pristine")
    build_case(root)
    return root


@pytest.fixture
def case(pristine, tmp_path):
    root = tmp_path / "c"
    shutil.copytree(pristine, root)
    return root / "CASE-1010F", root / "extra", root / "truth"


def run(case) -> list[str]:
    return validate(*case)


def has(problems: list[str], check: str) -> bool:
    return any(p.startswith(check + ":") for p in problems)


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_bytes().decode("utf-8")
    assert old in text, old
    path.write_bytes(text.replace(old, new, 1).encode("utf-8"))


def edit_json(path: Path, fn) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------------------------------- tests

def test_valid_fixture_passes(case):
    assert run(case) == []


def test_wrong_hash(case):
    c, _, _ = case
    edit(c / "access/badge_access.csv", "40455,rdr-219,OUT", "40455,rdr-219,OUT ")
    assert has(run(case), "check_manifest")


def test_tampered_file_hash_must_mismatch(case):
    c, _, _ = case
    sec = list(CSV_FILES["endpoint/security_log.csv"])
    sec[TAMPERED_LINE - 1] = ORIGINAL_SEC_ROW
    _write(c / "endpoint/security_log.csv", _lines_text(sec))
    probs = run(case)
    assert has(probs, "check_manifest") and has(probs, "check_C8")


def test_crlf(case):
    c, _, _ = case
    p = c / "cctv/index.csv"
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    assert has(run(case), "check_encoding")


def test_bom(case):
    c, _, _ = case
    p = c / "comms/mailbox.mbox"
    p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
    assert has(run(case), "check_encoding")


def test_unsorted_row(case):
    c, _, _ = case
    rows = list(CSV_FILES["access/badge_access.csv"])
    rows[6], rows[7] = rows[7], rows[6]
    _write(c / "access/badge_access.csv", _lines_text(rows))
    assert has(run(case), "check_sorted")


def test_bad_header_and_column_count(case):
    c, _, _ = case
    edit(c / "financial/transactions.csv", "timestamp,account", "time,account")
    edit(c / "endpoint/file_audit.csv", "48211968,E:", "48211968,E:,extra")
    probs = [p for p in run(case) if p.startswith("check_csv_headers:")]
    assert any("header" in p for p in probs) and any("columns" in p for p in probs)


def test_hank_at_219_after_revoke(case):
    c, _, _ = case
    edit(c / "access/badge_access.csv", f"2026-03-04T08:50:00{TS},40388,rdr-217,IN",
         f"2026-03-04T08:50:00{TS},40388,rdr-219,IN")
    assert has(run(case), "check_access_rules")


def test_unauthorized_badge_at_219(case):
    c, _, _ = case
    edit(c / "access/badge_access.csv", f"2026-03-04T09:00:00{TS},40392,rdr-217,IN",
         f"2026-03-04T09:00:00{TS},40392,rdr-219,IN")
    assert has(run(case), "check_access_rules")


def test_cam03_work_order_added(case):
    c, _, _ = case
    p = c / "it/maintenance_calendar.csv"
    p.write_bytes(p.read_bytes() + f"WO-9999,cam-03,2026-03-04T18:00:00{TS},2026-03-04T18:40:00{TS},"
                                   "Frederik Mendelssohn,Camera check\n".encode())
    assert has(run(case), "check_C6")


def test_other_camera_outage_without_work_order(case):
    c, _, _ = case
    edit(c / "it/maintenance_calendar.csv", "WO-3091,cam-02", "WO-3091,cam-05")
    assert has(run(case), "check_C6")


def test_quote_off_by_one_line(case):
    _, _, t = case
    edit_json(t / "events_expected.json", lambda evs: evs[3]["source"].update(line=evs[3]["source"]["line"] + 1))
    assert has(run(case), "check_truth_quotes")


def test_pdf_quote_off_by_one_line(case):
    _, _, t = case

    def bump(evs):
        e = next(e for e in evs if e["source"]["file"].endswith(".pdf"))
        e["source"]["line"] += 1
    edit_json(t / "events_expected.json", bump)
    assert has(run(case), "check_truth_quotes")


def test_uncited_row(case):
    _, _, t = case
    edit_json(t / "events_expected.json",
              lambda evs: evs.remove(next(e for e in evs if e["source"]["file"] == "financial/transactions.csv")))
    assert any("not cited" in p for p in run(case))


def test_duplicate_event_id(case):
    _, _, t = case
    edit_json(t / "events_expected.json", lambda evs: evs[1].update(id=evs[0]["id"]))
    assert has(run(case), "check_truth_quotes")


def test_answer_key_quote_wrong(case):
    _, _, t = case
    edit_json(t / "answer_key.json", lambda k: k["planted"][0]["sources"][0].update(line=3))
    assert has(run(case), "check_answer_key")


def test_answer_key_missing_c3(case):
    _, _, t = case
    edit_json(t / "answer_key.json", lambda k: k["planted"].pop(2))
    assert has(run(case), "check_answer_key")


def test_tamper_hits_hank_logon(case):
    _, _, t = case
    edit_json(t / "answer_key.json", lambda k: k["tamper"]["altered_lines"].append(2))
    assert has(run(case), "check_answer_key")


def test_missing_file(case):
    c, _, _ = case
    (c / "statements/maggie_price.pdf").unlink()
    probs = run(case)
    assert has(probs, "check_files_present") and has(probs, "check_C4")


def test_parking_inside_case_folder(case):
    c, e, _ = case
    shutil.move(str(e / "access/parking_exit.csv"), str(c / "access/parking_exit.csv"))
    assert has(run(case), "check_files_present")


def test_wrong_offset(case):
    c, _, _ = case
    edit(c / "network/wifi_ap_logs.csv", f"2026-03-04T09:12:00{TS}", "2026-03-04T09:12:00-04:00")
    assert has(run(case), "check_timestamps")


def test_wrong_offset_in_usbstor(case):
    c, _, _ = case
    edit(c / "endpoint/usbstor.txt", f"2025-06-12T14:22:09{TS}", "2025-06-12T19:22:09Z")
    assert has(run(case), "check_timestamps")


def test_mbox_date_not_est(case):
    c, _, _ = case
    edit(c / "comms/mailbox.mbox", "10:00:00 -0500", "10:00:00 +0000")
    assert has(run(case), "check_timestamps")


def test_non_example_address(case):
    c, _, _ = case
    edit(c / "comms/mailbox.mbox", "To: all@halvorsen.example", "To: all@princeton.edu")
    assert has(run(case), "check_no_real_domains")


def test_c1_hank_badge_after_out(case):
    c, _, _ = case
    edit(c / "access/badge_access.csv", f"2026-03-04T18:52:00{TS},40417", f"2026-03-04T18:20:00{TS},40388")
    assert has(run(case), "check_C1")


def test_c2_too_slow(case):
    c, _, _ = case
    edit(c / "access/badge_access.csv", f"2026-03-04T18:16:10{TS},40417,rdr-230",
         f"2026-03-04T18:15:00{TS},40417,rdr-230")
    assert has(run(case), "check_C2")


def test_c3_statement_missing(case):
    c, _, _ = case
    lines = list(STATEMENTS["statements/hank_gibson.pdf"])
    lines[2] = "I went home."
    _pdf(c / "statements/hank_gibson.pdf", lines)
    assert has(run(case), "check_C3")


def test_c5_no_titan_copy(case):
    c, _, _ = case
    edit(c / "endpoint/file_audit.csv", "hgibson,COPY", "hgibson,READ")
    assert has(run(case), "check_C5")


def test_c7_second_device_that_night(case):
    c, _, _ = case
    edit(c / "endpoint/usbstor.txt", "First InstallDate : 2025-06-12T14:22:09", "First InstallDate : 2026-03-04T09:22:09")
    assert has(run(case), "check_C7")


def test_red_herring_missing_patch_window(case):
    c, _, _ = case
    edit(c / "it/maintenance_calendar.csv", "WO-3117,lt-219", "WO-3117,lt-218")
    assert has(run(case), "check_red_herrings")


def test_badge_wifi_violation(case):
    c, _, _ = case
    edit(c / "network/wifi_ap_logs.csv", f"2026-03-04T18:50:00{TS},ap-2-07,{BG17}",
         f"2026-03-04T18:59:00{TS},ap-2-07,{BG17}")
    assert has(run(case), "check_badge_wifi_consistency")


def test_real_case_if_generated():
    if not (world.CASE_DIR.is_dir() and world.TRUTH_DIR.is_dir()):
        pytest.skip("real case not generated yet")
    problems = validate()
    assert problems == [], "\n".join(problems[:60])
