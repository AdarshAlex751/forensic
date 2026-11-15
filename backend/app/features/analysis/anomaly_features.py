"""Stage 6a: per person per day behaviour features (local EST days).

PLAN.md stage 6: after-hours badge minutes, distinct rooms, files touched, bytes copied, USB mounts,
deviation from the person's own baseline, graph centrality (added by the scorer).
"""
from collections import defaultdict

import pandas as pd

from app.features.analysis import timeutil, vocab

FEATURES = [
    "after_hours_minutes",
    "after_hours_badge_reads",
    "distinct_rooms",
    "files_touched",
    "bytes_copied",
    "usb_mounts",
]
# Reported next to the score but never fed to the forest: facts that explain a score, not behaviour.
CONTEXT = ["after_hours_in_work_order_minutes"]

# Presence on the floor: anything a person's badge, laptop or account did (not what they said or were paid).
PRESENCE = vocab.BADGE | vocab.WIFI | vocab.LOGON | vocab.LOGOFF | vocab.FILE_ACCESS | vocab.USB


def _work_orders(events: list[dict]) -> dict[str, list[tuple]]:
    """person -> [(start, end)] of maintenance windows assigned to them."""
    out = defaultdict(list)
    for e in events:
        a = e.get("attrs") or {}
        if e.get("type") in vocab.MAINTENANCE and e.get("person") and a.get("start") and a.get("end"):
            out[e["person"]].append((timeutil.parse(a["start"]), timeutil.parse(a["end"])))
    return out


def _after_hours_span(times: list) -> float:
    after = sorted(t for t in times if timeutil.is_after_hours(t))
    return (after[-1] - after[0]).total_seconds() / 60 if len(after) > 1 else 0.0


def daily_features(events: list[dict]) -> pd.DataFrame:
    """One row per (person, day). Columns: person, day, *FEATURES, *CONTEXT."""
    orders = _work_orders(events)
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for e in events:
        if e.get("person") and e.get("t") and e.get("type") in PRESENCE:
            dt = timeutil.parse(e["t"])
            buckets[(e["person"], timeutil.local_day(dt))].append({**e, "_dt": dt})

    rows = []
    for (person, day), evs in buckets.items():
        times = [x["_dt"] for x in evs]
        covered = [t for t in times if any(s <= t <= end for s, end in orders.get(person, []))]
        rows.append({
            "person": person,
            "day": day,
            "after_hours_minutes": _after_hours_span(times),
            "after_hours_badge_reads": sum(x["type"] in vocab.BADGE and timeutil.is_after_hours(x["_dt"]) for x in evs),
            "distinct_rooms": len({x["room"] for x in evs if x.get("room")}),
            "files_touched": len({(x.get("attrs") or {}).get("path") for x in evs if x["type"] in vocab.FILE_ACCESS} - {None}),
            "bytes_copied": float(sum((x.get("attrs") or {}).get("bytes") or 0 for x in evs if x["type"] in vocab.FILE_COPY)),
            "usb_mounts": sum(x["type"] in vocab.USB for x in evs),
            "after_hours_in_work_order_minutes": _after_hours_span(covered),
        })
    return pd.DataFrame(rows, columns=["person", "day", *FEATURES, *CONTEXT])


def add_baseline_deviation(df: pd.DataFrame) -> pd.DataFrame:
    """Add <feature>_dev = value minus that person's median over their *other* days.

    Uses all other days (not only earlier ones) so the first days of the case window still have a baseline.
    """
    if df.empty:
        return df
    df = df.copy()
    for f in FEATURES:
        def leave_one_out(s: pd.Series) -> pd.Series:
            return pd.Series([s.drop(i).median() if len(s) > 1 else s[i] for i in s.index], index=s.index)
        df[f"{f}_dev"] = df[f] - df.groupby("person", group_keys=False)[f].apply(leave_one_out)
    return df
