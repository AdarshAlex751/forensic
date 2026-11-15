from app.features.investigator.approvals import Approvals


def test_mark_ingested_moves_every_approved_request_to_ingested():
    a = Approvals()
    a.add_request("Ask one", "y")
    a.add_request("Ask two", "y")
    a.approve("r1")
    a.mark_ingested()
    assert [r["status"] for r in a.requests] == ["ingested", "pending"]
    assert a.overlay([{"id": "r1", "ask": "x", "why": "y", "status": "pending"}])[0]["status"] == "ingested"


def test_revoke_returns_an_approved_request_to_pending():
    a = Approvals()
    a.add_request("Ask one", "y")
    a.approve("r1")
    a.revoke("r1")
    assert a.requests[0]["status"] == "pending" and not a.any_approved()


def test_revoke_never_downgrades_an_ingested_request():
    a = Approvals()
    a.add_request("Ask one", "y")
    a.approve("r1")
    a.mark_ingested()
    a.revoke("r1")
    assert a.requests[0]["status"] == "ingested"


def test_reset_pending_keeps_the_humans_decisions_and_drops_leftover_pending_requests():
    a = Approvals()
    a.add_request("Leftover from a fake file", "y")  # r1, never approved
    a.add_request("Pull the parking log", "y")  # r2
    a.approve("r2")
    a.add_request("Another pending one", "y")  # r3
    a.reset_pending()
    assert [(r["id"], r["status"]) for r in a.requests] == [("r2", "approved")]
    assert a.add_request("Brand new ask", "y")["id"] == "r3"  # ids keep counting from what is left
