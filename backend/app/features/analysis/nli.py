"""Stage 7b: statement vs event contradictions with an NLI cross-encoder.

Events are rendered as short first-person sentences in local time ("I badged out of room 217 at 6:02 pm")
and paired with the speaker's own statements. Pairs above THRESHOLD are kept (PLAN.md risk table).
"""
import logging
from functools import lru_cache

from app.features.analysis import timeutil, vocab

log = logging.getLogger(__name__)

MODEL = "cross-encoder/nli-deberta-v3-small"
THRESHOLD = 0.85
MAX_CITED = 10
CLAIM_TYPES = vocab.STATEMENT | {"email"}
_STOPWORDS = {"I", "No", "Yes", "The", "A", "An", "My", "It", "We", "He", "She", "They", "Thanks", "Please"}


def anchors(claim: str, names: set[str]) -> set[str]:
    """Named things in a claim: capitalized words that are not the first word of the sentence, not a
    pronoun/filler, and not a person's name ('I never touched the Titan folder' -> {'titan'})."""
    import re
    words = re.findall(r"[A-Za-z][A-Za-z0-9]+", claim)
    return {w.lower() for w in words[1:] if w[0].isupper() and w not in _STOPWORDS and w.lower() not in names}


def shares_subject(claim: str, record: str, names: set[str] | None = None) -> bool:
    """NLI only judges a claim against records about the same named thing (PLAN.md risk table: back NLI
    with a rule). Common words ('logged', 'room', 'laptop') are not enough."""
    import re
    record_words = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9]+", record)}
    return bool(anchors(claim, names or set()) & record_words)


_TEMPLATES = {
    **{t: "I badged into room {room} at {time}." for t in vocab.BADGE_IN},
    **{t: "I badged out of room {room} at {time}." for t in vocab.BADGE_OUT},
    "wifi_assoc": "My laptop connected to the office Wi-Fi at {time}.",
    "wifi_roam": "My laptop was on the office Wi-Fi at {time}.",
    "wifi_disassoc": "My laptop disconnected from the office Wi-Fi at {time}.",
    **{t: "I logged on to {device} at {time}." for t in vocab.LOGON},
    **{t: "I opened {path} on {device} at {time}." for t in vocab.FILE_ACCESS},
    **{t: "I plugged a USB drive into {device} at {time}." for t in vocab.USB},
    "parking_exit": "My car left the campus parking at {time}.",
}


def render(event: dict) -> str | None:
    tpl = _TEMPLATES.get(event.get("type"))
    if not tpl or not event.get("t"):
        return None
    sentence = tpl.format(
        room=event.get("room") or "an unknown room",
        device=(event.get("attrs") or {}).get("host") or event.get("device") or "a computer",
        path=(event.get("attrs") or {}).get("path") or "files",
        time=timeutil.spoken(timeutil.parse(event["t"])),
    )
    first_seen = (event.get("attrs") or {}).get("first_seen")
    if event["type"] in vocab.USB and first_seen and timeutil.local_day(timeutil.parse(first_seen)) == timeutil.local_day(timeutil.parse(event["t"])):
        sentence += " It was the first time that USB drive was ever plugged into it."
    return sentence


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import CrossEncoder  # heavy import, only when NLI runs

    m = CrossEncoder(MODEL)
    labels = {v.lower(): int(k) for k, v in m.model.config.id2label.items()}
    return m, labels["contradiction"]


def candidate_pairs(events: list[dict], days: set, skip: set[str], names: set[str]) -> list[tuple[dict, dict, str]]:
    """(claim, event, rendered sentence): each statement/email the rules do not own, against the
    speaker's own records on the days the hard rules flag."""
    claims = [e for e in events if e.get("type") in CLAIM_TYPES and e.get("person") and e["id"] not in skip]
    own: dict[str, list[dict]] = {}
    for e in events:
        if e.get("person") and e.get("t") and timeutil.local_day(timeutil.parse(e["t"])) in days:
            own.setdefault(e["person"], []).append(e)
    pairs = []
    for c in claims:
        for e in own.get(c["person"], []):
            if e is not c and (sentence := render(e)) and shares_subject(c["source"]["quote"], sentence, names):
                pairs.append((c, e, sentence))
    return pairs


def find(events: list[dict], days: set, skip: set[str] | None = None, names: set[str] | None = None) -> list[dict]:
    """One contradiction per claim: the claim plus every record that contradicts it above THRESHOLD."""
    pairs = candidate_pairs(events, days, skip or set(), names or set())
    if not pairs:
        return []
    try:
        model, contra_idx = _model()
    except Exception as exc:  # model missing or offline: rules still run
        log.warning("NLI model unavailable (%s); skipping statement contradictions", exc)
        return []

    import numpy as np

    logits = model.predict([(sentence, c["source"]["quote"]) for c, _, sentence in pairs], show_progress_bar=False)
    probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)

    hits: dict[str, list[tuple[float, dict, str]]] = {}
    claims = {}
    for (c, e, sentence), p in zip(pairs, probs):
        if (score := float(p[contra_idx])) >= THRESHOLD:
            hits.setdefault(c["id"], []).append((score, e, sentence))
            claims[c["id"]] = c

    found = []
    for cid, hs in hits.items():
        hs.sort(key=lambda h: -h[0])
        best, c = hs[0], claims[cid]
        found.append({
            "kind": "statement",
            "events": [cid, *[e["id"] for _, e, _ in hs[:MAX_CITED]]],
            "score": round(best[0], 3),
            "explanation": (
                f"Statement \"{c['source']['quote']}\" vs the record \"{best[2]}\" (NLI contradiction {best[0]:.2f})"
                + (f", plus {len(hs) - 1} more record(s) like it." if len(hs) > 1 else ".")
            ),
            "persons": [c["person"]],
            "rule": "nli",
        })
    return found
