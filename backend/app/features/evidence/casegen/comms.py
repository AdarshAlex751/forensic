"""Communications content of Case 1010F: the mailbox, the Slack export, the three statements and the brief.

Everything is templates (personas.py) plus seeded random.Random, one sub-seed per section, so the output is the same
on every run. No LLM calls.

  email_records()      comms/mailbox.mbox, ~300 messages 2026-02-23 .. 2026-03-09
  slack_records()      comms/slack_export/<channel>/<YYYY-MM-DD>.json, ~500 messages 2026-02-23 .. 2026-03-08
  statement_records()  statements/hank_gibson.pdf, maggie_price.pdf, frederik_mendelssohn.pdf (2026-03-09)
  brief_record()       brief.pdf, Alma's incident brief (suspicion only)
  all_records()

Events (one per line):
  - email: every non-empty body line is its own 'email' EventSpec whose quote_text is that whole line. The story
    email events from story.required_docs() are the exact objects story.py hands out, attached to their line.
  - Slack: one 'chat' EventSpec per message.
  - statements: every answer paragraph is one PDF line and one 'statement' EventSpec (attrs speaker, page). Questions,
    bracketed interviewer notes, the intro and the closing declaration produce no events.
  - brief: no events.

Consistency with the rest of the case:
  - presence.records() badge reads give each person's room at any moment. A message that says the writer is on the
    floor (personas.FLOOR_HINTS) is only sent while the writer is inside a badge room.
  - lab-219 booking / running / done messages are derived from the real lt-219 sessions (security log 4624 -> 4634).
    Only people authorised for room 219 talk about being in it; others only ask.
  - lunch threads are derived from real lunch absences in the badge data.
  - noise text is checked against personas.FORBIDDEN, and nothing is posted between 16:45 and midnight on the
    incident day except the story itself. No two Slack messages and no two email bodies are identical.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cache

from . import personas as P
from . import presence, story
from .records import EventSpec, Record
from .world import (F_BRIEF, F_MBOX, F_SEC, F_SLACK_DIR, F_STATEMENTS_DIR, INCIDENT_DAY, SEED_COMMS, at, people,
                    person, parse_ts)

CHANNELS = ["general", "halvorsen-eng", "lab-219", "random", "summit-2026"]
SLACK_START, SLACK_END = date(2026, 2, 23), date(2026, 3, 8)
MAIL_START, MAIL_END = date(2026, 2, 23), date(2026, 3, 9)
SUMMIT_START, SUMMIT_END = date(2026, 3, 2), date(2026, 3, 6)
RESIGN_DAY, LAST_DAY = date(2026, 3, 2), date(2026, 3, 6)
CASE_DAY = date(2026, 3, 9)
BLACKOUT = (at(INCIDENT_DAY, 16, 45), at(INCIDENT_DAY, 23, 59, 59))
STORY_PEOPLE = {"p_alma", "p_hank", "p_maggie", "p_frederik", "p_bg_17"}
HOME_ROOM = "217"
LAB_ROOM = "219"
CASE_ID = "1010F"
INTERVIEWER = "Alma Imhoff"
INTERVIEW_ROOM = "Halvorsen Dynamics meeting room, suite 217, JRR Building, 2nd floor"

FORBIDDEN_RE = re.compile("|".join(P.FORBIDDEN), re.I)
FLOOR_RE = re.compile("|".join(P.FLOOR_HINTS), re.I)
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Slack messages per channel per day (weekday, weekend); summit-2026 is busier during summit week.
SLACK_TARGET = {"general": (11, 0), "halvorsen-eng": (15, 0), "lab-219": (7, 0), "random": (8, 4),
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


def _hm(t: datetime) -> str:
    return f"{t.hour}:{t.minute:02d}"


def _floor_to(t: datetime, minutes: int) -> datetime:
    return t.replace(minute=t.minute - t.minute % minutes, second=0, microsecond=0)


def _ceil_to(t: datetime, minutes: int) -> datetime:
    f = _floor_to(t, minutes)
    return f if f == t else f + timedelta(minutes=minutes)


@cache
def dm_channel() -> str:
    """The Hank / Kim DM channel id, taken from the story chat events (never hard-coded here)."""
    chans = {d["event"].attrs["channel"] for d in story.required_docs() if d["event"].type == "chat"}
    if len(chans) != 1:
        raise ValueError(f"expected one DM channel in the story chat events, got {sorted(chans)}")
    return next(iter(chans))


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


@cache
def _first_names() -> frozenset[str]:
    return frozenset(w.first for w in _people().values())


def auth219(pid: str, t: datetime) -> bool:
    """True if inventory.csv authorises this person for room 219 at time t (revocations respected)."""
    p = person(pid)
    if LAB_ROOM not in (p.get("authorized_rooms") or "").split(";"):
        return False
    for rv in filter(None, (p.get("revoked") or "").split(";")):
        room, _, when = rv.partition("@")
        if room == LAB_ROOM and t >= parse_ts(when):
            return False
    return True


# ============================================================================================ presence

@cache
def _floor() -> dict[tuple[str, date], tuple[datetime, datetime]]:
    d = {(f.person_id, f.day): (f.arrive, f.depart) for f in presence.floor_days()}
    # presence.py stops the story people's incident day at the 17:00 cut (story.py owns the evening). For writing
    # purposes they are at their desks until the blackout starts.
    for pid in STORY_PEOPLE:
        if (pid, INCIDENT_DAY) in d:
            d[(pid, INCIDENT_DAY)] = (d[(pid, INCIDENT_DAY)][0], BLACKOUT[0])
    return d


@cache
def _intervals() -> dict[tuple[str, date], tuple[tuple[str, datetime, datetime], ...]]:
    """(person, day) -> ((room, in, out), ...) from the badge reads (background plus story reads before 16:45)."""
    owner = {p["badge"]: p["person_id"] for p in people() if p.get("badge")}
    reads = [r.events[0] for r in presence.records() if r.events and r.events[0].type in ("badge_in", "badge_out")]
    reads += [e for r in story.csv_records() for e in r.events
              if e.type in ("badge_in", "badge_out") and not (e.t.date() == INCIDENT_DAY and e.t >= BLACKOUT[0])]
    by: dict[tuple[str, date], list[EventSpec]] = {}
    for e in sorted(reads, key=lambda e: e.t):
        pid = owner.get(e.actor["value"])
        if pid:
            by.setdefault((pid, e.t.date()), []).append(e)
    out = {}
    for (pid, day), evs in by.items():
        open_: dict[str, datetime] = {}
        iv = []
        for e in evs:
            if e.type == "badge_in":
                for room in list(open_):              # walked into another room without an OUT read
                    iv.append((room, open_.pop(room), e.t))
                open_[e.room] = e.t
            elif e.room in open_:
                iv.append((e.room, open_.pop(e.room), e.t))
        for room, t0 in open_.items():
            end = BLACKOUT[0] if (day == INCIDENT_DAY and pid in STORY_PEOPLE) else max(t0, at(day, 18, 0))
            iv.append((room, t0, end))
        out[(pid, day)] = tuple(sorted(iv, key=lambda x: x[1]))
    return out


def _room_at(pid: str, t: datetime) -> str | None:
    room = None
    for r, a, b in _intervals().get((pid, t.date()), ()):
        if a <= t <= b:
            room = r
    return room


def _present(pid: str, t: datetime) -> bool:
    return _room_at(pid, t) is not None


def _iv_at(pid: str, room: str, t: datetime, slack: int = 120) -> tuple[str, datetime, datetime] | None:
    for iv in _intervals().get((pid, t.date()), ()):
        if iv[0] == room and iv[1] - timedelta(seconds=slack) <= t <= iv[2]:
            return iv
    return None


def _floor_ok(w: Who | None, t: datetime, texts) -> bool:
    """A text that says the writer is on the floor needs the writer inside a badge room at t."""
    if w is None or w.pid in ("p_frederik", "p_kim") or t.date() >= CASE_DAY:
        return True
    if not any(FLOOR_RE.search(x) for x in texts):
        return True
    return _present(w.pid, t)


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
    if _room_at(w.pid, t) == LAB_ROOM:
        return False                    # busy on the bench in 219 (only the lab session messages come from there)
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


def _next_present(pid: str, t: datetime, limit_min: int, step: int = 1) -> datetime | None:
    for k in range(0, limit_min + 1, step):
        c = t + timedelta(minutes=k)
        if _present(pid, c) and not _blocked(c):
            return c
    return None


# ============================================================================================ lab sessions

@cache
def _lab_sessions() -> tuple[tuple[str, datetime, datetime, str], ...]:
    """Real lt-219 sessions by the lab users: (person_id, logon, logoff, task). Incident evening excluded."""
    acc = {p["local_account"]: p["person_id"] for p in people()
           if p.get("local_account") and p["person_id"] in P.LAB_TASKS}
    evs = []
    for r in list(presence.records()) + story.csv_records():
        if r.source != F_SEC:
            continue
        for e in r.events:
            if e.type in ("logon", "logoff") and e.actor and e.actor.get("value") in acc and not _blocked(e.t):
                evs.append(e)
    out, open_ = [], {}
    for e in sorted(evs, key=lambda e: e.t):
        a = e.actor["value"]
        if e.type == "logon":
            open_[a] = e.t
        elif a in open_:
            on = open_.pop(a)
            pid = acc[a]
            if auth219(pid, on):
                task = _rng("lab-task", pid, on.isoformat()).choice(P.LAB_TASKS[pid])
                out.append((pid, on, e.t, task))
    return tuple(sorted(out, key=lambda s: s[1]))


def _had_219(pid: str, t: datetime) -> bool:
    """Was in room 219 earlier the same day (interval ended before t)."""
    return any(r == LAB_ROOM and b < t for r, a, b in _intervals().get((pid, t.date()), ()))


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


def _lc_first(text: str) -> str:
    """Lower-case the first letter unless the text starts with a name, 'I', an acronym or a symbol."""
    word = re.split(r"[ ,.!?:']", text, maxsplit=1)[0]
    if len(word) > 1 and word.isalpha() and word[0].isupper() and word[1:].islower() and word not in _first_names():
        return text[0].lower() + text[1:]
    return text


def _alts(base: str, name: str | None) -> list[str]:
    """Natural rewordings used when the plain text is already taken somewhere in the export."""
    out = []
    if name:
        out.append(f"{base[:-1]}, {name}{base[-1]}" if base[-1:] in ".!?" else f"{base}, {name}")
        out.append(f"{name}, {_lc_first(base)}")
    else:
        out += [f"Hey all, {_lc_first(base)}", f"Quick one: {_lc_first(base)}"]
    return out


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
               n=rng.randint(2, 9), m=rng.randint(1, 9), talk=rng.choice(P.TALKS), food=rng.choice(P.FOOD),
               slot_min=base)
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
    base: str = ""                      # template text before styling (anecdotes are told once)


class _Slack:
    def __init__(self):
        self.msgs: list[_Msg] = []
        self.taken: set[str] = set()
        self.once_bases: set[str] = set()   # anecdote lines already told by someone

    def add(self, m: _Msg) -> _Msg:
        if m.text in self.taken:
            raise ValueError(f"duplicate Slack text {m.text!r}")
        self.msgs.append(m)
        self.taken.add(m.text)
        return m

    def say(self, w: Who, base: str, rng: random.Random, t: datetime, addressee: str | None = None,
            once: bool = False, late: bool = False) -> str | None:
        """w's version of base, unique in the export, allowed by the text and floor guards; None if impossible."""
        for c in [base] + ([] if once else _alts(base, addressee)):
            text = _stylize(c, w.persona, rng)
            if late:
                lp = rng.choice(w.persona.late)
                text = f"{lp} {text}" if lp[-1] in ".!?" else f"{lp} - {text}"
            if _slack_ok(text) and text not in self.taken and _floor_ok(w, t, [c, text]):
                return text
        return None


def _channel_members(ch: str, day: date) -> list[Who]:
    hal = [w for w in _people().values() if "hal" in w.tags and w.pid != "p_alma"]
    if day > LAST_DAY:
        hal = [w for w in hal if w.pid != "p_hank"]
    if ch == "lab-219":
        return [w for w in hal if "lab" in w.tags]
    if ch == "halvorsen-eng":
        return [w for w in hal if w.tags & {"eng", "pm", "lab", "ops"}]
    return hal


def _pool(tag: str, members: list[Who], day: date) -> list[Who]:
    noon = at(day, 12, 0)
    if tag == "hal":
        return members
    if tag == "rina":
        return [w for w in members if w.pid == "p_bg_17"]
    if tag == "lab_user":
        return [w for w in members if "lab" in w.tags and w.pid != "p_bg_17"]
    if tag == "auth219":
        return [w for w in members if auth219(w.pid, noon)]
    if tag == "lab_ask":
        return [w for w in members if "lab" in w.tags and not auth219(w.pid, noon)]
    return [w for w in members if tag in w.tags]


def _day_ok(spec: str | None, day: date) -> bool:
    wd = day.weekday()
    return {
        None: True, "weekday": wd < 5, "weekend": wd >= 5, "fri": wd == 4, "mon": wd == 0,
        "pre_summit": day < SUMMIT_START, "summit_first": day == SUMMIT_START, "summit": SUMMIT_START <= day <= SUMMIT_END,
        "pre_0302": day < RESIGN_DAY, "to_0305": day <= date(2026, 3, 5),
        "printer": day in (date(2026, 2, 26), date(2026, 2, 27), date(2026, 3, 3)),
    }[spec]


def _sim_thread(sl: _Slack, rng: random.Random, ch: str, tpl: dict, roles: dict[str, Who], params: dict,
                t0: datetime, home: bool) -> list[_Msg]:
    """Play a thread from t0: replies within minutes when the person is around, a late 'sorry, just saw this'
    when they come back later the same day, or the thread just stops. Nothing is added to sl here."""
    out: list[_Msg] = []
    taken_here: set[str] = set()
    t, last = t0, None
    idx, prev_len = 0, 0
    once = bool(tpl.get("once"))
    for i, (role, variants) in enumerate(tpl["turns"]):
        w = roles[role]
        # a turn with as many variants as the previous one continues the same branch (replies fit the question)
        idx = idx if len(variants) == prev_len else rng.randrange(len(variants))
        prev_len = len(variants)
        base = _fill(variants[idx], params, roles)
        late = False
        if i:
            gap = rng.uniform(0.2, 1.5) if role == last else rng.choice([0.6, 1, 1.5, 2, 3, 4, 6, 9]) * rng.uniform(0.8, 1.3)
            t = t + timedelta(minutes=gap, seconds=rng.randint(0, 50))
            if not _can_write(w, t, home):
                win = _window(w.pid, t.date())
                if not home and win and win[0] > t:
                    t, late = win[0] + timedelta(minutes=rng.randint(3, 35), seconds=rng.randint(0, 59)), True
                elif home and rng.random() < w.persona.evening * 2 and t.date().weekday() < 5:
                    t, late = max(t, at(t.date(), 19, 35)) + timedelta(minutes=rng.randint(0, 80)), True
                else:
                    break
                if not _can_write(w, t, home):
                    break
            elif role != last and not home and rng.random() < 0.07:
                later = t + timedelta(minutes=rng.randint(40, 150), seconds=rng.randint(0, 59))
                if _can_write(w, later, False):      # busy for a while, then answers
                    t, late = later, True
        if home and _present(w.pid, t):
            break                                    # a from-home thread is never written from a desk
        if once and base in sl.once_bases:
            break
        addressee = roles[last].first if last and roles[last] is not w else None
        sl.taken |= taken_here
        text = sl.say(w, base, rng, t, addressee=addressee, once=once, late=late)
        sl.taken -= taken_here
        if text is None or text in taken_here:
            break
        taken_here.add(text)
        out.append(_Msg(ch, t, w.handle, text, late=late, base=base))
        last = role
    return out


def _assign(rng: random.Random, roles_spec: dict[str, str], members: list[Who], day: date) -> dict[str, Who] | None:
    roles: dict[str, Who] = {}
    for r, tag in roles_spec.items():
        if tag.startswith("pid:"):
            cand = [_w(tag[4:])]
        else:
            cand = [w for w in _pool(tag, members, day) if w not in roles.values()]
        if not cand:
            return None
        roles[r] = rng.choice(cand)
    return roles


def _start_time(rng: random.Random, w: Who, day: date, home: bool) -> datetime | None:
    if home:
        for _ in range(12):
            t = _rand_time(rng, at(day, 10, 0), at(day, 21, 0)) if day.weekday() >= 5 else \
                _rand_time(rng, at(day, 19, 40), at(day, 21, 40))
            if not _present(w.pid, t):
                return t
        return None
    win = _window(w.pid, day)
    if win:
        return _rand_time(rng, win[0], win[1])
    return None


def _place(pid: str, day: date, hm: tuple[int, int], home: bool = False) -> datetime:
    """Requested time if the person can write then (inside a badge room when they are on the floor that day), else
    the nearest such time inside their window that day."""
    w = _w(pid)
    t = at(day, *hm)
    win = _window(pid, day)
    if not win:
        if _can_write(w, t, home) or day >= CASE_DAY or "hal" not in w.tags:
            return t                                        # no presence data for 03-09; externals keep office hours
        return at(day, 20, 0) + timedelta(minutes=hm[1] % 40)  # not on the floor that day: answers from home
    t = min(max(t, win[0] + timedelta(minutes=2)), win[1] - timedelta(minutes=10))
    for k in range(0, 240):
        for c in (t + timedelta(minutes=k), t - timedelta(minutes=k)):
            if win[0] <= c <= win[1] and _present(pid, c) and _can_write(w, c, False):
                return c
    return t


@cache
def _handover_slots() -> dict[date, tuple[int, int]]:
    """Handover session times (Tuesday 3 / Thursday 5 March) when Hank, Leila, Theo and Amara are all in."""
    out = {}
    for day in (date(2026, 3, 3), date(2026, 3, 5)):
        best = None
        for hm in [(14, 0), (14, 30), (15, 0), (15, 30), (16, 0), (13, 30), (13, 0), (11, 0), (10, 30)]:
            t = at(day, *hm)
            score = sum(_present(pid, t + timedelta(minutes=k))
                        for pid in ("p_hank", "p_bg_04", "p_bg_01", "p_bg_02") for k in (0, 20, 40, 55))
            if best is None or score > best[0]:
                best = (score, hm)
        out[day] = best[1]
    return out


def _slot_txt(hm: tuple[int, int]) -> str:
    return f"{hm[0]}:{hm[1]:02d}"


def _scripted_slack() -> list[tuple[str, date, tuple[int, int], list[tuple[str, str]]]]:
    """Fixed beats of the week: (channel, day, (h, m), [(person_id, text), ...])."""
    d = date
    hs = _handover_slots()
    tue, thu = _slot_txt(hs[d(2026, 3, 3)]), _slot_txt(hs[d(2026, 3, 5)])
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
            ("p_bg_04", f"Booked Tuesday {tue} and Thursday {thu} in the meeting room."),
            ("p_bg_01", "I can take the test stand scripts."),
            ("p_hank", "Ok. Notes will be in the handover doc."),
        ]),
        ("general", d(2026, 3, 3), (11, 5), [
            ("p_maggie", "Farewell lunch for Hank on Friday at 12:30, catered, in the 217 meeting room! Who is in??"),
            ("p_bg_01", "In."),
            ("p_bg_02", "Yes!!"),
            ("p_bg_03", "in"),
            ("p_bg_05", "in, as long as someone else does the speech"),
            ("p_bg_06", "In. Lunch is on Halvorsen :)"),
            ("p_bg_04", "Count me in!"),
            ("p_maggie", "Yay! Ordering food for everyone :tada:"),
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
            ("p_maggie", "Reminder: Hank's farewell lunch is tomorrow at 12:30 in the 217 meeting room, the food is ordered!"),
            ("p_bg_02", "Can't wait!"),
            ("p_bg_06", "The card is on my desk if anyone has not signed it yet."),
        ]),
        ("halvorsen-eng", d(2026, 3, 5), (14, 50), [
            ("p_hank", "Handover doc updated. Valve timing sweep section done."),
            ("p_bg_02", "Thanks Hank, super clear."),
        ]),
        ("general", d(2026, 3, 6), (12, 25), [
            ("p_maggie", "Food is here! 217 meeting room, come grab a plate :tada:"),
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


def _add_scripted_slack(sl: _Slack) -> None:
    rng = _rng("slack", "scripted")
    for ch, day, hm, lines in _scripted_slack():
        t = _place(lines[0][0], day, hm)
        last = None
        for i, (pid, text) in enumerate(lines):
            w = _w(pid)
            if i:
                t += timedelta(minutes=(rng.uniform(0.2, 1.2) if pid == last else rng.uniform(0.5, 4)),
                               seconds=rng.randint(0, 40))
                if not _can_write(w, t, False):
                    win = _window(pid, day)
                    if not (win and win[0] > t):
                        continue
                    t = win[0] + timedelta(minutes=rng.randint(4, 30))
                    lp = w.persona.late[0]
                    text = f"{lp} {text}" if lp[-1] in ".!?" else f"{lp} - {text}"
            if not _floor_ok(w, t, [text]):
                nt = _next_present(pid, t, 20)
                if nt is None:
                    continue
                t = nt
            if not _slack_ok(text):
                raise ValueError(f"scripted Slack text not allowed: {text!r}")
            sl.add(_Msg(ch, t, w.handle, text))
            last = pid


def _add_lab_slack(sl: _Slack) -> None:
    """lab-219 messages from the real lt-219 sessions: booking earlier that day (from the desk in 217) or a 'starting'
    note from 219, an optional 'running' note, and 'done' after logoff while the person is still in 219."""
    for pid, on, off, task in _lab_sessions():
        day = on.date()
        if not SLACK_START <= day <= SLACK_END:
            continue
        rng = _rng("lab-msg", pid, on.isoformat())
        w = _w(pid)
        iv = _iv_at(pid, LAB_ROOM, on)
        t_in = iv[1] if iv else on - timedelta(minutes=2)
        t_out = iv[2] if iv else None
        vals = dict(a=_hm(_floor_to(t_in, 15)), b=_hm(_ceil_to(off, 15)), task=task, Task=task[:1].upper() + task[1:])
        booked = None
        fl = _floor().get((pid, day))
        if fl:
            hi = t_in - timedelta(minutes=15)
            lo = max(fl[0] + timedelta(minutes=3), hi - timedelta(minutes=150), at(day, 7, 30))
            for _ in range(30):
                if hi <= lo:
                    break
                c = _rand_time(rng, lo, hi)
                if _room_at(pid, c) == HOME_ROOM and not _blocked(c):
                    booked = c
                    break
        if booked:
            text = sl.say(w, rng.choice(P.LAB_BOOK).format(**vals), rng, booked)
            if text:
                sl.add(_Msg("lab-219", booked, w.handle, text))
            if rng.random() < 0.35:
                others = [o for o in _channel_members("lab-219", day) if o.pid != pid]
                if others:
                    o = rng.choice(others)
                    tr = booked + timedelta(minutes=rng.randint(1, 8), seconds=rng.randint(0, 59))
                    if tr < t_in and _can_write(o, tr, False):
                        rt = sl.say(o, rng.choice(P.LAB_REPLY).format(n=rng.randint(1, 8)), rng, tr, addressee=w.first)
                        if rt:
                            sl.add(_Msg("lab-219", tr, o.handle, rt))
            if rng.random() < 0.4:
                trun = on + timedelta(seconds=rng.randint(60, 240))
                if trun < off - timedelta(minutes=2) and _room_at(pid, trun) == LAB_ROOM:
                    text = sl.say(w, rng.choice(P.LAB_RUNNING).format(**vals), rng, trun)
                    if text:
                        sl.add(_Msg("lab-219", trun, w.handle, text))
        else:
            ts = t_in + timedelta(seconds=rng.randint(60, 200))
            if ts < off and _room_at(pid, ts) == LAB_ROOM and not _blocked(ts):
                text = sl.say(w, rng.choice(P.LAB_START).format(**vals), rng, ts)
                if text:
                    sl.add(_Msg("lab-219", ts, w.handle, text))
        if t_out is not None and (t_out - off).total_seconds() >= 20:
            td = off + timedelta(seconds=rng.randint(10, int((t_out - off).total_seconds()) - 5))
        else:
            td = off + timedelta(seconds=rng.randint(30, 90))
        if _room_at(pid, td) in (LAB_ROOM, None) and not _blocked(td):
            text = sl.say(w, rng.choice(P.LAB_DONE).format(**vals), rng, td)
            if text:
                sl.add(_Msg("lab-219", td, w.handle, text))


def _add_lunch_slack(sl: _Slack) -> None:
    """general: lunch plans for groups who really are out of their rooms together around lunch."""
    for day in _days(SLACK_START, SLACK_END):
        if day.weekday() >= 5 or day == LAST_DAY:        # Friday 6 March is the catered lunch in 217
            continue
        rng = _rng("lunch", day.isoformat())
        members = _channel_members("general", day)
        gaps = []
        for w in members:
            ivs = _intervals().get((w.pid, day), ())
            for x, y in zip(ivs, ivs[1:]):
                s, e = x[2], y[1]
                if e - s >= timedelta(minutes=25) and at(day, 11, 20) <= s <= at(day, 13, 50):
                    gaps.append((w, s, e))
        gaps.sort(key=lambda g: g[1])
        used: set[str] = set()
        groups = []
        for g in gaps:
            if g[0].pid in used:
                continue
            mates, seen = [], {g[0].pid}
            for h in gaps:
                if h[0].pid in used or h[0].pid in seen:
                    continue
                if abs((h[1] - g[1]).total_seconds()) <= 480 and min(g[2], h[2]) - max(g[1], h[1]) >= timedelta(minutes=20):
                    mates.append(h)
                    seen.add(h[0].pid)
            if mates:
                grp = [g] + mates[:3]
                groups.append(grp)
                used |= {x[0].pid for x in grp}
        for grp in groups[:2]:
            rng.shuffle(grp)
            a_w = grp[0][0]
            slot = _floor_to(min(x[1] for x in grp), 5)
            t0 = None
            for _ in range(10):
                c = slot - timedelta(minutes=rng.randint(15, 60), seconds=rng.randint(0, 59))
                if c >= at(day, 10, 15) and _present(a_w.pid, c) and not _blocked(c):
                    t0 = c
                    break
            if t0 is None:
                continue
            food = rng.choice(P.FOOD)
            vals = dict(slot=_hm(slot), food=food, Food=food[:1].upper() + food[1:])
            thread = []
            ask = sl.say(a_w, rng.choice(P.LUNCH_ASK).format(**vals), rng, t0)
            if not ask:
                continue
            thread.append(_Msg("general", t0, a_w.handle, ask))
            sl.taken.add(ask)
            t = t0
            for mate, _, _ in grp[1:]:
                t = t + timedelta(minutes=rng.uniform(0.5, 6), seconds=rng.randint(0, 30))
                if t >= slot - timedelta(minutes=1) or not _present(mate.pid, t):
                    continue
                yes = sl.say(mate, rng.choice(P.LUNCH_YES), rng, t, addressee=a_w.first)
                if yes:
                    thread.append(_Msg("general", t, mate.handle, yes))
                    sl.taken.add(yes)
            if len(thread) < 2:
                for m in thread:
                    sl.taken.discard(m.text)
                continue
            if rng.random() < 0.4:
                stay = [w for w in members if w.pid not in {x[0].pid for x in grp}
                        and _present(w.pid, t + timedelta(minutes=1)) and _present(w.pid, slot + timedelta(minutes=10))]
                if stay:
                    c = rng.choice(stay)
                    tc = t + timedelta(minutes=rng.uniform(0.5, 3))
                    no = sl.say(c, rng.choice(P.LUNCH_NO), rng, tc, addressee=a_w.first)
                    if no and tc < slot:
                        thread.append(_Msg("general", tc, c.handle, no))
                        sl.taken.add(no)
                        t = tc
            tok = t + timedelta(minutes=rng.uniform(0.5, 3))
            if tok < slot and _present(a_w.pid, tok):
                ok = sl.say(a_w, rng.choice(P.LUNCH_OK).format(**vals), rng, tok)
                if ok:
                    thread.append(_Msg("general", tok, a_w.handle, ok))
            for m in thread:
                sl.taken.discard(m.text)
            lo, hi = thread[0].t - timedelta(minutes=3), thread[-1].t + timedelta(minutes=3)
            if any(lo <= g[-1].t and g[0].t <= hi for g in _groups(sl.msgs, "general", day)):
                continue                                 # never interleave with another conversation
            for m in thread:
                sl.add(m)


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


def _slot_ok(tpl: dict, roles: dict[str, Who], params: dict, day: date, t0: datetime) -> bool:
    """slot_check: the person who books the room at {slot} today is in a badge room for the whole half hour."""
    role = tpl.get("slot_check")
    if not role:
        return True
    s = at(day, params["slot_min"] // 60, params["slot_min"] % 60)
    return s > t0 and all(_present(roles[role].pid, s + timedelta(minutes=k)) for k in (0, 10, 20, 30))


@cache
def _slack_messages() -> tuple[_Msg, ...]:
    sl = _Slack()
    dm = dm_channel()
    # 1. story DM messages, untouched
    for d in story.required_docs():
        ev = d["event"]
        if ev.type == "chat":
            sl.add(_Msg(ev.attrs["channel"], ev.t, ev.actor["value"], ev.quote_text, ev, ev.attrs["ts"]))
    # 2. DM noise around them (Slack Connect with Kim)
    for ds, h, m, s, handle, text in P.KIM_DM_NOISE:
        sl.add(_Msg(dm, at(date.fromisoformat(ds), h, m, s), handle, text))
    # 3. scripted beats of the week, lab sessions, lunches
    _add_scripted_slack(sl)
    _add_lab_slack(sl)
    _add_lunch_slack(sl)
    # 4. generic threads until each channel-day reaches its target
    for day in _days(SLACK_START, SLACK_END):
        weekend = day.weekday() >= 5
        for ch in CHANNELS:
            rng = _rng("slack", ch, day.isoformat())
            target = SLACK_TARGET[ch][1 if weekend else 0]
            if ch == "summit-2026" and SUMMIT_START <= day <= SUMMIT_END:
                target = SUMMIT_WEEK_TARGET
            target += rng.randint(-1, 2) if target > 2 else 0
            have = sum(1 for m in sl.msgs if m.channel == ch and m.t.date() == day)
            tpls = [t for t in P.SLACK_THREADS if t["ch"] == ch and _day_ok(t.get("days"), day)
                    and (not weekend or t.get("home"))]
            if ch == "general":
                tpls = [t for t in tpls if t["id"] != "printer" or _day_ok("printer", day)]
            used: set[str] = set()
            tries = 0
            members = _channel_members(ch, day)
            busy = [(min(m.t for m in g), max(m.t for m in g)) for g in _groups(sl.msgs, ch, day)]
            while have < target and tries < 60 and tpls:
                tries += 1
                cand = [t for t in tpls if t["id"] not in used]
                if not cand:
                    break
                tpl = rng.choices(cand, weights=[t.get("weight", 1) for t in cand])[0]
                roles = _assign(rng, tpl["roles"], members, day)
                if not roles:
                    used.add(tpl["id"])
                    continue
                home = weekend or (bool(tpl.get("home")) and rng.random() < 0.35)
                first = roles[tpl["turns"][0][0]]
                t0 = _start_time(rng, first, day, home)
                if t0 is None or not _can_write(first, t0, home):
                    continue
                if "hours" in tpl and not tpl["hours"][0] <= t0.hour + t0.minute / 60 <= tpl["hours"][1]:
                    continue
                if tpl.get("needs219") and not _had_219(roles[tpl["needs219"]].pid, t0):
                    continue
                params = _params(rng, day, t0, future="{day" in repr(tpl["turns"]))
                if tpl.get("needs") and tpl["needs"] not in params:
                    continue
                if not _slot_ok(tpl, roles, params, day, t0):
                    continue
                thread = _sim_thread(sl, rng, ch, tpl, roles, params, t0, home)
                live = [m.t for m in thread if not m.late]
                span = (min(live) - timedelta(minutes=3), max(live) + timedelta(minutes=3)) if live else None
                if len(thread) < 2 or any(span[0] <= b and a <= span[1] for a, b in busy):
                    continue
                busy.append(span)
                thread = [m for m in thread if SLACK_START <= m.t.date() <= SLACK_END]
                used.add(tpl["id"])
                for m in thread:
                    sl.add(m)
                    if tpl.get("once"):
                        sl.once_bases.add(m.base)
                have += sum(1 for m in thread if m.t.date() == day)
    msgs = sl.msgs
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
    event: EventSpec | None = None      # the story event of a story email
    sender: Who | None = None


def lines_unique(body: list[str]) -> bool:
    """Every non-empty body line is on exactly one body line (the mbox writer matches quotes by substring)."""
    return all(sum(1 for b in body if line in b) == 1 for line in body if line.strip())


class _Mailer:
    def __init__(self):
        self.mails: list[_Mail] = []
        self.ids: set[str] = set()
        self.bodies: set[tuple[str, ...]] = set()
        self.id_rng = _rng("mail", "ids")

    def mid(self, t: datetime, addr: str) -> str:
        dom = addr.split("@")[1]
        while True:
            m = f"<{t:%Y%m%d%H%M%S}.{self.id_rng.getrandbits(16):04x}@{dom}>"
            if m not in self.ids:
                self.ids.add(m)
                return m

    def add(self, m: _Mail) -> _Mail:
        if tuple(m.body) in self.bodies:
            raise ValueError(f"duplicate email body: {m.subject!r}")
        self.mails.append(m)
        self.bodies.add(tuple(m.body))
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
          rng: random.Random, late: bool = False, greet: str | None = None) -> list[str]:
    """Greeting, content and sign-off in the sender's voice. Tries the other greeting / sign-off variants when one
    would make a body line a substring of another."""
    names = _greet_names(to)
    greets = [g.format(to=names) for g in per.greet] if names else ["Hello,"]
    greets = [g[:1].upper() + g[1:] for g in greets]
    if greet is not None:
        greets = [greet]
    signs = [[s.format(first=sender_first, full=sender_full, org=org) for s in blk] for blk in per.sign]
    gi, si = rng.randrange(len(greets)), rng.randrange(len(signs))
    lead = ["Sorry for the slow reply."] if late else []
    body = []
    for dg in range(len(greets)):
        for ds in range(len(signs)):
            body = [greets[(gi + dg) % len(greets)], ""] + lead + content + [""] + signs[(si + ds) % len(signs)]
            if lines_unique(body):
                return body
    return body


def _subject_re(s: str) -> str:
    return s if s.startswith("Re: ") else f"Re: {s}"


def _mail_ok(m: _Mail) -> bool:
    lines = [m.subject] + m.body
    return all(_clean(x) and "\r" not in x and "\n" not in x and not x.startswith("From ") for x in lines) \
        and lines_unique(m.body) and any(x.strip() for x in m.body)


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
    bodies: set[tuple[str, ...]] = set()
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
        if not _mail_ok(m) or not (MAIL_START <= t.date() <= MAIL_END) or not _floor_ok(m.sender, t, content) \
                or tuple(body) in mailer.bodies or tuple(body) in bodies:
            break
        bodies.add(tuple(body))
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
        rng: random.Random, cc: list[str] | None = None, reply_to: _Mail | None = None,
        event: EventSpec | None = None, greet: str | None = None, sign: list[str] | None = None) -> _Mail:
    """One scripted email in the sender's voice."""
    if isinstance(sender, tuple):
        addr, name = sender
        body = ([greet, ""] if greet else []) + content + ([""] + sign if sign else [])
        who = None
    else:
        addr, name, who = sender.email, sender.name, sender
        body = _body(sender.persona, sender.first, sender.name, sender.org, to, content, rng, greet=greet)
    m = _Mail(t=t, from_addr=addr, from_name=name, to=list(to), cc=list(cc or []), subject=subject, body=body,
              message_id=event.attrs["message_id"] if event else mailer.mid(t, addr),
              in_reply_to=reply_to.message_id if reply_to else None, event=event, sender=who)
    if event is None and not _mail_ok(m):
        raise ValueError(f"scripted email {subject!r}: forbidden word, bad line or a line that is not unique")
    if event is not None and not (lines_unique(body) and sum(1 for b in body if event.quote_text in b) == 1):
        raise ValueError(f"story email {subject!r}: quote or lines not unique")
    if not _floor_ok(who, t, content):
        raise ValueError(f"scripted email {subject!r} says the sender is on the floor at {t}, but they are not")
    return mailer.add(m)


def _story_mail(kind: str):
    for d in story.required_docs():
        ev = d["event"]
        if ev.type == "email" and kind in ev.attrs["subject"]:
            return ev
    raise KeyError(kind)


def _weekly_content(w: Who, day: date, tt: datetime, r: random.Random) -> list[str]:
    """One weekly update, in line with the person's role (Rina reports her real lab sessions of the week)."""
    t1, t2, t3 = r.sample(P.TOPICS, 3)
    if w.pid == "p_hank":
        return ["Done: handover doc final, test stand scripts and valve timing sweep handed over."
                if day == LAST_DAY else f"Done: {t1}, {r.choice(P.STATUS).format(day='Tuesday')}.",
                "Next: nothing." if day == LAST_DAY else f"Next: {t2}."]
    week = [s for s in _lab_sessions() if s[0] == w.pid and day - timedelta(days=4) <= s[1].date() <= day and s[2] < tt]
    tasks = list(dict.fromkeys(s[3] for s in week))
    blockers = "Blockers: none" if r.random() < 0.7 else "Blockers: waiting on machine shop parts"
    if w.pid == "p_bg_17":
        done = [f"- {task}: done, results in the binder" for task in tasks] or ["- calibration binder: up to date"]
        n1, n2 = r.sample(P.LAB_TOPICS, 2)
        return ["Done:"] + done + [f"- {n1}: {r.choice(['on track', 'started', 'ordered'])}", "Next:", f"- {n2}",
                                   "Blockers: none"]
    if w.pid == "p_bg_04":
        p1, p2, p3 = r.sample(P.PM_TOPICS, 3)
        return ["Done:", f"- {p1}: {r.choice(P.STATUS).format(day='Tuesday')}",
                f"- {p2}: {r.choice(P.STATUS).format(day='Wednesday')}", "Next:", f"- {p3}", blockers]
    lab = [f"- test stand: {task} done" for task in tasks[:2]]
    return ["Done:", f"- {t1}: {r.choice(P.STATUS).format(day='Tuesday')}",
            f"- {t2}: {r.choice(P.STATUS).format(day='Wednesday')}"] + lab + ["Next:", f"- {t3}", blockers]


def _scripted_mail(mailer: _Mailer) -> None:
    rng = _rng("mail", "scripted")
    fred, alma, hank, maggie, sofia, rina = (_w(p) for p in
                                             ("p_frederik", "p_alma", "p_hank", "p_maggie", "p_bg_06", "p_bg_17"))
    leila, theo, amara, jonah, marcus = (_w(p) for p in ("p_bg_04", "p_bg_01", "p_bg_02", "p_bg_03", "p_bg_05"))
    hannah, grace, mateo, owen, noah = (_w(p) for p in ("p_bg_08", "p_bg_10", "p_bg_11", "p_bg_09", "p_bg_22"))
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
            line, f"Coffee and lunch are served in the lounge on the second floor ({WEEKDAYS[day.weekday()]} menu on the summit site)."],
            greet="Good morning,")
    S(d(2026, 3, 3), 15, 0, "Reminder: welcome reception on Wednesday", [
        "A reminder that the summit welcome reception takes place on Wednesday evening in the ground-floor atrium.",
        "Please bring your summit name tag."])
    rec = _story_mail("Tonight: AI Summit welcome reception")
    _mk(mailer, rec.t, P.SUMMIT, rec.attrs["to"], rec.attrs["subject"], [
        rec.quote_text, "Drinks and light food will be served until 20:30.",
        "Members of all second-floor organisations are welcome."], rng, event=rec,
        greet="Hello JRR second floor members,", sign=summit_sign)
    S(d(2026, 3, 6), 16, 10, "Thank you for joining the AI Summit", [
        "Thank you for a wonderful summit week.",
        "Slides from most sessions are on the summit site. A short feedback survey is linked there as well."])
    S(d(2026, 3, 8), 10, 0, "Last chance: AI Summit feedback survey", [
        "The feedback survey closes on Monday evening. It takes about five minutes."], greet="Hello,")

    # ---------------- IT notices (Frederik) and replies; work orders match it/maintenance_calendar.csv
    n1 = _mk(mailer, at(d(2026, 2, 23), 8, 40), fred, [P.L_TENANTS], "Planned IT work on the 2nd floor this week", [
        "Planned IT work this week:",
        "- Mon 13:15-14:30, WO-3082: antivirus definition update on the Halvorsen lab laptop lt-219 (offline media)",
        "- Mon 22:00-22:40, WO-3083: firmware upgrade on access point ap-2-01",
        "- Tue 13:00-13:30, WO-3091: firmware update on camera cam-02 (west corridor)",
        "- Wed 22:00-22:40, WO-3095: firmware upgrade on access point ap-2-02",
        "- Thu 07:00-08:00, WO-3098: lens cleaning and PoE switch swap for camera cam-05 (lounge)",
        "- Thu 22:00-22:40, WO-3102: firmware upgrade on access point ap-2-03",
        "- Fri 15:00-15:45, WO-3106: printer service and drum replacement (copier vendor)",
        "Wi-Fi may drop for a few minutes during the access point upgrades."], rng, greet="Hello,")
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
    w2 = _mk(mailer, w1.t + timedelta(minutes=35), fred, [jonah.email], "Re: wifi in 217", [
        "Thanks Jonah. I can't see a fault on the access point from here.",
        "Logged as INC-2207. If it happens again, note the time and I will check the controller logs."], rng,
        reply_to=w1)
    _mk(mailer, _place("p_bg_03", d(2026, 2, 25), (15, 30)), jonah, [fred.email], "Re: wifi in 217", [
        "seems ok again now, will note the time if it comes back"], rng, reply_to=w2)
    p1 = _mk(mailer, _place("p_bg_08", d(2026, 2, 26), (9, 20)), hannah, [fred.email], "Printer by the kitchen", [
        "The printer by the kitchen jams on almost every second page this morning."], rng, cc=[P.L_TENANTS])
    _mk(mailer, p1.t + timedelta(minutes=45), fred, [hannah.email], "Re: Printer by the kitchen", [
        "Thanks. The copier vendor is booked for Friday 15:00 under WO-3106 (service and drum replacement).",
        "Until then please use the printer in the lounge."], rng, cc=[P.L_TENANTS], reply_to=p1)
    p2 = _mk(mailer, _place("p_maggie", d(2026, 3, 3), (10, 20)), maggie, [fred.email], "Printer jamming again", [
        "The kitchen printer is jamming again! Tray 2 this time, it ate half my handout for the summit poster :("],
        rng)
    _mk(mailer, p2.t + timedelta(minutes=40), fred, [maggie.email], "Re: Printer jamming again", [
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
    # The story quote line is used as given. The other lines (and Alma's and Sofia's replies) all say that his last
    # working day is Friday 6 March; his accounts stay active until the end of March.
    res = _story_mail("Resignation")
    r0 = _mk(mailer, res.t, hank, res.attrs["to"], res.attrs["subject"], [
        res.quote_text, "My last working day will be Friday 6 March, so that I can hand over my work.",
        "I will put the handover notes in the engineering folder."], rng, event=res,
        greet="Sofia, Alma,")
    r1 = _mk(mailer, _place("p_bg_06", RESIGN_DAY, (9, 48)), sofia, [hank.email], "Re: Resignation", [
        "Thank you for telling me in person this morning, and for the note.",
        "I am sorry to see you go, but I understand. Your last day with us will be Friday 6 March.",
        "Let's use the week for a proper handover, with the test stand scripts first.",
        "I will tell the team later this morning."], rng, cc=[alma.email], reply_to=r0)
    r2 = _mk(mailer, _place("p_alma", RESIGN_DAY, (10, 20)), alma, [hank.email], "Re: Resignation", [
        "Thank you for your notice. I have noted Friday 6 March as your last working day.",
        "As part of standard offboarding, your access to room 219 will be removed at 17:00 today.",
        "Your access to the 217 suite remains in place until the end of Friday 6 March for the handover.",
        "Your email and other Halvorsen accounts stay active until the end of March for handover and benefits questions.",
        "Please return your laptop and any other Halvorsen equipment to me on Friday afternoon."], rng,
        cc=[sofia.email], reply_to=r1)
    _mk(mailer, _place("p_hank", RESIGN_DAY, (10, 41)), hank, [alma.email], "Re: Resignation", ["Understood."],
        rng, cc=[sofia.email], reply_to=r2)
    tn = _mk(mailer, _place("p_bg_06", RESIGN_DAY, (11, 30)), sofia, [P.L_ALL], "Team news", [
        "I wanted to let you know that Hank has resigned. His last day with us will be this Friday, 6 March.",
        "Hank has been part of Halvorsen for over four years and much of our test infrastructure was built by him.",
        "Please make time for handover where Leila asks for it, and join me in wishing him well."], rng)
    _mk(mailer, _place("p_bg_17", RESIGN_DAY, (12, 5)), rina, [sofia.email], "Re: Team news", [
        "Thanks Sofia. Hank, good luck with the next step, and thanks for all the help with the test bench."], rng,
        cc=[P.L_ALL], reply_to=tn)
    hs = _handover_slots()
    _mk(mailer, _place("p_bg_04", RESIGN_DAY, (13, 40)), leila, [P.L_ENG], "Handover plan for Hank's work", [
        f"Handover sessions with Hank this week: Tuesday {_slot_txt(hs[d(2026, 3, 3)])} and Thursday "
        f"{_slot_txt(hs[d(2026, 3, 5)])} in the meeting room.",
        "Theo takes the test stand scripts, Amara the valve timing sweep.",
        "Please add questions to the handover doc before the sessions."], rng)
    # Farewell lunch: catered, in the 217 meeting room, organised by Maggie. Nobody leaves the floor for it.
    fl = _mk(mailer, _place("p_maggie", d(2026, 3, 3), (11, 20)), maggie, [P.L_ALL],
             "Farewell lunch for Hank, Friday 12:30", [
                 "Let's give Hank a proper send-off! Farewell lunch on Friday 6 March at 12:30 in the 217 meeting room.",
                 "I am ordering catering, so reply to me and I will get enough food for everyone!",
                 "Sofia is collecting for a card, it's on her desk."], rng)
    rina_in = (rina.pid, LAST_DAY) in _floor()
    for i, (w, line) in enumerate([(theo, "Count me in."), (amara, "Yes please! I will bring the card over."),
                                   (jonah, "in, thanks for organizing"),
                                   (rina, "I will be there." if rina_in else "Sorry, off on Friday, have a great send-off!"),
                                   (marcus, "In. Do we need a speech? Asking for a friend.")]):
        tt = _place(w.pid, d(2026, 3, 3), divmod(11 * 60 + 45 + 9 * i, 60))
        _mk(mailer, tt, w, [maggie.email], "Re: Farewell lunch for Hank, Friday 12:30", [line], rng, reply_to=fl)
    _mk(mailer, _place("p_maggie", d(2026, 3, 3), (14, 30)), maggie, [P.L_ALL],
        "Re: Farewell lunch for Hank, Friday 12:30", [
            "Catering is ordered for Friday at 12:30 in the 217 meeting room!! Thanks for all the replies."], rng,
        reply_to=fl)

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
            "Please reply with your weekly update by 16:00 today: done, next, blockers.",
            "Two or three bullets each is plenty." if day < LAST_DAY else
            "Short is fine. Hank, yours can just be the handover status."], rng)
        r = _rng("mail", "weekly", day.isoformat())
        for i, w in enumerate([theo, amara, jonah, marcus, maggie, hank, rina, leila]):
            if not _window(w.pid, day):
                continue
            tt = _place(w.pid, day, (10 + i // 2, 10 + 13 * (i % 2) + r.randint(0, 9)))
            _mk(mailer, tt, w, [sofia.email], _subject_re(ask.subject), _weekly_content(w, day, tt, r), rng,
                reply_to=ask)

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
    # Noah (Lumen Policy Group, room 230) asks Rina to look at a borrowed fixture before the reception.
    nf = _mk(mailer, _place("p_bg_22", INCIDENT_DAY, (15, 42)), noah, [rina.email], "Borrowed calibration fixture", [
        "Could you drop by 230 around six-fifteen, before the reception, and look at the load-cell calibration fixture we borrowed from you?",
        "The second channel has been reading a little high since Monday. It is on the side table by the window.",
        "Ten minutes should be plenty. Thank you, it would help us a lot before Friday's demo."], rng)
    _mk(mailer, _place("p_bg_17", INCIDENT_DAY, (16, 8)), rina, [noah.email], "Re: Borrowed calibration fixture", [
        "Sure, I will come by 230 around six-fifteen and take a look."], rng, reply_to=nf)

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
        reply_to=a1, event=hq, greet="Alma,")
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
                t0 = _start_time(rng, first, day, False) if not weekend and rng.random() >= first.persona.evening \
                    else (_start_time(rng, first, day, False) or _start_time(rng, first, day, True))
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
    """One Record per email; one 'email' EventSpec per non-empty body line (the story event on its own line)."""
    out = []
    for m in _mails():
        attrs = {"from": m.from_addr, "to": list(m.to), "subject": m.subject, "message_id": m.message_id}
        evs = []
        for line in m.body:
            if not line.strip():
                continue
            if m.event is not None and m.event.quote_text in line:
                evs.append(m.event)
            else:
                evs.append(EventSpec(type="email", t=m.t, actor={"kind": "email", "value": m.from_addr}, device=None,
                                     room=None, attrs=dict(attrs, to=list(m.to)), quote_text=line))
        fields = {"message_id": m.message_id, "from_name": m.from_name, "from_addr": m.from_addr, "to": list(m.to),
                  "cc": list(m.cc), "subject": m.subject, "date": m.t, "in_reply_to": m.in_reply_to,
                  "body": list(m.body)}
        out.append(Record(source=F_MBOX, t=m.t, fields=fields, events=evs, story=m.event is not None))
    return out


# ============================================================================================ statements, brief

def fits_pdf_line(text: str) -> bool:
    """True if the text fits one body line of the PDF writer (Helvetica 11 pt)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    from . import doc_writers

    return stringWidth(" ".join(text.split()), "Helvetica", 11) <= doc_writers.max_line_width()


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


def _pages(paragraphs: list[str], quotes: list[str], src: str) -> list[int]:
    """Page of each paragraph's first line, following the layout of doc_writers._render_pdf."""
    from . import doc_writers as dw

    top, floor = dw.PAGE_H - dw.MARGIN, dw.FOOT_Y + 30
    st = {"y": top, "page": 1}

    def line(h):
        if st["y"] - h < floor:
            st["page"] += 1
            st["y"] = top
        st["y"] -= h

    line(18)
    line(18)
    st["y"] -= 4
    for _ in range(5):
        line(14)
    if st["y"] - 10 < floor:
        st["page"] += 1
        st["y"] = top
    st["y"] -= 10
    st["y"] -= 4
    out = []
    for n, para in enumerate(paragraphs):
        if n:
            st["y"] -= dw.PARA_GAP
        plines = dw._para_lines(para, [q for q in quotes if q in para], src)
        first = None
        for _ in plines:
            line(dw.LEADING)
            first = first or st["page"]
        out.append(first or st["page"])
    return out


def _device_note() -> str:
    """The interviewer's note naming the device shown to Hank (the device first seen on lt-219 that evening)."""
    dev = next(r for r in story.usb_records() if r.fields["first_install"].date() == INCIDENT_DAY)
    f = dev.fields
    return (f"[Mr. Gibson was shown the examiner's entry for a {f['vendor']} {f['product'].replace('_', ' ')} USB "
            f"device, S/N {f['serial'].split('&')[0]}.]")


def _statement(pid: str, src: str, story_evs: list[EventSpec], items: list[tuple[str, str]]) -> Record:
    """items: ('intro' | 'q' | 'note' | 'a', text). Every 'a' is one PDF line and one statement event."""
    p = person(pid)
    t = story_evs[0].t
    speaker = story_evs[0].attrs["speaker"]
    assert speaker == p["name"]
    paras = [("Q: " + x) if k == "q" else x for k, x in items]
    answers = [x for k, x in items if k == "a"]
    by_quote = {e.quote_text: e for e in story_evs}
    missing = set(by_quote) - set(answers)
    if missing:
        raise ValueError(f"{src}: story quote not used as an answer: {sorted(missing)}")
    for a in answers:
        if not fits_pdf_line(a):
            raise ValueError(f"{src}: answer does not fit one PDF line: {a!r}")
        if sum(1 for x in paras if a in x) != 1 or "  " in a or a != a.strip():
            raise ValueError(f"{src}: answer is not unique among the paragraphs: {a!r}")
    pages = _pages(paras, answers, src)
    evs = []
    for (k, x), page in zip(items, pages):
        if k != "a":
            continue
        if x in by_quote:
            ev = by_quote[x]
            if ev.attrs.get("page") != page:
                raise ValueError(f"{src}: story quote {x!r} lands on page {page}, story says {ev.attrs.get('page')}")
            evs.append(ev)
        else:
            evs.append(EventSpec(type="statement", t=t, actor={"kind": "name", "value": speaker}, device=None,
                                 room=None, attrs={"speaker": speaker, "page": page}, quote_text=x))
    return Record(source=src, t=t, story=True, events=evs, fields={
        "title": "Witness statement", "case_id": CASE_ID, "speaker": speaker, "role": p["role"],
        "interviewer": INTERVIEWER, "date": t, "location": INTERVIEW_ROOM, "paragraphs": paras})


def statement_records() -> list[Record]:
    evs = _statement_events()

    def q(text, evlist):
        return next(e for e in evlist if e.quote_text == text).quote_text

    hank_f = f"{F_STATEMENTS_DIR}/hank_gibson.pdf"
    he = evs[hank_f]
    hank = [
        ("intro", _intro("Gibson", "Mr.")),
        ("q", "Please describe your role and your last weeks at Halvorsen."),
        ("a", "I was a senior engineer at Halvorsen for a little over four years."),
        ("a", "I handed in my notice on Monday 2 March."),
        ("a", "I spent the rest of the week on handover."),
        ("a", "Friday 6 March was my last day."),
        ("q", "Where were you on the evening of Wednesday 4 March?"),
        ("a", "I was at my desk in 217 in the afternoon, finishing handover notes."),
        ("a", q("I went straight home at six.", he)),
        ("q", "Did you attend the summit welcome reception?"),
        ("a", "No. I skipped it. I was tired and not in the mood for a crowd."),
        ("q", "Did you go into room 219 that day?"),
        ("a", "My access to 219 was removed on the Monday."),
        ("a", "I answered the question about the files in my email this morning."),
        ("note", _device_note()),
        ("q", "The examiner's report on lt-219 lists this external storage device. Do you know this device?"),
        ("a", q("IT gave me that drive last year.", he)),
        ("q", "Is there anything else you would like to add?"),
        ("a", "Nothing else."),
    ]
    mag_f = f"{F_STATEMENTS_DIR}/maggie_price.pdf"
    me = evs[mag_f]
    maggie = [
        ("intro", _intro("Price", "Ms.")),
        ("q", "How do you know Hank Gibson?"),
        ("a", "Hank and I have worked together at Halvorsen for about four years."),
        ("a", "We are friends. I was really sad when he told us he was leaving."),
        ("q", "Where were you on the evening of Wednesday 4 March?"),
        ("a", "I worked in 217 that day."),
        ("a", q("Hank and I left together around 6:30.", me)),
        ("q", "Did you see Hank go into any other room that evening?"),
        ("a", "No, I did not see him go into any other room."),
        ("q", "Is there anything else you would like to add?"),
        ("a", "Hank is a good person. I hope this gets sorted out quickly."),
    ]
    fr_f = f"{F_STATEMENTS_DIR}/frederik_mendelssohn.pdf"
    fe = evs[fr_f]
    fred = [
        ("intro", _intro("Mendelssohn", "Mr.")),
        ("q", "Please describe your role on the floor."),
        ("a", "I am an IT contractor with Ostrander IT."),
        ("a", "I look after the shared IT on the JRR second floor."),
        ("a", "That includes the access points, the printers and the lab laptop lt-219."),
        ("q", "What did you do on the evening of Wednesday 4 March?"),
        ("a", fe[0].quote_text),
        ("a", "I went into room 219 with my own badge just before 19:00."),
        ("a", "I logged on with my own admin account."),
        ("a", "I installed the updates from the offline patch media and restarted the laptop."),
        ("a", "I logged off shortly before 21:30 and left the room."),
        ("a", "The work was in the weekly IT notice on Monday 2 March and on the maintenance calendar."),
        ("q", "Did you see anyone else in room 219?"),
        ("a", "No, I did not see anyone else in room 219."),
        ("q", "Did you notice anything unusual on lt-219?"),
        ("a", "Nothing stood out to me. The patching went normally."),
    ]
    return [_statement("p_hank", hank_f, he, hank), _statement("p_maggie", mag_f, me, maggie),
            _statement("p_frederik", fr_f, fe, fred)]


def brief_record() -> Record:
    acct = person("p_hank")["bank_account"]
    paras = [
        "Purpose. This brief records why Halvorsen Dynamics opened case 1010F and what was collected. It describes a "
        "suspicion only. It contains no findings and names no one as responsible.",
        "Background. Room 219 on the second floor of the JRR Building is a secure, badge-only room. It holds lt-219, "
        "an isolated laptop with no network connection that stores Halvorsen's Titan design files.",
        "Location. Julis Romo Rabinowitz Building, Princeton University, Princeton, NJ",
        "What was noticed. On Monday 9 March 2026, during a routine review of access to room 219, Halvorsen security "
        "noticed activity in room 219 on the evening of Wednesday 4 March, the evening of the AI Summit welcome "
        "reception (from 18:15), when most floor members were downstairs.",
        "Question for the review. Were the project files on lt-219 accessed or taken that evening, and if so, by whom?",
        "What was collected. On 9 March 2026 Alma Imhoff, with R. Castell (forensic examiner), collected: badge reader "
        "logs for rooms 210 to 230; floor Wi-Fi access point logs; a forensic image of lt-219 (Windows security event "
        "log, local file audit log, device history); the CCTV index for the floor cameras; the IT maintenance "
        "calendar; the Halvorsen mailbox and Slack export; an account transactions extract obtained for the review; "
        "and three interview statements taken that afternoon.",
        "CCTV. CCTV video older than 72 hours had already been overwritten under the building's retention policy when "
        "the review began; only the camera status index could be recovered.",
        f"Account records. financial/transactions.csv is an extract of checking account {acct}, provided with the "
        f"account holder H. Gibson's consent.",
        "Period covered. Background records run from Monday 23 February to Sunday 8 March 2026. The forensic image, "
        "the interviews and this brief date from 9 March 2026.",
        "Not collected. Campus parking records are held by the campus parking office and can be requested if needed.",
        "Integrity. Every file was hashed at collection; the hashes are listed in manifest.csv. All times in the case "
        "files are EST with a fixed -05:00 offset.",
    ]
    return Record(source=F_BRIEF, t=at(CASE_DAY, 18, 0), story=True, fields={
        "title": "Incident brief: The Titan Files", "case_id": CASE_ID, "author": "Alma Imhoff, Head of Security, Halvorsen Dynamics",
        "date": at(CASE_DAY, 18, 0), "paragraphs": paras})


def all_records() -> list[Record]:
    return email_records() + slack_records() + statement_records() + [brief_record()]


__all__ = ["email_records", "slack_records", "statement_records", "brief_record", "all_records", "dm_channel",
           "CHANNELS", "FLOOR_RE", "auth219", "lines_unique", "fits_pdf_line"]

