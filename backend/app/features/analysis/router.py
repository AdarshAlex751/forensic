"""Analysis routes for the two analysis pages. Read-only views over data/analysis/*.json
(fake or real per USE_REAL_ANALYSIS, same switch as the findings merge)."""
from fastapi import APIRouter, HTTPException

from app.features.analysis import views
from app.shared.merge import load

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"slice": "analysis", "status": "ok"}


@router.get("/red-flags")
def red_flags() -> dict:
    """Anomalies page: people ranked by Isolation Forest score, each with red flags and context that cite events.
    A score means "unusual day", never a verdict."""
    persons = load("analysis", "persons.json")
    ranked = sorted((p for p in persons if p.get("anomaly", 0) > 0), key=lambda p: -p["anomaly"])
    return {"persons": ranked, "unscored": [p["id"] for p in persons if not p.get("anomaly")]}


@router.get("/contradictions")
def contradictions() -> dict:
    """Contradictions page: cards (both sides + fact -> evidence chain), grouped by rule, and the id of the
    newest new/updated finding so the page can open on it after released evidence is ingested."""
    cards = load("analysis", "contradictions.json")
    return {"contradictions": cards, "groups": views.groups(cards), "latest": views.latest_change(cards),
            "changed": views.changed(cards)}


@router.get("/contradictions/{cid}")
def contradiction(cid: str) -> dict:
    for c in load("analysis", "contradictions.json"):
        if c["id"] == cid:
            return c
    raise HTTPException(404, f"no contradiction {cid}")
