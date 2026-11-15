import pytest
from app.features.investigator import inputs


def test_event_from_dict_keeps_known_fields_and_ignores_unknown():
    e = inputs.Event.from_dict({
        "id": "e1", "t": "2026-03-04T18:16:40-05:00", "type": "badge_in", "mystery": 1,
        "actor": {"kind": "badge", "value": "40420"}, "attrs": {"reader": "rdr-219"},
        "source": {"file": "a.csv", "line": 2, "quote": "q", "sha256": "ab"},
    })
    assert e.id == "e1" and e.actor == inputs.Actor("badge", "40420")
    assert e.person is None and e.device is None and e.source.line == 2


def test_event_missing_optionals_gets_defaults():
    e = inputs.Event.from_dict({"id": "e1", "t": "t", "type": "x", "source": {"file": "f", "line": 1, "quote": "q", "sha256": "s"}})
    assert e.actor is None and e.attrs == {} and e.room is None


def test_event_without_source_is_rejected_with_value_error():
    import pytest
    with pytest.raises(ValueError):
        inputs.Event.from_dict({"id": "e1", "t": "t", "type": "x"})


def test_parse_list_skips_bad_records_and_logs(caplog):
    good = {"id": "e1", "t": "t", "type": "x", "source": {"file": "f", "line": 1, "quote": "q", "sha256": "s"}}
    with caplog.at_level("WARNING"):
        out = inputs.parse_list([good, {"id": "e2"}, "junk", good | {"id": "e3"}], inputs.Event, "events")
    assert [e.id for e in out] == ["e1", "e3"]
    assert "skipping" in caplog.text


def test_load_inputs_reads_fakes_and_never_raises_on_missing_file(monkeypatch):
    def fake_load(slice_name, filename):
        if filename == "events.json":
            return [{"id": "e1", "t": "t", "type": "x", "source": {"file": "f", "line": 1, "quote": "q", "sha256": "s"}}]
        raise FileNotFoundError(filename)

    monkeypatch.setattr(inputs, "_merge_load", fake_load)
    snap = inputs.load_inputs()
    assert [e.id for e in snap.events] == ["e1"]
    assert snap.persons == [] and snap.contradictions == []


def test_extra_events_only_when_released(monkeypatch):
    src = {"file": "f", "line": 1, "quote": "q", "sha256": "s"}

    def fake_load(slice_name, filename):
        if filename == "events.json":
            return [{"id": "e1", "t": "t", "type": "x", "source": src}]
        if filename == "events_extra.json":
            return [{"id": "e9", "t": "t", "type": "parking_exit", "source": src}]
        raise FileNotFoundError(filename)

    monkeypatch.setattr(inputs, "_merge_load", fake_load)
    monkeypatch.setattr(inputs, "_real_evidence", lambda: False)
    assert [e.id for e in inputs.load_inputs().events] == ["e1"]
    assert [e.id for e in inputs.load_inputs(include_extra=True).events] == ["e1", "e9"]


def test_case_files_reads_bytes_and_blocks_path_escape(case):
    files = inputs.CaseFiles(case.root)
    assert files.read_bytes("access/badge_access.csv").startswith(b"timestamp")
    assert files.read_bytes("nope.csv") is None
    (case.root.parent / "outside.txt").write_text("secret")
    assert files.read_bytes("../outside.txt") is None
    assert files.read_bytes("access/../../outside.txt") is None
    assert files.read_bytes("/etc/passwd") is None


def test_released_extra_evidence_is_read_from_the_sibling_extra_folder(case):
    extra = case.root.parent / "extra" / "access"
    extra.mkdir(parents=True)
    (extra / "parking_exit.csv").write_bytes(b"timestamp,plate\n2026-03-04T18:20:00-05:00,TX1\n")
    files = inputs.CaseFiles(case.root)
    assert files.read_bytes("access/parking_exit.csv").startswith(b"timestamp,plate")
    assert files.read_bytes("extra/access/parking_exit.csv").startswith(b"timestamp,plate")
    assert files.read_bytes("../extra/../outside.txt") is None


def test_case_folder_file_wins_over_the_extra_folder(case):
    extra = case.root.parent / "extra" / "access"
    extra.mkdir(parents=True)
    (extra / "badge_access.csv").write_bytes(b"decoy")
    assert inputs.CaseFiles(case.root).read_bytes("access/badge_access.csv").startswith(b"timestamp")


@pytest.fixture()
def tmp_path():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="inv-ev-") as d:
        yield Path(d)


def _fake_evidence_dir(tmp_path, monkeypatch, uploaded: bool):
    ev = tmp_path / "evidence"
    (ev / "CASE-1010F").mkdir(parents=True)
    (ev / "CASE-1010F" / "marker.txt").write_text("builtin")
    (ev / "work" / "extra" / "access").mkdir(parents=True)  # where an uploaded extra file is saved
    (ev / "work" / "extra" / "access" / "parking_exit.csv").write_text("parking")
    if uploaded:
        (ev / "work" / "CASE-1010F").mkdir(parents=True)
        (ev / "work" / "CASE-1010F" / "manifest.csv").write_text("filename,sha256\n")
        (ev / "work" / "CASE-1010F" / "marker.txt").write_text("uploaded")
    monkeypatch.setattr(inputs, "DATA_DIR", tmp_path)
    return ev


def test_default_case_folder_is_the_builtin_one(tmp_path, monkeypatch):
    _fake_evidence_dir(tmp_path, monkeypatch, uploaded=False)
    assert inputs.CaseFiles().read_bytes("marker.txt") == b"builtin"


def test_an_uploaded_case_replaces_the_builtin_one_like_in_the_evidence_slice(tmp_path, monkeypatch):
    _fake_evidence_dir(tmp_path, monkeypatch, uploaded=True)
    assert inputs.CaseFiles().read_bytes("marker.txt") == b"uploaded"


def test_released_extra_files_are_found_even_when_an_uploaded_case_is_active(tmp_path, monkeypatch):
    _fake_evidence_dir(tmp_path, monkeypatch, uploaded=True)
    assert inputs.CaseFiles().read_bytes("access/parking_exit.csv") == b"parking"


def test_real_evidence_mode_never_loads_the_separate_baseline_or_extra_files(monkeypatch):
    """Real events.json already holds the baseline and any released events; the separate files are fake-mode only."""
    asked = []

    def fake_load(slice_name, filename):
        asked.append(filename)
        if filename == "events.json":
            return []
        raise FileNotFoundError(filename)

    monkeypatch.setattr(inputs, "_merge_load", fake_load)
    monkeypatch.setattr(inputs, "_real_evidence", lambda: True)
    inputs.load_inputs(include_extra=True)
    assert "events_baseline.json" not in asked and "events_extra.json" not in asked


def test_fake_evidence_mode_still_merges_baseline_and_released_extra(monkeypatch):
    asked = []
    monkeypatch.setattr(inputs, "_merge_load", lambda s, f: asked.append(f) or [])
    monkeypatch.setattr(inputs, "_real_evidence", lambda: False)
    inputs.load_inputs(include_extra=True)
    assert "events_baseline.json" in asked and "events_extra.json" in asked


def test_withheld_sources_lists_names_only_and_tolerates_a_missing_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(inputs, "DATA_DIR", tmp_path)
    assert inputs.withheld_sources() == []  # no extra/ folder at all
    (tmp_path / "evidence" / "extra" / "access").mkdir(parents=True)
    (tmp_path / "evidence" / "extra" / "access" / "parking_exit.csv").write_text("secret contents")
    (tmp_path / "evidence" / "extra" / "notes.txt").write_text("x")
    assert inputs.withheld_sources() == ["access/parking_exit.csv", "notes.txt"]
