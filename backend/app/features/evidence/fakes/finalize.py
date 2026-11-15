"""Finalize the hand-made evidence fakes so they match data/evidence/FORMAT.md.

The story, baseline and extra fake events are written with id, CSV source.line and source.sha256 left as null.
This script fills them in deterministically:
  - CSV line numbers per file, in time order (header is line 1), shared by all three fake files
  - event IDs e1.. in (t, file, line) order over story + baseline, then extra events after them (append-only)
  - placeholder sha256 per file (the fake case files do not exist yet); security_log.csv gets a hash that
    differs from its manifest hash, which is the planted custody mismatch (C8)
  - evidence.json (one row per case file)
  - fake/answer_key.json line numbers, by matching each source quote to an event

Run from the repo root:  python backend/app/features/evidence/fakes/finalize.py
"""
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = ROOT / "data" / "evidence"
FAKE = EVIDENCE / "fake"

TAMPERED = "endpoint/security_log.csv"
EXTRA_FILES = {"access/parking_exit.csv"}  # withheld until the evidence request is approved
# Case files that exist in the folder but produce no events.
NO_EVENT_FILES = ["manifest.csv", "brief.pdf", "facilities/devices.csv"]
PARSERS = {".csv": "csv", ".txt": "text", ".mbox": "mbox", ".json": "slack_json", ".pdf": "pdf", ".jpg": "image"}


def fake_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def manifest_sha(file: str) -> str:
    return fake_sha(f"fake:{file}")


def received_sha(file: str) -> str:
    return fake_sha(f"fake:tampered:{file}") if file == TAMPERED else manifest_sha(file)


def load(name: str) -> list[dict]:
    path = FAKE / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def save(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def number_csv_lines(events: list[dict]) -> None:
    """Give every distinct quote in a CSV file a line number, ordered by the earliest event citing it."""
    by_file: dict[str, dict[str, str]] = {}
    for e in events:
        src = e["source"]
        if not src["file"].endswith(".csv"):
            continue
        first = by_file.setdefault(src["file"], {})
        if src["quote"] not in first or e["t"] < first[src["quote"]]:
            first[src["quote"]] = e["t"]
    line_of: dict[tuple[str, str], int] = {}
    for file, quotes in by_file.items():
        for i, quote in enumerate(sorted(quotes, key=lambda q: (quotes[q], q)), start=2):
            line_of[(file, quote)] = i
    for e in events:
        src = e["source"]
        if src["file"].endswith(".csv"):
            src["line"] = line_of[(src["file"], src["quote"])]


def order_key(e: dict) -> tuple:
    return (e["t"], e["source"]["file"], e["source"]["line"], e["type"])


def main() -> None:
    story, baseline, extra = load("events.json"), load("events_baseline.json"), load("events_extra.json")
    for e in story:
        e["_part"] = "story"
    for e in baseline:
        e["_part"] = "baseline"
    for e in extra:
        e["_part"] = "extra"
    everything = story + baseline + extra

    number_csv_lines(everything)
    for e in everything:
        e["person"] = None
        e["source"]["sha256"] = received_sha(e["source"]["file"])

    main_events = sorted(story + baseline, key=order_key)
    for i, e in enumerate(main_events, start=1):
        e["id"] = f"e{i}"
    for i, e in enumerate(sorted(extra, key=order_key), start=len(main_events) + 1):
        e["id"] = f"e{i}"

    for name, part in [("events.json", story), ("events_baseline.json", baseline), ("events_extra.json", extra)]:
        if not part:
            continue
        rows = sorted(part, key=order_key)
        for e in rows:
            del e["_part"]
        save(FAKE / name, rows)

    # evidence.json: one row per case file, records = events citing it (extra file left out until released)
    counts: dict[str, int] = {}
    for e in main_events:
        counts[e["source"]["file"]] = counts.get(e["source"]["file"], 0) + 1
    files = sorted(set(counts) | set(NO_EVENT_FILES))
    evidence = []
    for f in files:
        evidence.append({
            "file": f,
            "sha256": received_sha(f),
            "manifest_sha256": manifest_sha(f),
            "manifest_match": received_sha(f) == manifest_sha(f),
            "parser": PARSERS[Path(f).suffix],
            "records": counts.get(f, 0),
        })
    save(FAKE / "evidence.json", evidence)

    # answer_key.json: resolve source lines by quote
    key_path = FAKE / "answer_key.json"
    if key_path.exists():
        key = json.loads(key_path.read_text(encoding="utf-8"))
        line_of = {(e["source"]["file"], e["source"]["quote"]): e["source"]["line"] for e in everything}
        missing = []
        for c in key.get("planted", []):
            for s in c.get("sources", []):
                if s.get("quote") is None:
                    continue
                s["line"] = line_of.get((s["file"], s["quote"]))
                if s["line"] is None:
                    missing.append((c["id"], s["file"], s["quote"]))
        # tampered rows: 4 security_log lines chosen with the case seed, never Hank's 4624 logon row
        tamper = key.get("tamper", {})
        protected = {e["source"]["line"] for e in everything
                     if e["source"]["file"] == TAMPERED and e["type"] == "logon" and e["actor"]["value"] == "hgibson"
                     and e["t"].startswith("2026-03-04")}
        candidates = sorted({e["source"]["line"] for e in everything if e["source"]["file"] == TAMPERED} - protected)
        rng = random.Random(tamper.get("seed", 1010))
        tamper["altered_lines"] = sorted(rng.sample(candidates, min(4, len(candidates))))
        save(key_path, key)
        if missing:
            raise SystemExit(f"answer key quotes with no matching event: {missing}")

    print(f"story {len(story)}, baseline {len(baseline)}, extra {len(extra)}, evidence files {len(evidence)}")


if __name__ == "__main__":
    main()
