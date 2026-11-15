"""Event-type vocabulary for the analysis slice, from data/evidence/FORMAT.md section 3.1.

The only place that knows Person 1's event `type` strings and identifier kinds.
"""

BADGE_IN = {"badge_in"}
BADGE_OUT = {"badge_out"}
BADGE = BADGE_IN | BADGE_OUT

WIFI_ASSOC = {"wifi_assoc"}
WIFI_DISASSOC = {"wifi_disassoc"}
WIFI = WIFI_ASSOC | WIFI_DISASSOC | {"wifi_roam"}

LOGON = {"logon"}
LOGOFF = {"logoff"}
FILE_ACCESS = {"file_access", "file_read", "file_copy"}  # file_access comes from security_log.csv (tampered copy)
FILE_COPY = {"file_copy"}
USB = {"usb_mount"}

CAMERA_OFFLINE = {"camera_offline"}
CAMERA_ONLINE = {"camera_online"}
MAINTENANCE = {"maintenance_window"}

MESSAGE = {"email", "chat"}
STATEMENT = {"statement"}
PAYMENT = {"transaction"}
PARKING = {"parking_entry", "parking_exit"}

# Events whose room says where the identity physically was at that moment (Wi-Fi AP rooms are too coarse).
LOCATING = BADGE | LOGON

# Event type -> fact-graph edge type (person -> device).
EDGE_TYPE = {
    **{t: "used" for t in BADGE | WIFI | PARKING},
    **{t: "accessed" for t in LOGON | LOGOFF | FILE_ACCESS | USB | MAINTENANCE},
    **{t: "sent" for t in MESSAGE},
    **{t: "paid" for t in PAYMENT},
    **{t: "said" for t in STATEMENT},
}

# inventory.csv column -> actor.kind (FORMAT.md sections 3 and 7).
ALIAS_COLUMNS = {
    "badge": "badge",
    "laptop_mac": "mac",
    "local_account": "account",
    "bank_account": "account",  # transactions carry actor {kind: account, value: CHK-7731} (FORMAT.md 3.1)
    "email": "email",
    "slack_handle": "slack",
    "parking_permit": "permit",
    "plate": "plate",
    "name": "name",
}
