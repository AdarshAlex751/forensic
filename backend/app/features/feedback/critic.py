"""The critic: sends the bundle to Groq and gets back questions for the investigator (RawReply, see contract.py).

ask() never raises. When Groq is unavailable (no key, error, timeout, unparseable JSON) it returns the recorded
fallback reply if there is one, otherwise a deterministic mock built from the bundle.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from . import contract, prompts

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


# ------------------------------------------------------------------ messages / parsing

def build_messages(bundle: dict) -> list[tuple[str, str]]:
    return [("system", prompts.SYSTEM_PROMPT), ("human", prompts.user_message(bundle))]


def _content(resp: Any) -> str:
    content = getattr(resp, "content", resp)
    if isinstance(content, list):  # some chat models return content blocks
        content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return content if isinstance(content, str) else str(content)


def parse_json(text: str) -> dict:
    """Strip code fences and parse the outermost JSON object. Raises ValueError if there is none."""
    text = _FENCE.sub("", (text or "").strip())
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
    dec = json.JSONDecoder()  # last resort: first decodable object anywhere
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
            if isinstance(obj, dict) and "questions" in obj:
                return obj
        except ValueError:
            continue
    raise ValueError("no JSON object in model reply")


def _norm_question(q: Any) -> dict | None:
    if not isinstance(q, dict):
        return None
    cites = q.get("cites") if isinstance(q.get("cites"), dict) else {}
    norm_cites = {}
    for k in ("events", "contradictions", "persons"):
        v = cites.get(k) or []
        if isinstance(v, str):
            v = [v]
        norm_cites[k] = [str(x) for x in v if isinstance(x, (str, int))] if isinstance(v, list) else []
    focus = q.get("focus")
    return {
        "kind": str(q.get("kind", "")).strip(),
        "question": str(q.get("question", "")).strip(),
        "why": str(q.get("why", "")).strip(),
        "cites": norm_cites,
        "focus": str(focus) if focus not in (None, "", "null") else None,
    }


def _questions(obj: dict) -> list[dict]:
    qs = obj.get("questions")
    if not isinstance(qs, list):
        raise ValueError("reply has no 'questions' list")
    out = [n for n in (_norm_question(q) for q in qs) if n]
    if not out:
        raise ValueError("reply has no usable questions")
    return out


# ------------------------------------------------------------------ public API

def ask(bundle: dict, *, llm: Any = None, use_fallback: bool = True) -> dict:
    """Ask the critic for questions about the bundle. Returns a RawReply dict; never raises."""
    model = getattr(llm, "model_name", None) or getattr(llm, "model", None) or contract.MODEL
    try:
        if llm is None:
            from app.shared import config  # noqa: F401  (loads the repo-root .env)
            from app.shared.llm_client import get_llm

            if not os.environ.get("GROQ_API_KEY"):
                raise RuntimeError("GROQ_API_KEY is not set")
            llm = get_llm(
                contract.MODEL,
                temperature=contract.TEMPERATURE,
                timeout=60,
                max_retries=0,
                max_tokens=contract.MAX_REPLY_TOKENS,   # Groq counts the reply cap against the per-minute limit
                **({"reasoning_effort": contract.REASONING_EFFORT} if "gpt-oss" in contract.MODEL else {}),
                model_kwargs={"response_format": {"type": "json_object"}},
            )
            model = contract.MODEL
        from app.shared.llm_client import with_backoff

        messages = build_messages(bundle)
        resp = with_backoff(lambda: llm.invoke(messages), retries=4, base_s=8.0)  # waits up to ~2 min: Groq's token window is per minute
        questions = _questions(parse_json(_content(resp)))
        return {"questions": questions[: contract.MAX_QUESTIONS], "source": "groq", "model": str(model), "error": None}
    except Exception as exc:  # noqa: BLE001  never raise to the caller
        error = _safe_error(exc)
    if use_fallback:
        fb = _load_fallback()
        if fb is not None:
            return {"questions": fb["questions"], "source": "fallback", "model": fb.get("model") or str(model),
                    "error": error}
    reply = mock_reply(bundle)
    reply["error"] = error
    return reply


def _safe_error(exc: Exception) -> str:
    msg = f"{type(exc).__name__}: {exc}"
    key = os.environ.get("GROQ_API_KEY")
    if key:
        msg = msg.replace(key, "***")
    msg = re.sub(r"gsk_[A-Za-z0-9]+", "gsk_***", msg)
    return msg[:500]


def _load_fallback() -> dict | None:
    try:
        obj = json.loads(contract.FALLBACK_FILE.read_text(encoding="utf-8"))
        return {"questions": _questions(obj), "model": obj.get("model")}
    except Exception:  # noqa: BLE001
        return None


def save_fallback(raw: dict) -> None:
    """Record a good RawReply (e.g. the best real Groq run) as the fallback."""
    questions = _questions(raw)
    out = {"questions": questions, "source": raw.get("source", "groq"), "model": raw.get("model", contract.MODEL),
           "error": None}
    contract.FALLBACK_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def smoke(bundle: dict) -> tuple[bool, int, str, str | None]:
    """One real Groq call, no fallback. Returns (ok, n_questions, source, error)."""
    r = ask(bundle, use_fallback=False)
    return r["source"] == "groq" and len(r["questions"]) > 0, len(r["questions"]), r["source"], r["error"]


# ------------------------------------------------------------------ deterministic mock

def mock_reply(bundle: dict) -> dict:
    """3 to 6 template questions built from the bundle, citing only bundle ids. For tests and offline demos."""
    events = bundle.get("events") or {}
    contras = [c for c in bundle.get("contradictions") or [] if isinstance(c, dict) and c.get("id")]
    persons = [p for p in bundle.get("persons") or [] if isinstance(p, dict) and p.get("id")]
    person_ids = [p["id"] for p in persons]
    contra_ids = {c["id"] for c in contras}

    def evs(ids) -> list[str]:
        return [e for e in dict.fromkeys(ids or []) if e in events][:4]

    def persons_in(c: dict) -> list[str]:
        text = json.dumps(c, ensure_ascii=False)
        found = [pid for pid in person_ids if re.search(rf"\b{re.escape(pid)}\b", text)]
        for e in c.get("events") or []:
            pid = (events.get(e) or {}).get("person")
            if pid in person_ids and pid not in found:
                found.append(pid)
        return found[:3]

    qs: list[dict] = []

    def add(kind, question, why, ev=(), cs=(), ps=(), focus=None):
        qs.append({"kind": kind, "question": question, "why": why,
                   "cites": {"events": list(ev), "contradictions": list(cs), "persons": list(ps)}, "focus": focus})

    for c in contras:
        if c.get("kind") == "physical" or c.get("rule") == "impossible_travel":
            add("assumption",
                f"Finding {c['id']} reads both records as the same holder. What record shows who physically held "
                "that identifier at each of the two times?",
                "The finding links two reads of one identifier that are too close together for one walk.",
                evs(c.get("events")), [c["id"]], persons_in(c), c["id"])

    for f in bundle.get("untrusted_files") or []:
        custody = [c["id"] for c in contras if c.get("file") == f or f in str(c.get("explanation", ""))]
        add("weak_evidence",
            f"{f} failed its custody check. Which findings still lean on it, and is there an independent record "
            "for the same activity?",
            f"The manifest hash for {f} does not match, so its rows cannot be trusted on their own.",
            [], custody[:2], [], custody[0] if custody else None)

    temporal = [c for c in contras if c.get("kind") == "temporal"]
    if temporal:
        c = temporal[0]
        add("alternative",
            f"For {c['id']}, what ordinary explanation, such as a device left behind or a scheduled task, would the "
            "same records also allow?",
            "The finding rests on a timing gap that more than one routine situation could produce.",
            evs(c.get("events")), [c["id"]], persons_in(c), c["id"])

    ranked = [p for p in persons if isinstance(p.get("anomaly"), (int, float))]
    if ranked:
        top = sorted(ranked, key=lambda p: (p.get("anomaly_rank") or 10**6, -p["anomaly"]))[0]
        flag_events = [e for fl in top.get("red_flags") or [] if isinstance(fl, dict) for e in fl.get("events") or []]
        add("confirm_or_disprove",
            f"{top['id']} had the most unusual day in the analysis. Which record, such as a calendar or work order, "
            "would confirm or rule out a routine reason for it?",
            "The anomaly score only shows the day differed from this person's own baseline.",
            evs(flag_events), [], [top["id"]], top["id"])

    statements = [c for c in contras if c.get("kind") == "statement"]
    if statements and len(qs) < 6:
        c = statements[0]
        add("gap",
            f"For {c['id']}, has anyone checked whether the stated time was an estimate, and what other record "
            "covers that window?",
            "The finding compares a spoken statement against a single kind of record.",
            evs(c.get("events")), [c["id"]], persons_in(c), c["id"])

    generic = [
        ("gap", "Which records for the same window, such as parking, visitor or camera logs, has the analysis not "
                "looked at yet?", "The findings draw on a limited set of sources."),
        ("assumption", "Does every finding assume clocks on different systems agree? What record shows how far "
                       "apart they drift?", "Timing findings depend on clocks being aligned across sources."),
        ("alternative", "Which people with access to the same rooms have not been compared against these "
                        "findings?", "The analysis focuses on a subset of the people who had access."),
    ]
    for kind, q, why in generic:
        if len(qs) >= 3:
            break
        add(kind, q, why)

    qs = qs[:6]
    for q in qs:  # final guard: only bundle ids
        q["cites"]["contradictions"] = [x for x in q["cites"]["contradictions"] if x in contra_ids]
        q["cites"]["persons"] = [x for x in q["cites"]["persons"] if x in person_ids]
        q["cites"]["events"] = [x for x in q["cites"]["events"] if x in events]
        if q["focus"] not in contra_ids and q["focus"] not in person_ids:
            q["focus"] = None
    return {"questions": qs, "source": "mock", "model": "mock", "error": None}
