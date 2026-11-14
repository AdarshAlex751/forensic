"""Data shapes, from the findings.json schema in docs/PLAN.md.

Adding a field is fine. Renaming or removing one needs the owner and the team to agree.
Timestamps are Houston local time with offset, e.g. 2026-03-04T18:18:00-06:00 (CONTRACTS rule 7).
"""
from typing import Any

from pydantic import BaseModel, ConfigDict


class _M(BaseModel):
    model_config = ConfigDict(extra="allow")


class Source(_M):
    file: str
    line: int
    quote: str
    sha256: str


class CaseInfo(_M):
    id: str
    title: str
    address: str
    summary: str
    costar_property_id: str
    matterport_model_id: str


class Evidence(_M):
    file: str
    sha256: str
    manifest_match: bool
    parser: str
    records: int


class Person(_M):
    id: str
    name: str
    role: str
    suite: str
    aliases: list[str]
    anomaly: float
    features: dict[str, Any]
    community: int


class Device(_M):
    id: str
    type: str
    room: str
    sweep: str
    tag_xyz: list[float]


class Event(_M):
    id: str
    t: str
    type: str
    person: str | None = None
    device: str | None = None
    room: str | None = None
    source: Source
    verified: bool = False  # set by the merge code from verification.json, never by evidence


class Edge(_M):
    # "from" is a Python keyword; the JSON key stays "from" and is read as a plain dict.
    to: str
    type: str
    events: list[str]


class Contradiction(_M):
    id: str
    kind: str  # physical | temporal | statement | custody
    events: list[str]
    score: float
    explanation: str
    path: list[str] = []
    walk_s: float | None = None
    gap_s: float | None = None


class Hypothesis(_M):
    id: str
    text: str
    confidence: float
    supports: list[str]
    disproved_by: str


class Request(_M):
    id: str
    ask: str
    why: str
    status: str  # pending | approved | ingested


class Note(_M):
    text: str
    kind: str  # check_next | todo | cleared


class Rejected(_M):
    claim: str
    reason: str


class Verification(_M):
    claims: int
    verified: int
    rejected: list[Rejected]
    verified_event_ids: list[str] = []  # extra field: lets the merge code set events[].verified


class Eval(_M):
    planted: int
    found: int
    false_alarms: int
    runtime_s: float
    missed: list[dict[str, str]] = []


class Findings(_M):
    case: CaseInfo
    evidence: list[Evidence]
    persons: list[Person]
    devices: list[Device]
    rooms: list[dict[str, Any]] = []
    events: list[Event]
    edges: list[dict[str, Any]]
    contradictions: list[Contradiction]
    hypotheses: list[Hypothesis]
    requests: list[Request]
    notes: list[Note]
    verification: Verification
    eval: Eval
