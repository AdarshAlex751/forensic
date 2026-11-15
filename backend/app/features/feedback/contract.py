"""The contract between the three parts of the feedback slice. Agents build against this file; change it only together.

Flow:   context.build_bundle() -> Bundle (dict)   ->   critic.ask(bundle) -> RawReply (dict)
        ->   check.validate(raw, bundle) -> Feedback (dict)   ->   check.write(feedback)  ->  data/feedback/feedback.json

Inputs (read-only, through app.shared.merge.load so the fake/real switch applies):
  data/analysis/persons.json, edges.json, contradictions.json      (Person 3)
  data/evidence/events.json                                        (Person 1, for quotes of cited events)
Never read: Person 4's data/investigator/*, data/evidence/truth/, any answer_key.json, CASE.md, casegen/.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = ROOT / "data" / "feedback"
OUT_FILE = OUT_DIR / "feedback.json"
FALLBACK_FILE = Path(__file__).with_name("fallback_reply.json")   # recorded good reply, used when Groq is unavailable

# Groq model. The project's planned Llama models are not available on this key (GET /v1/models); gpt-oss-120b is the
# strongest model it has. Override with FEEDBACK_MODEL in .env (e.g. qwen/qwen3.8-27b) without changing code.
MODEL = __import__("os").environ.get("FEEDBACK_MODEL") or "openai/gpt-oss-120b"
TEMPERATURE = 0.2
MAX_QUESTIONS = 12
# Free tier for gpt-oss-120b: 8,000 tokens per minute, counting prompt + reply cap. The chars/4 estimate undercounts
# real tokens (~1.3x for this JSON), and the system prompt adds ~900, so the bundle budget stays well below 8,000.
MAX_BUNDLE_TOKENS = 4000               # rough budget (chars / 4); the real case bundle floors at ~3,670 and that request fits
MAX_REPLY_TOKENS = 2000                # reply cap (gpt-oss reasons first; low effort + this leaves room for the JSON)
REASONING_EFFORT = "low"               # gpt-oss: keep the hidden reasoning short so the JSON fits the cap

KINDS = ("assumption", "alternative", "confirm_or_disprove", "weak_evidence", "gap")
KIND_LABELS = {
    "assumption": "Question the assumption",
    "alternative": "Consider an alternative",
    "confirm_or_disprove": "What would confirm or disprove it",
    "weak_evidence": "Weak or tainted evidence",
    "gap": "Gap",
}

# Verdict / labelling language the critic must never use (checked case-insensitively on question and why).
FORBIDDEN = ("guilty", "innocent", "culprit", "perpetrator", "thief", "stole", "is lying", "lied", "did it",
             "responsible for", "suspect is", "confess", "criminal", "obviously", "clearly guilty", "framed")

# ------------------------------------------------------------------ Bundle (context.build_bundle -> critic)
# {
#   "case": {"id": "1010F", "title": "..."},
#   "contradictions": [ {"id": "c2", "kind", "rule", "title", "explanation", "score", "t", "room",
#                        "sides": [{"label", "events": [...], "quotes": [...]}], "events": [...]} ],
#   "persons": [ {"id": "p_bg_17", "name", "role", "anomaly", "anomaly_rank", "centrality", "community",
#                 "red_flags": [{"text", "events": [...]}], "context": [{"text", "events": [...]}],
#                 "links": {"devices": [...], "rooms": [...], "files": [...], "accounts": [...]}} ],
#   "events": { "e9507": {"t", "type", "person", "device", "room", "file", "line", "quote"} },   # every cited event
#   "untrusted_files": ["endpoint/security_log.csv"],
#   "notes": ["contradiction c1 is a custody finding: events from untrusted files are excluded elsewhere", ...],
#   "budget": {"approx_tokens": 4100, "dropped": {"persons": 0, "events": 0}}
# }
# Ids in the bundle are the only ids a question may cite.

# ------------------------------------------------------------------ RawReply (critic -> check)
# {"questions": [ {"kind": one of KINDS, "question": str, "why": str,
#                  "cites": {"events": [...], "contradictions": [...], "persons": [...]},
#                  "focus": "c2" | "p_bg_17" | null } ],
#  "source": "groq" | "mock" | "fallback", "model": str, "error": str | null}

# ------------------------------------------------------------------ Feedback (check -> feedback.json)
# {
#   "case_id": "1010F",
#   "generated_at": "2026-03-09T...-05:00" (fixed-offset EST),
#   "source": "groq" | "mock" | "fallback", "model": str,
#   "input_fingerprint": sha256 of the canonical bundle JSON (same analysis -> same fingerprint),
#   "questions": [ {"id": "q1", "kind", "kind_label", "question", "why",
#                   "cites": {"events": [...], "contradictions": [...], "persons": [...]},
#                   "quotes": [ {"event": "e9507", "file", "line", "quote"} ],     # filled from the bundle
#                   "focus": str | null} ],
#   "rejected": [ {"question": str, "reason": str} ],
#   "counts": {"asked": int, "kept": int, "rejected": int}
# }
