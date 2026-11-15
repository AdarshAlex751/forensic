"""Context builder (feedback slice) on the real repo data."""
import builtins
import io
import json
from pathlib import Path

import pytest

from app.features.feedback import context, contract
from app.shared.config import DATA_DIR

BUNDLE_KEYS = {"case", "contradictions", "persons", "events", "untrusted_files", "notes", "budget"}
CONTRADICTION_KEYS = {"id", "kind", "rule", "title", "explanation", "score", "t", "room", "sides", "events"}
PERSON_KEYS = {"id", "name", "role", "anomaly", "anomaly_rank", "centrality", "community", "red_flags", "context", "links"}
EVENT_KEYS = {"t", "type", "person", "room", "quote"}   # compact view sent to the model (file/line live in bundle["sources"])
FORBIDDEN = ("data/investigator", "/truth/", "answer_key", "case.md", "casegen")


def _real(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def real_data(monkeypatch):
    for f in ("analysis/persons.json", "analysis/contradictions.json", "analysis/edges.json", "evidence/events.json"):
        if not (DATA_DIR / f).exists():
            pytest.skip(f"real data missing: {f}")
    monkeypatch.setenv("USE_REAL_ANALYSIS", "true")
    monkeypatch.setenv("USE_REAL_EVIDENCE", "true")


@pytest.fixture
def bundle():
    return context.build_bundle()


def _cited(b):
    ids = set()
    for c in b["contradictions"]:
        ids.update(c["events"])
        for s in c["sides"]:
            ids.update(s["events"])
    for p in b["persons"]:
        for item in p["red_flags"] + p["context"]:
            ids.update(item["events"])
    return ids


def test_shape_matches_contract(bundle):
    assert BUNDLE_KEYS <= set(bundle)
    assert set(bundle["case"]) >= {"id", "title"} and bundle["case"]["id"]
    for c in bundle["contradictions"]:
        assert CONTRADICTION_KEYS <= set(c)
        assert len(c["events"]) <= context.CONTRADICTION_EVENTS
        for s in c["sides"]:
            assert {"label", "events"} <= set(s) and "quotes" not in s   # quotes live in bundle["events"]
            assert all(e in bundle["events"] or e in bundle["budget"]["missing_events"] for e in s["events"])
    for p in bundle["persons"]:
        assert PERSON_KEYS <= set(p)
        assert {"devices", "rooms", "files", "accounts"} <= set(p["links"])
        for item in p["red_flags"] + p["context"]:
            assert {"text", "events"} <= set(item)
        for g in ("devices", "rooms", "files", "accounts", "others"):
            assert len(p["links"][g]) <= 10
    for e in bundle["events"].values():
        assert set(e) == EVENT_KEYS
    assert isinstance(bundle["untrusted_files"], list) and isinstance(bundle["notes"], list) and bundle["notes"]
    assert {"approx_tokens", "dropped"} <= set(bundle["budget"])
    assert {"persons", "events"} <= set(bundle["budget"]["dropped"])


def test_every_cited_event_is_in_bundle(bundle):
    missing = set(bundle["budget"]["missing_events"])
    for x in _cited(bundle):
        assert x in bundle["events"] or x in missing, x
    assert not missing & set(bundle["events"])
    allowed = context.allowed_ids(bundle)
    assert allowed["events"] == set(bundle["events"])


def test_all_contradictions_present(bundle):
    assert [c["id"] for c in bundle["contradictions"]] == [c["id"] for c in sorted(
        _real("analysis/contradictions.json"), key=lambda c: int(c["id"][1:]))]
    assert context.allowed_ids(bundle)["contradictions"] == {c["id"] for c in _real("analysis/contradictions.json")}


def test_persons_include_contradiction_persons_and_top_ranked(bundle):
    ids = {p["id"] for p in bundle["persons"]}
    for c in _real("analysis/contradictions.json"):
        assert set(c.get("persons") or []) <= ids, c["id"]
        if c.get("rule") != "custody_mismatch":
            assert {link["person"] for link in c.get("chain") or [] if link.get("person")} <= ids, c["id"]
    persons = _real("analysis/persons.json")
    top = sorted((p for p in persons if p.get("anomaly_rank")), key=lambda p: p["anomaly_rank"])[: context.TOP_RANKED]
    dropped = set(bundle["budget"]["dropped"].get("person_ids", []))
    assert {p["id"] for p in top} - dropped <= ids


def test_untrusted_files(bundle):
    expected = sorted(f["file"] for f in _real("evidence/evidence.json")
                      if f.get("manifest_sha256") and f.get("manifest_match") is False)
    assert bundle["untrusted_files"] == expected


def test_within_budget(bundle):
    assert bundle["budget"]["approx_tokens"] <= contract.MAX_BUNDLE_TOKENS
    sent = {k: v for k, v in bundle.items() if k not in ("sources", "budget")}   # what the model sees
    assert bundle["budget"]["approx_tokens"] == len(json.dumps(sent, separators=(",", ":"), ensure_ascii=False)) // 4
    assert set(bundle["sources"]) == set(bundle["events"])


def test_deterministic():
    a, b = context.build_bundle(), context.build_bundle()
    assert a == b
    assert json.dumps(a) == json.dumps(b)
    assert context.bundle_fingerprint(a) == context.bundle_fingerprint(b)
    assert len(context.bundle_fingerprint(a)) == 64


def test_never_opens_forbidden_paths(monkeypatch):
    opened: list[str] = []
    real_open, real_io_open = builtins.open, io.open
    real_read_text, real_path_open = Path.read_text, Path.open

    def rec(p):
        opened.append(str(p).replace("\\", "/").lower())

    def fake_open(file, *a, **k):
        rec(file)
        return real_open(file, *a, **k)

    def fake_io_open(file, *a, **k):
        rec(file)
        return real_io_open(file, *a, **k)

    def fake_read_text(self, *a, **k):
        rec(self)
        return real_read_text(self, *a, **k)

    def fake_path_open(self, *a, **k):
        rec(self)
        return real_path_open(self, *a, **k)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(io, "open", fake_io_open)
    monkeypatch.setattr(Path, "read_text", fake_read_text)
    monkeypatch.setattr(Path, "open", fake_path_open)
    context.build_bundle()
    assert any(p.endswith("data/evidence/events.json") for p in opened)
    assert any(p.endswith("data/analysis/contradictions.json") for p in opened)
    for p in opened:
        assert not any(bad in p for bad in FORBIDDEN), p


def test_tiny_budget_shrinks_without_dropping_contradictions():
    full = context.build_bundle(max_tokens=10**9)   # unshrunk, to compare against
    tiny = context.build_bundle(max_tokens=1000)
    assert [c["id"] for c in tiny["contradictions"]] == [c["id"] for c in full["contradictions"]]
    assert tiny["budget"]["approx_tokens"] < full["budget"]["approx_tokens"]
    assert tiny["budget"]["dropped"]["steps"]
    ids = {p["id"] for p in tiny["persons"]}
    for c in tiny["contradictions"]:
        if c["rule"] != "custody_mismatch":
            assert set(c["persons"]) <= ids
    for x in _cited(tiny):
        assert x in tiny["events"] or x in tiny["budget"]["missing_events"]
    assert context.build_bundle(max_tokens=1000) == tiny
