"""Tests for the document writers: read every file back independently and check line/quote and determinism."""
import json
import mailbox
from datetime import datetime

import pdfplumber
import pytest

from app.features.evidence.casegen import doc_writers, records, world

EST = world.EST


def ev(type_, t, quote=None, **attrs):
    return records.EventSpec(type=type_, t=t, actor=None, device=None, room=None, attrs=dict(attrs), quote_text=quote)


def file_lines(path):
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data and data.endswith(b"\n")
    return data.decode("utf-8").split("\n")


def tree_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def assert_deterministic(writer, make, tmp_path):
    writer(make(), tmp_path / "a")
    writer(make(), tmp_path / "b")
    a, b = tree_bytes(tmp_path / "a"), tree_bytes(tmp_path / "b")
    assert a and a == b


# ---------------------------------------------------------------- usbstor

def usb_records():
    t1 = datetime(2026, 3, 4, 18, 17, 30, tzinfo=EST)
    t0 = datetime(2026, 2, 10, 9, 0, 0, tzinfo=EST)
    return [
        records.Record(world.F_USB, t0, {"vendor": "Kingston", "product": "DataTraveler_3.0", "rev": "PMAP",
                                         "serial": "E0D55EA574F1F4B0A9&0", "friendly_name": "Kingston DT 3.0 USB Device",
                                         "first_install": t0, "last_write": t0}),
        records.Record(world.F_USB, t1, {"vendor": "SanDisk", "product": "Ultra", "rev": "1.00",
                                         "serial": "4C530001230918112443&0", "friendly_name": "SanDisk Ultra USB Device",
                                         "first_install": t1, "last_write": t1},
                       events=[ev("usb_mount", t1, serial="4C530001230918112443&0")]),
    ]


def test_usbstor(tmp_path):
    w = doc_writers.write_usbstor(usb_records(), tmp_path)
    lines = file_lines(tmp_path / world.F_USB)
    assert len(w) == 1
    assert w[0].quote == "  S/N: 4C530001230918112443&0 [2026-03-04T18:17:30-05:00]"
    assert lines[w[0].line - 1] == w[0].quote
    i = w[0].line - 1
    assert lines[i - 1] == "Disk&Ven_SanDisk&Prod_Ultra&Rev_1.00 [2026-03-04T18:17:30-05:00]"
    assert lines[i + 1] == "  FriendlyName  : SanDisk Ultra USB Device"
    assert lines[i + 2] == "  First InstallDate : 2026-03-04T18:17:30-05:00"
    assert lines[i - 2] == ""  # blank line between blocks
    assert lines[0] == "usbstor v.20200515"


def test_usbstor_deterministic(tmp_path):
    assert_deterministic(doc_writers.write_usbstor, usb_records, tmp_path)


# ---------------------------------------------------------------- mbox

def mbox_records():
    d1 = datetime(2026, 3, 4, 17, 30, 0, tzinfo=EST)
    d2 = datetime(2026, 3, 4, 19, 5, 0, tzinfo=EST)
    return [
        records.Record(world.F_MBOX, d1, {
            "message_id": "<m1@halvorsen.example>", "from_name": "Hank Gibson",
            "from_addr": "hank.gibson@halvorsen.example", "to": ["kim.sayers@northline.example"], "cc": [],
            "subject": "Summit dinner", "date": d1, "in_reply_to": None,
            "body": ["Hi Kim,", "", "See you at the summit dinner tonight.", "Bring the paperwork — café at 8.",
                     "", "Hank"]},
            events=[ev("email", d1, quote="Bring the paperwork")]),
        records.Record(world.F_MBOX, d2, {
            "message_id": "<m2@northline.example>", "from_name": "Kim Sayers",
            "from_addr": "kim.sayers@northline.example", "to": ["hank.gibson@halvorsen.example"],
            "cc": ["alma.imhoff@halvorsen.example"], "subject": "Re: Summit dinner", "date": d2,
            "in_reply_to": "<m1@halvorsen.example>", "body": ["", "Looking forward to it.", "Kim"]},
            events=[ev("email", d2)]),
    ]


def test_mbox(tmp_path):
    w = doc_writers.write_mbox(mbox_records(), tmp_path)
    path = tmp_path / world.F_MBOX
    msgs = list(mailbox.mbox(str(path)))
    assert len(msgs) == 2
    m1, m2 = msgs
    assert m1["From"] == '"Hank Gibson" <hank.gibson@halvorsen.example>'
    assert m1["To"] == "kim.sayers@northline.example"
    assert m1["Cc"] is None and m1["In-Reply-To"] is None
    assert m1["Date"] == "Wed, 04 Mar 2026 17:30:00 -0500"
    assert m1["Message-ID"] == "<m1@halvorsen.example>"
    assert m1["Content-Type"] == "text/plain; charset=utf-8"
    assert "Bring the paperwork — café at 8." in m1.get_payload(decode=True).decode("utf-8")
    assert m1.get_from().startswith("hank.gibson@halvorsen.example Wed Mar  4 17:30:00 2026")
    assert m2["Cc"] == "alma.imhoff@halvorsen.example"
    assert m2["In-Reply-To"] == "<m1@halvorsen.example>"
    assert m2["Subject"] == "Re: Summit dinner"

    lines = file_lines(path)
    assert w[0].quote == "Bring the paperwork"
    assert lines[w[0].line - 1] == "Bring the paperwork — café at 8."
    assert w[1].quote == "Looking forward to it."  # first non-empty body line
    assert lines[w[1].line - 1] == w[1].quote


def test_mbox_deterministic(tmp_path):
    assert_deterministic(doc_writers.write_mbox, mbox_records, tmp_path)


def test_mbox_guards(tmp_path):
    recs = mbox_records()
    recs[0].fields["body"] = ["From x on the summit"]
    with pytest.raises(ValueError, match="From "):
        doc_writers.write_mbox(recs, tmp_path)
    recs = mbox_records()
    recs[0].fields["body"] = ["line\r"]
    with pytest.raises(ValueError):
        doc_writers.write_mbox(recs, tmp_path)
    recs = mbox_records()
    recs[0].events[0].quote_text = "not in the body"
    with pytest.raises(ValueError):
        doc_writers.write_mbox(recs, tmp_path)


# ---------------------------------------------------------------- Slack

def slack_rec(channel, user, text, dt, events=True, **extra):
    src = f"{world.F_SLACK_DIR}/{channel}/{dt:%Y-%m-%d}.json"
    f = {"channel": channel, "user": user, "text": text, "ts": dt, **extra}
    return records.Record(src, dt, f, events=[ev("chat", dt, quote=text, channel=channel)] if events else [])


def slack_records():
    t = datetime(2026, 3, 4, 10, 30, 0, tzinfo=EST)
    t2 = datetime(2026, 3, 4, 11, 0, 0, tzinfo=EST)
    return [
        slack_rec("general", "alma.imhoff", "Reminder: summit badges at the front desk.", t2),
        slack_rec("general", "hank.gibson", "Thanks Alma — will grab mine.", t),
        slack_rec("general", "alma.imhoff", "Same second message.", t, events=False),
        slack_rec("D0HANKKIM", "kim.sayers", "Are we still on for tonight?", t),
        slack_rec("D0HANKKIM", "hank.gibson", "Yes. 6:45 at the usual place.", t2, ts_str="1772640000.123456"),
    ]


def test_slack(tmp_path):
    w = doc_writers.write_slack(slack_records(), tmp_path)
    root = tmp_path / world.F_SLACK_DIR
    assert len(w) == 4
    for x in w:
        path = tmp_path / x.record.source
        msgs = json.loads(path.read_text(encoding="utf-8"))
        assert [m["ts"] for m in msgs] == sorted(m["ts"] for m in msgs)
        lines = file_lines(path)
        assert f'"text": "{x.quote}"' in lines[x.line - 1]
        assert x.quote == x.record.fields["text"]
        assert any(m["text"] == x.quote and m["ts"] == x.event.attrs["ts"] and
                   m["user"] == world.slack_user_id(x.record.fields["user"]) for m in msgs)

    general = json.loads((root / "general" / "2026-03-04.json").read_text(encoding="utf-8"))
    sec = int(datetime(2026, 3, 4, 10, 30, tzinfo=EST).timestamp())
    assert [m["ts"] for m in general] == [f"{sec}.000100", f"{sec}.000200", f"{sec + 1800}.000100"]
    assert general[0]["text"] == "Thanks Alma — will grab mine."
    dm = json.loads((root / "D0HANKKIM" / "2026-03-04.json").read_text(encoding="utf-8"))
    assert dm[1]["ts"] == "1772640000.123456"

    users = json.loads((root / "users.json").read_text(encoding="utf-8"))
    names = {u["name"] for u in users}
    assert {"kim.sayers", "hank.gibson", "alma.imhoff"} <= names
    assert all(u["id"] == world.slack_user_id(u["name"]) for u in users)
    channels = json.loads((root / "channels.json").read_text(encoding="utf-8"))
    assert [c["name"] for c in channels] == ["general"]
    dms = json.loads((root / "dms.json").read_text(encoding="utf-8"))
    assert dms[0]["id"] == "D0HANKKIM"
    assert set(dms[0]["members"]) == {world.slack_user_id("kim.sayers"), world.slack_user_id("hank.gibson")}


def test_slack_deterministic(tmp_path):
    assert_deterministic(doc_writers.write_slack, slack_records, tmp_path)


@pytest.mark.parametrize("text", ['He said "fine"', "back\\slash", "two\nlines"])
def test_slack_guards(tmp_path, text):
    t = datetime(2026, 3, 4, 10, 30, 0, tzinfo=EST)
    with pytest.raises(ValueError):
        doc_writers.write_slack([slack_rec("general", "hank.gibson", text, t)], tmp_path)


# ---------------------------------------------------------------- PDFs

Q1 = "I left room 219 at about 18:30 that evening."
Q2 = "I did not plug any USB drive into LT-219."
LONG = ("I believe that I left the lab sometime after six thirty that evening, though I honestly cannot be "
        "completely certain about it.")


def pdf_records():
    d = datetime(2026, 3, 9, 10, 0, tzinfo=EST)
    filler = ("I have worked at Halvorsen for six years as a senior engineer on the Titan program and I know the "
              "lab layout on the second floor well, including the access readers and cameras. ")
    st = records.Record("statements/hank_gibson.pdf", d, {
        "title": "Witness Statement", "case_id": "CASE-1010F", "speaker": "Hank Gibson",
        "role": "Halvorsen senior engineer", "interviewer": "Alma Imhoff", "date": d,
        "location": "Room 217, Halvorsen Dynamics", "paragraphs": [
            filler * 3,
            Q1,
            "On the evening of 4 March I was in the building for the summit. " + Q2 + " The laptop was "
            "scheduled for patching that night, which I knew about from the IT calendar.",
        ] + [filler] * 12 + ["That is everything I remember."]},
        events=[ev("statement", d, quote=Q1, speaker="Hank Gibson"), ev("statement", d, quote=Q2,
                                                                         speaker="Hank Gibson")])
    brief = records.Record(world.F_BRIEF, d, {
        "title": "Incident Brief", "case_id": "CASE-1010F", "author": "Alma Imhoff", "date": d,
        "paragraphs": ["Design files for the Titan thruster may have left the building on 4 March.", filler]})
    return [st, brief]


def pdf_lines(path):
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages).split("\n"), len(pdf.pages)


def test_pdfs(tmp_path):
    w = doc_writers.write_pdfs(pdf_records(), tmp_path)
    assert [x.quote for x in w] == [Q1, Q2]
    lines, pages = pdf_lines(tmp_path / "statements/hank_gibson.pdf")
    assert pages >= 2  # long statement spans pages
    for x in w:
        assert lines[x.line - 1].rstrip() == x.quote
    text = "\n".join(lines)
    assert "Halvorsen Dynamics - Security Office" in text
    assert "Statement of: Hank Gibson (Halvorsen senior engineer)" in text
    assert "Interviewer: Alma Imhoff" in text
    assert "Signature:" in text
    blines, _ = pdf_lines(tmp_path / world.F_BRIEF)
    assert "Incident Brief" in blines


def test_pdfs_deterministic(tmp_path):
    assert_deterministic(doc_writers.write_pdfs, pdf_records, tmp_path)


def test_pdf_quote_too_long(tmp_path):
    recs = pdf_records()
    recs[0].fields["paragraphs"].append(LONG)
    recs[0].events.append(ev("statement", recs[0].t, quote=LONG))
    with pytest.raises(ValueError, match="too long"):
        doc_writers.write_pdfs(recs, tmp_path)


def test_pdf_quote_missing(tmp_path):
    recs = pdf_records()
    recs[0].events.append(ev("statement", recs[0].t, quote="Never said this."))
    with pytest.raises(ValueError):
        doc_writers.write_pdfs(recs, tmp_path)


# ---------------------------------------------------------------- dispatch

def test_write_all(tmp_path):
    recs = usb_records() + mbox_records() + slack_records() + pdf_records()
    w = doc_writers.write_all(recs, tmp_path)
    assert len(w) == sum(len(r.events) for r in recs)
    assert (tmp_path / world.F_USB).exists() and (tmp_path / world.F_MBOX).exists()
    assert (tmp_path / world.F_BRIEF).exists() and (tmp_path / world.F_SLACK_DIR / "users.json").exists()
    with pytest.raises(ValueError):
        doc_writers.write_all([records.Record("access/badge_access.csv", recs[0].t, {})], tmp_path)
