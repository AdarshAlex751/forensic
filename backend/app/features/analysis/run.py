"""Analysis slice entry point: resolve -> graph -> detect (PLAN.md stages 3, 4, 6, 7).

Writes data/analysis/persons.json, edges.json, contradictions.json (CONTRACTS.md, Person 3).
Each stage after resolution is isolated so one failure does not wipe out the others' output.
"""
import logging
from collections import Counter
from pathlib import Path

from app.features.analysis import (
    anomaly_features,
    anomaly_scorer,
    entity_resolution,
    fact_graph,
    files,
    nli,
    rules,
    views,
)
from app.features.scene.tools import walk_time  # CONTRACTS: the only import allowed from scene

log = logging.getLogger(__name__)


def analyze(inputs: dict, use_nli: bool = True, walk=walk_time, previous: list[dict] | None = None) -> dict:
    """`walk` is scene's walk_time; tests may pass another with the same signature.
    `previous` is the last contradictions.json: keeps ids stable and marks new/updated findings."""
    # Stage 3: resolve every raw identifier to one person
    persons = entity_resolution.build_persons(inputs["inventory"])
    index = entity_resolution.build_alias_index(inputs["inventory"])
    untrusted = rules.untrusted_files(inputs["evidence"])
    all_events = entity_resolution.resolve_events(inputs["events"], index, persons, untrusted)
    # Events from a file that fails custody are reported once (custody rule) and used nowhere else.
    events = [e for e in all_events if (e.get("source") or {}).get("file") not in untrusted]
    unresolved = Counter(e["type"] for e in all_events if e.get("actor") and not e.get("person"))
    if unresolved:
        log.info("unresolved (outside) actors by type: %s", dict(unresolved))

    # Stage 4: fact graph, centrality, communities
    g = fact_graph.build_graph(events, persons, inputs["devices_csv"], index)
    betweenness, community = fact_graph.metrics(g)
    for p in persons:
        p["centrality"] = round(betweenness.get(p["id"], 0.0), 4)  # new field (rule 6): yarn-board node size
        p["community"] = community.get(p["id"], -1)

    # Stage 6: anomaly scores (facts about unusual days, never a verdict)
    try:
        df = anomaly_features.add_baseline_deviation(anomaly_features.daily_features(events))
        scores, features = anomaly_scorer.score(df, extra={"centrality": {p["id"]: p["centrality"] for p in persons}})
    except Exception:
        log.exception("anomaly scoring failed; scores left at 0")
        scores, features = {}, {}
    for p in persons:
        p["anomaly"] = scores.get(p["id"], 0.0)
        p["features"] = features.get(p["id"], {})
    views.red_flags(persons, events)  # page fields: rank, red flags and context, each citing its events

    # Stage 7: contradictions. Hard rules first; their days anchor the statement checks.
    found = rules.custody_mismatch(all_events, inputs["evidence"]) + rules.run_hard(events, inputs["evidence"], walk)
    days = rules.focus_days(found, events)
    found += rules.run_statement_rules(events, persons, days)
    if use_nli:
        try:
            names = {part.lower() for p in persons for part in (p.get("name") or "").split()}
            found += nli.find(events, days, skip=rules.nli_excluded_claims(events), names=names)
        except Exception:
            log.exception("NLI failed; keeping rule-based contradictions only")

    return {
        "persons": persons,
        "edges": fact_graph.export_edges(g),
        "contradictions": views.number(found, all_events, previous),
        "events": all_events,
        "untrusted_files": sorted(untrusted),
        "focus_days": sorted(str(d) for d in days),
    }


def run(case_id: str, out_dir: Path | None = None, use_nli: bool = True) -> None:
    result = analyze(files.load_inputs(), use_nli=use_nli, previous=files.load_previous("contradictions", out_dir))
    files.write_outputs({k: result[k] for k in ("persons", "edges", "contradictions")}, out_dir)
    log.info("analysis %s: %d persons, %d edges, %d contradictions",
             case_id, len(result["persons"]), len(result["edges"]), len(result["contradictions"]))
