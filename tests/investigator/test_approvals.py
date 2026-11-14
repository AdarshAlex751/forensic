from app.features.investigator.approvals import Approvals


def test_register_keeps_the_first_status_and_overlay_applies_approval():
    a = Approvals()
    a.add_request("Ask for the parking log", "why")
    assert a.overlay([{"id": "r1", "ask": "x", "why": "y", "status": "pending"}])[0]["status"] == "pending"
    assert a.approve("r1") == "approved"
    assert a.overlay([{"id": "r1", "ask": "x", "why": "y", "status": "pending"}])[0]["status"] == "approved"
    assert a.approved_ids() == ["r1"] and a.any_approved()


def test_approve_unknown_request_returns_none():
    assert Approvals().approve("r404") is None


def test_approving_a_request_known_only_from_the_findings_file_works():
    a = Approvals()
    a.sync([{"id": "r1", "ask": "x", "why": "y", "status": "pending"}])
    assert a.approve("r1") == "approved"


def test_ingested_requests_are_never_downgraded_by_the_overlay():
    a = Approvals()
    a.sync([{"id": "r1", "ask": "x", "why": "y", "status": "ingested"}])
    a.approve("r1")
    assert a.overlay([{"id": "r1", "ask": "x", "why": "y", "status": "ingested"}])[0]["status"] == "ingested"
