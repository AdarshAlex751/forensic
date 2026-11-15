"""Builds the Bundle (feedback/contract.py) the critic reads: contradictions, the persons that matter, every cited event.

Reads only Person 3's analysis outputs and Person 1's evidence, through app.shared.merge.load (fake/real switch).
Never reads data/investigator/*, data/evidence/truth/, answer_key.json, CASE.md, and imports no casegen/fakes/
analysis code (CONTRACTS rule 2: their JSON files only).

Deterministic: same inputs -> identical dict. Lists whose order carries no meaning are sorted.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.features.feedback import contract
from app.shared.config import CASE_ID
from app.shared.merge import fill_persons, load

TOP_RANKED = 6          # persons by anomaly_rank always included
CONTRADICTION_EVENTS = 12
CUSTODY_EVENTS = 3      # a custody finding cites every event of the bad file; a sample is enough (event_count has all)
QUOTE_CHARS = 240       # a quoted source line is cut to this length

# Shrink ladder, applied in order until the bundle fits. Each step is (knob, value).
DEFAULT_CAPS = {"quotes": 3, "flag_events": 10, "links": 10, "c_events": CONTRADICTION_EVENTS}
# Rounds of (quotes per side, events per red flag, link items), in that order within a round; then the
# lowest-ranked extra persons go; contradiction event lists are cut last. A contradiction is never dropped.
SHRINK_STEPS = (
    [("quotes", 2), ("flag_events", 6), ("links", 6)]
    + [("quotes", 1), ("flag_events", 4), ("links", 3)]
    + [("flag_events", 2), ("links", 1)]
    + [("flag_events", 1), ("links", 0)]
    + [("drop_person", None)]          # repeated: lowest-ranked extra person first
    + [("c_events", n) for n in (8, 5, 3, 1)]
)

LINK_GROUPS = {"device": "devices", "room": "rooms", "file": "files", "account": "accounts"}


def _load(slice_name: str, filename: str, default: Any) -> Any:
    try:
        return load(slice_name, filename)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _cnum(cid: str) -> tuple[int, str]:
    s = str(cid)
    return (int(s[1:]), s) if s[1:].isdigit() else (10**9, s)


def _rank_key(p: dict) -> tuple:
    r = p.get("anomaly_rank")
    return (r if isinstance(r, int) else 10**9, -(p.get("anomaly") or 0.0), p.get("id", ""))


def _cut(text: Any, n: int = QUOTE_CHARS) -> Any:
    if isinstance(text, str) and len(text) > n:
        return text[: n - 3] + "..."
    return text


# ---------------------------------------------------------------- inputs


def _inputs() -> dict[str, Any]:
    persons = _load("analysis", "persons.json", [])
    raw_events = _load("evidence", "events.json", [])
    return {
        "case": _load("evidence", "case.json", {}),
        "evidence": _load("evidence", "evidence.json", []),
        "persons": persons,
        "edges": _load("analysis", "edges.json", []),
        "contradictions": sorted(_load("analysis", "contradictions.json", []), key=lambda c: _cnum(c.get("id", ""))),
        # evidence leaves `person` null; resolve it from the analysis aliases (the shared resolver).
        "events": {e["id"]: e for e in fill_persons(raw_events, persons) if e.get("id")},
    }


def _chain_persons(contradictions: list[dict]) -> dict[str, str]:
    """event id -> person as Person 3 resolved it in each contradiction's chain."""
    out: dict[str, str] = {}
    for c in contradictions:
        for link in c.get("chain") or []:
            if link.get("event") and link.get("person"):
                out.setdefault(link["event"], link["person"])
    return out


def _contradiction_persons(c: dict, events: dict, chain: dict) -> set[str]:
    found = {p for p in c.get("persons") or [] if p}
    for x in c.get("events") or []:
        pid = (events.get(x) or {}).get("person") or chain.get(x)
        if pid:
            found.add(pid)
    return found


# ---------------------------------------------------------------- sections


def _contradiction(c: dict, caps: dict) -> tuple[dict, int]:
    """Returns the bundle entry and how many cited event ids the caps left out."""
    dropped = 0
    sides = []
    for s in c.get("sides") or []:
        # quotes are not repeated here: every side event's quote is in bundle["events"]
        sides.append({"label": s.get("label"), "events": list(s.get("events") or []),
                      "more_events": int(s.get("more") or 0)})
    evs = list(c.get("events") or [])
    cap = min(caps["c_events"], CUSTODY_EVENTS) if c.get("rule") == "custody_mismatch" else caps["c_events"]
    shown = evs[:cap]
    dropped += len(evs) - len(shown)
    # A side lists its events in full only while that stays within the event cap.
    for side in sides:
        if len(side["events"]) > cap:
            dropped += len(side["events"]) - cap
            side["more_events"] = len(side["events"]) - cap
            side["events"] = side["events"][:cap]
    return {
        "id": c.get("id"), "kind": c.get("kind"), "rule": c.get("rule"), "title": c.get("title"),
        "explanation": c.get("explanation"), "score": c.get("score"), "t": c.get("t"), "room": c.get("room"),
        "persons": sorted(p for p in c.get("persons") or [] if p),
        "sides": sides, "events": shown, "event_count": len(evs),
    }, dropped


def _items(entries: list[dict], cap: int) -> tuple[list[dict], int]:
    out, dropped = [], 0
    for r in entries:
        evs = list(r.get("events") or [])
        item = {"text": r.get("text"), "events": evs[:cap]}
        if len(evs) > cap:
            item["more_events"] = len(evs) - cap
            dropped += len(evs) - cap
        out.append(item)
    return out, dropped


def _links_index(edges: list[dict]) -> tuple[dict[str, list[dict]], dict[str, str]]:
    by_from: dict[str, list[dict]] = {}
    device_room: dict[str, str] = {}
    for e in edges:
        by_from.setdefault(e.get("from"), []).append(e)
        if e.get("from_kind") == "device" and e.get("to_kind") == "room" and e.get("to"):
            device_room[e["from"]] = str(e["to"]).removeprefix("room:")
    return by_from, device_room


def _links(pid: str, by_from: dict, device_room: dict, cap: int) -> tuple[dict, int]:
    weight: dict[str, dict[str, int]] = {g: {} for g in ("devices", "rooms", "files", "accounts", "others")}
    for e in by_from.get(pid, []):
        to, kind, n = e.get("to"), e.get("to_kind") or "other", len(e.get("events") or [])
        if not to:
            continue
        group = LINK_GROUPS.get(kind, "others")
        key = to if group != "others" or str(to).startswith(f"{kind}:") else f"{kind}:{to}"
        weight[group][key] = weight[group].get(key, 0) + n
        if group == "devices" and to in device_room:   # rooms: those of the devices the person used
            room = device_room[to]
            weight["rooms"][room] = weight["rooms"].get(room, 0) + n
    out: dict[str, Any] = {}
    dropped = 0
    for g, w in weight.items():
        ordered = sorted(w, key=lambda k: (-w[k], k))   # most events first, then id
        out[g] = ordered[:cap]
        dropped += max(0, len(ordered) - cap)
    out["counts"] = {g: len(w) for g, w in weight.items()}
    return out, dropped


def _person(p: dict, reasons: list[str], by_from: dict, device_room: dict, caps: dict) -> tuple[dict, dict]:
    flags, d1 = _items(p.get("red_flags") or [], caps["flag_events"])
    ctx, d2 = _items(p.get("context") or [], caps["flag_events"])
    links, d3 = _links(p["id"], by_from, device_room, caps["links"])
    return {
        "id": p["id"], "name": p.get("name"), "role": p.get("role"), "anomaly": p.get("anomaly"),
        "anomaly_rank": p.get("anomaly_rank"), "centrality": p.get("centrality"), "community": p.get("community"),
        "included_because": reasons, "red_flags": flags, "context": ctx, "links": links,
    }, {"events": d1 + d2, "link_items": d3}


def _event(e: dict, chain: dict) -> dict:
    """What the critic sees of an event: compact (log quotes already carry device and time detail)."""
    src = e.get("source") or {}
    return {"t": e.get("t"), "type": e.get("type"), "person": e.get("person") or chain.get(e.get("id")),
            "room": e.get("room"), "quote": _cut(src.get("quote"))}


def _source(e: dict) -> dict:
    """Where an event's quote lives (for the checker's citations; never sent to the model)."""
    src = e.get("source") or {}
    return {"file": src.get("file"), "line": src.get("line"), "quote": src.get("quote")}


def _cited(contradictions: list[dict], persons: list[dict]) -> set[str]:
    ids: set[str] = set()
    for c in contradictions:
        ids.update(c["events"])
        for s in c["sides"]:
            ids.update(s["events"])
    for p in persons:
        for item in p["red_flags"] + p["context"]:
            ids.update(item["events"])
    return ids


def _untrusted(evidence: list[dict]) -> list[str]:
    return sorted(f["file"] for f in evidence if f.get("file") and f.get("manifest_sha256") and f.get("manifest_match") is False)


def _notes(inp: dict, contradictions: list[dict], untrusted: list[str], persons: list[dict]) -> list[str]:
    notes = []
    custody = [c["id"] for c in contradictions if c.get("rule") == "custody_mismatch"]
    if untrusted:
        where = f" except the custody finding{'s' if len(custody) > 1 else ''} {', '.join(custody)}" if custody else ""
        notes.append(f"Events from untrusted files ({', '.join(untrusted)}: hash does not match the manifest) are "
                     f"excluded from analysis{where}; a red flag or other finding never rests on them.")
    notes.append("Anomaly scores mean an unusual day compared with the person's own baseline and the others, not a "
                 "verdict; anomaly_rank 1 is the most unusual day, and a person with anomaly 0 has no rank.")
    notes.append("Person is resolved from raw identifiers (badge, MAC, account, name); a badge read resolves to the "
                 "badge holder, which is an assumption: it shows the badge was used, not who held it.")
    if any(c.get("rule") in ("leave_time_claim", "drive_history_claim", "nli") for c in contradictions):
        notes.append("In statement contradictions the 'Said' side is an interview statement and the 'Records' side "
                     "is log data; the statement time is when it was said, the contradiction t is the records' time.")
    nobody = [c["id"] for c in contradictions if not c.get("persons") and c.get("rule") != "custody_mismatch"]
    if nobody:
        notes.append(f"Contradiction(s) {', '.join(nobody)} cite no person: they are about a device or the record, "
                     "not an individual.")
    if any(c.get("rule") == "nli" for c in contradictions):
        notes.append("Rule 'nli' findings come from a language model comparing a statement with records; the score "
                     "is that model's confidence, weaker than a hard rule.")
    notes.append("Sides list event ids; each cited event's time, type, person, room and exact quote are in events. "
                 "Links: rooms are those of the devices the person used; ids are sorted by event count.")
    times = sorted({str(e.get("t"))[19:] for e in inp["events"].values() if e.get("t") and len(str(e["t"])) > 19})
    if len(times) == 1:
        notes.append(f"All timestamps carry the fixed offset {times[0]} (local time).")
    return notes


# ---------------------------------------------------------------- bundle


def _assemble(inp: dict, chain: dict, selected: list[tuple[dict, list[str]]], caps: dict,
              base_dropped: dict) -> dict:
    by_from, device_room = _links_index(inp["edges"])
    dropped = dict(base_dropped)
    contradictions = []
    for c in inp["contradictions"]:
        entry, d = _contradiction(c, caps)
        contradictions.append(entry)
        dropped["events"] += d
    persons = []
    for p, reasons in selected:
        entry, d = _person(p, reasons, by_from, device_room, caps)
        persons.append(entry)
        dropped["events"] += d["events"]
        dropped["link_items"] += d["link_items"]
    cited = _cited(contradictions, persons)
    events, sources, missing = {}, {}, []
    for x in sorted(cited, key=lambda s: (len(s), s)):
        if x in inp["events"]:
            events[x] = _event(inp["events"][x], chain)
            sources[x] = _source(inp["events"][x])
        else:
            missing.append(x)
    untrusted = _untrusted(inp["evidence"])
    case = inp["case"] if isinstance(inp["case"], dict) else {}
    return {
        "case": {"id": case.get("id") or CASE_ID, "title": case.get("title") or f"Case {case.get('id') or CASE_ID}"},
        "contradictions": contradictions,
        "persons": persons,
        "events": events,
        "sources": sources,          # file/line/quote per cited event, for the checker; not sent to the model
        "untrusted_files": untrusted,
        "notes": _notes(inp, inp["contradictions"], untrusted, persons),
        "budget": {"approx_tokens": 0, "max_tokens": 0, "fits": True, "caps": dict(caps),
                   "dropped": dropped, "missing_events": missing},
    }


def _measure(bundle: dict, max_tokens: int) -> dict:
    # approx_tokens is measured with itself filled in; two passes settle the digit count.
    for _ in range(3):
        bundle["budget"]["max_tokens"] = max_tokens
        sent = {k: v for k, v in bundle.items() if k not in ("sources", "budget")}  # what the model actually sees
        bundle["budget"]["approx_tokens"] = len(json.dumps(sent, separators=(",", ":"), ensure_ascii=False)) // 4
        bundle["budget"]["fits"] = bundle["budget"]["approx_tokens"] <= max_tokens
    return bundle


def _select(inp: dict, chain: dict) -> tuple[list[tuple[dict, list[str]]], set[str]]:
    """Persons that matter, ranked: everyone in a contradiction, plus the top TOP_RANKED by anomaly_rank.
    Returns them in rank order and the ids that may never be dropped."""
    by_id = {p["id"]: p for p in inp["persons"] if p.get("id")}
    reasons: dict[str, list[str]] = {}
    protected: set[str] = set()
    for c in inp["contradictions"]:
        # A custody finding is about a file: the persons on its (untrusted) events are listed but not protected.
        custody = c.get("rule") == "custody_mismatch"
        for pid in sorted(_contradiction_persons(c, inp["events"], chain)):
            if pid in by_id:
                reasons.setdefault(pid, []).append(f"{'custody' if custody else 'contradiction'}:{c.get('id')}")
                if not custody:
                    protected.add(pid)
    ranked = sorted((p for p in by_id.values() if isinstance(p.get("anomaly_rank"), int)), key=_rank_key)
    if not ranked:   # older analysis output without anomaly_rank: rank by anomaly
        ranked = sorted((p for p in by_id.values() if (p.get("anomaly") or 0) > 0), key=_rank_key)
    for i, p in enumerate(ranked[:TOP_RANKED], start=1):
        reasons.setdefault(p["id"], []).append(f"anomaly_rank:{p.get('anomaly_rank') or i}")
    selected = [(by_id[pid], reasons[pid]) for pid in sorted(reasons, key=lambda i: _rank_key(by_id[i]))]
    return selected, protected


def build_bundle(max_tokens: int = contract.MAX_BUNDLE_TOKENS) -> dict:
    inp = _inputs()
    chain = _chain_persons(inp["contradictions"])
    selected, protected = _select(inp, chain)
    caps = dict(DEFAULT_CAPS)
    base = {"persons": 0, "person_ids": [], "events": 0, "quotes": 0, "link_items": 0, "steps": []}
    bundle = _measure(_assemble(inp, chain, selected, caps, base), max_tokens)
    for knob, value in SHRINK_STEPS:
        if bundle["budget"]["fits"]:
            break
        if knob == "drop_person":
            while not bundle["budget"]["fits"]:
                extra = [i for i, (p, _) in enumerate(selected) if p["id"] not in protected]
                if not extra:
                    break
                p, _ = selected.pop(extra[-1])          # selected is in rank order: last = lowest ranked
                base["persons"] += 1
                base["person_ids"] = base["person_ids"] + [p["id"]]
                base["steps"] = base["steps"] + [f"drop_person={p['id']}"]
                bundle = _measure(_assemble(inp, chain, selected, caps, base), max_tokens)
            continue
        caps[knob] = value
        base["steps"] = base["steps"] + [f"{knob}={value}"]
        bundle = _measure(_assemble(inp, chain, selected, caps, base), max_tokens)
    return bundle


def bundle_fingerprint(bundle: dict) -> str:
    return hashlib.sha256(json.dumps(bundle, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def allowed_ids(bundle: dict) -> dict[str, set[str]]:
    """The ids a question may cite."""
    return {
        "events": set(bundle.get("events") or {}),
        "contradictions": {c["id"] for c in bundle.get("contradictions") or [] if c.get("id")},
        "persons": {p["id"] for p in bundle.get("persons") or [] if p.get("id")},
    }
