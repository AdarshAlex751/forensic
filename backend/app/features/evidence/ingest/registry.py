"""Which parser handles which file. Add a data type = write a parser + add one row here.

Matching is on the path relative to the case (or extra) folder. Files without a parser (manifest.csv, brief.pdf,
facilities/devices.csv, Slack users/channels/dms) still get an evidence.json row, with 0 records.
"""
from __future__ import annotations

import fnmatch

from .base import Parser


def _table() -> list[tuple[str, Parser]]:
    from . import csv_parsers as c, doc_parsers as d  # lazy: keeps the registry importable on its own

    return [
        ("access/badge_access.csv", c.parse_badge),
        ("network/wifi_ap_logs.csv", c.parse_wifi),
        ("endpoint/security_log.csv", c.parse_security_log),
        ("endpoint/file_audit.csv", c.parse_file_audit),
        ("cctv/index.csv", c.parse_cctv),
        ("it/maintenance_calendar.csv", c.parse_maintenance),
        ("financial/transactions.csv", c.parse_transactions),
        ("access/parking_exit.csv", c.parse_parking),
        ("endpoint/usbstor.txt", d.parse_usbstor),
        ("comms/mailbox.mbox", d.parse_mbox),
        ("comms/slack_export/*/*.json", d.parse_slack_day),
        ("statements/*.pdf", d.parse_statement),
    ]


def parser_for(rel: str) -> Parser | None:
    for pattern, fn in _table():
        if fnmatch.fnmatchcase(rel, pattern):
            return fn
    return None
