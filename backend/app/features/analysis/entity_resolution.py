"""Stage 3: entity resolution.

Evidence events arrive with `person: null` and a raw `actor: {kind, value}` (FORMAT.md section 3).
Hard links: inventory.csv identifiers. Soft links: fuzzy name match for `name` actors.
Host sessions: events with no actor on a host (usb_mount) go to the account logged on there at that time.
TODO: all-MiniLM-L6-v2 similarity for name variants fuzzy matching misses.
"""
import re
from typing import Any

from rapidfuzz import fuzz, process

from app.features.analysis import timeutil, vocab

FUZZY_THRESHOLD = 90


def normalize(kind: str, value: Any) -> str:
    v = str(value).strip()
    if kind == "mac":
        hexes = re.sub(r"[^0-9a-fA-F]", "", v).upper()
        return ":".join(hexes[i:i + 2] for i in range(0, len(hexes), 2))
    if kind in ("plate", "permit", "badge"):
        return re.sub(r"[\s-]", "", v).upper()
    if kind == "account":
        return v.split("\\")[-1].split("@")[0].lower()  # DOMAIN\hgibson, hgibson@host -> hgibson
    if kind == "slack":
        return v.lstrip("@").lower()
    return v.lower()


def alias_key(kind: str, value: Any) -> str:
    return f"{kind}:{normalize(kind, value)}"


def _pid(row: dict) -> str | None:
    return row.get("person_id") or row.get("id") or None


def build_alias_index(inventory: list[dict[str, str]]) -> dict[str, str]:
    """'badge:40417' -> 'p_bg_17' for every identifier column in the inventory."""
    index: dict[str, str] = {}
    for row in inventory:
        if pid := _pid(row):
            for col, kind in vocab.ALIAS_COLUMNS.items():
                if row.get(col):
                    index[alias_key(kind, row[col])] = pid
    return index


def build_persons(inventory: list[dict[str, str]]) -> list[dict[str, Any]]:
    persons = []
    for row in inventory:
        if not (pid := _pid(row)):
            continue
        persons.append({
            "id": pid,
            "name": row.get("name", ""),
            "role": row.get("role", ""),
            "suite": row.get("home_room") or row.get("suite", ""),
            "aliases": [f"{kind}:{row[col]}" for col, kind in vocab.ALIAS_COLUMNS.items() if row.get(col)],
            "anomaly": 0.0,
            "features": {},
            "community": -1,
        })
    return persons


def match_name(name: str, persons: list[dict[str, Any]]) -> str | None:
    """Fuzzy-match a free-text name ('H. Gibson', 'Hank') to a person id."""
    choices = {p["id"]: p["name"] for p in persons if p.get("name")}
    if not name or not choices:
        return None
    hit = process.extractOne(name, choices, scorer=fuzz.WRatio)
    return hit[2] if hit and hit[1] >= FUZZY_THRESHOLD else None


def resolve_identifier(kind: str, value: Any, index: dict[str, str]) -> str | None:
    """Exact lookup of one raw identifier ('email', 'x@y') -> person id."""
    return index.get(alias_key(kind, value)) if value not in (None, "") else None


def _resolve_actor(actor: dict | None, index: dict[str, str], persons: list[dict]) -> str | None:
    if not actor or actor.get("value") in (None, ""):
        return None
    hit = resolve_identifier(actor["kind"], actor["value"], index)
    if not hit and actor["kind"] == "name":
        hit = match_name(str(actor["value"]), persons)
    return hit


HOST_ACTIVITY_WINDOW_S = 15 * 60


def _host(e: dict) -> str | None:
    return (e.get("attrs") or {}).get("host") or e.get("device")


def _attribute_host_sessions(events: list[dict], untrusted_files: set[str]) -> None:
    """Give actor-less host events (usb_mount) a person, using trusted records only:
    1. the account logged on to that host at the time (logon/logoff), else
    2. the account with the nearest file activity on that host within 15 min.
    Logons from an untrusted file (manifest mismatch) are never used.
    """
    ordered = sorted((e for e in events if e.get("t")), key=lambda e: timeutil.parse(e["t"]))
    trusted = [e for e in ordered if (e.get("source") or {}).get("file") not in untrusted_files]
    session: dict[str, str | None] = {}
    for e in ordered:
        trusted_e = (e.get("source") or {}).get("file") not in untrusted_files
        if e["type"] in vocab.LOGON and e.get("person") and trusted_e:
            session[_host(e)] = e["person"]
        elif e["type"] in vocab.LOGOFF and trusted_e:
            session[_host(e)] = None
        elif not e.get("person") and not e.get("actor") and session.get(_host(e)):
            e["person"], e["person_via"] = session[_host(e)], "host_session"

    activity = [e for e in trusted if e["type"] in vocab.FILE_ACCESS and e.get("person")]
    for e in ordered:
        if e.get("person") or e.get("actor") or e["type"] not in vocab.USB:
            continue
        t = timeutil.parse(e["t"])
        near = [(abs((timeutil.parse(a["t"]) - t).total_seconds()), a) for a in activity if _host(a) == _host(e)]
        near = [x for x in near if x[0] <= HOST_ACTIVITY_WINDOW_S]
        if near:
            e["person"], e["person_via"] = min(near, key=lambda x: x[0])[1]["person"], "host_activity"


def resolve_events(events: list[dict], index: dict[str, str], persons: list[dict],
                   untrusted_files: set[str] | None = None) -> list[dict]:
    """Copies of events with `person` filled. Badge reads go to the card holder, which is a fact
    about the card, not about who held it (CASE.md: the system never concludes a badge was copied)."""
    out = []
    for e in events:
        e = dict(e)
        e["person"] = _resolve_actor(e.get("actor"), index, persons) or e.get("person")
        out.append(e)
    _attribute_host_sessions(out, untrusted_files or set())
    return out
