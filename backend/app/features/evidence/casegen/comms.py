"""Communications content of Case 1010F: the mailbox, the Slack export, the three statements and the brief.

Everything is templates (personas.py) plus seeded random.Random, one sub-seed per section, so the output is the same
on every run. No LLM calls.

  email_records()      comms/mailbox.mbox, ~300 messages 2026-02-23 .. 2026-03-09
  slack_records()      comms/slack_export/<channel>/<YYYY-MM-DD>.json, ~600 messages 2026-02-23 .. 2026-03-08
  statement_records()  statements/hank_gibson.pdf, maggie_price.pdf, frederik_mendelssohn.pdf (2026-03-09)
  brief_record()       brief.pdf, Alma's incident brief (suspicion only)
  all_records()

The story documents (story.required_docs()) are built around the exact EventSpec objects story.py hands out; their
quote lines are used verbatim. Every noise email / Slack message carries one 'email' / 'chat' EventSpec. Noise text
is checked against personas.FORBIDDEN so no background message hints at the answer, and nothing is posted between
16:45 and midnight on the incident day except the story itself.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cache

from . import personas as P
from . import story
from .presence import floor_days
from .records import EventSpec, Record
from .world import (EST, F_BRIEF, F_MBOX, F_SLACK_DIR, F_STATEMENTS_DIR, INCIDENT_DAY, SEED_COMMS, at, people,
                    person)

DM = "D0HANKKIM"
CHANNELS = ["general", "halvorsen-eng", "lab-219", "random", "summit-2026"]
SLACK_START, SLACK_END = date(2026, 2, 23), date(2026, 3, 8)
MAIL_START, MAIL_END = date(2026, 2, 23), date(2026, 3, 9)
SUMMIT_START, SUMMIT_END = date(2026, 3, 2), date(2026, 3, 6)
RESIGN_DAY, LAST_DAY = date(2026, 3, 2), date(2026, 3, 6)
CASE_DAY = date(2026, 3, 9)
BLACKOUT = (at(INCIDENT_DAY, 16, 45), at(INCIDENT_DAY, 23, 59, 59))
STORY_PEOPLE = {"p_alma", "p_hank", "p_maggie", "p_frederik", "p_bg_17"}
CASE_ID = "1010F"
INTERVIEWER = "Alma Imhoff"
INTERVIEW_ROOM = "Halvorsen Dynamics meeting room, suite 217, JRR Building, 2nd floor"

FORBIDDEN_RE = re.compile("|".join(P.FORBIDDEN), re.I)
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Slack messages per channel per day (weekday, weekend); summit-2026 is busier during summit week.
SLACK_TARGET = {"general": (11, 0), "halvorsen-eng": (16, 0), "lab-219": (9, 0), "random": (9, 6),
                "summit-2026": (2, 0)}
SUMMIT_WEEK_TARGET = 9
MAIL_TARGET = (23, 1)   # generic email messages per weekday / weekend day


def _rng(*parts) -> random.Random:
    """Independent deterministic stream per section (string seeds are hashed with sha512 by random)."""
    return random.Random(f"{SEED_COMMS}:" + ":".join(str(p) for p in parts))


def _days(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


# ============================================================================================ people

@dataclass(frozen=True)
class Who:
    pid: str
    name: str
    first: str
    email: str
    handle: str
    org: str
    persona: P.Persona

    @property
    def tags(self):
        return self.persona.tags


@cache
def _people() -> dict[str, Who]:
    out = {}
    n_ext = 0
    for p in people():
        pid = p["person_id"]
        if pid in P.CAST:
            per = P.CAST[pid]
        elif pid in P.BG_HALVORSEN:
            arch, tags = P.BG_HALVORSEN[pid]
            per = P.Persona(pid, arch, **P.ARCHETYPES[arch], tags=frozenset(tags))
        else:
            arch = "external_formal" if n_ext % 3 else "external_casual"
            n_ext += 1
            per = P.Persona(pid, arch, **P.ARCHETYPES[arch], tags=frozenset({"tenant"}))
        dom = p["email"].split("@")[1]
        out[pid] = Who(pid, p["name"], p["name"].split()[0], p["email"], p["slack_handle"], P.ORGS.get(dom, dom),
                       per)
    return out


def _w(pid: str) -> Who:
    return _people()[pid]


def _by_handle(handle: str) -> Who:
    return next(w for w in _people().values() if w.handle == handle)


# ============================================================================================ presence

@cache
def _floor() -> dict[tuple[str, date], tuple[datetime, datetime]]:
    d = {(f.person_id, f.day): (f.arrive, f.depart) for f in floor_days()}
    # presence.py stops the story people's incident day at the 17:00 cut (story.py owns the evening). For writing
    # purposes they are at their desks until the blackout starts.
    for pid in STORY_PEOPLE:
        if (pid, INCIDENT_DAY) in d:
            d[(pid, INCIDENT_DAY)] = (d[(pid, INCIDENT_DAY)][0], BLACKOUT[0])
    return d


def _blocked(t: datetime) -> bool:
    return BLACKOUT[0] <= t <= BLACKOUT[1]


def _on_floor(pid: str, t: datetime) -> bool:
    w = _floor().get((pid, t.date()))
    return bool(w) and w[0] + timedelta(minutes=3) <= t <= w[1] - timedelta(minutes=3)


def _home_ok(t: datetime) -> bool:
    """Plausible time to write from home: weekend daytime / evening, weekday evening."""
    h = t.hour + t.minute / 60
    if t.weekday() >= 5:
        return 9.5 <= h < 22
    return 19.5 <= h < 22.25


def _can_write(w: Who, t: datetime, home: bool) -> bool:
    if _blocked(t) or not 7 <= t.hour < 23:
        return False
    if w.pid in STORY_PEOPLE and t.date() == INCIDENT_DAY and t >= BLACKOUT[0]:
        return False
    if "tenant" in w.tags or w.pid == "p_frederik":
        return t.weekday() < 5 and 8.5 <= t.hour + t.minute / 60 < 17.5
    if _on_floor(w.pid, t):
        return True
    return home and _home_ok(t)


def _window(pid: str, day: date) -> tuple[datetime, datetime] | None:
    """Working window on the floor that day, clipped to office hours."""
    w = _floor().get((pid, day))
    if not w:
        return None
    a = max(w[0] + timedelta(minutes=8), at(day, 8, 45))
    b = min(w[1] - timedelta(minutes=8), at(day, 17, 45), BLACKOUT[0] if day == INCIDENT_DAY else at(day, 23))
    return (a, b) if b > a else None


def _rand_time(rng: random.Random, a: datetime, b: datetime) -> datetime:
    return a + timedelta(seconds=rng.randint(0, max(0, int((b - a).total_seconds()))))


# ============================================================================================ text helpers

def _typo(text: str, rng: random.Random) -> str:
    words = text.split(" ")
    idx = [i for i, wd in enumerate(words) if wd.isalpha() and wd.islower() and len(wd) >= 5]
    if not idx:
        return text
    i = rng.choice(idx)
    wd = words[i]
    k = rng.randint(1, len(wd) - 3)
    words[i] = wd[:k] + wd[k + 1] + wd[k] + wd[k + 2:]
    return " ".join(words)


def _stylize(text: str, per: P.Persona, rng: random.Random) -> str:
    """Apply one person's Slack habits to a neutral template line."""
    if per.clip and rng.random() < per.clip:
        m = re.match(r"^(.+?[.?!])\s", text)
        if m:
            text = m.group(1)
    if text.endswith(".") and per.exclaim and rng.random() < per.exclaim:
        text = text[:-1] + ("!!" if rng.random() < 0.3 else "!")
    if per.typo and rng.random() < per.typo:
        text = _typo(text, rng)
    if per.lower and rng.random() < per.lower:
        text = text.lower()
    if text.endswith(".") and per.drop_period and rng.random() < per.drop_period:
        text = text[:-1]
    if per.emoji and rng.random() < per.emoji_p:
        text = f"{text} {rng.choice(per.emoji)}"
    return text


def _params(rng: random.Random, day: date, t0: datetime | None = None, future: bool = False) -> dict:
    """Thread-level fillers. Days named are workdays one to three days ahead. Times lie after the thread start, or
    (future=True, the thread names another day) inside office hours."""
    ahead = []
    d = day
    while len(ahead) < 4:
        d += timedelta(days=1)
        if d.weekday() < 5:
            ahead.append(WEEKDAYS[d.weekday()])
    t0 = t0 or at(day, 9, 0)
    base = t0.hour * 60 + t0.minute + rng.randint(20, 110)
    base = min(-(-base // 15) * 15, 17 * 60 + 30)
    if future:
        base = rng.choice([9, 10, 10, 11, 13, 14, 14, 15]) * 60 + rng.choice([0, 0, 15, 30, 30, 45])
    slot = f"{base // 60}:{base % 60:02d}"
    end = base + rng.choice([60, 60, 90, 120])
    slot2 = f"{end // 60}:{end % 60:02d}"
    t1, t2 = rng.sample(P.TOPICS, 2)
    out = dict(day=ahead[rng.randint(0, 2)], day2=ahead[3], slot=slot, slot2=slot2, topic=t1, topic2=t2,
               n=rng.randint(2, 9), m=rng.randint(1, 9), talk=rng.choice(P.TALKS), food=rng.choice(P.FOOD))
    prog = P.PROGRAM.get(day.isoformat(), [])
    now = f"{t0.hour:02d}:{t0.minute:02d}"
    nxt = [(n, s) for n, s in prog if s.zfill(5) > now]
    past = [(n, s) for n, s in prog if f"{int(s[:2]) + 1:02d}{s[2:]}" < now]   # an hour after it started
    if nxt:
        out["next_talk"], out["next_slot"] = nxt[0]
    if past:
        out["past_talk"] = past[-1][0]
    return out


def _fill(s: str, params: dict, roles: dict[str, Who]) -> str:
    vals = dict(params)
    for r, w in roles.items():
        vals[r] = w.first
        vals[r + "full"] = w.name
        vals[r + "org"] = w.org
    vals.setdefault("org", next((w.org for w in roles.values() if "tenant" in w.tags), "our team"))
    out = s.format(**vals)
    return out[:1].upper() + out[1:] if out and out[0].isalpha() else out


def _clean(text: str) -> bool:
    return not FORBIDDEN_RE.search(text)


def _slack_ok(text: str) -> bool:
    return bool(text) and not any(c in text for c in '"\\\r\n') and all(ord(c) >= 0x20 for c in text) \
        and text.isascii() and _clean(text)


# ============================================================================================ Slack

@dataclass
class _Msg:
    channel: str
    t: datetime
    handle: str
    text: str
    event: EventSpec | None = None      # story event (kept as is) or None for noise
    ts_str: str | None = None
    late: bool = False                  # a late 'sorry, just saw this' reply


def _channel_members(ch: str, day: date) -> list[Who]:
    hal = [w for w in _people().values() if "hal" in w.tags and w.pid != "p_alma"]
    if day > LAST_DAY:
        hal = [w for w in hal if w.pid != "p_hank"]
    if ch == "lab-219":
        return [w for w in hal if "lab" in w.tags]
    if ch == "halvorsen-eng":
        return [w for w in hal if w.tags & {"eng", "pm", "lab", "ops"}]
    return hal


def _pool(tag: str, members: list[Who]) -> list[Who]:
    if tag == "hal":
        return members
    if tag == "rina":
        return [w for w in members if w.pid == "p_bg_17"]
    if tag == "lab_user":
        return [w for w in members if "lab" in w.tags and w.pid != "p_bg_17"]
    return [w for w in members if tag in w.tags]


def _day_ok(spec: str | None, day: date) -> bool:
    wd = day.weekday()
    return {
        None: True, "weekday": wd < 5, "weekend": wd >= 5, "fri": wd == 4, "mon": wd == 0,
        "pre_summit": day < SUMMIT_START, "summit_first": day == SUMMIT_START, "summit": SUMMIT_START <= day <= SUMMIT_END,
        "pre_0302": day < RESIGN_DAY, "to_0305": day <= date(2026, 3, 5),
        "printer": day in (date(2026, 2, 26), date(2026, 2, 27), date(2026, 3, 3)),
    }[spec]


def _sim_thread(rng: random.Random, ch: str, turns: list[tuple[str, list[str]]], roles: dict[str, Who],
                params: dict, t0: datetime, home: bool, taken: set[str], evening_late: bool = True) -> list[_Msg]:
    """Play a thread from t0: replies within minutes when the person is around, a late 'sorry, just saw this'
    when they come back later the same day, or the thread just stops."""
    out: list[_Msg] = []
    t, last = t0, None
    idx, prev_len = 0, 0
    for i, (role, variants) in enumerate(turns):
        w = roles[role]
        # a turn with as many variants as the previous one continues the same branch (replies fit the question)
        idx = idx if len(variants) == prev_len else rng.randrange(len(variants))
        prev_len = len(variants)
        text = _fill(variants[idx], params, roles)
        late = False
        if i:
            gap = rng.uniform(0.2, 1.5) if role == last else rng.choice([0.6, 1, 1.5, 2, 3, 4, 6, 9]) * rng.uniform(0.8, 1.3)
            t = t + timedelta(minutes=gap, seconds=rng.randint(0, 50))
            if not _can_write(w, t, home):
                win = _window(w.pid, t.date())
                if win and win[0] > t:
                    t, late = win[0] + timedelta(minutes=rng.randint(3, 35), seconds=rng.randint(0, 59)), True
                elif evening_late and rng.random() < w.persona.evening * 2 and t.date().weekday() < 5:
                    t, late = max(t, at(t.date(), 19, 35)) + timedelta(minutes=rng.randint(0, 80)), True
                else:
                    break
                if not _can_write(w, t, True):
                    break
            elif role != last and not home and rng.random() < 0.07:
                later = t + timedelta(minutes=rng.randint(40, 150), seconds=rng.randint(0, 59))
                if _can_write(w, later, False):      # busy for a while, then answers
                    t, late = later, True
        text = _stylize(text, w.persona, rng)
        if late:
            lp = rng.choice(w.persona.late)
            text = f"{lp} {text}" if lp[-1] in ".!?" else f"{lp} - {text}"
        if not _slack_ok(text) or text in taken:
            break
        taken.add(text)
        out.append(_Msg(ch, t, w.handle, text, late=late))
        last = role
    return out


def _assign(rng: random.Random, roles_spec: dict[str, str], members: list[Who]) -> dict[str, Who] | None:
    roles: dict[str, Who] = {}
    for r, tag in roles_spec.items():
        if tag.startswith("pid:"):
            cand = [_w(tag[4:])]
        else:
            cand = [w for w in _pool(tag, members) if w not in roles.values()]
        if not cand:
            return None
        roles[r] = rng.choice(cand)
    return roles


def _start_time(rng: random.Random, w: Who, day: date, home: bool) -> datetime | None:
    win = _window(w.pid, day)
    if win:
        return _rand_time(rng, win[0], win[1])
    if home:
        if day.weekday() >= 5:
            return _rand_time(rng, at(day, 10, 0), at(day, 21, 0))
        return _rand_time(rng, at(day, 19, 40), at(day, 21, 40))
    return None


def _scripted_slack() -> list[tuple[str, date, tuple[int, int], list[tuple[str, str]]]]:
    """Fixed beats of the week: (channel, day, (h, m), [(person_id, text), ...])."""
    d = date
    return [
        ("general", d(2026, 2, 24), (10, 5), [
            ("p_alma", "A reminder that the fire exit next to the lounge must be kept clear at all times. Thank you."),
            ("p_bg_06", "Thanks Alma, I moved the boxes from the summit delivery."),
        ]),
        ("general", d(2026, 2, 27), (10, 20), [
            ("p_alma", "Summit week starts on Monday. Visitors must sign in at the front desk and be accompanied in the Halvorsen suite at all times."),
            ("p_bg_06", "Thanks Alma. I will mention it at standup too."),
            ("p_bg_02", "Noted, thanks!"),
        ]),
        ("summit-2026", d(2026, 3, 2), (9, 40), [
            ("p_bg_04", "Summit week! Agenda is pinned. Drop your notes from any session in the shared summit doc."),
            ("p_bg_01", "Will do. Going to the keynote at 10."),
            ("p_bg_02", "Same! Saving seats on the left side :)"),
            ("p_bg_03", "be there in 5"),
        ]),
        ("general", d(2026, 3, 2), (10, 50), [
            ("p_bg_06", "Some news to share: Hank has decided to move on from Halvorsen, and Friday will be his last day. Please join me in wishing him well."),
            ("p_bg_01", "Big loss. Congrats Hank."),
            ("p_bg_02", "Oh no! Congratulations Hank, we will miss you :("),
            ("p_maggie", "Going to miss you so so much!! :sob:"),
            ("p_bg_03", "noooo. congrats though"),
            ("p_bg_05", "who is going to explain the old test rig to me now :joy:"),
            ("p_hank", "Thanks all. It has been a good run."),
            ("p_bg_04", "Congrats Hank! Let's make sure we get time for a proper handover this week."),
            ("p_bg_17", "Congrats Hank, best of luck"),
        ]),
        ("halvorsen-eng", d(2026, 3, 2), (14, 10), [
            ("p_bg_04", "Hank, can we set up handover sessions this week? Thinking the test stand scripts and the valve timing sweep."),
            ("p_hank", "Yes. Tuesday and Thursday afternoons work."),
            ("p_bg_04", "Booked Tuesday 14:00 and Thursday 14:00 in the meeting room."),
            ("p_bg_01", "I can take the test stand scripts."),
            ("p_hank", "Ok. Notes will be in the handover doc."),
        ]),
        ("general", d(2026, 3, 3), (11, 5), [
            ("p_maggie", "Farewell lunch for Hank on Friday at 12:30! Thinking the dumpling spot, who is in??"),
            ("p_bg_01", "In."),
            ("p_bg_02", "Yes!!"),
            ("p_bg_03", "in"),
            ("p_bg_05", "in, as long as someone else does the speech"),
            ("p_bg_06", "In. Lunch is on Halvorsen :)"),
            ("p_bg_04", "Count me in!"),
            ("p_maggie", "Yay! Booking a table for nine :tada:"),
            ("p_hank", "Thanks Maggie."),
        ]),
        ("halvorsen-eng", d(2026, 3, 3), (15, 40), [
            ("p_hank", "Handover doc is up. Test stand section done, the rest by Thursday."),
            ("p_bg_01", "Thanks Hank, reading it tonight."),
        ]),
        ("summit-2026", d(2026, 3, 4), (9, 55), [
            ("p_bg_06", "Reminder: the summit welcome reception is tonight at 18:15 in the ground-floor atrium."),
            ("p_bg_01", "Thanks for the reminder."),
            ("p_bg_02", "Ooh, thanks Sofia!"),
        ]),
        ("general", d(2026, 3, 5), (10, 15), [
            ("p_maggie", "Reminder: Hank's farewell lunch is tomorrow, meet at the elevators at 12:20!"),
            ("p_bg_02", "Can't wait!"),
            ("p_bg_06", "The card is on my desk if anyone has not signed it yet."),
        ]),
        ("halvorsen-eng", d(2026, 3, 5), (14, 50), [
            ("p_hank", "Handover doc updated. Valve timing sweep section done."),
            ("p_bg_02", "Thanks Hank, super clear."),
        ]),
        ("general", d(2026, 3, 6), (12, 15), [
            ("p_maggie", "Elevators in 5 minutes for lunch everyone!"),
            ("p_bg_03", "omw"),
        ]),
        ("general", d(2026, 3, 6), (14, 5), [
            ("p_hank", "Thanks for lunch everyone. And for the card. Appreciate it."),
            ("p_bg_02", ":heart:"),
            ("p_maggie", "We will miss you!! Stay in touch <3"),
            ("p_bg_05", "the test rig and I will never be the same"),
        ]),
        ("halvorsen-eng", d(2026, 3, 6), (16, 20), [
            ("p_hank", "Handover doc is final. Theo has the test stand scripts, Amara has the valve timing sweep."),
            ("p_bg_01", "Thanks Hank. Good luck."),
            ("p_bg_04", "Thank you for all the work this week, Hank."),
        ]),
    ]


def _groups(msgs: list[_Msg], ch: str, day: date) -> list[list[_Msg]]:
    """Messages already in a channel-day, split into conversations (gaps over 20 minutes)."""
    ms = sorted((m for m in msgs if m.channel == ch and m.t.date() == day and not m.late), key=lambda m: m.t)
    out: list[list[_Msg]] = []
    for m in ms:
        if out and (m.t - out[-1][-1].t) <= timedelta(minutes=20):
            out[-1].append(m)
        else:
            out.append([m])
    return out


def _place(pid: str, day: date, hm: tuple[int, int], home: bool = False) -> datetime:
    """Requested time if the person can write then, else the nearest time inside their window that day."""
    w = _w(pid)
    t = at(day, *hm)
    if _can_write(w, t, home):
        return t
    win = _window(pid, day)
    if not win:
        if day >= CASE_DAY or "hal" not in w.tags:
            return t                                        # no presence data for 03-09; externals keep office hours
        return at(day, 20, 0) + timedelta(minutes=hm[1] % 40)  # not on the floor that day: answers from home
    return min(max(t, win[0] + timedelta(minutes=2)), win[1] - timedelta(minutes=10))


@cache
def _slack_messages() -> tuple[_Msg, ...]:
    msgs: list[_Msg] = []
    taken: dict[tuple[str, date], set[str]] = {}

    def tk(ch, d):
        return taken.setdefault((ch, d), set())

    # 1. story DM messages, untouched
    for d in story.required_docs():
        ev = d["event"]
        if ev.type == "chat":
            msgs.append(_Msg(ev.attrs["channel"], ev.t, ev.actor["value"], ev.quote_text, ev, ev.attrs["ts"]))
            tk(ev.attrs["channel"], ev.t.date()).add(ev.quote_text)
    # 2. DM noise around them (Slack Connect with Kim)
    for ds, h, m, s, handle, text in P.KIM_DM_NOISE:
        t = at(date.fromisoformat(ds), h, m, s)
        msgs.append(_Msg(DM, t, handle, text))
        tk(DM, t.date()).add(text)
    # 3. scripted beats of the week
    rng = _rng("slack", "scripted")
    for ch, day, hm, lines in _scripted_slack():
        t = _place(lines[0][0], day, hm)
        last = None
        for i, (pid, text) in enumerate(lines):
            if i:
                t += timedelta(minutes=(rng.uniform(0.2, 1.2) if pid == last else rng.uniform(0.5, 4)),
                               seconds=rng.randint(0, 40))
                if not _can_write(_w(pid), t, False):
                    win = _window(pid, day)
                    if not (win and win[0] > t):
                        continue
                    t = win[0] + timedelta(minutes=rng.randint(4, 30))
                    lp = _w(pid).persona.late[0]
                    text = f"{lp} {text}" if lp[-1] in ".!?" else f"{lp} - {text}"
            if not _slack_ok(text):
                raise ValueError(f"scripted Slack text not allowed: {text!r}")
            msgs.append(_Msg(ch, t, _w(pid).handle, text))
            tk(ch, t.date()).add(text)
            last = pid
    # 4. generic threads until each channel-day reaches its target
    for day in _days(SLACK_START, SLACK_END):
        weekend = day.weekday() >= 5
        for ch in CHANNELS:
            rng = _rng("slack", ch, day.isoformat())
            target = SLACK_TARGET[ch][1 if weekend else 0]
            if ch == "summit-2026" and SUMMIT_START <= day <= SUMMIT_END:
                target = SUMMIT_WEEK_TARGET
            target += rng.randint(-1, 2) if target > 2 else 0
            have = sum(1 for m in msgs if m.channel == ch and m.t.date() == day)
            tpls = [t for t in P.SLACK_THREADS if t["ch"] == ch and _day_ok(t.get("days"), day)
                    and (not weekend or t.get("evening"))]
            if ch == "general":
                tpls = [t for t in tpls if t["id"] != "printer" or _day_ok("printer", day)]
            used: set[str] = set()
            tries = 0
            members = _channel_members(ch, day)
            busy = [(min(m.t for m in g), max(m.t for m in g)) for g in _groups(msgs, ch, day)]
            while have < target and tries < 60 and tpls:
                tries += 1
                cand = [t for t in tpls if t["id"] not in used]
                if not cand:
                    break
                tpl = rng.choices(cand, weights=[t.get("weight", 1) for t in cand])[0]
                roles = _assign(rng, tpl["roles"], members)
                if not roles:
                    used.add(tpl["id"])
                    continue
                home = weekend or (bool(tpl.get("evening")) and rng.random() < 0.35)
                t0 = _start_time(rng, roles[tpl["turns"][0][0]], day, home)
                if t0 is None or not _can_write(roles[tpl["turns"][0][0]], t0, home):
                    continue
                if "hours" in tpl and not tpl["hours"][0] <= t0.hour + t0.minute / 60 <= tpl["hours"][1]:
                    continue
                params = _params(rng, day, t0, future="{day" in repr(tpl["turns"]))
                if tpl.get("needs") and tpl["needs"] not in params:
                    continue
                thread = _sim_thread(rng, ch, tpl["turns"], roles, params, t0, home, tk(ch, day),
                                     evening_late=bool(tpl.get("evening")))
                live = [m.t for m in thread if not m.late]
                span = (min(live) - timedelta(minutes=3), max(live) + timedelta(minutes=3)) if live else None
                if len(thread) < 2 or any(span[0] <= b and a <= span[1] for a, b in busy):
                    for m in thread:
                        tk(ch, day).discard(m.text)
                    continue
                busy.append(span)
                thread = [m for m in thread if SLACK_START <= m.t.date() <= SLACK_END]
                used.add(tpl["id"])
                msgs.extend(thread)
                have += sum(1 for m in thread if m.t.date() == day)
    # 5. ts strings: story keeps its own; others f"{epoch}.{n:06d}", n = 100, 200, ... within one second of a file
    msgs.sort(key=lambda m: (m.channel, m.t, m.event is None, m.handle, m.text))
    used_ts: dict[tuple[str, date], set[str]] = {}
    for m in msgs:
        if m.ts_str:
            used_ts.setdefault((m.channel, m.t.date()), set()).add(m.ts_str)
    for m in msgs:
        if m.ts_str:
            continue
        pool = used_ts.setdefault((m.channel, m.t.date()), set())
        sec, n = int(m.t.timestamp()), 100
        while f"{sec}.{n:06d}" in pool:
            n += 100
        m.ts_str = f"{sec}.{n:06d}"
        pool.add(m.ts_str)
    return tuple(msgs)


def slack_records() -> list[Record]:
    out = []
    for m in _slack_messages():
        if m.event is not None:
            ev, is_story = m.event, True
        else:
            ev = EventSpec(type="chat", t=m.t, actor={"kind": "slack", "value": m.handle}, device=None, room=None,
                           attrs={"channel": m.channel, "ts": m.ts_str}, quote_text=m.text)
            is_story = False
        fields = {"channel": m.channel, "user": m.handle, "text": m.text, "ts": m.t, "ts_str": m.ts_str}
        out.append(Record(source=f"{F_SLACK_DIR}/{m.channel}/{m.t:%Y-%m-%d}.json", t=m.t, fields=fields,
                          events=[ev], story=is_story))
    out.sort(key=lambda r: (r.source, float(r.fields["ts_str"])))
    return out


# ============================================================================================ email

@dataclass
class _Mail:
    t: datetime
    from_addr: str
    from_name: str
    to: list[str]
    cc: list[str]
    subject: str
    body: list[str]
    message_id: str
    in_reply_to: str | None = None
    quote: str | None = None
    event: EventSpec | None = None
    sender: Who | None = None


class _Mailer:
    def __init__(self):
        self.mails: list[_Mail] = []
        self.ids: set[str] = set()
        self.id_rng = _rng("mail", "ids")

    def mid(self, t: datetime, addr: str) -> str:
        dom = addr.split("@")[1]
        while True:
            m = f"<{t:%Y%m%d%H%M%S}.{self.id_rng.getrandbits(16):04x}@{dom}>"
            if m not in self.ids:
                self.ids.add(m)
                return m

    def add(self, m: _Mail) -> _Mail:
        self.mails.append(m)
        if m.message_id:
            self.ids.add(m.message_id)
        return m


LISTS = {P.L_ALL, P.L_ENG, P.L_TENANTS, P.L_SUMMIT}


def _greet_names(to: list[str]) -> str | None:
    """First names for the greeting, 'all' for lists and groups, None for an unnamed external mailbox."""
    names = []
    for a in to:
        w = next((x for x in _people().values() if x.email == a), None)
        if w is None:
            return "all" if a in LISTS or len(to) > 1 else None
        names.append(w.first)
    return names[0] if len(names) == 1 else " and ".join(names) if len(names) == 2 else "all"


def _body(per: P.Persona, sender_first: str, sender_full: str, org: str, to: list[str], content: list[str],
          rng: random.Random, late: bool = False) -> list[str]:
    names = _greet_names(to)
    greet = rng.choice(per.greet).format(to=names) if names else "Hello,"
    greet = greet[:1].upper() + greet[1:]
    sign = [s.format(first=sender_first, full=sender_full, org=org) for s in rng.choice(per.sign)]
    lead = ["Sorry for the slow reply."] if late else []
    return [greet, ""] + lead + content + [""] + sign


def _pick_quote(body: list[str], content: list[str]) -> str | None:
    """The most distinctive content line: on exactly one body line, long enough to be specific."""
    best = None
    for c in content:
        if len(c) < 12 or not c.strip():
            continue
        if sum(1 for b in body if c in b) == 1 and (best is None or len(c) > len(best)):
            best = c
    return best


def _subject_re(s: str) -> str:
    return s if s.startswith("Re: ") else f"Re: {s}"


def _mail_ok(m: _Mail) -> bool:
    lines = [m.subject] + m.body
    return all(_clean(x) and "\r" not in x and "\n" not in x and not x.startswith("From ") for x in lines)


def _sender_time(rng: random.Random, w: Who, after: datetime, max_day: date) -> tuple[datetime, bool] | None:
    """When w answers an email received at `after`: soon if around, else at their next window (late=True)."""
    t = after + timedelta(minutes=rng.choice([6, 12, 20, 35, 50, 75, 110, 160]), seconds=rng.randint(0, 59))
    if _can_write(w, t, rng.random() < w.persona.evening * 2):
        return t, False
    d = after.date()
    for k in range(0, 4):
        day = d + timedelta(days=k)
        if day > max_day:
            return None
        if "tenant" in w.tags or w.pid == "p_frederik":
            if day.weekday() < 5:
                cand = max(at(day, 8, 40), t if k == 0 else at(day, 8, 40))
                if cand.hour < 17 and not _blocked(cand):
                    cand += timedelta(minutes=rng.randint(0, 60))
                    if _can_write(w, cand, False):
                        return cand, cand.date() != d
            continue
        win = _window(w.pid, day)
        if win and win[1] > t:
            cand = max(win[0], t) + timedelta(minutes=rng.randint(2, 40), seconds=rng.randint(0, 59))
            if cand < win[1] and _can_write(w, cand, False):
                return cand, cand.date() != d
    return None


def _thread_mails(mailer: _Mailer, rng: random.Random, tpl: dict, day: date, roles: dict[str, Who | tuple],
                  start: datetime) -> list[_Mail]:
    params = _params(rng, day, start, future="{day" in repr(tpl["turns"]) + repr(tpl["subject"]))
    if tpl.get("needs") and tpl["needs"] not in params:
        return []
    first_body = tpl["turns"][0]["body"]
    idx, prev_len = rng.randrange(len(first_body)), len(first_body)
    subjects = tpl["subject"]
    subj = subjects[idx] if len(subjects) == prev_len else rng.choice(subjects)   # subject fits the first message
    subj = _fill(subj, params, {r: v for r, v in roles.items() if isinstance(v, Who)})
    out: list[_Mail] = []
    prev: _Mail | None = None
    t = start
    for i, turn in enumerate(tpl["turns"]):
        if i and rng.random() > turn.get("p", 1.0):
            break
        sender = roles[turn["by"]]
        if isinstance(sender, tuple):       # external address
            addr, name = sender
            per = P.Persona("ext", "external_formal", greet=("Hello {to},", "Hi {to},"),
                            sign=(("Best regards,", "{full}"), ("Kind regards,", "{full}")))
            first, full, org = name.split()[0], name, P.ORGS.get(addr.split("@")[1], "")
        else:
            addr, name, per, first, full, org = sender.email, sender.name, sender.persona, sender.first, sender.name, sender.org
        late = False
        if i:
            nxt = _sender_time(rng, sender, prev.t, MAIL_END - timedelta(days=1)) if isinstance(sender, Who) else \
                (prev.t + timedelta(minutes=rng.randint(15, 140)), False)
            if nxt is None:
                break
            t, late = nxt
            if _blocked(t) or (isinstance(sender, tuple) and not (t.weekday() < 5 and 8 <= t.hour < 18)):
                break
        if "to" in turn:
            to = []
            for r in turn["to"]:
                if r.startswith("list:"):
                    to.append(r[5:])
                else:
                    v = roles[r]
                    to.append(v[0] if isinstance(v, tuple) else v.email)
            cc = []
        elif prev.from_addr == addr:        # a follow-up to one's own message
            to, cc = list(prev.to), list(prev.cc)
        else:
            to = [prev.from_addr]
            cc = sorted({a for a in prev.to + prev.cc if a not in (addr, prev.from_addr)})
        variants = turn["body"]
        idx = idx if len(variants) == prev_len else rng.randrange(len(variants))
        prev_len = len(variants)
        content = [_fill(x, params, {r: v for r, v in roles.items() if isinstance(v, Who)})
                   for x in variants[idx]]
        body = _body(per, first, full, org, to, content, rng, late)
        m = _Mail(t=t, from_addr=addr, from_name=name, to=to, cc=cc, subject=subj if not i else _subject_re(subj),
                  body=body, message_id="", in_reply_to=prev.message_id if prev else None,
                  sender=sender if isinstance(sender, Who) else None)
        m.quote = _pick_quote(body, content)
        if m.quote is None or not _mail_ok(m) or not (MAIL_START <= t.date() <= MAIL_END):
            break
        m.message_id = mailer.mid(t, addr)
        out.append(m)
        prev = m
    return out


def _mail_roles(rng: random.Random, spec: dict[str, str], day: date) -> dict | None:
    hal = [w for w in _people().values() if "hal" in w.tags and w.pid != "p_alma"]
    if day > LAST_DAY:
        hal = [w for w in hal if w.pid != "p_hank"]
    tenants = [w for w in _people().values() if "tenant" in w.tags]
    roles: dict = {}
    for r, s in spec.items():
        if s.startswith("pid:"):
            cand = [_w(s[4:])]
            if s[4:] == "p_hank" and day > LAST_DAY:
                return None
        elif s.startswith("ext:"):
            addr, name = s[4:].split("|")
            roles[r] = (addr, name)
            continue
        elif s == "tenant":
            cand = tenants
        elif s == "hal":
            cand = hal
        else:
            cand = [w for w in hal if s in w.tags]
        cand = [w for w in cand if w not in roles.values()]
        if not cand:
            return None
        roles[r] = rng.choice(cand)
    return roles


def _mk(mailer: _Mailer, t: datetime, sender: Who | tuple, to: list[str], subject: str, content: list[str],
        rng: random.Random, cc: list[str] | None = None, reply_to: _Mail | None = None, quote: str | None = None,
        event: EventSpec | None = None, greet: str | None = None, sign: list[str] | None = None) -> _Mail:
    """One scripted email in the sender's voice."""
    if isinstance(sender, tuple):
        addr, name = sender
        body = ([greet, ""] if greet else []) + content + ([""] + sign if sign else [])
        who = None
    else:
        addr, name, who = sender.email, sender.name, sender
        body = _body(sender.persona, sender.first, sender.name, sender.org, to, content, rng)
        if greet is not None:
            body[0] = greet
    m = _Mail(t=t, from_addr=addr, from_name=name, to=list(to), cc=list(cc or []), subject=subject, body=body,
              message_id=event.attrs["message_id"] if event else mailer.mid(t, addr),
              in_reply_to=reply_to.message_id if reply_to else None, event=event, sender=who)
    m.quote = quote if quote is not None else _pick_quote(body, content)
    if event is None and (m.quote is None or not _mail_ok(m)):
        raise ValueError(f"scripted email {subject!r} has no distinctive line or a forbidden word")
    return mailer.add(m)


def _story_mail(kind: str):
    for d in story.required_docs():
        ev = d["event"]
        if ev.type == "email" and kind in ev.attrs["subject"]:
            return ev
    raise KeyError(kind)


def _scripted_mail(mailer: _Mailer) -> None:
    rng = _rng("mail", "scripted")
    fred, alma, hank, maggie, sofia, rina = (_w(p) for p in
                                             ("p_frederik", "p_alma", "p_hank", "p_maggie", "p_bg_06", "p_bg_17"))
    leila, theo, amara, jonah, marcus = (_w(p) for p in ("p_bg_04", "p_bg_01", "p_bg_02", "p_bg_03", "p_bg_05"))
    hannah, grace, mateo, owen = (_w(p) for p in ("p_bg_08", "p_bg_10", "p_bg_11", "p_bg_09"))
    d = date
    summit_sign = ["The JRR AI Summit team"]

    def S(day, h, m, subject, content, greet="Hello JRR second floor members,"):
        return _mk(mailer, at(day, h, m), P.SUMMIT, [P.L_SUMMIT], subject, content, rng, greet=greet, sign=summit_sign)

    # ---------------- AI summit (events@jrr-aisummit.example)
    S(d(2026, 2, 23), 10, 0, "AI Summit 2026: registration is open", [
        "Registration for the campus AI Summit (2 to 6 March) is now open on the summit site.",
        "Members of the JRR second floor can register free of charge with the floor member code JRR2-26.",
        "The welcome reception is on Wednesday 4 March at 18:15 in the ground-floor atrium.",
        "Talks take place in the auditorium and in the second-floor lounge."])
    S(d(2026, 2, 26), 11, 0, "AI Summit 2026: the full agenda is online", [
        "The full agenda for next week is now online.",
        "Highlights include sessions on autonomy in orbit, safety cases for ML and an AI policy panel with Lumen Policy Group.",
        "Please register by Friday so we can plan catering."])
    S(d(2026, 3, 1), 18, 0, "See you tomorrow: AI Summit week starts", [
        "The AI Summit starts tomorrow at 09:30 with the opening keynote in the auditorium.",
        "Name tags can be collected at the registration desk on the ground floor from 08:30."])
    daily = {
        d(2026, 3, 2): "Today: opening keynote at 10:00, autonomy in orbit at 14:00, poster session from 16:00.",
        d(2026, 3, 3): "Today: LLMs for test automation at 10:30, edge inference on small satellites at 14:00.",
        d(2026, 3, 4): "Today: safety cases for ML at 10:00, the AI policy panel at 13:30, welcome reception this evening.",
        d(2026, 3, 5): "Today: digital twins for test labs at 10:00, robot learning on a budget at 14:30.",
        d(2026, 3, 6): "Today: data provenance in ML pipelines at 10:00, closing session at 15:00.",
    }
    for day, line in daily.items():
        S(day, 7, 30, f"AI Summit day {(day - SUMMIT_START).days + 1}: today's programme", [
            line, "Coffee and lunch are served in the lounge on the second floor."], greet="Good morning,")
    S(d(2026, 3, 3), 15, 0, "Reminder: welcome reception on Wednesday", [
        "A reminder that the summit welcome reception takes place on Wednesday evening in the ground-floor atrium.",
        "Please bring your summit name tag."])
    rec = _story_mail("Tonight: AI Summit welcome reception")
    _mk(mailer, rec.t, P.SUMMIT, rec.attrs["to"], rec.attrs["subject"], [
        rec.quote_text, "Drinks and light food will be served until 20:30.",
        "Members of all second-floor organisations are welcome."], rng, event=rec, quote=rec.quote_text,
        greet="Hello JRR second floor members,", sign=summit_sign)
    S(d(2026, 3, 6), 16, 10, "Thank you for joining the AI Summit", [
        "Thank you for a wonderful summit week.",
        "Slides from most sessions are on the summit site. A short feedback survey is linked there as well."])
    S(d(2026, 3, 8), 10, 0, "Last chance: AI Summit feedback survey", [
        "The feedback survey closes on Monday evening. It takes about five minutes."], greet="Hello,")

    # ---------------- IT notices (Frederik) and replies; work orders match it/maintenance_calendar.csv
    it_sign_rng = rng
    n1 = _mk(mailer, at(d(2026, 2, 23), 8, 40), fred, [P.L_TENANTS], "Planned IT work on the 2nd floor this week", [
        "Planned IT work this week:",
        "- Mon 13:15-14:30, WO-3082: antivirus definition update on the Halvorsen lab laptop lt-219 (offline media)",
        "- Mon 22:00-22:40, WO-3083: firmware upgrade on access point ap-2-01",
        "- Tue 13:00-13:30, WO-3091: firmware update on camera cam-02 (west corridor)",
        "- Wed 22:00-22:40, WO-3095: firmware upgrade on access point ap-2-02",
        "- Thu 07:00-08:00, WO-3098: lens cleaning and PoE switch swap for camera cam-05 (lounge)",
        "- Thu 22:00-22:40, WO-3102: firmware upgrade on access point ap-2-03",
        "- Fri 15:00-15:45, WO-3106: printer service and drum replacement (copier vendor)",
        "Wi-Fi may drop for a few minutes during the access point upgrades."], it_sign_rng, greet="Hello,")
    _mk(mailer, at(d(2026, 2, 23), 11, 2), hannah, [fred.email], _subject_re(n1.subject), [
        "Will the printer be out of use for the whole afternoon on Friday?"], rng, cc=[P.L_TENANTS], reply_to=n1)
    _mk(mailer, at(d(2026, 2, 23), 11, 40), fred, [hannah.email], _subject_re(n1.subject), [
        "No, only 15:00 to 15:45 while the vendor replaces the drum."], rng, cc=[P.L_TENANTS],
        reply_to=mailer.mails[-1])
    n2 = _mk(mailer, at(d(2026, 3, 2), 8, 35), fred, [P.L_TENANTS], "Planned IT work on the 2nd floor this week", [
        "Planned IT work this week:",
        "- Mon 22:00-22:40, WO-3111: firmware upgrade on access point ap-2-04",
        "- Wed 07:00-07:30, WO-3115: printer paper feed repair (copier vendor)",
        "- Wed 19:00-21:30, WO-3117: monthly security patching on the Halvorsen lab laptop lt-219 (offline media)",
        "- Thu 22:00-22:40, WO-3120: firmware upgrade on access point ap-2-05",
        "- Sun 22:00-22:40, WO-3128: firmware upgrade on access point ap-2-06",
        "Summit week means more guests on the guest network. Please use JRR2-SECURE for work devices."], rng,
        greet="Hello,")
    _mk(mailer, at(d(2026, 3, 2), 9, 50), grace, [fred.email], _subject_re(n2.subject), [
        "Thanks Frederik. Could the guest network handle our demo robot on Tuesday? It streams video."], rng,
        cc=[P.L_TENANTS], reply_to=n2)
    _mk(mailer, at(d(2026, 3, 2), 10, 35), fred, [grace.email], _subject_re(n2.subject), [
        "It should, but please plug the robot into the lounge ethernet port to be safe. Logged as INC-2241."], rng,
        cc=[P.L_TENANTS], reply_to=mailer.mails[-1])
    w1 = _mk(mailer, _place("p_bg_03", d(2026, 2, 25), (14, 5)), jonah, [fred.email], "wifi in 217", [
        "wifi in 217 keeps dropping every few minutes since lunch, video calls are unusable"], rng)
    w2 = _mk(mailer, at(d(2026, 2, 25), 14, 40), fred, [jonah.email], "Re: wifi in 217", [
        "Thanks Jonah. I can't see a fault on the access point from here.",
        "Logged as INC-2207. If it happens again, note the time and I will check the controller logs."], rng,
        reply_to=w1)
    _mk(mailer, _place("p_bg_03", d(2026, 2, 25), (15, 30)), jonah, [fred.email], "Re: wifi in 217", [
        "seems ok again now, will note the time if it comes back"], rng, reply_to=w2)
    p1 = _mk(mailer, at(d(2026, 2, 26), 9, 20), hannah, [fred.email], "Printer by the kitchen", [
        "The printer by the kitchen jams on almost every second page this morning."], rng, cc=[P.L_TENANTS])
    _mk(mailer, at(d(2026, 2, 26), 10, 5), fred, [hannah.email], "Re: Printer by the kitchen", [
        "Thanks. The copier vendor is booked for Friday 15:00 under WO-3106 (service and drum replacement).",
        "Until then please use the printer in the lounge."], rng, cc=[P.L_TENANTS], reply_to=p1)
    p2 = _mk(mailer, _place("p_maggie", d(2026, 3, 3), (10, 20)), maggie, [fred.email], "Printer jamming again", [
        "The kitchen printer is jamming again! Tray 2 this time, it ate half my handout for the summit poster :("],
        rng)
    _mk(mailer, at(d(2026, 3, 3), 11, 0), fred, [maggie.email], "Re: Printer jamming again", [
        "Thanks Maggie. The paper feed repair is booked for tomorrow 07:00 under WO-3115.",
        "The lounge printer works in the meantime."], rng, reply_to=p2)

    # ---------------- facilities (work orders from it/maintenance_calendar.csv)
    fac_sign = ["Ravi Castellanos", "JRR Building Facilities"]
    for day, hm, subject, lines in [
        (d(2026, 2, 23), (9, 15), "HVAC filter change on Tuesday morning",
         ["We will change the filters on air handler 2 on Tuesday 24 February from 08:00 to 09:00 (WO-3086).",
          "You may hear some noise from the ceiling vents on the west side."]),
        (d(2026, 2, 26), (10, 0), "Thermostat calibration and weekend inspection",
         ["Thermostat calibration on air handler 2: Friday 27 February, 07:00 to 08:00 (WO-3104).",
          "Belt inspection on air handler 1: Saturday 28 February, 10:00 to 12:00 (WO-3108).",
          "Temperatures may vary a little during the work. Thank you for your patience with the cold rooms this week."]),
        (d(2026, 3, 2), (9, 0), "Lounge AV setup for summit week",
         ["The second-floor lounge will be busy on Tuesday 3 March from 09:00 to 10:30 while we set up AV for the summit (WO-3113)."]),
        (d(2026, 3, 5), (10, 0), "Lounge AV teardown and weekend filter change",
         ["Lounge AV teardown after the summit: Friday 6 March, 14:00 to 14:30 (WO-3124).",
          "Filter change on air handler 1: Saturday 7 March, 09:00 to 11:00 (WO-3126)."]),
    ]:
        _mk(mailer, at(day, *hm), P.FACILITIES2, [P.L_TENANTS], subject, lines, rng, greet="Dear tenants,",
            sign=fac_sign)

    # ---------------- Hank's resignation (story) and the week around it
    res = _story_mail("Resignation")
    r0 = _mk(mailer, res.t, hank, res.attrs["to"], res.attrs["subject"], [
        res.quote_text, "My last working day will be Friday 6 March so that I can hand over my work.",
        "I will put the handover notes in the engineering folder."], rng, event=res, quote=res.quote_text,
        greet="Sofia, Alma,")
    r1 = _mk(mailer, _place("p_bg_06", RESIGN_DAY, (9, 48)), sofia, [hank.email], "Re: Resignation", [
        "Thank you for telling me in person this morning, and for the note.",
        "I am sorry to see you go, but I understand. Let's use the week for a proper handover, with the test stand scripts first.",
        "I will tell the team later this morning."], rng, cc=[alma.email], reply_to=r0)
    r2 = _mk(mailer, _place("p_alma", RESIGN_DAY, (10, 20)), alma, [hank.email], "Re: Resignation", [
        "Thank you for your notice.",
        "As part of standard offboarding, your access to room 219 will be removed at 17:00 today.",
        "Your access to the 217 suite and your accounts remain active until the end of Friday 6 March for the handover.",
        "Please return your laptop and any other Halvorsen equipment to me on Friday afternoon."], rng,
        cc=[sofia.email], reply_to=r1)
    _mk(mailer, _place("p_hank", RESIGN_DAY, (10, 41)), hank, [alma.email], "Re: Resignation", ["Understood."],
        rng, cc=[sofia.email], reply_to=r2, quote="Understood.")
    tn = _mk(mailer, _place("p_bg_06", RESIGN_DAY, (11, 30)), sofia, [P.L_ALL], "Team news", [
        "I wanted to let you know that Hank has resigned. His last day with us will be this Friday, 6 March.",
        "Hank has been part of Halvorsen for over four years and much of our test infrastructure was built by him.",
        "Please make time for handover where Leila asks for it, and join me in wishing him well."], rng)
    _mk(mailer, _place("p_bg_17", RESIGN_DAY, (12, 5)), rina, [sofia.email], "Re: Team news", [
        "Thanks Sofia. Hank, good luck with the next step, and thanks for all the help with the test bench."], rng,
        cc=[P.L_ALL], reply_to=tn)
    _mk(mailer, _place("p_bg_04", RESIGN_DAY, (13, 40)), leila, [P.L_ENG], "Handover plan for Hank's work", [
        "Handover sessions with Hank this week: Tuesday 14:00 and Thursday 14:00 in the meeting room.",
        "Theo takes the test stand scripts, Amara the valve timing sweep.",
        "Please add questions to the handover doc before the sessions."], rng)
    fl = _mk(mailer, _place("p_maggie", d(2026, 3, 3), (11, 20)), maggie, [P.L_ALL], "Farewell lunch for Hank, Friday 12:30", [
        "Let's give Hank a proper send-off! Farewell lunch on Friday 6 March at 12:30 at the dumpling spot near the station.",
        "Reply to me so I can book the right table size!",
        "Sofia is collecting for a card, it's on her desk."], rng)
    prev = fl
    for i, (w, line) in enumerate([(theo, "Count me in."), (amara, "Yes please! I will bring the card over."),
                                   (jonah, "in, thanks for organizing"), (rina, "I will be there."),
                                   (marcus, "In. Do we need a speech? Asking for a friend.")]):
        tt = _place(w.pid, d(2026, 3, 3), divmod(11 * 60 + 45 + 9 * i, 60))
        _mk(mailer, tt, w, [maggie.email], "Re: Farewell lunch for Hank, Friday 12:30", [line], rng, reply_to=fl,
            quote=line)
    _mk(mailer, _place("p_maggie", d(2026, 3, 3), (14, 30)), maggie, [P.L_ALL],
        "Re: Farewell lunch for Hank, Friday 12:30", [
            "Table booked for nine on Friday at 12:30!! Meet at the elevators at 12:20."], rng, reply_to=prev)

    # ---------------- Sofia's Monday priorities and Friday weekly updates
    for day in (d(2026, 2, 23), d(2026, 3, 2), CASE_DAY):
        lines = {
            d(2026, 2, 23): ["Priorities for this week:", "- design review for the mounting plate redesign on Thursday",
                             "- lab calibration schedule, see Rina's post", "- summit registration by Friday"],
            d(2026, 3, 2): ["Priorities for summit week:", "- keep the review schedule, sessions are optional",
                            "- handover from Hank, Leila is coordinating", "- weekly updates on Friday as usual"],
            CASE_DAY: ["Priorities for this week:", "- redistribute Hank's open items, Leila will share a list",
                       "- vibration test results by Thursday", "- summit follow-ups with the other tenants"],
        }[day]
        tt = _place("p_bg_06", day, (8, 55)) if day != CASE_DAY else at(day, 8, 55)
        _mk(mailer, tt, sofia, [P.L_ALL], f"Week of {day.day} {'February' if day.month == 2 else 'March'}", lines,
            rng)
    for day in (d(2026, 2, 27), LAST_DAY):
        ask = _mk(mailer, _place("p_bg_06", day, (9, 30)), sofia, [P.L_ENG], f"Weekly updates, {WEEKDAYS[day.weekday()]} {day.day} {'February' if day.month == 2 else 'March'}", [
            "Please reply with your weekly update by 16:00: done, next, blockers.",
            "Two or three bullets each is plenty."], rng)
        r = _rng("mail", "weekly", day.isoformat())
        for i, w in enumerate([theo, amara, jonah, marcus, maggie, hank, rina, leila]):
            t1, t2, t3 = r.sample(P.TOPICS, 3)
            if not _window(w.pid, day):
                continue
            if w.pid == "p_hank":
                content = ["Done: handover doc final, test stand scripts and valve timing sweep handed over."
                           if day == LAST_DAY else f"Done: {t1}, {r.choice(P.STATUS).format(day='Tuesday')}.",
                           "Next: nothing." if day == LAST_DAY else f"Next: {t2}."]
            else:
                content = ["Done:", f"- {t1}: {r.choice(P.STATUS).format(day='Tuesday')}",
                           f"- {t2}: {r.choice(P.STATUS).format(day='Wednesday')}", "Next:", f"- {t3}",
                           "Blockers: none" if r.random() < 0.7 else "Blockers: waiting on machine shop parts"]
            tt = _place(w.pid, day, (10 + i // 2, 10 + 13 * (i % 2) + r.randint(0, 9)))
            _mk(mailer, tt, w, [sofia.email], _subject_re(ask.subject), content, rng, reply_to=ask)

    # ---------------- security notices
    v = _mk(mailer, _place("p_alma", d(2026, 2, 27), (9, 40)), alma, [P.L_ALL], "Visitors during summit week", [
        "During the AI Summit (2 to 6 March) the floor will have many visitors.",
        "Please make sure that your visitors sign in at the front desk and are accompanied in the Halvorsen suite at all times.",
        "Please keep the door to 217 closed, and do not let people you do not know follow you into the suite.",
        "Secure rooms remain restricted to authorised staff."], rng, greet="Dear colleagues,")
    _mk(mailer, _place("p_bg_06", d(2026, 2, 27), (10, 5)), sofia, [alma.email], "Re: Visitors during summit week", [
        "Thanks Alma, I will repeat this at standup on Monday."], rng, reply_to=v)

    # ---------------- tenants writing to Halvorsen
    _mk(mailer, at(d(2026, 2, 24), 14, 20), mateo, [leila.email], "Panel invitation: AI policy for space hardware", [
        "Lumen Policy Group is hosting the AI policy panel at the summit on Wednesday 4 March at 13:30.",
        "Would you or a colleague join as a panelist for 45 minutes? We would love an engineering view."], rng)
    _mk(mailer, _place("p_bg_04", d(2026, 2, 24), (16, 10)), leila, [mateo.email],
        "Re: Panel invitation: AI policy for space hardware", [
            "Thank you for thinking of us. I would be happy to join the panel.",
            "Could you send the questions a few days before?"], rng, reply_to=mailer.mails[-1])
    _mk(mailer, at(d(2026, 2, 25), 9, 30), mateo, [leila.email], "Re: Panel invitation: AI policy for space hardware", [
        "Wonderful. Questions will follow by Friday. Thank you!"], rng, reply_to=mailer.mails[-1])
    fr = _mk(mailer, at(d(2026, 2, 26), 15, 10), owen, [P.L_TENANTS], "Shared kitchen fridge clean-out on Friday", [
        "The shared kitchen fridge will be cleaned out on Friday at 15:00.",
        "Anything without a name and date goes, including the mystery jar on the top shelf."], rng)
    _mk(mailer, _place("p_bg_05", d(2026, 2, 26), (15, 40)), marcus, [owen.email], _subject_re(fr.subject), [
        "the mystery jar is mine, it is pickles and it is fine. labeling it now"], rng, cc=[P.L_TENANTS], reply_to=fr)
    _mk(mailer, at(d(2026, 3, 3), 13, 15), grace, [theo.email], "Summit demo feedback", [
        "Thanks for stopping by our booth this morning. The tip about the cable strain relief was spot on.",
        "If you have time on Thursday, we would like to show you the revised setup."], rng)

    # ---------------- 2026-03-09: Alma opens the case
    sr = _mk(mailer, at(CASE_DAY, 8, 45), alma, [sofia.email], "Security review: room 219", [
        "As discussed this morning, I have opened a security review concerning access to room 219 on the evening of Wednesday 4 March.",
        "I am collecting the relevant records today and will speak with a small number of people this afternoon.",
        "Please keep this confidential for now."], rng)
    _mk(mailer, at(CASE_DAY, 9, 4), sofia, [alma.email], "Re: Security review: room 219", [
        "Thanks Alma. Understood. Let me know if you need anything from me or from the team."], rng, reply_to=sr)
    hq = _story_mail("Room 219 access on March 4")
    a1 = _mk(mailer, at(CASE_DAY, 9, 31), alma, [hank.email], "Room 219 access on March 4", [
        "I am reviewing access to room 219 and to the lab laptop lt-219 on the evening of Wednesday 4 March.",
        "Could you please confirm in writing whether you accessed room 219, or any files stored on lt-219, that day?",
        "I would also like to speak with you in person this afternoon at 14:00 in the 217 meeting room."], rng)
    hq_mail = _mk(mailer, hq.t, hank, hq.attrs["to"], hq.attrs["subject"], [
        "My access to 219 was removed on the Monday. You know that.", hq.quote_text, "14:00 is fine."], rng,
        reply_to=a1, event=hq, quote=hq.quote_text, greet="Alma,")
    _mk(mailer, at(CASE_DAY, 10, 32), alma, [hank.email], "Re: Room 219 access on March 4", [
        "Thank you for your reply. I will see you at 14:00 in the 217 meeting room."], rng, reply_to=hq_mail)
    m1 = _mk(mailer, at(CASE_DAY, 11, 10), alma, [maggie.email], "Short interview this afternoon", [
        "As part of a security review I would like to speak with you this afternoon at 15:30 in the 217 meeting room.",
        "It should take about 20 minutes."], rng)
    _mk(mailer, at(CASE_DAY, 11, 26), maggie, [alma.email], "Re: Short interview this afternoon", [
        "Sure, 15:30 works! See you then."], rng, reply_to=m1)
    f1 = _mk(mailer, at(CASE_DAY, 11, 15), alma, [fred.email], "Interview this afternoon: lt-219 maintenance", [
        "I would like to go through last week's maintenance work on lt-219 with you this afternoon at 16:30 in the 217 meeting room."],
        rng)
    _mk(mailer, at(CASE_DAY, 11, 42), fred, [alma.email], "Re: Interview this afternoon: lt-219 maintenance", [
        "Confirmed for 16:30. I will bring the work order and the maintenance log."], rng, reply_to=f1)


@cache
def _mails() -> tuple[_Mail, ...]:
    mailer = _Mailer()
    _scripted_mail(mailer)
    total: dict[str, int] = {}
    subjects = {m.subject for m in mailer.mails}
    for day in _days(MAIL_START, MAIL_END - timedelta(days=1)):
        rng = _rng("mail", day.isoformat())
        weekend = day.weekday() >= 5
        target = MAIL_TARGET[1 if weekend else 0] + (0 if weekend else rng.randint(-3, 3))
        have = 0
        tries = 0
        used: dict[str, int] = {}
        while have < target and tries < 80:
            tries += 1
            cand = [t for t in P.EMAIL_THREADS if _day_ok(t.get("days"), day) and used.get(t["id"], 0) < 2
                    and total.get(t["id"], 0) < t.get("max", 99)]
            if weekend:
                cand = [t for t in cand if t["id"] in ("question", "expenses")]
            if not cand:
                break
            tpl = rng.choices(cand, weights=[t.get("weight", 1) for t in cand])[0]
            roles = _mail_roles(rng, tpl["roles"], day)
            if not roles or (tpl.get("no_hank_after") and day >= RESIGN_DAY
                             and any(isinstance(v, Who) and v.pid == "p_hank" for v in roles.values())):
                continue
            first = roles[tpl["turns"][0]["by"]]
            if isinstance(first, tuple) or "tenant" in first.tags or first.pid == "p_frederik":
                if weekend:
                    continue
                t0 = _rand_time(rng, at(day, 8, 50), at(day, 16, 30))
            else:
                t0 = _start_time(rng, first, day, weekend or rng.random() < first.persona.evening)
            if t0 is None or (isinstance(first, Who) and not _can_write(first, t0, True)) or _blocked(t0):
                continue
            thread = _thread_mails(mailer, rng, tpl, day, roles, t0)
            if not thread or thread[0].subject in subjects:
                continue
            subjects.add(thread[0].subject)
            used[tpl["id"]] = used.get(tpl["id"], 0) + 1
            total[tpl["id"]] = total.get(tpl["id"], 0) + 1
            for m in thread:
                mailer.add(m)
            have += len(thread)
    return tuple(sorted(mailer.mails, key=lambda m: (m.t, m.message_id)))


def email_records() -> list[Record]:
    out = []
    for m in _mails():
        if m.event is not None:
            ev, is_story = m.event, True
        else:
            ev = EventSpec(type="email", t=m.t, actor={"kind": "email", "value": m.from_addr}, device=None, room=None,
                           attrs={"from": m.from_addr, "to": list(m.to), "subject": m.subject,
                                  "message_id": m.message_id}, quote_text=m.quote)
            is_story = False
        fields = {"message_id": m.message_id, "from_name": m.from_name, "from_addr": m.from_addr, "to": list(m.to),
                  "cc": list(m.cc), "subject": m.subject, "date": m.t, "in_reply_to": m.in_reply_to,
                  "body": list(m.body)}
        out.append(Record(source=F_MBOX, t=m.t, fields=fields, events=[ev], story=is_story))
    return out


# ============================================================================================ statements, brief

def _statement_events() -> dict[str, list[EventSpec]]:
    out: dict[str, list[EventSpec]] = {}
    for d in story.required_docs():
        if d["event"].type == "statement":
            out.setdefault(d["source_file"], []).append(d["event"])
    return out


def _intro(name: str, title: str) -> str:
    return (f"This statement was taken by Alma Imhoff, Head of Security, Halvorsen Dynamics, as part of a security "
            f"review of room 219. {title} {name} was told that the interview is voluntary and that it may be "
            f"stopped at any time. The questions and answers below are recorded in the order they were given.")


def statement_records() -> list[Record]:
    evs = _statement_events()

    def q(text, evlist):
        return next(e for e in evlist if e.quote_text == text).quote_text

    out = []
    hank_f = f"{F_STATEMENTS_DIR}/hank_gibson.pdf"
    he = evs[hank_f]
    out.append(("p_hank", hank_f, he, [
        _intro("Gibson", "Mr."),
        "Q: Please describe your role and your last weeks at Halvorsen.",
        "I was a senior engineer at Halvorsen for a little over four years. I handed in my notice on Monday 2 March "
        "and spent the rest of the week on handover. Friday 6 March was my last day.",
        "Q: Where were you on the evening of Wednesday 4 March?",
        "I was at my desk in 217 in the afternoon, finishing handover notes.",
        q("I went straight home at six.", he),
        "Q: Did you attend the summit welcome reception?",
        "No. I was tired and not in the mood for a crowd.",
        "Q: Did you go into room 219 that day?",
        "My access to 219 was removed on the Monday. I answered the question about the files in my email this morning.",
        "Q: The examiner's report on lt-219 lists an external storage device. Mr. Gibson was shown its make and "
        "serial number. Do you know this device?",
        q("IT gave me that drive last year.", he),
        "Q: Is there anything else you would like to add?",
        "No.",
    ]))
    mag_f = f"{F_STATEMENTS_DIR}/maggie_price.pdf"
    me = evs[mag_f]
    out.append(("p_maggie", mag_f, me, [
        _intro("Price", "Ms."),
        "Q: How do you know Hank Gibson?",
        "Hank and I have worked together at Halvorsen for about four years, and we are friends. I was really sad "
        "when he told us he was leaving.",
        "Q: Where were you on the evening of Wednesday 4 March?",
        "I worked in 217 that day.",
        q("Hank and I left together around 6:30.", me),
        "Q: Did you see Hank go into any other room that evening?",
        "No.",
        "Q: Is there anything else you would like to add?",
        "Hank is a good person. I hope this gets sorted out quickly.",
    ]))
    fr_f = f"{F_STATEMENTS_DIR}/frederik_mendelssohn.pdf"
    fe = evs[fr_f]
    out.append(("p_frederik", fr_f, fe, [
        _intro("Mendelssohn", "Mr."),
        "Q: Please describe your role on the floor.",
        "I am an IT contractor with Ostrander IT. I look after the shared IT on the JRR second floor, including the "
        "access points, the printers and Halvorsen's isolated lab laptop lt-219.",
        "Q: What did you do on the evening of Wednesday 4 March?",
        fe[0].quote_text,
        "I badged into room 219 with my own badge just before 19:00 and logged on with my own admin account. I "
        "installed the updates from the offline patch media and restarted the laptop. I logged off shortly before "
        "21:30 and left the room.",
        "The work was announced in the weekly IT notice on Monday 2 March and is on the maintenance calendar.",
        "Q: Did you see anyone else in room 219?",
        "No, I did not see anyone else in room 219.",
        "Q: Did you notice anything unusual on lt-219?",
        "Nothing stood out to me. The patching went normally.",
    ]))
    recs = []
    for pid, src, evlist, paras in out:
        p = person(pid)
        for ev in evlist:
            assert ev.attrs["speaker"] == p["name"] and paras.count(ev.quote_text) == 1
        recs.append(Record(source=src, t=evlist[0].t, fields={
            "title": "Witness statement", "case_id": CASE_ID, "speaker": evlist[0].attrs["speaker"], "role": p["role"],
            "interviewer": INTERVIEWER, "date": evlist[0].t, "location": INTERVIEW_ROOM, "paragraphs": paras},
            events=list(evlist), story=True))
    return recs


def brief_record() -> Record:
    paras = [
        "Purpose. This brief records why Halvorsen Dynamics opened case 1010F and what was collected. It describes a "
        "suspicion only. It contains no findings and names no one as responsible.",
        "Background. Room 219 on the second floor of the JRR Building is a secure, badge-only room. It holds lt-219, "
        "an isolated laptop with no network connection that stores Halvorsen's Titan design files.",
        "What was noticed. On Monday 9 March 2026, during a routine review of access to room 219, Halvorsen security "
        "noticed activity in room 219 on the evening of Wednesday 4 March, the evening of the AI Summit welcome "
        "reception (from 18:15), when most floor members were downstairs.",
        "Question for the review. Were the project files on lt-219 accessed or taken that evening, and if so, by whom?",
        "What was collected. On 9 March 2026 Alma Imhoff, with R. Castell (forensic examiner), collected: badge reader "
        "logs for rooms 210 to 230; floor Wi-Fi access point logs; a forensic image of lt-219 (Windows security event "
        "log, local file audit log, device history); the CCTV index for the floor cameras; the IT maintenance "
        "calendar; the Halvorsen mailbox and Slack export; an account transactions extract obtained for the review; "
        "and three interview statements taken that afternoon.",
        "Period covered. Background records run from Monday 23 February to Sunday 8 March 2026. The forensic image, "
        "the interviews and this brief date from 9 March 2026.",
        "Not collected. Campus parking records are held by the campus parking office and can be requested if needed.",
        "Integrity. Every file was hashed at collection; the hashes are listed in manifest.csv. All times in the case "
        "files are EST with a fixed -05:00 offset.",
    ]
    return Record(source=F_BRIEF, t=at(CASE_DAY, 18, 0), story=True, fields={
        "title": "Incident brief", "case_id": CASE_ID, "author": "Alma Imhoff, Head of Security, Halvorsen Dynamics",
        "date": at(CASE_DAY, 18, 0), "paragraphs": paras})


def all_records() -> list[Record]:
    return email_records() + slack_records() + statement_records() + [brief_record()]


__all__ = ["email_records", "slack_records", "statement_records", "brief_record", "all_records", "DM", "CHANNELS"]
