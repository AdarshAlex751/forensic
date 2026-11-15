"""Parsers for the CSV evidence files (data/evidence/RAW_FORMATS.md, FORMAT.md section 3.1).

Every parser reads ctx.lines (header = line 1), checks the header, parses each data line with the csv module and
cites the whole raw line as source.quote. Room/device data comes only from the case's facilities/devices.csv
(ctx.device_room / ctx.host_device). A malformed row raises ValueError("<file>:<line>: ...").
"""
from __future__ import annotations

import csv
from typing import Iterator

from .base import FileCtx, est_ts, make_event, parse_iso

BADGE_HEADER = ["timestamp", "badge_id", "reader_id", "direction", "result"]
WIFI_HEADER = ["timestamp", "ap_id", "client_mac", "event", "rssi", "ssid"]
SECURITY_HEADER = ["TimeCreated", "EventID", "Computer", "TargetUserName", "LogonType", "ObjectName", "AccessMask",
                   "ProcessName"]
FILE_AUDIT_HEADER = ["timestamp", "host", "user", "action", "path", "bytes", "target_volume"]
CCTV_HEADER = ["camera_id", "window_start", "window_end", "status", "clip_ref"]
MAINTENANCE_HEADER = ["work_order", "asset", "start", "end", "technician", "description"]
TRANSACTIONS_HEADER = ["timestamp", "account", "description", "counterparty", "amount", "balance"]
PARKING_HEADER = ["timestamp", "lane", "permit_id", "plate", "direction"]


def _split(line: str) -> list[str]:
    return next(csv.reader([line]), [])


def _rows(ctx: FileCtx, header: list[str]) -> Iterator[tuple[int, str, dict[str, str]]]:
    """Yield (line number, raw line, {column: value}) for every non-empty data line."""
    lines = ctx.lines
    if not lines:
        raise ValueError(f"{ctx.rel}:1: empty file, expected header {','.join(header)}")
    got = _split(lines[0].lstrip("﻿").rstrip("\r"))
    if got != header:
        raise ValueError(f"{ctx.rel}:1: unexpected header {lines[0]!r}, expected {','.join(header)}")
    for i, raw in enumerate(lines[1:], start=2):
        if raw.strip() == "":
            continue
        vals = _split(raw.rstrip("\r"))
        if len(vals) != len(header):
            raise ValueError(f"{ctx.rel}:{i}: expected {len(header)} columns, got {len(vals)}: {raw!r}")
        yield i, raw, dict(zip(header, vals))


def _ts(ctx: FileCtx, line: int, text: str) -> str:
    try:
        return est_ts(parse_iso(text))
    except ValueError as exc:
        raise ValueError(f"{ctx.rel}:{line}: bad timestamp {text!r}: {exc}") from None


def _int(ctx: FileCtx, line: int, text: str, col: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"{ctx.rel}:{line}: {col} is not an integer: {text!r}") from None


def _float(ctx: FileCtx, line: int, text: str, col: str) -> float:
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{ctx.rel}:{line}: {col} is not a number: {text!r}") from None


def _opt(text: str) -> str | None:
    """FORMAT.md rule: a missing scalar is null, never ""."""
    return text if text != "" else None


def _pick(ctx: FileCtx, line: int, value: str, mapping: dict[str, str], col: str) -> str:
    try:
        return mapping[value]
    except KeyError:
        raise ValueError(f"{ctx.rel}:{line}: unknown {col} {value!r}") from None


def parse_badge(ctx: FileCtx) -> list[dict]:
    types = {"IN": "badge_in", "OUT": "badge_out"}
    out = []
    for n, raw, r in _rows(ctx, BADGE_HEADER):
        reader = r["reader_id"]
        out.append(make_event(
            ctx, n, raw, t=_ts(ctx, n, r["timestamp"]), type=_pick(ctx, n, r["direction"], types, "direction"),
            device=_opt(reader), room=ctx.device_room(reader),
            actor={"kind": "badge", "value": r["badge_id"]},
            attrs={"reader": _opt(reader), "result": _opt(r["result"])}))
    return out


def parse_wifi(ctx: FileCtx) -> list[dict]:
    types = {"ASSOC": "wifi_assoc", "DISASSOC": "wifi_disassoc", "ROAM": "wifi_roam"}
    out = []
    for n, raw, r in _rows(ctx, WIFI_HEADER):
        ap = r["ap_id"]
        out.append(make_event(
            ctx, n, raw, t=_ts(ctx, n, r["timestamp"]), type=_pick(ctx, n, r["event"], types, "event"),
            device=_opt(ap), room=ctx.device_room(ap),
            actor={"kind": "mac", "value": r["client_mac"]},
            attrs={"ap": _opt(ap), "rssi": _int(ctx, n, r["rssi"], "rssi"), "ssid": _opt(r["ssid"])}))
    return out


def parse_security_log(ctx: FileCtx) -> list[dict]:
    out = []
    for n, raw, r in _rows(ctx, SECURITY_HEADER):
        event_id = _int(ctx, n, r["EventID"], "EventID")
        host = ctx.host_device(r["Computer"])
        if event_id == 4624:
            typ = "logon"
            attrs = {"event_id": event_id, "logon_type": _int(ctx, n, r["LogonType"], "LogonType"), "host": host}
        elif event_id == 4634:
            typ = "logoff"
            attrs = {"event_id": event_id, "host": host}
        elif event_id == 4663:
            typ = "file_access"
            attrs = {"event_id": event_id, "path": _opt(r["ObjectName"]), "access_mask": _opt(r["AccessMask"]),
                     "host": host}
        else:
            raise ValueError(f"{ctx.rel}:{n}: unsupported EventID {event_id}")
        out.append(make_event(
            ctx, n, raw, t=_ts(ctx, n, r["TimeCreated"]), type=typ, device=host, room=ctx.device_room(host),
            actor={"kind": "account", "value": r["TargetUserName"]}, attrs=attrs))
    return out


def parse_file_audit(ctx: FileCtx) -> list[dict]:
    types = {"READ": "file_read", "COPY": "file_copy"}
    out = []
    for n, raw, r in _rows(ctx, FILE_AUDIT_HEADER):
        host = ctx.host_device(r["host"])
        out.append(make_event(
            ctx, n, raw, t=_ts(ctx, n, r["timestamp"]), type=_pick(ctx, n, r["action"], types, "action"),
            device=host, room=ctx.device_room(host),
            actor={"kind": "account", "value": r["user"]},
            attrs={"path": _opt(r["path"]), "bytes": _int(ctx, n, r["bytes"], "bytes"),
                   "target_volume": _opt(r["target_volume"]), "host": host}))
    return out


def parse_cctv(ctx: FileCtx) -> list[dict]:
    out = []
    for n, raw, r in _rows(ctx, CCTV_HEADER):
        status = r["status"]
        if status == "RECORDING":
            continue
        if status != "OFFLINE":
            raise ValueError(f"{ctx.rel}:{n}: unknown status {status!r}")
        cam = r["camera_id"]
        room = ctx.device_room(cam)
        attrs = {"camera": _opt(cam), "clip_ref": _opt(r["clip_ref"])}
        for typ, col in (("camera_offline", "window_start"), ("camera_online", "window_end")):
            out.append(make_event(ctx, n, raw, t=_ts(ctx, n, r[col]), type=typ, device=_opt(cam), room=room,
                                  actor=None, attrs=dict(attrs)))
    return out


def parse_maintenance(ctx: FileCtx) -> list[dict]:
    out = []
    for n, raw, r in _rows(ctx, MAINTENANCE_HEADER):
        asset = r["asset"]
        device = asset if asset in ctx.devices else None
        start = _ts(ctx, n, r["start"])
        out.append(make_event(
            ctx, n, raw, t=start, type="maintenance_window", device=device, room=ctx.device_room(device),
            actor={"kind": "name", "value": r["technician"]},
            attrs={"start": start, "end": _ts(ctx, n, r["end"]), "asset": _opt(asset),
                   "work_order": _opt(r["work_order"]), "technician": _opt(r["technician"])}))
    return out


def parse_transactions(ctx: FileCtx) -> list[dict]:
    out = []
    for n, raw, r in _rows(ctx, TRANSACTIONS_HEADER):
        out.append(make_event(
            ctx, n, raw, t=_ts(ctx, n, r["timestamp"]), type="transaction", device=None, room=None,
            actor={"kind": "account", "value": r["account"]},
            attrs={"account": _opt(r["account"]), "amount": _float(ctx, n, r["amount"], "amount"),
                   "counterparty": _opt(r["counterparty"]), "description": _opt(r["description"])}))
    return out


def parse_parking(ctx: FileCtx) -> list[dict]:
    types = {"IN": "parking_entry", "OUT": "parking_exit"}
    out = []
    for n, raw, r in _rows(ctx, PARKING_HEADER):
        out.append(make_event(
            ctx, n, raw, t=_ts(ctx, n, r["timestamp"]), type=_pick(ctx, n, r["direction"], types, "direction"),
            device=None, room=None, actor={"kind": "permit", "value": r["permit_id"]},
            attrs={"plate": _opt(r["plate"]), "lane": _opt(r["lane"])}))
    return out
