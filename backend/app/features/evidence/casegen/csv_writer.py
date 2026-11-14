"""One writer for all eight CSV case files (headers exactly as data/evidence/RAW_FORMATS.md)."""
from __future__ import annotations

from pathlib import Path

from .records import Record, Written
from .world import F_AUDIT, F_BADGE, F_CCTV, F_MAINT, F_PARKING, F_SEC, F_TXN, F_WIFI

HEADERS: dict[str, list[str]] = {
    F_BADGE: ["timestamp", "badge_id", "reader_id", "direction", "result"],
    F_WIFI: ["timestamp", "ap_id", "client_mac", "event", "rssi", "ssid"],
    F_SEC: ["TimeCreated", "EventID", "Computer", "TargetUserName", "LogonType", "ObjectName", "AccessMask",
            "ProcessName"],
    F_AUDIT: ["timestamp", "host", "user", "action", "path", "bytes", "target_volume"],
    F_CCTV: ["camera_id", "window_start", "window_end", "status", "clip_ref"],
    F_MAINT: ["work_order", "asset", "start", "end", "technician", "description"],
    F_TXN: ["timestamp", "account", "description", "counterparty", "amount", "balance"],
    F_PARKING: ["timestamp", "lane", "permit_id", "plate", "direction"],
}


def row_text(source: str, fields: dict[str, str]) -> str:
    """Render one CSV line. Fields never contain commas, quotes or newlines (checked), so no CSV quoting."""
    header = HEADERS[source]
    if set(fields) != set(header):
        raise ValueError(f"{source}: fields {sorted(fields)} != header {header}")
    values = []
    for col in header:
        v = fields[col]
        v = "" if v is None else str(v)
        if any(c in v for c in ',"\r\n'):
            raise ValueError(f"{source}: field {col!r} has a comma, quote or newline: {v!r}")
        values.append(v)
    return ",".join(values)


def parse_row(source: str, line: str) -> dict[str, str]:
    """Inverse of row_text, for builders that start from an existing raw line."""
    header = HEADERS[source]
    parts = line.split(",")
    if len(parts) != len(header):
        raise ValueError(f"{source}: {len(parts)} values for {len(header)} columns: {line!r}")
    return dict(zip(header, parts))


def write_csv(records: list[Record], out_dir: Path) -> list[Written]:
    """Write every CSV file the records belong to. Rows keep the given order; header is line 1."""
    by_file: dict[str, list[Record]] = {}
    for r in records:
        if r.source not in HEADERS:
            raise ValueError(f"not a CSV source: {r.source}")
        by_file.setdefault(r.source, []).append(r)
    written: list[Written] = []
    for source, recs in by_file.items():
        lines = [",".join(HEADERS[source])]
        for r in recs:
            text = row_text(source, r.fields)
            lines.append(text)
            for ev in r.events:
                written.append(Written(event=ev, record=r, line=len(lines), quote=text))
        path = out_dir / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return written
