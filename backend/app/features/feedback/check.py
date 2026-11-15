"""Checker and writer of the feedback slice: RawReply + Bundle -> Feedback (see contract.py), then feedback.json.

Every question the model returns is checked against the bundle; a question that fails any check is kept
out of the output and listed in `rejected` with the reason, so nothing unchecked ever reaches the page."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.features.feedback import contract as _contract
from app.features.feedback.contract import (FORBIDDEN, KIND_LABELS, KINDS, MAX_QUESTIONS, OUT_FILE)  # noqa: F401

EST = timezone(timedelta(hours=-5), "EST")
MAX_WORDS = 60
MAX_QUOTES = 4
DUPLICATE_JACCARD = 0.8
CITE_KINDS = ("events", "contradictions", "persons")

_FORBIDDEN_RES = [
    (phrase, re.compile(r"(?<!\w)" + r"\s+".join(re.escape(w) for w in phrase.split()) + r"(?!\w)", re.IGNORECASE))
    for phrase in FORBIDDEN
]


def bundle_fingerprint(bundle: dict) -> str:
    return hashlib.sha256(json.dumps(bundle, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def allowed_ids(bundle: dict) -> dict[str, set[str]]:
    """The ids a question may cite, per category, taken from the bundle itself."""
    return {
        "events": set((bundle.get("events") or {}).keys()),
        "contradictions": {c["id"] for c in bundle.get("contradictions") or [] if isinstance(c, dict) and "id" in c},
        "persons": {p["id"] for p in bundle.get("persons") or [] if isinstance(p, dict) and "id" in p},
    }


def _tokens(text: str) -> set[str]:
    return set(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _forbidden_hit(text: str) -> str | None:
    for phrase, rx in _FORBIDDEN_RES:
        if rx.search(text):
            return phrase
    return None


def _check_one(q, allowed: dict[str, set[str]], kept_tokens: list[set[str]]) -> tuple[str | None, dict | None]:
    """Return (reason, None) on rejection, or (None, normalized cites) when the question passes."""
    if not isinstance(q, dict):
        return "not an object", None
    kind = q.get("kind")
    if kind not in KINDS:
        return f"unknown kind {kind!r}", None
    question = q.get("question")
    if not isinstance(question, str) or not question.strip():
        return "empty question", None
    question = question.strip()
    if not question.endswith("?"):
        return "question does not end with '?'", None
    if len(question.split()) > MAX_WORDS:
        return f"question longer than {MAX_WORDS} words", None
    why = q.get("why")
    if not isinstance(why, str) or not why.strip():
        return "missing 'why'", None
    cites = q.get("cites")
    if not isinstance(cites, dict):
        return "missing cites", None
    norm: dict[str, list[str]] = {}
    for cat in CITE_KINDS:
        ids = cites.get(cat) or []
        if isinstance(ids, str):
            ids = [ids]
        if not isinstance(ids, list):
            return f"cites.{cat} is not a list", None
        norm[cat] = [str(i) for i in ids]
    if not any(norm.values()):
        return "cites no ids", None
    for cat in CITE_KINDS:
        unknown = [i for i in norm[cat] if i not in allowed[cat]]
        if unknown:
            return f"cites unknown {cat} id(s): {', '.join(unknown)}", None
    for field, text in (("question", question), ("why", why)):
        hit = _forbidden_hit(text)
        if hit:
            return f"forbidden phrase {hit!r} in {field}", None
    toks = _tokens(question)
    for prev in kept_tokens:
        if _jaccard(toks, prev) >= DUPLICATE_JACCARD:
            return "near-duplicate of a kept question", None
    return None, norm


MAX_PER_POINT = 2   # at most two questions (of different kinds) on an identical set of citations

# Typographic punctuation models like to use -> plain ASCII, so the UI and any console show it cleanly.
_ASCII = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
                        "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", " ": " ",
                        " ": " "})


def _ascii_question(q):
    if not isinstance(q, dict):
        return q
    return {**q, **{k: q[k].translate(_ASCII) for k in ("question", "why") if isinstance(q.get(k), str)}}


def validate(raw: dict, bundle: dict, *, fingerprint: str | None = None, now: datetime | None = None) -> dict:
    allowed = allowed_ids(bundle)
    all_ids = set().union(*allowed.values())
    events = bundle.get("events") or {}
    sources = bundle.get("sources") or {}
    asked = raw.get("questions") or []
    if not isinstance(asked, list):
        asked = []
    asked = [_ascii_question(q) for q in asked]

    kept: list[dict] = []
    kept_tokens: list[set[str]] = []
    per_point: dict[tuple, list[str]] = {}   # identical citations -> kinds already kept
    rejected: list[dict] = []
    for q in asked:
        text = q.get("question") if isinstance(q, dict) else None
        text = text if isinstance(text, str) else str(q if text is None else text)
        if len(kept) >= MAX_QUESTIONS:
            rejected.append({"question": text, "reason": f"over the cap of {MAX_QUESTIONS} questions"})
            continue
        reason, cites = _check_one(q, allowed, kept_tokens)
        if not reason:
            point = (tuple(sorted(cites["contradictions"])), tuple(sorted(cites["events"])))
            kinds = per_point.get(point, [])
            if q["kind"] in kinds:
                reason = "repeats the same point (same kind and citations as a kept question)"
            elif len(kinds) >= MAX_PER_POINT:
                reason = f"more than {MAX_PER_POINT} questions on the same citations"
        if reason:
            rejected.append({"question": text, "reason": reason})
            continue
        per_point.setdefault(point, []).append(q["kind"])
        question = q["question"].strip()
        quotes = []
        for eid in cites["events"][:MAX_QUOTES]:
            ev = {**(events.get(eid) or {}), **(sources.get(eid) or {})}
            quotes.append({"event": eid, "file": ev.get("file"), "line": ev.get("line"), "quote": ev.get("quote")})
        focus = q.get("focus")
        kept.append({
            "id": f"q{len(kept) + 1}",
            "kind": q["kind"],
            "kind_label": KIND_LABELS[q["kind"]],
            "question": question,
            "why": q["why"].strip(),
            "cites": cites,
            "quotes": quotes,
            "focus": focus if isinstance(focus, str) and focus in all_ids else None,
        })
        kept_tokens.append(_tokens(question))

    when = (now or datetime.now(EST))
    when = when.replace(tzinfo=EST) if when.tzinfo is None else when.astimezone(EST)
    return {
        "case_id": (bundle.get("case") or {}).get("id"),
        "generated_at": when.isoformat(timespec="seconds"),
        "source": raw.get("source"),
        "model": raw.get("model"),
        "input_fingerprint": fingerprint or bundle_fingerprint(bundle),
        "questions": kept,
        "rejected": rejected,
        "counts": {"asked": len(asked), "kept": len(kept), "rejected": len(rejected)},
    }


def write(feedback: dict, out_file: Path | None = None) -> None:
    """Atomic write: temp file in the same folder, then os.replace. UTF-8, LF, indent 2.
    The default path is read from contract.OUT_FILE at call time (so tests and callers can redirect it)."""
    out_file = Path(out_file or _contract.OUT_FILE)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=out_file.name + ".", suffix=".tmp", dir=out_file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(feedback, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, out_file)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_current(out_file: Path | None = None) -> dict | None:
    out_file = Path(out_file or _contract.OUT_FILE)
    if not out_file.exists():
        return None
    return json.loads(out_file.read_text(encoding="utf-8"))
