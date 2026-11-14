from app.features.investigator.approvals import Approvals


def test_mark_ingested_moves_every_approved_request_to_ingested():
    a = Approvals()
    a.add_request("Ask one", "y")
    a.add_request("Ask two", "y")
    a.approve("r1")
    a.mark_ingested()
    assert [r["status"] for r in a.requests] == ["ingested", "pending"]
    assert a.overlay([{"id": "r1", "ask": "x", "why": "y", "status": "pending"}])[0]["status"] == "ingested"
