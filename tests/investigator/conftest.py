"""Shared fixtures for the investigator tests: a tiny synthetic case folder with real bytes on disk.

Characters come from CASE.md (test fixtures only; production code never hard-codes them).
"""
import hashlib
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


BS = chr(92)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_pdf(lines: list[str]) -> bytes:
    """Smallest valid one-page PDF with one text line per line (pdfplumber extracts them in order)."""
    esc = lambda s: s.replace(BS, BS * 2).replace("(", BS + "(").replace(")", BS + ")")  # noqa: E731
    body = "BT /F1 12 Tf 72 720 Td 16 TL " + " ".join(f"({esc(x)}) Tj T*" for x in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(body)} >>\nstream\n{body}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


FILES: dict[str, bytes] = {
    "access/badge_access.csv": (
        "timestamp,badge_id,reader_id,direction,result\n"
        "2026-03-04T18:16:10-05:00,40420,rdr-230,IN,GRANTED\n"
        "2026-03-04T18:16:40-05:00,40420,rdr-219,IN,GRANTED\n"
    ).encode(),
    # the tampered copy: its hash will not match the manifest hash below
    "endpoint/security_log.csv": (
        "TimeCreated,EventID,Computer,TargetUserName,LogonType,ObjectName,AccessMask,ProcessName\n"
        "2026-03-04T18:17:05-05:00,4624,LT-219,hgibson,2,,,C:\\Windows\\System32\\winlogon.exe\n"
        "2026-03-04T18:18:02-05:00,4663,LT-219,hgibson,,C:\\Projects\\Titan\\thruster_v4.step,0x1,C:\\Windows\\explorer.exe\n"
    ).encode(),
    "endpoint/file_audit.csv": (
        "timestamp,host,user,action,path,bytes,target_volume\n"
        "2026-03-04T18:18:02-05:00,LT-219,hgibson,COPY,C:\\Projects\\Titan\\thruster_v4.step,48211968,E:\n"
    ).encode(),
    "comms/slack_export/D0HANKKIM/2026-03-04.json": (
        '[\n  {\n    "type": "message",\n    "user": "U1",\n'
        '    "text": "bring what you can",\n    "ts": "1772638200.000100"\n  }\n]\n'
    ).encode(),
    "statements/hank_gibson.pdf": make_pdf(["Statement of Hank Gibson", "Date: 2026-03-09", "", "I went straight home at six."]),
}


@dataclass
class Case:
    root: Path
    evidence: list[dict] = field(default_factory=list)

    def line(self, rel: str, n: int) -> str:
        text = (self.root / rel).read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
        return text[n - 1]

    def hash(self, rel: str) -> str:
        return sha((self.root / rel).read_bytes())

    def event(self, eid: str, etype: str, t: str, rel: str, line: int, quote: str | None = None,
              actor: dict | None = None, **extra) -> dict:
        return {
            "id": eid, "t": t, "type": etype, "person": None, "device": None, "room": None,
            "actor": actor, "attrs": {},
            "source": {"file": rel, "line": line, "quote": self.line(rel, line) if quote is None else quote,
                       "sha256": self.hash(rel)},
            **extra,
        }


@pytest.fixture()
def case() -> Case:
    with tempfile.TemporaryDirectory(prefix="inv-case-") as tmp:
        root = Path(tmp) / "CASE-1010F"
        for rel, data in FILES.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        c = Case(root=root)
        for rel in FILES:
            h = c.hash(rel)
            manifest = sha(b"original untampered bytes") if rel == "endpoint/security_log.csv" else h
            c.evidence.append({"file": rel, "sha256": h, "manifest_sha256": manifest,
                               "manifest_match": h == manifest, "parser": "csv", "records": 1})
        yield c
