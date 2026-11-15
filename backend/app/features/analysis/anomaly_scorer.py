"""Stage 6b: Isolation Forest over person-day features -> one 0..1 score per person.

A score says "this day is unusual for this floor", never "this person did it" (Arlequin: facts only).
Context columns (e.g. work-order coverage) are reported next to the score but not scored.
"""
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.features.analysis.anomaly_features import CONTEXT

SEED = 42
MIN_ROWS = 8  # below this a forest is meaningless; scores stay 0


def score(df: pd.DataFrame, extra: dict[str, dict[str, float]] | None = None) -> tuple[dict[str, float], dict[str, dict]]:
    """Returns (score per person, features of that person's most anomalous day).

    `extra` adds per-person constant features (e.g. centrality) to every row.
    """
    if df.empty:
        return {}, {}
    df = df.copy()
    for name, per_person in (extra or {}).items():
        df[name] = df["person"].map(per_person).fillna(0.0)
    X = df.drop(columns=["person", "day", *CONTEXT]).astype(float)

    if len(df) < MIN_ROWS:
        df["_score"] = 0.0
    else:
        forest = IsolationForest(n_estimators=300, contamination="auto", random_state=SEED)
        raw = -forest.fit(X).score_samples(X)  # higher = more anomalous
        lo, hi = raw.min(), raw.max()
        df["_score"] = (raw - lo) / (hi - lo) if hi > lo else 0.0

    worst = df.loc[df.groupby("person")["_score"].idxmax()]
    scores = {r["person"]: round(float(r["_score"]), 3) for _, r in worst.iterrows()}
    features = {
        r["person"]: {"day": str(r["day"]), **{k: round(float(v), 2) for k, v in r.items() if k not in ("person", "day", "_score")}}
        for _, r in worst.iterrows()
    }
    return scores, features
