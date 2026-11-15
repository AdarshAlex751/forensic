"""Build Case 1010F: raw case folder, withheld extra evidence, expected events and answer key.

Run from backend/:   python -m app.features.evidence.casegen.build
Outputs (all regenerated from scratch, byte-identical on every run):
  data/evidence/CASE-1010F/        the case folder (what the investigator drops in)
  data/evidence/CASE-1010F.zip     the same folder zipped, for the upload demo
  data/evidence/extra/             withheld evidence released on approval (parking exit log)
  data/evidence/truth/events_expected.json   every event the parsers should extract (FORMAT.md section 3)
  data/evidence/truth/answer_key.json        planted contradictions by file + line (FORMAT.md section 8)
"""
from __future__ import annotations

import hashlib
import json
import random
import shutil
import zipfile
from datetime import timedelta
from pathlib import Path

from . import comms, doc_writers, presence, sources, story
from .csv_writer import parse_row, row_text, write_csv
from .records import Record, Written
from .world import (CASE_DIR, COLLECTED_AT, EVIDENCE, EXTRA_DIR, F_AUDIT, F_BRIEF, F_DEVICES, F_MANIFEST, F_PARKING,
                    F_SEC, SEED_TAMPER, TAMPERED_FILE, TRUTH_DIR, at, parse_ts, ts)

ZIP_PATH = EVIDENCE / "CASE-1010F.zip"
PUBLISHED_KEY = EVIDENCE / "answer_key.json"   # CONTRACTS.md path read by the evaluator
REVOKED_AT = parse_ts("2026-03-02T17:00:00-05:00")  # Hank's 219 access revoked (CASE.md section 2)
ZIP_TIME = (2026, 3, 9, 17, 30, 0)

# Answer-key metadata per planted contradiction (CASE.md section 7).
PLANTED = {
    "C1": ("temporal", "rule", ["p_hank"]),
    "C2": ("physical", "physics", ["p_bg_17"]),
    "C3": ("statement", "nli+rule", ["p_hank"]),
    "C4": ("statement", "nli+rule", ["p_maggie"]),
    "C5": ("statement", "nli", ["p_hank"]),
    "C6": ("temporal", "rule", []),
    "C7": ("statement", "nli+rule", ["p_hank"]),
    "C8": ("custody", "custody", []),
}
FALSE_ALARM_PERSONS = ["p_frederik", "p_bg_17"]
N_TAMPERED_ROWS = 4


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reset(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _csv_sorted(records: list[Record]) -> list[Record]:
    return sorted(records, key=lambda r: (r.source, r.t, row_text(r.source, r.fields)))


def _doc_sorted(records: list[Record]) -> list[Record]:
    def key(r: Record):
        tie = r.fields.get("message_id") or r.fields.get("ts_str") or r.fields.get("serial") or ""
        return (r.source, r.t, str(tie))
    return sorted(records, key=key)


def _write_devices_copy(case_dir: Path) -> None:
    """Evidence copy of the device map, always LF so its hash is the same on every machine."""
    text = (EVIDENCE / "devices.csv").read_text(encoding="utf-8").replace("\r\n", "\n")
    out = case_dir / F_DEVICES
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(text.encode("utf-8"))


def _case_files(case_dir: Path) -> list[str]:
    return sorted(p.relative_to(case_dir).as_posix() for p in case_dir.rglob("*")
                  if p.is_file() and p.relative_to(case_dir).as_posix() != F_MANIFEST)


def _tamper(case_dir: Path, written: list[Written]) -> list[int]:
    """Shift the timestamp of a few seeded security_log rows (never Hank's 03-04 logon). Updates the Written
    entries of those rows so the expected events describe the file as received. Returns the altered lines."""
    path = case_dir / TAMPERED_FILE
    lines = path.read_text(encoding="utf-8").split("\n")
    protected = {w.line for w in written if w.record.source == F_SEC and w.event.type == "logon"
                 and w.event.actor["value"] == "hgibson" and w.event.t.date().isoformat() == "2026-03-04"}
    candidates = [i for i in range(2, len(lines)) if lines[i - 1] and i not in protected]
    rng = random.Random(SEED_TAMPER)
    altered = sorted(rng.sample(candidates, N_TAMPERED_ROWS))
    new_text = {}
    changes = []
    for ln in altered:
        original = lines[ln - 1]
        fields = parse_row(F_SEC, original)
        old_t = parse_ts(fields["TimeCreated"])
        shift = timedelta(minutes=rng.choice([-1, 1]) * rng.randint(37, 180), seconds=rng.randint(0, 59))
        fields["TimeCreated"] = ts(old_t + shift)
        lines[ln - 1] = row_text(F_SEC, fields)
        new_text[ln] = (lines[ln - 1], old_t + shift)
        changes.append({"line": ln, "original": original, "altered": lines[ln - 1]})
    path.write_bytes("\n".join(lines).encode("utf-8"))
    for w in written:
        if w.record.source == F_SEC and w.line in new_text:
            w.quote, new_t = new_text[w.line]
            w.event = type(w.event)(**{**w.event.__dict__, "t": new_t})
    return changes


def _custody(written: list[Written]):
    """Who collected each file and when, on 2026-03-09 (EST): laptop image first, then building logs, mail and
    Slack once the last message is in, the bank extract, and each statement right after its interview."""
    day = COLLECTED_AT.date()
    examiner, security = "R. Castell (forensic examiner)", "Alma Imhoff (Halvorsen security)"
    last_comms = max((w.record.t for w in written if w.record.source.startswith("comms/")), default=None)
    comms_at = max(at(day, 11, 40), (last_comms + timedelta(minutes=12)) if last_comms else at(day, 11, 40))
    doc_time = {w.record.source: w.record.fields["date"] for w in written
                if w.record.source.startswith("statements/") or w.record.source == F_BRIEF}

    def custody(name: str):
        if name.startswith("endpoint/"):
            return examiner, at(day, 8, 55)
        if name.startswith("comms/"):
            return examiner, comms_at
        if name.startswith("financial/"):
            return security, at(day, 12, 30)
        if name in doc_time:
            return security, doc_time[name] + timedelta(minutes=50)
        if name == F_BRIEF:
            return security, at(day, 17, 25)
        return security, at(day, 10, 20)  # access/, network/, cctv/, it/, facilities/
    return custody


def _event_dict(w: Written, sha: dict[str, str]) -> dict:
    e = w.event
    return {
        "id": None,
        "t": ts(e.t),
        "type": e.type,
        "person": None,
        "device": e.device,
        "room": e.room,
        "actor": e.actor,
        "attrs": {k: (ts(v) if hasattr(v, "isoformat") else v) for k, v in e.attrs.items()},
        "source": {"file": w.record.source, "line": w.line, "quote": w.quote, "sha256": sha[w.record.source]},
    }


def _zip(case_dir: Path) -> None:
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(p.relative_to(case_dir.parent).as_posix() for p in case_dir.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(rel, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, (case_dir.parent / rel).read_bytes())


def build(case_dir: Path = CASE_DIR, extra_dir: Path = EXTRA_DIR, truth_dir: Path = TRUTH_DIR) -> dict:
    for d in (case_dir, extra_dir, truth_dir):
        _reset(d)

    # 1. CSV sources: background presence + story rows + structured noise; parking goes to extra/
    noise = sources.all_records()
    main_csv = presence.records() + story.csv_records("story") + [r for r in noise if r.source != F_PARKING]
    extra_csv = story.csv_records("extra") + [r for r in noise if r.source == F_PARKING]
    written = write_csv(_csv_sorted(main_csv), case_dir)
    written_extra = write_csv(_csv_sorted(extra_csv), extra_dir)

    # 2. documents: USB history, email, Slack, statements, brief
    written += doc_writers.write_all(_doc_sorted(story.usb_records() + comms.all_records()), case_dir)
    _write_devices_copy(case_dir)

    # 3. chain of custody: hash everything as collected, then the post-collection edit of security_log.csv
    collected = {f: sha256_file(case_dir / f) for f in _case_files(case_dir)}
    changes = _tamper(case_dir, written)
    altered = [c["line"] for c in changes]
    custody = _custody(written)
    rows = []
    for name, digest in collected.items():
        who, when = custody(name)
        rows.append((name, digest, who, ts(when)))
    for value in (v for row in rows for v in row):
        if any(c in value for c in ',"\r\n'):
            raise ValueError(f"manifest value would break the CSV: {value!r}")
    with open(case_dir / F_MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        f.write("filename,sha256,collected_by,collected_at\n")
        for row in rows:
            f.write(",".join(row) + "\n")

    # 4. expected events: ids e1.. over the case in (t, file, line) order, extra numbered after them
    sha = {f: sha256_file(case_dir / f) for f in _case_files(case_dir)}
    sha.update({f: sha256_file(extra_dir / f) for f in _case_files(extra_dir)})
    events = sorted((_event_dict(w, sha) for w in written),
                    key=lambda e: (e["t"], e["source"]["file"], e["source"]["line"], e["type"]))
    extra_events = sorted((_event_dict(w, sha) for w in written_extra),
                          key=lambda e: (e["t"], e["source"]["file"], e["source"]["line"], e["type"]))
    for i, e in enumerate(events + extra_events, start=1):
        e["id"] = f"e{i}"

    # 5. answer key from the story tags the writers carried through
    planted = []
    for cid, (kind, detector, persons) in PLANTED.items():
        srcs = sorted({(w.record.source, w.line, w.quote) for w in written + written_extra if cid in w.event.tags})
        if cid == "C5":  # "never touched the Titan folder" is also refuted by his ordinary pre-resignation reads
            srcs = sorted(set(srcs) | {(w.record.source, w.line, w.quote) for w in written
                                       if w.record.source == F_AUDIT and w.event.actor == {"kind": "account",
                                                                                            "value": "hgibson"}
                                       and "\\Titan\\" in w.event.attrs.get("path", "") and w.event.t < REVOKED_AT})
        sources_ = [{"file": f, "line": ln, "quote": q} for f, ln, q in srcs]
        if cid == "C8":
            sources_ = [{"file": TAMPERED_FILE, "line": None, "quote": None}]
        if not sources_:
            raise RuntimeError(f"{cid} has no tagged sources")
        planted.append({"id": cid, "kind": kind, "detector": detector, "sources": sources_, "persons": persons})
    key = {"case_id": "1010F", "planted": planted, "false_alarm_persons": FALSE_ALARM_PERSONS,
           "tamper": {"file": TAMPERED_FILE, "seed": SEED_TAMPER, "altered_lines": altered, "changes": changes}}

    def dump(path: Path, data) -> None:
        path.write_bytes((json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))

    dump(truth_dir / "events_expected.json", events + extra_events)
    dump(truth_dir / "answer_key.json", key)
    if truth_dir == TRUTH_DIR:  # publish the evaluator's copy at the CONTRACTS.md path
        dump(PUBLISHED_KEY, key)
    _zip(case_dir)
    return {"case_files": len(collected) + 1, "events": len(events), "extra_events": len(extra_events),
            "tampered_lines": altered}


def main() -> None:
    from . import validate

    summary = build()
    print("built:", summary)
    problems = validate.validate()
    for p in problems:
        print("PROBLEM", p)
    print("VALID" if not problems else f"{len(problems)} problems")
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
