"""The four specialist subagents the lead investigator delegates to (deepagents `SubAgent` specs).

Each gets only the tools it needs, a narrow job, and the same ground rules: report facts with source ids,
never label a person's role in the case, and say what would disprove a finding.
"""
from __future__ import annotations

from typing import Any

from app.features.investigator.agent_tools import AgentTools

_RULES = (
    " Ground rules: report only facts that come back from your tools, each with its event id and source file and line."
    " Never say a person is guilty or label their role in the case; a human decides that."
    " If a tool returns an error or nothing, say so plainly. Finish with a short list: finding, event ids, and what would disprove it."
)

# name -> (description, prompt, tool names)
_SPECS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "timeline": (
        "Rebuilds who did what, when, from badge, Wi-Fi, laptop and parking records. Use for questions about order of events and gaps.",
        "You are the timeline analyst. Rebuild the sequence of verified events for the people and window you are given and point out"
        " gaps, overlaps and records that cannot both be true." + _RULES,
        ("query_timeline", "graph_neighbors"),
    ),
    "physics": (
        "Checks whether movements are physically possible: walking time between rooms, Wi-Fi coverage, camera views.",
        "You are the physical-plausibility analyst. Use walk_time, ap_covers and camera_sees to test whether two records"
        " could belong to the same person, and report the gap in seconds against the walking time." + _RULES,
        ("query_timeline", "walk_time", "ap_covers", "camera_sees"),
    ),
    "comms": (
        "Searches emails, chat messages and interview statements and compares what people said with what the records show.",
        "You are the communications analyst. Find statements and messages relevant to the question and compare each with the"
        " verified timeline. Quote exactly; do not paraphrase a quote." + _RULES,
        ("search_comms", "query_timeline"),
    ),
    "money": (
        "Follows payments and transfers and their timing relative to the other events.",
        "You are the financial-records analyst. Look at verified transaction events and related messages and report amounts,"
        " dates and counterparties exactly as recorded." + _RULES,
        ("query_timeline", "search_comms"),
    ),
}


def build_subagents(tools: AgentTools, model: Any = None) -> list[dict[str, Any]]:
    specs = []
    for name, (description, prompt, tool_names) in _SPECS.items():
        spec: dict[str, Any] = {
            "name": name,
            "description": description,
            "system_prompt": prompt,
            "tools": tools.as_functions(tool_names),
        }
        if model is not None:
            spec["model"] = model
        specs.append(spec)
    return specs
