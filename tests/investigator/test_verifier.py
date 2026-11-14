from app.features.investigator import inputs
from app.features.investigator.verifier import verify_contradictions, verify_events


def ev(case, *a, **k):
    return inputs.Event.from_dict(case.event(*a, **k))


def run(case, events):
    ef = inputs.parse_list(case.evidence, inputs.EvidenceFile, "evidence")
    return verify_events(events, ef, inputs.CaseFiles(case.root))


BADGE = "access/badge_access.csv"
T219 = "2026-03-04T18:16:40-05:00"


def badge_in(case, **k):
    return ev(case, "e1", "badge_in", T219, BADGE, 3, actor={"kind": "badge", "value": "40420"}, **k)


def test_exact_quote_at_cited_line_is_verified(case):
    r = run(case, [badge_in(case)])
    assert r.verified_event_ids == ["e1"] and r.claims == 1 and r.verified == 1 and r.rejected == []


def test_quote_not_in_cited_line_is_rejected(case):
    e = badge_in(case)
    e.source.quote = "2026-03-04T18:20:00-05:00,40420,rdr-219,OUT,GRANTED"
    r = run(case, [e])
    assert r.verified_event_ids == [] and r.rejected[0].reason == "quote not found"


def test_cited_hash_that_does_not_match_the_file_is_rejected(case):
    e = badge_in(case)
    e.source.sha256 = "0" * 64
    assert run(case, [e]).rejected[0].reason == "sha256 does not match the cited file"


def test_missing_file_is_rejected(case):
    e = badge_in(case)
    e.source.file = "access/nope.csv"
    assert run(case, [e]).rejected[0].reason == "cited file not found"


def test_line_past_end_of_file_is_rejected(case):
    e = badge_in(case)
    e.source.line = 99
    assert run(case, [e]).rejected[0].reason == "cited line not in file"


def test_event_time_not_in_cited_csv_row_is_a_field_mismatch(case):
    e = badge_in(case)
    e.t = "2026-03-04T18:99:99-05:00"
    assert run(case, [e]).rejected[0].reason == "field mismatch in cited row"


def test_actor_not_in_cited_csv_row_is_a_field_mismatch(case):
    e = badge_in(case)
    e.actor = inputs.Actor("badge", "11111")
    assert run(case, [e]).rejected[0].reason == "field mismatch in cited row"


def test_whitespace_differences_are_ignored_in_the_quote(case):
    e = ev(case, "e2", "chat", "2026-03-04T17:30:00-05:00", "comms/slack_export/D0HANKKIM/2026-03-04.json", 5,
           quote="bring   what you can", actor={"kind": "slack", "value": "U1"})
    assert run(case, [e]).verified_event_ids == ["e2"]


def test_pdf_statement_line_verified_with_pdfplumber_numbering(case):
    e = ev(case, "e3", "statement", "2026-03-09T14:00:00-05:00", "statements/hank_gibson.pdf", 3,
           quote="I went straight home at six.", actor={"kind": "name", "value": "Hank Gibson"})
    r = run(case, [e])
    assert r.verified_event_ids == ["e3"], r.rejected


def test_pdf_wrong_line_is_rejected(case):
    e = ev(case, "e3", "statement", "2026-03-09T14:00:00-05:00", "statements/hank_gibson.pdf", 1,
           quote="I went straight home at six.", actor={"kind": "name", "value": "Hank Gibson"})
    assert run(case, [e]).rejected[0].reason == "quote not found"


def test_events_from_a_custody_failed_file_are_excluded_with_custody_reason(case):
    logon = ev(case, "e4", "logon", "2026-03-04T18:17:05-05:00", "endpoint/security_log.csv", 2,
               actor={"kind": "account", "value": "hgibson"})
    r = run(case, [logon])
    assert r.verified_event_ids == []
    assert r.rejected[0].reason == "custody: hash mismatch"
    assert "false" not in r.rejected[0].reason


def test_custody_failed_fact_is_reported_with_its_file_audit_corroboration(case):
    access = ev(case, "e5", "file_access", "2026-03-04T18:18:02-05:00", "endpoint/security_log.csv", 3,
                actor={"kind": "account", "value": "hgibson"}, device="lt-219",
                ) 
    access.attrs = {"path": "C:\Projects\Titan\thruster_v4.step", "host": "lt-219"}
    copy = ev(case, "e6", "file_copy", "2026-03-04T18:18:02-05:00", "endpoint/file_audit.csv", 2,
              actor={"kind": "account", "value": "hgibson"})
    copy.attrs = {"path": "C:\Projects\Titan\thruster_v4.step", "host": "lt-219"}
    r = run(case, [access, copy])
    assert r.verified_event_ids == ["e6"]
    assert r.corroborated_by["e5"] == ["e6"]
    assert "file_audit.csv" in r.rejected[0].reason


def test_counts_are_derived_from_results_not_hard_coded(case):
    good, bad = badge_in(case), badge_in(case)
    bad.id = "e9"
    bad.source.quote = "nope"
    r = run(case, [good, bad])
    assert (r.claims, r.verified, len(r.rejected)) == (2, 1, 1)


def test_to_json_matches_the_verification_schema(case):
    from app.shared.schema import Verification
    r = run(case, [badge_in(case)])
    Verification.model_validate(r.to_json())


def test_contradiction_needs_all_cited_events_verified(case):
    good, bad = badge_in(case), badge_in(case)
    bad.id = "e9"
    bad.source.quote = "nope"
    r = run(case, [good, bad])
    cs = [inputs.Contradiction("c1", "physical", ["e1"]), inputs.Contradiction("c2", "physical", ["e1", "e9"]),
          inputs.Contradiction("c3", "temporal", ["e404"])]
    r = verify_contradictions(cs, r)
    assert r.claims == 5 and r.verified == 2
    reasons = {x.claim.split(":")[0]: x.reason for x in r.rejected if x.claim.startswith("c")}
    assert reasons["c2"] == "cites event e9 that is not verified"
    assert reasons["c3"] == "cites unknown event e404"


def test_custody_contradiction_is_about_the_file_so_it_may_cite_the_unverified_event(case):
    logon = ev(case, "e4", "logon", "2026-03-04T18:17:05-05:00", "endpoint/security_log.csv", 2,
               actor={"kind": "account", "value": "hgibson"})
    r = verify_contradictions([inputs.Contradiction("c8", "custody", ["e4"])], run(case, [logon]))
    assert [x.claim for x in r.rejected if x.claim.startswith("c8")] == []
