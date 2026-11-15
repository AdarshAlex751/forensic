"""The ONLY module in the investigator slice that reads other slices' files.

Everything else imports typed objects from here. If another person's real format differs from the fake,
only this file changes. Parsing is tolerant: unknown fields are ignored, missing optional fields get
defaults, and a bad record is skipped with a warning instead of crashing the run.

Reads (never writes): data/evidence/{case,evidence,events,events_baseline,events_extra}.json via shared
merge.load(), data/analysis/*.json, data/scene/{devices,rooms}.json, and the raw case files under
data/evidence/CASE-1010F/ (evidence, not the answer key). It never touches answer_key.json or eval.json.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from app.shared.config import DATA_DIR, use_real
from app.shared.merge import load as _merge_load

log = logging.getLogger(__name__)

CASE_FOLDER_NAME = "CASE-1010F"


def _s(v: Any, default: str = "") -> str:
    return default if v is None else str(v)


def _opt(v: Any) -> str | None:
    return None if v is None else str(v)


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@dataclass
class Source:
    file: str
    line: int
    quote: str
    sha256: str

    @classmethod
    def from_dict(cls, d: Any) -> "Source":
        if not isinstance(d, dict) or "file" not in d:
            raise ValueError("source missing")
        try:
            line = int(d.get("line", 0))
        except (TypeError, ValueError):
            line = 0
        return cls(_s(d["file"]), line, _s(d.get("quote")), _s(d.get("sha256")))


@dataclass(frozen=True)
class Actor:
    kind: str
    value: str


@dataclass
class Event:
    id: str
    t: str
    type: str
    source: Source
    person: str | None = None
    device: str | None = None
    room: str | None = None
    actor: Actor | None = None
    attrs: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Any) -> "Event":
        if not isinstance(d, dict):
            raise ValueError("event is not an object")
        for key in ("id", "t", "type"):
            if not d.get(key):
                raise ValueError(f"event missing {key}")
        a = d.get("actor")
        actor = Actor(_s(a.get("kind")), _s(a.get("value"))) if isinstance(a, dict) and a.get("value") is not None else None
        attrs = d.get("attrs") if isinstance(d.get("attrs"), dict) else {}
        return cls(
            id=_s(d["id"]), t=_s(d["t"]), type=_s(d["type"]), source=Source.from_dict(d.get("source")),
            person=_opt(d.get("person")), device=_opt(d.get("device")), room=_opt(d.get("room")),
            actor=actor, attrs=attrs,
        )


@dataclass
class EvidenceFile:
    file: str
    sha256: str
    manifest_match: bool = True
    manifest_sha256: str | None = None
    parser: str = ""
    records: int = 0

    @classmethod
    def from_dict(cls, d: Any) -> "EvidenceFile":
        if not isinstance(d, dict) or not d.get("file"):
            raise ValueError("evidence missing file")
        return cls(_s(d["file"]), _s(d.get("sha256")), bool(d.get("manifest_match", True)),
                   _opt(d.get("manifest_sha256")), _s(d.get("parser")), int(d.get("records") or 0))


@dataclass
class Person:
    id: str
    name: str = ""
    role: str = ""
    aliases: list[str] = field(default_factory=list)
    anomaly: float = 0.0
    features: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Any) -> "Person":
        if not isinstance(d, dict) or not d.get("id"):
            raise ValueError("person missing id")
        aliases = d.get("aliases") if isinstance(d.get("aliases"), list) else []
        features = d.get("features") if isinstance(d.get("features"), dict) else {}
        return cls(_s(d["id"]), _s(d.get("name")), _s(d.get("role")), [str(a) for a in aliases], _f(d.get("anomaly")), features)


@dataclass
class Contradiction:
    id: str
    kind: str
    events: list[str] = field(default_factory=list)
    score: float = 0.0
    explanation: str = ""
    path: list[str] = field(default_factory=list)
    walk_s: float | None = None
    gap_s: float | None = None

    @classmethod
    def from_dict(cls, d: Any) -> "Contradiction":
        if not isinstance(d, dict) or not d.get("id"):
            raise ValueError("contradiction missing id")
        return cls(_s(d["id"]), _s(d.get("kind")), [str(e) for e in d.get("events") or []], _f(d.get("score")),
                   _s(d.get("explanation")), [str(p) for p in d.get("path") or []],
                   None if d.get("walk_s") is None else _f(d["walk_s"]), None if d.get("gap_s") is None else _f(d["gap_s"]))


@dataclass
class Device:
    id: str
    type: str = ""
    room: str = ""

    @classmethod
    def from_dict(cls, d: Any) -> "Device":
        if not isinstance(d, dict) or not (d.get("id") or d.get("device_id")):
            raise ValueError("device missing id")
        return cls(_s(d.get("id") or d.get("device_id")), _s(d.get("type")), _s(d.get("room")))


@dataclass
class Room:
    id: str
    label: str = ""
    floor: int = 0

    @classmethod
    def from_dict(cls, d: Any) -> "Room":
        if not isinstance(d, dict) or not d.get("id"):
            raise ValueError("room missing id")
        return cls(_s(d["id"]), _s(d.get("label")), int(d.get("floor") or 0))


@dataclass
class Edge:
    src: str
    to: str
    type: str = ""
    events: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Any) -> "Edge":
        if not isinstance(d, dict) or "from" not in d or "to" not in d:
            raise ValueError("edge missing endpoints")
        return cls(_s(d["from"]), _s(d["to"]), _s(d.get("type")), [str(e) for e in d.get("events") or []])


@dataclass
class CaseInfo:
    id: str = ""
    title: str = ""
    address: str = ""
    summary: str = ""

    @classmethod
    def from_dict(cls, d: Any) -> "CaseInfo":
        d = d if isinstance(d, dict) else {}
        return cls(_s(d.get("id")), _s(d.get("title")), _s(d.get("address")), _s(d.get("summary")))


T = TypeVar("T")


def parse_list(raw: Any, model: type[T], label: str) -> list[T]:
    """Parse a JSON array into model objects, skipping (and logging) every bad record."""
    if not isinstance(raw, list):
        log.warning("%s: expected a list, got %s; using empty", label, type(raw).__name__)
        return []
    out: list[T] = []
    for i, item in enumerate(raw):
        try:
            out.append(model.from_dict(item))  # type: ignore[attr-defined]
        except (ValueError, TypeError, KeyError) as exc:
            log.warning("%s[%d]: skipping bad record (%s)", label, i, exc)
    return out


def _load(slice_name: str, filename: str, default: Any) -> Any:
    try:
        return _merge_load(slice_name, filename)
    except FileNotFoundError:
        log.info("%s/%s not found; using default", slice_name, filename)
    except Exception as exc:  # noqa: BLE001 - tolerant by design: a broken neighbour file must not crash the run
        log.warning("%s/%s unreadable (%s); using default", slice_name, filename, exc)
    return default


@dataclass
class Inputs:
    case: CaseInfo
    evidence: list[EvidenceFile]
    events: list[Event]
    persons: list[Person]
    contradictions: list[Contradiction]
    edges: list[Edge]
    devices: list[Device]
    rooms: list[Room]
    extra_event_ids: list[str] = field(default_factory=list)  # events that came from released extra evidence


def _real_evidence() -> bool:
    return use_real("evidence")


def load_inputs(include_extra: bool = False) -> Inputs:
    """Snapshot of everything the investigator may read. `include_extra` adds the released extra evidence
    (events_extra.json) and is true only after a human approved a request."""
    events = parse_list(_load("evidence", "events.json", []), Event, "events")
    seen = {e.id for e in events}
    extra_ids: list[str] = []
    # Real evidence already merged the baseline and any released events into events.json; the separate files are
    # fake-mode only (and merge.load would fall back to stale fakes if asked for them).
    extra_files = [] if _real_evidence() else ["events_baseline.json"] + (["events_extra.json"] if include_extra else [])
    for name in extra_files:
        for e in parse_list(_load("evidence", name, []), Event, name):
            if e.id not in seen:  # real mode merges these into events.json already
                seen.add(e.id)
                events.append(e)
                if name == "events_extra.json":
                    extra_ids.append(e.id)
    return Inputs(
        case=CaseInfo.from_dict(_load("evidence", "case.json", {})),
        evidence=parse_list(_load("evidence", "evidence.json", []), EvidenceFile, "evidence"),
        events=events,
        persons=parse_list(_load("analysis", "persons.json", []), Person, "persons"),
        contradictions=parse_list(_load("analysis", "contradictions.json", []), Contradiction, "contradictions"),
        edges=parse_list(_load("analysis", "edges.json", []), Edge, "edges"),
        devices=parse_list(_load("scene", "devices.json", []), Device, "devices"),
        rooms=parse_list(_load("scene", "rooms.json", []), Room, "rooms"),
        extra_event_ids=extra_ids,
    )


class CaseFiles:
    """Read-only access to the raw case folder. Paths that escape the folder are refused.

    Released extra evidence lives in the sibling `extra/` folder (the hashed case folder is never edited), so a
    file missing from the case folder is looked up there too; a leading `extra/` in the path is accepted.
    """

    def __init__(self, root: Path | None = None, extra_root: Path | None = None) -> None:
        evidence = DATA_DIR / "evidence"
        if root:
            self.root = Path(root)
            default_extra = self.root.parent / "extra"
        else:
            # Same rule as the evidence slice: an uploaded case (work/CASE-1010F) replaces the built-in one.
            uploaded = evidence / "work" / CASE_FOLDER_NAME
            self.root = uploaded if (uploaded / "manifest.csv").is_file() else evidence / CASE_FOLDER_NAME
            default_extra = evidence / "extra"
        self.extra_root = Path(extra_root) if extra_root else default_extra

    @staticmethod
    def _read_under(base: Path, rel: str) -> bytes | None:
        root = base.resolve()
        path = (root / rel).resolve()
        if root != path and root not in path.parents:
            return None
        try:
            return path.read_bytes() if path.is_file() else None
        except OSError as exc:
            log.warning("cannot read %s (%s)", path, exc)
            return None

    def read_bytes(self, rel: str) -> bytes | None:
        if not rel or rel.startswith(("/", "\\")) or ":" in rel:
            return None
        data = self._read_under(self.root, rel)
        if data is not None:
            return data
        return self._read_under(self.extra_root, rel[len("extra/"):] if rel.startswith("extra/") else rel)
