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
