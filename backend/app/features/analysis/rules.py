"""Stage 7a: hard-conflict rules. Each rule is a pure function returning contradiction dicts
(without ids; run.py numbers them). Wording stays factual: report what conflicts, never who did it.
"""
import logging
import re
from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Any, Callable

from app.features.analysis import timeutil, vocab

WalkTime = Callable[[str, str], dict]
log = logging.getLogger(__name__)

# Leaving a room and dropping off Wi-Fi a few minutes later is normal; tune on the real baseline.
WIFI_AFTER_BADGE_MIN = timedelta(minutes=20)


def _t(e: dict):
    return timeutil.parse(e["t"])


def _sorted(events: list[dict]) -> list[dict]:
    return sorted((e for e in events if e.get("t")), key=_t)


def _by_person(events: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for e in _sorted(events):
        if e.get("person"):
            out[e["person"]].append(e)
    return out


def _attrs(e: dict) -> dict:
    return e.get("attrs") or {}


def impossible_travel(events: list[dict], walk_time: WalkTime) -> list[dict]:
    """Same identity at two rooms closer in time than the shortest walk between them (C2).
    A room pair scene cannot route (walk_time raises) is skipped: no walk estimate, no claim."""
    found, unmapped = [], set()
    for person, evs in _by_person(events).items():
        located = [e for e in evs if e["type"] in vocab.LOCATING and e.get("room")]
        for a, b in zip(located, located[1:]):
            if a["room"] == b["room"]:
                continue
            gap = (_t(b) - _t(a)).total_seconds()
            try:
                walk = walk_time(a["room"], b["room"])
            except ValueError:
                unmapped.add(tuple(sorted((a["room"], b["room"]))))
                continue
            if gap < walk["seconds"]:
                ident = (a.get("actor") or {}).get("kind", "identity")
                found.append({
                    "kind": "physical",
                    "events": [a["id"], b["id"]],
                    "score": 1.0,
                    "explanation": (
                        f"The same {ident} ({person}) is recorded in room {a['room']} at {timeutil.spoken(_t(a))} "
                        f"and in room {b['room']} at {timeutil.spoken(_t(b))}, {gap:.0f} s apart. "
                        f"The shortest walk is {walk['seconds']:.0f} s."
                    ),
                    "path": walk.get("path", []),
                    "walk_s": walk["seconds"],
                    "gap_s": gap,
                    "persons": [person],
                    "rule": "impossible_travel",
                })
    if unmapped:
        log.warning("impossible_travel: %d room pair(s) have no walking route from scene; skipped", len(unmapped))
    return found


def wifi_after_last_badge(events: list[dict]) -> list[dict]:
    """Laptop still on the floor Wi-Fi well after the person's last badge read of the day (C1)."""
    found = []
    for person, evs in _by_person(events).items():
        by_day: dict = defaultdict(list)
        for e in evs:
            by_day[timeutil.local_day(_t(e))].append(e)
        for day_evs in by_day.values():
            badges = [e for e in day_evs if e["type"] in vocab.BADGE]
            if not badges or badges[-1]["type"] not in vocab.BADGE_OUT:
                continue
            last_out = badges[-1]
            wifi_after = [e for e in day_evs if e["type"] in vocab.WIFI and _t(e) - _t(last_out) > WIFI_AFTER_BADGE_MIN]
            if not wifi_after:
                continue
            last_wifi = wifi_after[-1]
            found.append({
                "kind": "temporal",
                "events": [last_out["id"], last_wifi["id"]],
                "score": 0.9,
                "explanation": (
                    f"{person}'s last badge read was OUT of room {last_out.get('room')} at {timeutil.spoken(_t(last_out))}, "
                    f"with no later badge read, but their laptop was on the floor Wi-Fi until {timeutil.spoken(_t(last_wifi))}."
                ),
                "gap_s": (_t(last_wifi) - _t(last_out)).total_seconds(),
                "persons": [person],
                "rule": "wifi_after_last_badge",
            })
    return found


def camera_gap_without_work_order(events: list[dict]) -> list[dict]:
    """Camera offline window with no maintenance window on that camera overlapping it (C6)."""
    windows = defaultdict(list)
    for e in events:
        if e.get("type") in vocab.MAINTENANCE and _attrs(e).get("start") and _attrs(e).get("end"):
            windows[_attrs(e).get("asset")].append((timeutil.parse(_attrs(e)["start"]), timeutil.parse(_attrs(e)["end"])))

    found = []
    ordered = _sorted(events)
    for i, off in enumerate(ordered):
        if off["type"] not in vocab.CAMERA_OFFLINE:
            continue
        cam = _attrs(off).get("camera") or off.get("device")
        on = next((e for e in ordered[i + 1:] if e["type"] in vocab.CAMERA_ONLINE
                   and (_attrs(e).get("camera") or e.get("device")) == cam), None)
        start, end = _t(off), (_t(on) if on else _t(off))
        if any(ws <= end and start <= we for ws, we in windows.get(cam, [])):
            continue
        until = f" until {timeutil.spoken(end)}" if on else ""
        found.append({
            "kind": "temporal",
            "events": [off["id"]] + ([on["id"]] if on else []),
            "score": 0.8,
            "explanation": f"Camera {cam} was offline from {timeutil.spoken(start)}{until} with no maintenance window or work order covering it.",
            "gap_s": (end - start).total_seconds(),
            "rule": "camera_gap_without_work_order",
        })
    return found


MANIFEST = "manifest.csv"


def _tampered(ev: dict) -> bool:
    """Listed in the manifest with a different hash. A file the manifest does not list (manifest_sha256 null)
    is withheld evidence released later (extra/, e.g. the parking exit log), not a custody failure."""
    if ev["file"] == MANIFEST or ev.get("manifest_match", True) or ev.get("released"):
        return False
    return ev.get("manifest_sha256", "unknown") is not None


def untrusted_files(evidence: list[dict]) -> set[str]:
    """Files whose hash does not match the manifest. The manifest itself is the reference, never in the list."""
    return {ev["file"] for ev in evidence if _tampered(ev)}


def custody_mismatch(events: list[dict], evidence: list[dict]) -> list[dict]:
    """Evidence file whose hash does not match its manifest entry (C8), with the events drawn from it.
    Those events are excluded from every other check."""
    found = []
    for ev in evidence:
        if not _tampered(ev):
            continue
        tainted = [e["id"] for e in events if (e.get("source") or {}).get("file") == ev["file"]]
        found.append({
            "kind": "custody",
            "events": tainted,
            "score": 1.0,
            "explanation": (
                f"{ev['file']} does not match its manifest hash; "
                f"{len(tainted)} event(s) come from this file. They are treated as untrusted and left out of every other check."
            ),
            "file": ev["file"],
            "rule": "custody_mismatch",
        })
    return found


# ---------------------------------------------------------------- statements vs records
# The NLI model cannot do clock arithmetic ("home at six" vs a 6:44 pm car exit scores ~0.02), so claims
# about *when* someone left and *when* a drive was first used are checked here; nli.py handles the rest.

CLAIM_TYPES = vocab.STATEMENT | {"email"}
PRESENCE = vocab.BADGE | vocab.WIFI | vocab.LOGON | vocab.LOGOFF | vocab.FILE_ACCESS | vocab.USB | {"parking_exit"}

_WORD_HOURS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
_TIME_RE = re.compile(
    r"\b(?P<approx>around|about|roughly|at|by|after|before)?\s*"
    r"(?P<h>\d{1,2}|" + "|".join(_WORD_HOURS) + r")(?::(?P<m>\d{2}))?\s*(?P<ampm>am|pm|a\.m\.|p\.m\.)?",
    re.IGNORECASE,
)
_LEAVE_RE = re.compile(r"\b(left|leave|went home|go home|headed home|straight home|went straight home)\b", re.IGNORECASE)
# "left the room / lab / office": a claim about one room, checked against badge reads only, never against
# building-level records (Wi-Fi, parking exit). "went home" / "left" are building-level.
_ROOM_SCOPE_RE = re.compile(r"\bleft (?:the |my |our )?(?:room|lab|office|suite)\b|\bleft room \d+", re.IGNORECASE)
_DRIVE_RE = re.compile(r"\b(drive|usb|thumb ?drive|stick)\b", re.IGNORECASE)
_PAST_RE = re.compile(r"\blast (year|month)\b|\b(\d+|a|two|three|several) (years?|months?) ago\b", re.IGNORECASE)
TOLERANCE = {"approx": timedelta(minutes=20), "exact": timedelta(minutes=10)}


def claimed_time(quote: str) -> tuple[int, int, timedelta] | None:
    """'at six' -> (18, 0, 10 min); 'around 6:30' -> (18, 30, 20 min). Needs a time word or am/pm nearby.

    Hours 1-7 without am/pm read as evening: these statements are about leaving work.
    """
    for m in _TIME_RE.finditer(quote):
        if not (m.group("approx") or m.group("m") or m.group("ampm")):
            continue  # a bare number ("two files") is not a time
        h_raw = m.group("h").lower()
        h = _WORD_HOURS.get(h_raw, int(h_raw) if h_raw.isdigit() else -1)
        if not 0 <= h <= 23:
            continue
        ampm = (m.group("ampm") or "").replace(".", "").lower()
        if ampm == "pm" and h < 12 or (not ampm and 1 <= h <= 7):
            h += 12
        tol = TOLERANCE["approx" if (m.group("approx") or "").lower() in ("around", "about", "roughly") else "exact"]
        return h, int(m.group("m") or 0), tol
    return None


def _claim_persons(claim: dict, persons: list[dict]) -> list[str]:
    """Speaker plus anyone named by first name in the quote ('Hank and I ...')."""
    out = [claim["person"]]
    quote = claim["source"]["quote"]
    for p in persons:
        first = (p.get("name") or "").split(" ")[0]
        if first and re.search(rf"\b{re.escape(first)}\b", quote) and p["id"] not in out:
            out.append(p["id"])
    return out


def focus_days(found: list[dict], events: list[dict], min_rules: int = 2) -> set:
    """Days on which at least `min_rules` *different* hard rules fire (physical/temporal).

    Statements are checked against these days only: an interview is about a specific night, and the
    logs, not the answer key, say which one. Requiring two independent rules keeps one noisy rule
    (e.g. walk times before the real floor plan lands) from picking the night on its own.
    """
    by_id = {e["id"]: e for e in events}
    rules_per_day: dict = defaultdict(set)
    for c in found:
        if c["kind"] in ("physical", "temporal"):
            for eid in c["events"]:
                if eid in by_id:
                    rules_per_day[timeutil.local_day(_t(by_id[eid]))].add(c["rule"])
    return {day for day, hit in rules_per_day.items() if len(hit) >= min_rules}


def leave_time_claims(events: list[dict], persons: list[dict], days: set) -> list[dict]:
    """'I went home at six' / 'X and I left around 6:30' vs each named person's last presence that day (C3, C4)."""
    by_person = _by_person(events)
    found = []
    for claim in (e for e in _sorted(events) if e["type"] in CLAIM_TYPES and e.get("person")):
        quote = claim["source"]["quote"]
        when = claimed_time(quote)
        if not (when and _LEAVE_RE.search(quote)):
            continue
        h, m, tol = when
        room_scope = bool(_ROOM_SCOPE_RE.search(quote))
        for day in sorted(days):
            stated = datetime.combine(day, time(h, m), tzinfo=timeutil.EST)
            for pid in _claim_persons(claim, persons):
                scope = vocab.BADGE if room_scope else PRESENCE
                present = [e for e in by_person.get(pid, []) if e["type"] in scope and timeutil.local_day(_t(e)) == day]
                if not present:
                    continue
                last = present[-1]
                last_badge = next((e for e in reversed(present) if e["type"] in vocab.BADGE), None)
                delta = (_t(last) - stated).total_seconds()
                if abs(delta) <= tol.total_seconds():
                    continue
                cited = [claim["id"], *dict.fromkeys(x["id"] for x in (last_badge, last) if x)]
                badge_txt = (f" Their last badge read was {last_badge['type'].replace('badge_', '').upper()} of room "
                             f"{last_badge.get('room')} at {timeutil.spoken(_t(last_badge))}." if last_badge else "")
                found.append({
                    "kind": "statement",
                    "events": cited,
                    "score": 0.95,
                    "explanation": (
                        f"{claim['attrs'].get('speaker') or claim['person']} said \"{quote}\" "
                        f"({pid}'s stated time {timeutil.spoken(stated)}).{badge_txt} "
                        f"Their last recorded activity that day was {last['type']} at {timeutil.spoken(_t(last))}, "
                        f"{abs(delta) / 60:.0f} min {'after' if delta > 0 else 'before'} the stated time."
                    ),
                    "gap_s": delta,
                    "persons": [pid],
                    "rule": "leave_time_claim",
                })
    return found


def drive_history_claims(events: list[dict]) -> list[dict]:
    """'IT gave me that drive last year' vs the drive's first_seen time in the USB history (C7)."""
    by_person = _by_person(events)
    found = []
    for claim in (e for e in _sorted(events) if e["type"] in CLAIM_TYPES and e.get("person")):
        quote = claim["source"]["quote"]
        past = _PAST_RE.search(quote)
        if not (_DRIVE_RE.search(quote) and past):
            continue
        said = _t(claim)
        unit = (past.group(1) or past.group(3) or "year").lower()
        cutoff = said.replace(month=1, day=1, hour=0, minute=0, second=0) if unit.startswith("year") \
            else said.replace(day=1, hour=0, minute=0, second=0)
        for usb in (e for e in by_person.get(claim["person"], []) if e["type"] in vocab.USB):
            first_seen = (usb.get("attrs") or {}).get("first_seen")
            if first_seen and timeutil.parse(first_seen) >= cutoff:
                serial = usb["attrs"].get("serial")
                found.append({
                    "kind": "statement",
                    "events": [claim["id"], usb["id"]],
                    "score": 0.95,
                    "explanation": (
                        f"{claim['attrs'].get('speaker') or claim['person']} said \"{quote}\", but the USB history on "
                        f"{usb['attrs'].get('host')} records drive {serial} as first seen "
                        f"{timeutil.parse(first_seen).date()} at {timeutil.spoken(timeutil.parse(first_seen))}."
                    ),
                    "persons": [claim["person"]],
                    "rule": "drive_history_claim",
                })
    return found


def run_hard(events: list[dict], evidence: list[dict], walk_time: WalkTime) -> list[dict[str, Any]]:
    """Rules over trusted events. custody_mismatch runs separately, over all events."""
    return [
        *impossible_travel(events, walk_time),
        *wifi_after_last_badge(events),
        *camera_gap_without_work_order(events),
    ]


def run_statement_rules(events: list[dict], persons: list[dict], days: set) -> list[dict[str, Any]]:
    return [*leave_time_claims(events, persons, days), *drive_history_claims(events)]


def nli_excluded_claims(events: list[dict]) -> set[str]:
    """Claim ids NLI must not judge: any claim with a clock time (the model cannot do time arithmetic;
    leave times are checked by leave_time_claims) and drive-history claims (drive_history_claims)."""
    out = set()
    for e in events:
        if e.get("type") in CLAIM_TYPES:
            q = e["source"]["quote"]
            if claimed_time(q) or (_DRIVE_RE.search(q) and _PAST_RE.search(q)):
                out.add(e["id"])
    return out
