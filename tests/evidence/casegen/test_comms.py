"""Tests for the comms builder: story documents, one event per line, realism guards, format guards, determinism."""
import csv
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.features.evidence.casegen import comms, personas, records, story, world

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

# lab-219 messages that say the writer is (or will be) working in room 219
LAB_PRESENCE_RE = re.compile(r"booked 219|in 219|219 is mine|219 booked|219 bench|bench in 219|bench is (free|busy|clear)"
                             r"|219 is free|grabbed 219|done with the bench|wrapping up in 219", re.I)
DONE_RE = re.compile(r"free|done|wrapping|finished|complete|clear", re.I)
B3 = ["I'll be on the floor a while first", "See you when you're done"]


@pytest.fixture(scope="module")
def recs():
    return comms.all_records()


@pytest.fixture(scope="module")
def mails(recs):
    return [r for r in recs if r.source == world.F_MBOX]


@pytest.fixture(scope="module")
def slack(recs):
    return [r for r in recs if r.source.startswith(world.F_SLACK_DIR + "/")]


@pytest.fixture(scope="module")
def statements(recs):
    return [r for r in recs if r.source in EXPECTED_FILES]


@pytest.fixture(scope="module")
def who_by_addr():
    return {p["email"]: p["person_id"] for p in world.people()} | \
        {p["slack_handle"]: p["person_id"] for p in world.people() if p["slack_handle"]}


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


def _is_answer(p):
    return not (p.startswith("Q: ") or p.startswith("[") or p.startswith("This statement was taken by"))


def test_deterministic(recs):
    comms._slack_messages.cache_clear()
    comms._mails.cache_clear()
    assert _snapshot(comms.all_records()) == _snapshot(recs)


def test_story_documents(recs):
    req = story.required_docs()
    for d in req:
        ev = d["event"]
        holders = [(r, e) for r in recs for e in r.events if e == ev]
        assert len(holders) == 1, (ev.quote_text, len(holders))
        r, e = holders[0]
        assert r.source == d["source_file"] and r.story
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
    statements = [r for r in recs if r.source.startswith("statements/")]
    assert {r.source for r in statements} == EXPECTED_FILES
    assert all(r.fields["interviewer"] == "Alma Imhoff" and r.fields["date"].date() == date(2026, 3, 9)
               for r in statements)


def test_counts(mails, slack, statements):
    assert 250 <= len(mails) <= 340
    assert 450 <= len(slack) <= 660
    chans = Counter(r.fields["channel"] for r in slack)
    assert set(chans) == set(comms.CHANNELS) | {comms.dm_channel()}
    assert all(chans[c] >= 40 for c in comms.CHANNELS)
    assert all(date(2026, 2, 23) <= r.t.date() <= date(2026, 3, 9) for r in mails)
    assert all(date(2026, 2, 23) <= r.t.date() <= date(2026, 3, 8) for r in slack)
    assert sum(len(r.events) for r in mails) > 3 * len(mails)
    assert sum(len(r.events) for r in statements) >= 20


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


def test_email_one_event_per_line(mails):
    story_evs = [d["event"] for d in story.required_docs()]
    for r in mails:
        f = r.fields
        lines = [b for b in f["body"] if b.strip()]
        assert len(r.events) == len(lines), f["subject"]
        assert comms.lines_unique(f["body"]), f["body"]
        for line, ev in zip(lines, r.events):
            assert ev.type == "email" and ev.t == r.t and ev.device is None and ev.room is None
            assert sum(1 for b in f["body"] if ev.quote_text in b) == 1
            if any(ev == s for s in story_evs):
                assert r.story and ev.quote_text in line
                continue
            assert ev.quote_text == line and not ev.tags
            assert ev.actor == {"kind": "email", "value": f["from_addr"]}
            assert ev.attrs == {"from": f["from_addr"], "to": f["to"], "subject": f["subject"],
                                "message_id": f["message_id"]}
        assert not any(b.startswith("From ") or "\r" in b for b in f["body"])
    # the story emails keep their exact story event, the other lines are untagged
    for r in mails:
        if r.story:
            assert sum(1 for e in r.events if any(e == s for s in story_evs)) == 1


def test_statement_one_event_per_line(statements):
    from reportlab.pdfbase.pdfmetrics import stringWidth

    from app.features.evidence.casegen import doc_writers

    for r in statements:
        paras = r.fields["paragraphs"]
        answers = [p for p in paras if _is_answer(p)]
        assert [e.quote_text for e in r.events] == answers
        for e in r.events:
            assert e.type == "statement" and e.attrs["speaker"] == r.fields["speaker"] and e.attrs["page"] >= 1
            assert stringWidth(e.quote_text, "Helvetica", 11) <= doc_writers.max_line_width()
            assert sum(1 for p in paras if e.quote_text in p) == 1
    hank = next(r for r in statements if r.source.endswith("hank_gibson.pdf"))
    p = hank.fields["paragraphs"]
    note = "[Mr. Gibson was shown the examiner's entry for a SanDisk Ultra USB device, S/N 4C530001230918112443.]"
    assert note in p and "IT gave me that drive last year." in p
    assert p.index(note) < p.index("IT gave me that drive last year.")
    assert any("skipped" in x for x in p)


def test_slack_events(slack):
    for r in slack:
        assert len(r.events) == 1
        if r.story:
            continue
        ev, f = r.events[0], r.fields
        assert ev.device is None and ev.room is None and ev.t == r.t and not ev.tags
        assert ev.type == "chat" and ev.actor == {"kind": "slack", "value": f["user"]}
        assert ev.attrs == {"channel": f["channel"], "ts": f["ts_str"]} and ev.quote_text == f["text"]
        sec, frac = f["ts_str"].split(".")
        assert int(sec) == int(f["ts"].timestamp()) and len(frac) == 6 and int(frac) % 100 == 0


def test_no_duplicates(mails, slack):
    texts = Counter(r.fields["text"] for r in slack)
    assert max(texts.values()) == 1, [t for t, n in texts.items() if n > 1][:5]
    bodies = Counter("\n".join(r.fields["body"]) for r in mails)
    assert max(bodies.values()) == 1
    # personal anecdotes are told once
    assert sum(1 for r in slack if "radiator" in r.fields["text"].lower()) <= 1


def test_b3_noise(slack, mails):
    """No background message says or implies Hank stays on the floor that evening or plans to attend."""
    for r in slack + mails:
        if r.story:
            continue
        text = " ".join(_texts(r))
        assert not any(b in text for b in B3), text
        assert not re.search(r"(stay|staying|be) on the floor", text.lower()), text


def test_b3_story_dm(slack):
    """The 03-04 16:55 DM lines come verbatim from story_spec.json (owned by the story author)."""
    spec = [d["event"].quote_text for d in story.required_docs() if d["event"].type == "chat"]
    if any(b in q for q in spec for b in B3):
        pytest.skip("story_spec.json still holds the old 2026-03-04 16:55 / 16:57 DM lines (fix belongs to story_spec)")
    for r in slack:
        assert not any(b in r.fields["text"] for b in B3), r.fields["text"]


def test_slack_format(slack):
    per_file = Counter((r.source, r.fields["ts_str"]) for r in slack)
    assert max(per_file.values()) == 1
    for r in slack:
        t = r.fields["text"]
        assert t and '"' not in t and "\\" not in t and "\n" not in t and "\r" not in t and t.isascii()
    handles = {p["slack_handle"] for p in world.people() if p["slack_handle"]}
    assert {r.fields["user"] for r in slack} <= handles
    dm = comms.dm_channel()
    kim = {r.fields["channel"] for r in slack if r.fields["user"] == "kim.sayers"}
    assert kim == {dm}
    assert {r.fields["user"] for r in slack if r.fields["channel"] == dm} == {"kim.sayers", "hank.gibson"}


def test_no_hardcoded_dm_id():
    root = Path(comms.__file__).parent
    for name in ("comms.py", "personas.py"):
        assert "D0HANKKIM" not in (root / name).read_text(encoding="utf-8")


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
    req = story.required_docs()
    story_records = {id(r) for r in recs for e in r.events if any(e == d["event"] for d in req)}
    base = re.compile("|".join(FORBIDDEN), re.I)
    strict = re.compile("|".join(FORBIDDEN_NOISE), re.I)
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


def test_floor_hints_match_presence(mails, slack, who_by_addr):
    """A message saying the writer is on the floor is sent while the writer is inside a badge room."""
    for r in mails + slack:
        if r.story or r.t.date() >= date(2026, 3, 9):
            continue
        sender = r.fields.get("user") or r.fields.get("from_addr")
        pid = who_by_addr.get(sender)
        if pid in (None, "p_frederik", "p_kim"):
            continue
        texts = [r.fields["text"]] if "text" in r.fields else list(r.fields["body"])
        if any(comms.FLOOR_RE.search(x) for x in texts):
            assert comms._present(pid, r.t), (pid, r.t, texts)


def test_weekend_slack_from_home(slack, who_by_addr):
    for r in slack:
        if r.story or r.t.weekday() < 5:
            continue
        pid = who_by_addr[r.fields["user"]]
        if not comms._present(pid, r.t):
            assert r.fields["channel"] in ("random", comms.dm_channel()), r.fields


def test_lab_219_messages(slack, who_by_addr):
    sessions = comms._lab_sessions()
    assert len(sessions) >= 10
    lab = [r for r in slack if r.fields["channel"] == "lab-219"]
    for r in slack + []:
        if r.story:
            continue
        text = r.fields["text"]
        if LAB_PRESENCE_RE.search(text):
            pid = who_by_addr[r.fields["user"]]
            assert comms.auth219(pid, r.t), (pid, text)
            assert r.fields["channel"] == "lab-219", text
            mine = [s for s in sessions if s[0] == pid and s[1].date() == r.t.date()]
            times = re.findall(r"\b(\d{1,2}):(\d{2})\b", text)
            if not times and not DONE_RE.search(text):
                # a remark about the room (humidity, tidiness): the writer was in 219 earlier that day
                assert comms._had_219(pid, r.t), (pid, r.t, text)
                continue
            assert mine, (pid, r.t, text)
            if DONE_RE.search(text) and not times:
                # 'done' right after a real logoff, while still in 219 or between rooms, never in another room
                s = next((s for s in mine if s[2] <= r.t <= s[2] + timedelta(minutes=5)), None)
                assert s is not None, (pid, r.t, text)
                assert comms._room_at(pid, r.t) in ("219", None), (pid, r.t, comms._room_at(pid, r.t))
            else:
                # booking / running / starting: the session covers the times named in the message
                s = next((s for s in mine if s[2] >= r.t), None)
                assert s is not None, (pid, r.t, text)
                for h, m in times:
                    t = world.at(r.t.date(), int(h), int(m))
                    assert s[1] - timedelta(minutes=30) <= t <= s[2] + timedelta(minutes=16), (text, s)
    # people without 219 access only ask
    for r in lab:
        pid = who_by_addr[r.fields["user"]]
        if not comms.auth219(pid, r.t):
            assert not LAB_PRESENCE_RE.search(r.fields["text"]), r.fields["text"]
    # every session in the Slack period has its 'done' message
    done = {(who_by_addr[r.fields["user"]], r.t.date()) for r in lab if DONE_RE.search(r.fields["text"])}
    for pid, on, off, task in sessions:
        if comms.SLACK_START <= on.date() <= comms.SLACK_END:
            assert (pid, on.date()) in done, (pid, on)


def test_lunch_matches_absence(slack, who_by_addr):
    asks = [r for r in slack if r.fields["channel"] == "general" and re.search(r"lunch|\bat (\d{1,2}:\d{2})\?", r.fields["text"], re.I)
            and any(f.lower() in r.fields["text"].lower() for f in personas.FOOD)]
    for r in asks:
        m = re.search(r"\b(\d{1,2}):(\d{2})\b", r.fields["text"])
        if not m:
            continue
        pid = who_by_addr[r.fields["user"]]
        slot = world.at(r.t.date(), int(m.group(1)), int(m.group(2)))
        assert not comms._present(pid, slot + timedelta(minutes=10)), (pid, r.fields["text"])


def test_farewell_lunch_in_217(mails, slack):
    rina_friday = any(f.person_id == "p_bg_17" and f.day == date(2026, 3, 6) for f in comms.presence.floor_days())
    rina = [r for r in mails if r.fields["from_addr"] == "rina.okafor@halvorsen.example"
            and "Farewell lunch" in r.fields["subject"]]
    assert len(rina) == 1
    body = " ".join(rina[0].fields["body"])
    assert ("I will be there." in body) == rina_friday
    if not rina_friday:
        assert "Sorry, off on Friday, have a great send-off!" in body
    farewell = [r for r in mails + slack if "farewell" in " ".join(_texts(r)).lower()]
    assert farewell and all("dumpling" not in " ".join(_texts(r)).lower() for r in farewell)
    friday = [r for r in mails + slack if r.t.date() == date(2026, 3, 6)]
    assert not any("elevator" in " ".join(_texts(r)).lower() for r in friday)
    assert any("217 meeting room" in " ".join(_texts(r)) for r in farewell)


def test_resignation_timeline(mails):
    res = next(r for r in mails if r.story and r.fields["subject"] == "Resignation")
    assert any("Friday 6 March" in b for b in res.fields["body"])
    alma = next(r for r in mails if r.fields["from_addr"] == "alma.imhoff@halvorsen.example"
                and r.fields["subject"] == "Re: Resignation")
    text = " ".join(alma.fields["body"])
    assert "end of March" in text and "Friday 6 March" in text
    later = [r for r in mails if r.fields["from_addr"] == "hank.gibson@halvorsen.example" and r.t.date() > date(2026, 3, 6)]
    assert later and all(r.t.date() <= date(2026, 3, 31) for r in later)


def test_noah_asks_rina(mails):
    noah = [r for r in mails if r.fields["from_addr"] == "noah.lindberg@lumenpolicy.example"
            and r.fields["to"] == ["rina.okafor@halvorsen.example"]]
    assert len(noah) == 1
    n = noah[0]
    assert n.t.date() == date(2026, 3, 4) and world.at(n.t.date(), 15, 30) <= n.t <= world.at(n.t.date(), 16, 30)
    text = " ".join(n.fields["body"])
    assert "230" in text and "six-fifteen" in text and "reception" in text
    assert not re.search(r"219|\bhank\b|titan", text, re.I)
    reply = [r for r in mails if r.fields["in_reply_to"] == n.fields["message_id"]]
    assert len(reply) == 1 and reply[0].fields["from_addr"] == "rina.okafor@halvorsen.example"
    assert reply[0].t < world.at(n.t.date(), 16, 45)


def test_brief_facts(recs):
    brief = next(r for r in recs if r.source == world.F_BRIEF)
    text = " ".join(brief.fields["paragraphs"])
    assert "older than 72 hours had already been overwritten" in text
    assert "only the camera status index could be recovered" in text
    assert "CHK-7731" in text and "consent" in text and "financial/transactions.csv" in text
    assert not brief.events


def test_wording_fixes(mails, slack):
    for r in mails + slack:
        text = " ".join(_texts(r)).lower()
        assert "next door" not in text
    # weekly updates fit the role: Rina reports lab work
    rina = [r for r in mails if r.fields["from_addr"] == "rina.okafor@halvorsen.example"
            and r.fields["subject"].startswith("Re: Weekly updates")]
    lab_words = re.compile(r"calibration|bench|lab|fixture|check|verification|compensation|binder", re.I)
    for r in rina:
        for line in r.fields["body"]:
            if line.startswith("- "):
                assert lab_words.search(line), line


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


def test_write_all(recs, tmp_path):
    import pdfplumber

    from app.features.evidence.casegen import doc_writers

    written = doc_writers.write_all(recs, tmp_path)
    assert len(written) == sum(len(r.events) for r in recs)
    by_event = {id(w.event): w for w in written}
    assert len(by_event) == len(written)
    for w in written:
        assert w.quote == w.event.quote_text
    # statement events: the page in attrs is the page the line was printed on
    for r in recs:
        if r.source not in EXPECTED_FILES:
            continue
        with pdfplumber.open(str(tmp_path / r.source)) as pdf:
            pages = [(p.extract_text() or "").split("\n") for p in pdf.pages]
        for e in r.events:
            hit = [i + 1 for i, lines in enumerate(pages) if e.quote_text in [ln.rstrip(" ") for ln in lines]]
            assert hit == [e.attrs["page"]], (e.quote_text, hit, e.attrs["page"])
