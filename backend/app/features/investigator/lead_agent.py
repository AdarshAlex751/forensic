"""Stage 9: the lead investigator.

A deepagents agent (Llama 3.3 70B on Groq) that sees only VERIFIED facts. It plans with the deepagents to-do tool,
delegates to the timeline / physics / comms / money subagents, ranks hypotheses with what would disprove each,
and may call request_evidence, which creates a request that waits for human approval. Approval triggers a pipeline
rerun; this function then runs again with the released evidence included and replans.

It reports facts and contradictions only. It never labels anyone's role in the crime (a human does).

The LLM is behind an injectable `runner(prompt) -> str`, so everything except the actual Groq call is unit-tested.
If there is no key, the library cannot load, the call fails or the answer is unusable, a rules-based fallback builds
hypotheses straight from the verified contradictions (code does the math) and says so in `engine`/`warnings`.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from app.features.investigator.agent_tools import AgentTools, ToolContext, _matches_a_source
from app.features.investigator.subagents import build_subagents
from app.features.investigator.trace import Trace, trace as global_trace
from app.shared.llm_client import EXTRACTOR_MODEL, LEAD_MODEL, get_llm, with_backoff

log = logging.getLogger(__name__)

Runner = Callable[[str], str]
MAX_HYPOTHESES = 5
_NOTE_KINDS = {"check_next", "todo", "cleared"}
# The investigator reports what the records show and where they disagree. It never labels a person's role in the
# crime and never speaks of intent, motive, deception or fault; a human draws those conclusions.
_LABELS = re.compile(
    r"\b(guilty|culprit|perpetrator|thief|criminal|committed the|responsible for the"
    r"|lie[sd]?|lying|liar|false statement|is false|was false|untrue"
    r"|deliberate(?:ly)?|intentional(?:ly)?|motive|conceal\w*|cover[- ]?up|hid(?:e|ing|den)? (?:it|the|his|her|their)"
    r"|spoof\w*|fabricat\w*|tamper\w*|steal|stole|stolen|theft|exfiltrat\w*|sabotag\w*|possibly to|in order to)\b",
    re.I,
)

_DISPROOF = {
    "physical": "A record showing the second read was made by someone other than the card holder, or a shorter walking route than the model found.",
    "temporal": "A log entry showing the later activity came from a different person or device, or a clock error in the logs.",
    "statement": "A corrected or clarified statement, or evidence that the compared record belongs to someone else.",
    "custody": "An unaltered copy of the file whose hash matches the manifest.",
}
_DEFAULT_DISPROOF = "Evidence that the two cited records do not describe the same person, device or moment."

LEAD_PROMPT = """You are the lead investigator in a digital-forensics case. You work only from VERIFIED facts: the brief you are given and
what your tools return. You never see raw files.

Rules:
- Report facts and contradictions only. Never say a person is guilty and never label anyone's role in the crime; a human does that.
- Describe what the RECORDS show and where they disagree. Never describe anyone's intent, motive, purpose, honesty or fault:
  no "deliberately", "to conceal", "lied", "false statement", "spoofed", "tampered". Write "the records conflict" or
  "the statement is not supported by the badge record". Each hypothesis is a testable claim about the records.
- Every hypothesis must cite the verified contradiction ids that support it, and say what evidence would DISPROVE it.
- Prefer hypotheses you can challenge: ask what facts say a person would be where the records place them.
- Plan with your to-do list, delegate to subagents (timeline, physics, comms, money) for checks, then rank.
- If one more piece of evidence would settle the leading hypothesis, call request_evidence once (what to pull, and which
  hypothesis it would disprove). Do not assume the answer; a human must approve it.

Finish with ONLY a JSON object, no other text:
{"hypotheses":[{"text":"...","confidence":0.0-1.0,"supports":["c1"],"disproved_by":"..."}],
 "notes":[{"text":"...","kind":"check_next|todo|cleared"}]}
Use "cleared" for people the evidence clears (say which record clears them). At most 5 hypotheses."""


@dataclass
class LeadResult:
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    notes: list[dict[str, str]] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)
    engine: str = "rules"  # "llm" | "rules"
    warnings: list[str] = field(default_factory=list)


def build_brief(ctx: ToolContext) -> str:
    lines = [f"Verified events: {len(ctx.events)}. Verified contradictions: {len(ctx.contradictions)}.", "", "Contradictions (verified):"]
    for c in sorted(ctx.contradictions, key=lambda c: -c.score)[:12]:
        extra = f", walk {c.walk_s:g}s vs gap {c.gap_s:g}s" if c.walk_s is not None and c.gap_s is not None else ""
        lines.append(f"- {c.id} [{c.kind}] score {c.score:.2f}, events {', '.join(c.events)}{extra}: {c.explanation}")
    if ctx.persons:
        lines += ["", "People and anomaly scores (a high score is a reason to look, not a finding):"]
        for p in sorted(ctx.persons, key=lambda p: -p.anomaly)[:6]:
            lines.append(f"- {p.id} {p.name}: anomaly {p.anomaly:.2f}")
    obtainable = AgentTools(ctx)._still_obtainable()
    if obtainable is not None:
        lines += ["", "Withheld sources a human can release if you request them: "
                  + (", ".join(obtainable) if obtainable else "none (the case has no further evidence)")]
    if ctx.approvals.requests:
        lines += ["", "Evidence requests so far:"]
        for r in ctx.approvals.requests:
            lines.append(f"- {r['id']} [{r['status']}] {r['ask']} (why: {r['why']})")
    return "\n".join(lines)


def sanitize_hypotheses(raw: Any, known_ids: set[str],
                        neutral: dict[str, str] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Keep only hypotheses that are about the records. `neutral` maps a contradiction id to plain wording: a hypothesis
    that speaks of intent or fault is rewritten to it (same support, same confidence) instead of being lost."""
    warns: list[str] = []
    kept: list[dict[str, Any]] = []
    for h in raw if isinstance(raw, list) else []:
        if not isinstance(h, dict) or not str(h.get("text", "")).strip():
            warns.append("dropped a hypothesis with no text")
            continue
        text = str(h["text"]).strip()
        if _LABELS.search(text):
            first = next((str(s) for s in (h.get("supports") or []) if neutral and str(s) in neutral), None)
            if first is None:
                warns.append(f"dropped a hypothesis that speaks of intent or fault, or labels a person: {text[:60]}")
                continue
            warns.append(f"replaced a hypothesis that speaks of intent or fault with neutral wording for {first}: {text[:60]}")
            text = neutral[first]
        disproof = str(h.get("disproved_by", "")).strip()
        if not disproof:
            warns.append(f"dropped a hypothesis with no 'what would disprove it': {text[:60]}")
            continue
        supports = [str(s) for s in (h.get("supports") or [])]
        bad = [s for s in supports if s not in known_ids]
        if bad:
            warns.append(f"removed unknown supports {', '.join(bad)} from: {text[:60]}")
        supports = [s for s in supports if s in known_ids]
        if not supports:
            warns.append(f"dropped a hypothesis with no verified support: {text[:60]}")
            continue
        try:
            conf = max(0.0, min(1.0, float(h.get("confidence", 0))))
        except (TypeError, ValueError):
            conf = 0.0
        kept.append({"text": text, "confidence": round(conf, 2), "supports": supports, "disproved_by": disproof})
    kept.sort(key=lambda h: -h["confidence"])
    kept = kept[:MAX_HYPOTHESES]
    return [{"id": f"h{i}", **h} for i, h in enumerate(kept, 1)], warns


def _sanitize_notes(raw: Any) -> list[dict[str, str]]:
    out = []
    for n in raw if isinstance(raw, list) else []:
        if isinstance(n, dict) and str(n.get("text", "")).strip() and not _LABELS.search(str(n["text"])):
            kind = str(n.get("kind", "check_next"))
            out.append({"text": str(n["text"]).strip(), "kind": kind if kind in _NOTE_KINDS else "check_next"})
    return out[:8]


def _extract_json(text: str) -> Any:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(candidate)


_LEAVING = re.compile(r"\b(home|left|leave|leaving|exit|exited)\b", re.I)
_PARKING_TYPES = {"parking_entry", "parking_exit"}
_PARKING_ASK = "Pull the parking entry and exit log for the evening of the incident."


def _request_parking_log_if_it_would_settle_a_departure_claim(ctx: ToolContext) -> None:
    """The one evidence request the rules engine can justify: a statement conflict that hinges on WHEN someone left,
    when no parking record is part of the case yet. Idempotent (same ask -> same request)."""
    if any(e.type in _PARKING_TYPES for e in ctx.events):
        return
    hinges = [c for c in ctx.contradictions if c.kind == "statement" and _LEAVING.search(c.explanation)]
    if not hinges:
        return
    c = max(hinges, key=lambda c: c.score)
    names = AgentTools(ctx)._still_obtainable()
    # one request per source, whatever the wording: the model may already have asked for it in its own words
    if any(_matches_a_source(r["ask"], names) if names else "parking" in r["ask"].lower() for r in ctx.approvals.requests):
        return
    # through the tool, so the "only what can really be released" rule applies here too
    AgentTools(ctx).request_evidence(
        _PARKING_ASK,
        f"Contradiction {c.id} rests on when someone left the building. A parking record can place a vehicle's "
        f"exit in time and either support or weaken the badge-based timing; no other source here can.",
    )


def rules_result(ctx: ToolContext, warnings: list[str] | None = None) -> LeadResult:
    """Hypotheses straight from the verified contradictions: confidence follows the detector's score."""
    _request_parking_log_if_it_would_settle_a_departure_claim(ctx)
    hyps = []
    for c in sorted(ctx.contradictions, key=lambda c: -c.score)[:MAX_HYPOTHESES]:
        hyps.append({
            "text": f"The records conflict: {c.explanation}".strip(),
            "confidence": round(min(0.95, c.score * 0.9), 2),
            "supports": [c.id],
            "disproved_by": _DISPROOF.get(c.kind, _DEFAULT_DISPROOF),
        })
    hyps = [{"id": f"h{i}", **h} for i, h in enumerate(hyps, 1)]
    notes = [{"text": f"Waiting for approval: {r['ask']}", "kind": "check_next"} for r in ctx.approvals.requests if r["status"] == "pending"]
    return LeadResult(hyps, notes, [dict(r) for r in ctx.approvals.requests], "rules", warnings or [])


# Groq accounts differ in which models they can use, and the shared defaults can be retired. Try, in order: an env
# override, the shared default, then these. Only models the account actually lists are chosen.
LEAD_FALLBACKS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b")
SUBAGENT_FALLBACKS = ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b")


def pick_model(candidates: list[str], available: set[str] | None) -> str | None:
    """First candidate the account has; the first candidate if the account's list is unknown; None if none exist."""
    if available is None:
        return candidates[0] if candidates else None
    return next((m for m in candidates if m in available), None)


def _candidates(env_name: str, shared_default: str, fallbacks: tuple[str, ...]) -> list[str]:
    seen: list[str] = []
    for m in (os.getenv(env_name, "").strip(), shared_default, *fallbacks):
        if m and m not in seen:
            seen.append(m)
    return seen


def _available_models() -> set[str] | None:
    """Model ids this Groq key can use, or None if the list cannot be fetched (then we just try the first choice)."""
    try:
        import httpx

        r = httpx.get("https://api.groq.com/openai/v1/models",
                      headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}, timeout=15)
        r.raise_for_status()
        return {m["id"] for m in r.json().get("data", []) if m.get("active", True)}
    except Exception as exc:  # noqa: BLE001 - a failed lookup must not stop the investigation
        log.warning("could not list Groq models (%s); trying the first configured model", exc)
        return None


def build_llm_runner(ctx: ToolContext, tools: AgentTools, trace: Trace) -> Runner | None:
    """The real deepagents + Groq runner, or None if it cannot be built here (no key, library missing or blocked)."""
    if not os.getenv("GROQ_API_KEY"):
        log.info("GROQ_API_KEY not set; using the rules engine")
        return None
    try:
        from deepagents import create_deep_agent  # lazy: heavy, and may be unavailable

        available = _available_models()
        lead = pick_model(_candidates("INVESTIGATOR_LEAD_MODEL", LEAD_MODEL, LEAD_FALLBACKS), available)
        sub = pick_model(_candidates("INVESTIGATOR_SUBAGENT_MODEL", EXTRACTOR_MODEL, SUBAGENT_FALLBACKS), available)
        if not lead or not sub:
            log.warning("no usable Groq model for this key (lead=%s, subagents=%s); using the rules engine", lead, sub)
            return None
        log.info("investigator models: lead=%s subagents=%s", lead, sub)
        agent = create_deep_agent(
            model=get_llm(lead, temperature=0),
            tools=tools.as_functions(("request_evidence", "graph_neighbors")),
            system_prompt=LEAD_PROMPT,
            subagents=build_subagents(tools, model=get_llm(sub, temperature=0)),
        )
    except Exception as exc:  # noqa: BLE001 - any build failure means "use the fallback", not "crash the pipeline"
        log.warning("deepagents unavailable (%s); using the rules engine", exc)
        return None

    def run(prompt: str) -> str:
        final = ""
        for update in agent.stream({"messages": [{"role": "user", "content": prompt}]},
                                   config={"recursion_limit": 60}, stream_mode="updates"):
            for node, delta in (update or {}).items():
                for m in (delta or {}).get("messages", []) if isinstance(delta, dict) else []:
                    for call in getattr(m, "tool_calls", None) or []:
                        name = call.get("name", "")
                        args = call.get("args", {}) or {}
                        if name == "write_todos":
                            todos = [{"text": str(t.get("content", "")), "status": {"in_progress": "doing", "completed": "done"}.get(t.get("status"), "pending")}
                                     for t in args.get("todos", []) if isinstance(t, dict)]
                            trace.emit("lead", "plan", "Updated the plan", todos=todos)
                        elif name == "task":
                            trace.emit(str(args.get("subagent_type", "lead")), "delegate", str(args.get("description", ""))[:160])
                        elif name == "request_evidence":
                            trace.emit("lead", "request", str(args.get("ask", ""))[:160])
                    content = getattr(m, "content", "")
                    if isinstance(content, str) and content and getattr(m, "type", "") == "ai":
                        final = content
        return final

    return run


def investigate(ctx: ToolContext, runner: Runner | None = None, trace: Trace | None = None) -> LeadResult:
    tr = trace or global_trace
    tools = AgentTools(ctx)
    known = {c.id for c in ctx.contradictions}
    tr.emit("lead", "plan", f"Reading {len(ctx.contradictions)} verified contradictions from {len(ctx.events)} verified events")
    if runner is None:
        runner = build_llm_runner(ctx, tools, tr)
    if runner is None:
        res = rules_result(ctx, ["no language model available; hypotheses built by rules from verified contradictions"])
    else:
        brief = build_brief(ctx)
        try:
            raw = with_backoff(lambda: runner(brief))
            data = _extract_json(raw)
            neutral = {c.id: f"The records conflict: {c.explanation}".strip() for c in ctx.contradictions}
            hyps, warns = sanitize_hypotheses(data.get("hypotheses"), known, neutral)
            if not hyps:
                raise ValueError("the model returned no usable hypotheses")
            notes = _sanitize_notes(data.get("notes"))
            # The model may not think to ask; the same justified request is raised for it (never a duplicate).
            _request_parking_log_if_it_would_settle_a_departure_claim(ctx)
            for r in ctx.approvals.requests:
                if r["status"] == "pending" and not any(r["ask"] in n["text"] for n in notes):
                    notes.append({"text": f"Waiting for approval: {r['ask']}", "kind": "check_next"})
            res = LeadResult(hyps, notes, [dict(r) for r in ctx.approvals.requests], "llm", warns)
        except Exception as exc:  # noqa: BLE001 - never let a flaky model take down the pipeline
            log.warning("lead investigator failed (%s); using the rules engine", exc)
            res = rules_result(ctx, [f"language model unusable ({type(exc).__name__}: {exc}); used rules"])
    tr.emit("lead", "rank", f"Ranked {len(res.hypotheses)} hypotheses ({res.engine})")
    if res.requests:
        pending = [r for r in res.requests if r["status"] == "pending"]
        if pending:
            tr.emit("lead", "request", f"Waiting for approval: {pending[0]['ask']}")
    tr.emit("lead", "done", "Investigation finished")
    return res
