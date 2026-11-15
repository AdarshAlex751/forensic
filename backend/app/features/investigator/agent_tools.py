"""Tools the investigator agents can call. Each returns facts with source ids, and only ever sees VERIFIED data.

The three spatial functions live in scene/tools.py (Person 2). They are called only from here, through guarded
wrappers: a stub today, the real sweep-graph math later, with no change needed on this side.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from app.features.investigator.approvals import Approvals
from app.features.investigator.inputs import Contradiction, Edge, Event, Person

log = logging.getLogger(__name__)

_COMMS_TYPES = {"email", "chat", "statement"}
_KINDS = {"badge", "mac", "email", "account", "permit", "slack", "name"}
MAX_RESULTS = 25


_H_LIST = r"h\d+(?:\s*(?:,|and|&)\s*h\d+)*"


def without_hypothesis_ids(text: str) -> str:
    """Request text must not cite hypothesis ids ("H2"): the final ranking renumbers them, so the id would point at the
    wrong card. Contradiction ids (c5) are stable and stay."""

    def is_plural(ids: str) -> bool:
        return bool(re.search(r"[,&]|\band\b", ids, re.I))

    def named(m: re.Match[str]) -> str:
        return "the hypotheses" if m.group(1).lower().endswith("es") or is_plural(m.group(2)) else "the hypothesis"

    text = re.sub(rf"\b(hypothes(?:is|es))\s+({_H_LIST})\b", named, text, flags=re.I)
    text = re.sub(rf"\s*\(\s*{_H_LIST}\s*\)", "", text, flags=re.I)
    text = re.sub(rf"\b{_H_LIST}\b", lambda m: "the hypotheses" if is_plural(m.group(0)) else "the hypothesis", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).replace(" ,", ",").strip()


_GENERIC_WORDS = {"exit", "entry", "log", "logs", "record", "records", "csv", "txt", "json", "access", "the", "pull"}


def _source_keywords(name: str) -> set[str]:
    """Distinctive words of a source file name ('access/parking_exit.csv' -> {'parking'})."""
    stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
    return {w for w in re.split(r"[^a-z0-9]+", stem) if len(w) >= 4 and w not in _GENERIC_WORDS}


def _matches_a_source(ask: str, names: list[str]) -> bool:
    text = ask.lower()
    return any(k in text for n in names for k in _source_keywords(n))


def _alias_forms(p: Person) -> set[str]:
    forms = {p.id.lower(), p.name.lower()}
    for a in p.aliases:
        a = a.lower()
        forms.add(a)
        if ":" in a and a.split(":", 1)[0] in _KINDS:
            forms.add(a.split(":", 1)[1])
    return {f for f in forms if f}


def resolve_person(e: Event, persons: list[Person]) -> str | None:
    """Person id for an event: the id already on it, else the person whose aliases contain its raw actor."""
    if e.person:
        return e.person
    if not e.actor:
        return None
    value = e.actor.value.lower()
    for p in persons:
        if value in _alias_forms(p):
            return p.id
    return None


def _parse_t(s: str) -> datetime:
    return datetime.fromisoformat(s.strip())


def _brief(e: Event, person: str | None) -> dict[str, Any]:
    return {
        "id": e.id, "t": e.t, "type": e.type, "person": person, "device": e.device, "room": e.room,
        "actor": {"kind": e.actor.kind, "value": e.actor.value} if e.actor else None,
        "quote": e.source.quote, "source": {"file": e.source.file, "line": e.source.line},
    }


@dataclass
class ToolContext:
    events: list[Event]  # verified events only
    persons: list[Person] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)  # verified only
    edges: list[Edge] = field(default_factory=list)
    approvals: Approvals = field(default_factory=Approvals)
    scene: Any = None  # the scene.tools module (or a stand-in); None -> imported lazily
    # Names of withheld sources a human can release on request (from the case's extra/ folder). None = unknown, so
    # requests are not restricted; [] = nothing more can be requested.
    requestable: list[str] | None = None


class AgentTools:
    NAMES = ("query_timeline", "search_comms", "graph_neighbors", "request_evidence", "walk_time", "ap_covers", "camera_sees")

    def __init__(self, ctx: ToolContext) -> None:
        self.ctx = ctx

    # ---- evidence tools -------------------------------------------------------------------------------
    def query_timeline(self, person: str, start: str, end: str) -> dict[str, Any]:
        """List verified events for a person id (empty string = everyone) between start and end (ISO 8601 with -05:00), oldest first."""
        try:
            lo, hi = _parse_t(start), _parse_t(end)
        except ValueError:
            return {"error": "start and end must be ISO 8601 with offset, e.g. 2026-03-04T18:00:00-05:00"}
        rows = []
        for e in self.ctx.events:
            try:
                t = _parse_t(e.t)
            except ValueError:
                continue
            who = resolve_person(e, self.ctx.persons)
            if lo <= t <= hi and (not person or who == person):
                rows.append((t, _brief(e, who)))
        rows.sort(key=lambda r: r[0])
        events = [r[1] for r in rows]
        return {"events": events[:MAX_RESULTS], "total": len(events), "truncated": len(events) > MAX_RESULTS}

    def search_comms(self, query: str) -> dict[str, Any]:
        """Search verified emails, chat messages and statements for a phrase (case-insensitive)."""
        q = query.strip().lower()
        hits = [_brief(e, resolve_person(e, self.ctx.persons)) for e in self.ctx.events
                if e.type in _COMMS_TYPES and q and q in e.source.quote.lower()]
        return {"events": hits[:MAX_RESULTS], "total": len(hits)}

    def graph_neighbors(self, node: str) -> dict[str, Any]:
        """Nodes linked to a person, device or room in the fact graph, with the event ids behind each edge."""
        out = []
        for ed in self.ctx.edges:
            if ed.src == node:
                out.append({"node": ed.to, "type": ed.type, "events": ed.events})
            elif ed.to == node:
                out.append({"node": ed.src, "type": ed.type, "events": ed.events})
        return {"neighbors": out}

    def _still_obtainable(self) -> list[str] | None:
        """Withheld sources not yet part of the case (a source whose events are already here cannot be requested again)."""
        if self.ctx.requestable is None:
            return None
        have = {e.source.file for e in self.ctx.events}
        return [n for n in self.ctx.requestable if n not in have]

    def request_evidence(self, ask: str, why: str) -> dict[str, Any]:
        """Ask the human investigator to release more evidence. State what to pull and which hypothesis it would disprove.
        Only sources that can really be released are accepted; the reply lists them if yours is not one."""
        obtainable = self._still_obtainable()
        if obtainable is not None and not _matches_a_source(ask, obtainable):
            listing = ", ".join(obtainable) if obtainable else "none; the case has no further evidence to release"
            return {"error": f"That record type cannot be obtained in this case. Obtainable sources: {listing}."}
        r = self.ctx.approvals.add_request(without_hypothesis_ids(ask), without_hypothesis_ids(why))
        return {"id": r["id"], "status": r["status"], "note": "Waiting for human approval; do not assume the answer."}

    # ---- scene tools (Person 2), always through guarded wrappers ------------------------------------------
    def _scene(self) -> Any:
        if self.ctx.scene is not None:
            return self.ctx.scene
        from app.features.scene import tools as scene_tools  # lazy: Person 2's stubs today, real math later

        return scene_tools

    def _call(self, name: str, *args: str) -> dict[str, Any]:
        try:
            value = getattr(self._scene(), name)(*args)
        except Exception as exc:  # noqa: BLE001 - spatial model may be unavailable; the agent must be told, not crash
            log.warning("scene.tools.%s failed: %s", name, exc)
            return {"error": f"{name} unavailable: {exc}"}
        return {"value": value, "source": f"scene.tools.{name}"}

    def walk_time(self, room_a: str, room_b: str) -> dict[str, Any]:
        """Shortest walking time in seconds, and the path, between two room ids."""
        r = self._call("walk_time", room_a, room_b)
        return r if "error" in r else {**r["value"], "source": r["source"]}

    def ap_covers(self, ap_id: str, room_id: str) -> dict[str, Any]:
        """Whether a Wi-Fi access point covers a room."""
        r = self._call("ap_covers", ap_id, room_id)
        return r if "error" in r else {"covers": bool(r["value"]), "source": r["source"]}

    def camera_sees(self, camera_id: str, room_id: str) -> dict[str, Any]:
        """Whether a camera's view includes a room."""
        r = self._call("camera_sees", camera_id, room_id)
        return r if "error" in r else {"sees": bool(r["value"]), "source": r["source"]}

    def as_functions(self, names: tuple[str, ...] | None = None) -> list[Callable[..., dict[str, Any]]]:
        """Plain functions (with docstrings and type hints) that LangChain/deepagents can wrap as tools."""
        return [getattr(self, n) for n in (names or self.NAMES)]
