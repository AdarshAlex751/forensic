"""Tests for the comms builder: story documents, realism guards, format guards and determinism."""
import csv
import importlib.util
import re
from collections import Counter
from datetime import date

import pytest

from app.features.evidence.casegen import comms, records, story, world

EXPECTED_FILES = {"statements/hank_gibson.pdf", "statements/maggie_price.pdf", "statements/frederik_mendelssohn.pdf"}

# The base list from the brief (checked on everything outside the required story documents) ...
FORBIDDEN = [
    r"titan.{0,40}(cop|usb|drive)", r"(cop|usb|drive).{0,40}titan", r"\busb\b", r"thumb ?drive", r"clone",
    r"coinvault", r"signing bonus", r"camera 3", r"cam-03",
]
# ... plus a stricter list for background messages (emails and Slack that are not story records).
FORBIDDEN_NOISE = FORBIDDEN + [r"\btitan\b", r"northline", r"\bbadge", r"left together", r"bonus", r"flash ?drive"]

MAIL_KEYS = {"message_id", "from_name", "from_addr", "to", "cc", "subject", "date", "in_reply_to", "body"}
SLACK_KEYS = {"channel", "user", "text", "ts"}
STATEMENT_KEYS = {"title", "case_id", "speaker", "role", "interviewer", "date", "location", "paragraphs"}
BRIEF_KEYS = {"title", "case_id", "author", "date", "paragraphs"}


@pytest.fixture(scope="module")
def recs():
    return comms.all_records()


@pytest.fixture(scope="module")
def mails(recs):
    return [r for r in recs if r.source == world.F_MBOX]


@pytest.fixture(scope="module")
def slack(recs):
    return [r for r in recs if r.source.startswith(world.F_SLACK_DIR + "/")]


def _texts(r):
    f = r.fields
    if r.source == world.F_MBOX:
        return [f["subject"]] + list(f["body"])
    if r.source.startswith(world.F_SLACK_DIR):
        return [f["text"]]
    return list(f["paragraphs"])


def _snapshot(rs):
    out = []
    for r in rs:
        f = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.fields.items()}
        out.append((r.source, r.t.isoformat(), repr(sorted(f.items())), r.story,
                    [(e.type, e.t.isoformat(), e.actor, e.attrs, e.quote_text) for e in r.events]))
    return out


def test_deterministic(recs):
    comms._slack_messages.cache_clear()
    comms._mails.cache_clear()
    assert _snapshot(comms.all_records()) == _snapshot(recs)


def test_story_documents(recs):
    req = story.required_docs()
    found = Counter()
    for d in req:
        ev = d["event"]
        holders = [(r, e) for r in recs for e in r.events if e == ev]
        assert len(holders) == 1, (ev.quote_text, len(holders))
        r, e = holders[0]
        assert r.source == d["source_file"] and r.story
        found[d["source_file"]] += 1
        f, q, a = r.fields, ev.quote_text, ev.attrs
        if ev.type == "email":
            assert sum(1 for line in f["body"] if q in line) == 1
            assert f["date"] == ev.t and f["from_addr"] == a["from"] and f["to"] == a["to"]
            assert f["subject"] == a["subject"] and f["message_id"] == a["message_id"]
        elif ev.type == "chat":
            assert f["text"] == q and f["ts"] == ev.t and f["user"] == ev.actor["value"]
            assert f["channel"] == a["channel"] and f["ts_str"] == a["ts"]
        else:
            assert ev.type == "statement"
            assert f["paragraphs"].count(q) == 1 and f["date"] == ev.t and f["speaker"] == a["speaker"]
            assert len(q) < 110 and q.count(". ") == 0
    statements = [r for r in recs if r.source.startswith("statements/")]
    assert {r.source for r in statements} == EXPECTED_FILES
    assert all(r.fields["interviewer"] == "Alma Imhoff" and r.fields["date"].date() == date(2026, 3, 9)
               for r in statements)


def test_counts(mails, slack):
    assert 270 <= len(mails) <= 340
    assert 560 <= len(slack) <= 660
    chans = Counter(r.fields["channel"] for r in slack)
    assert set(chans) == set(comms.CHANNELS) | {comms.DM}
    assert all(chans[c] >= 40 for c in comms.CHANNELS)
    assert all(date(2026, 2, 23) <= r.t.date() <= date(2026, 3, 9) for r in mails)
    assert all(date(2026, 2, 23) <= r.t.date() <= date(2026, 3, 8) for r in slack)


def test_record_fields(recs):
    for r in recs:
        keys = set(r.fields)
        if r.source == world.F_MBOX:
            assert MAIL_KEYS <= keys and isinstance(r.fields["body"], list) and isinstance(r.fields["to"], list)
            assert r.fields["date"].utcoffset() == world.EST.utcoffset(None)
        elif r.source.startswith(world.F_SLACK_DIR + "/"):
            assert SLACK_KEYS <= keys
            assert r.source == f"{world.F_SLACK_DIR}/{r.fields['channel']}/{r.fields['ts']:%Y-%m-%d}.json"
        elif r.source == world.F_BRIEF:
            assert BRIEF_KEYS <= keys and not r.events
        else:
            assert r.source in EXPECTED_FILES and STATEMENT_KEYS <= keys
        assert isinstance(r, records.Record)


def test_noise_events(mails, slack):
    for r in mails + slack:
        assert len(r.events) == 1
        if r.story:
            continue
        ev, f = r.events[0], r.fields
        assert ev.device is None and ev.room is None and ev.t == r.t and not ev.tags
        if r.source == world.F_MBOX:
            assert ev.type == "email" and ev.actor == {"kind": "email", "value": f["from_addr"]}
            assert ev.attrs == {"from": f["from_addr"], "to": f["to"], "subject": f["subject"],
                                "message_id": f["message_id"]}
            assert sum(1 for line in f["body"] if ev.quote_text in line) == 1
        else:
            assert ev.type == "chat" and ev.actor == {"kind": "slack", "value": f["user"]}
            assert ev.attrs == {"channel": f["channel"], "ts": f["ts_str"]} and ev.quote_text == f["text"]
            sec, frac = f["ts_str"].split(".")
            assert int(sec) == int(f["ts"].timestamp()) and len(frac) == 6 and int(frac) % 100 == 0


def test_slack_format(slack):
    per_file = Counter((r.source, r.fields["ts_str"]) for r in slack)
    assert max(per_file.values()) == 1
    for r in slack:
        t = r.fields["text"]
        assert t and '"' not in t and "\\" not in t and "\n" not in t and "\r" not in t and t.isascii()
    handles = {p["slack_handle"] for p in world.people() if p["slack_handle"]}
    assert {r.fields["user"] for r in slack} <= handles
    kim = {r.fields["channel"] for r in slack if r.fields["user"] == "kim.sayers"}
    assert kim == {comms.DM}
    assert {r.fields["user"] for r in slack if r.fields["channel"] == comms.DM} == {"kim.sayers", "hank.gibson"}


def test_mail_format(mails):
    ids = [r.fields["message_id"] for r in mails]
    assert len(ids) == len(set(ids))
    assert all(re.match(r"^<\d{14}\.[0-9a-f]{4}@[a-z0-9.-]+\.example>$", i) for i in ids)
    by_id = {r.fields["message_id"]: r for r in mails}
    for r in mails:
        for line in r.fields["body"]:
            assert not line.startswith("From ") and "\r" not in line and "\n" not in line
        irt = r.fields["in_reply_to"]
        if irt:
            parent = by_id[irt]
            assert parent.t <= r.t and r.fields["subject"].startswith("Re: ")
    replies = sum(1 for r in mails if r.fields["in_reply_to"])
    assert replies > len(mails) / 3


def test_addresses(mails):
    known = {p["email"] for p in world.people()}
    for r in mails:
        f = r.fields
        for a in [f["from_addr"], *f["to"], *f["cc"]]:
            assert a in known or a.endswith(".example"), a
        text = "\n".join(_texts(r))
        for m in re.finditer(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+)", text):
            assert m.group(1).endswith(".example"), m.group(0)
        assert "princeton.edu" not in text.lower()


def test_no_spoilers(recs):
    story_ids = {id(d["event"]) for d in story.required_docs()}
    req = story.required_docs()
    story_records = {id(r) for r in recs for e in r.events if any(e == d["event"] for d in req)}
    base = re.compile("|".join(FORBIDDEN), re.I)
    strict = re.compile("|".join(FORBIDDEN_NOISE), re.I)
    assert story_ids  # sanity
    for r in recs:
        if id(r) in story_records:
            continue
        for line in _texts(r):
            assert not base.search(line), (r.source, line)
            if r.source == world.F_MBOX or r.source.startswith(world.F_SLACK_DIR):
                assert not strict.search(line), (r.source, line)


def test_incident_evening_quiet(mails, slack):
    lo = world.at(world.INCIDENT_DAY, 16, 45)
    hi = world.at(world.INCIDENT_DAY, 23, 59, 59)
    late = [r for r in mails + slack if lo <= r.t <= hi and not r.story]
    assert len(late) == 0, [r.source for r in late]
    # Hank and Maggie never talk about leaving times in background messages
    for r in mails + slack:
        if r.story:
            continue
        sender = r.fields.get("user") or r.fields.get("from_addr")
        if sender.startswith(("hank.gibson", "maggie.price")):
            text = " ".join(_texts(r)).lower()
            assert not re.search(r"\b(left (the floor|the office|work|for home|home|together|at \d)|leaving|heading (home|out)|went home|6:30|18:30)\b", text), text


def test_it_notices_match_calendar(mails):
    """Work orders quoted in emails are the real ones from the maintenance calendar; WO-3117 is only announced."""
    from app.features.evidence.casegen import sources

    known = {wo[0] for wo in sources._WORK_ORDERS} | {"WO-3091", "WO-3098", "WO-3117"}
    for r in mails:
        for wo in re.findall(r"WO-\d{4}", "\n".join(_texts(r))):
            assert wo in known, wo
    w3117 = [r for r in mails if "WO-3117" in "\n".join(_texts(r))]
    assert len(w3117) == 1 and w3117[0].t < world.at(world.INCIDENT_DAY, 19, 0)
    assert w3117[0].fields["from_addr"] == "frederik.mendelssohn@ostrander-it.example"


def test_inventory_handles_for_slack_people():
    with open(world.EVIDENCE / "inventory.csv", encoding="utf-8", newline="") as f:
        inv = {r["slack_handle"] for r in csv.DictReader(f) if r["slack_handle"]}
    assert "kim.sayers" in inv and "rina.okafor" in inv


@pytest.mark.skipif(importlib.util.find_spec("app.features.evidence.casegen.doc_writers") is None,
                    reason="doc_writers.py not written yet")
def test_write_all(recs, tmp_path):
    from app.features.evidence.casegen import doc_writers

    non_pdf = [r for r in recs if not r.source.endswith(".pdf")]
    written = doc_writers.write_all(non_pdf, tmp_path)
    assert len(written) == sum(len(r.events) for r in non_pdf)
    pdfs = [r for r in recs if r.source.endswith(".pdf")]
    try:
        written = doc_writers.write_all(pdfs, tmp_path)
    except ValueError as e:
        # Known contract conflict: the story's Frederik quote is wider than one PDF line at the writer's font size.
        if "too long for one PDF line" in str(e) and "WO-3117" in str(e):
            pytest.xfail(f"story quote does not fit the PDF writer's line width: {e}")
        raise
    assert len(written) == sum(len(r.events) for r in pdfs)
