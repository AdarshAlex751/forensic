"""Generate FAKE background behaviour events for case 1010F.

Writes data/evidence/fake/events_baseline.json: two weeks (2026-02-23 .. 2026-03-08, EST, fixed -05:00)
of normal badge, Wi-Fi and lt-219 lab-session events for everyone in inventory.csv who has a badge.

Deterministic: standard library only, one random.Random(1010), fixed iteration order, so the output is
byte-identical on every run. Run from anywhere:

    python backend/app/features/evidence/fakes/make_baseline.py

Story events (incident night etc.) are written elsewhere. This script leaves out:
  - p_alma, p_hank, p_maggie, p_frederik, p_bg_17: nothing on 2026-03-04 at or after 17:00:00
  - p_frederik: nothing at all on 2026-03-04
  - p_kim: nothing (no badge)
  - lab sessions of fmendelssohn (written elsewhere)
"""

from __future__ import annotations

import csv
import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = ROOT / "data" / "evidence"
OUT = EVIDENCE / "fake" / "events_baseline.json"

EST = timezone(timedelta(hours=-5))
START = date(2026, 2, 23)
END = date(2026, 3, 8)
INCIDENT_DAY = date(2026, 3, 4)
INCIDENT_CUTOFF = datetime(2026, 3, 4, 17, 0, 0, tzinfo=EST)
STORY_PEOPLE = {"p_alma", "p_hank", "p_maggie", "p_frederik", "p_bg_17"}

SSID = "JRR2-SECURE"
LAB_ROOM = "219"
LAB_HOST = "lt-219"
LAB_HOST_RAW = "LT-219"
LAB_ACCOUNTS = {"rokafor", "mbell", "hgibson"}  # fmendelssohn's lt-219 work is in another file

F_BADGE = "access/badge_access.csv"
F_WIFI = "network/wifi_ap_logs.csv"
F_SEC = "endpoint/security_log.csv"
F_AUDIT = "endpoint/file_audit.csv"


# ----------------------------------------------------------------------------- inputs

def load_inputs():
    with open(EVIDENCE / "devices.csv", newline="", encoding="utf-8") as f:
        devices = {r["device_id"]: r for r in csv.DictReader(f)}
    with open(EVIDENCE / "inventory.csv", newline="", encoding="utf-8") as f:
        people = list(csv.DictReader(f))
    with open(EVIDENCE / "layout_placeholder.json", encoding="utf-8") as f:
        layout = json.load(f)
    return devices, people, layout


def parse_revoked(text: str) -> dict[str, datetime]:
    out = {}
    for item in filter(None, (text or "").split(";")):
        room, when = item.split("@", 1)
        out[room] = datetime.fromisoformat(when)
    return out


# ----------------------------------------------------------------------------- helpers

def ts(t: datetime) -> str:
    return t.astimezone(EST).strftime("%Y-%m-%dT%H:%M:%S") + "-05:00"


def walk_s(a: str, b: str) -> int:
    """Crude placeholder walk time between two badge rooms (seconds)."""
    try:
        ia, ib = int(a), int(b)
    except ValueError:
        return 30

    def corr(i):
        return 0 if i <= 216 else (1 if i <= 223 else 2)

    return max(8, abs(ia - ib) * 6 + (20 if corr(ia) != corr(ib) else 0))


class Gen:
    def __init__(self):
        self.rng = random.Random(1010)
        self.devices, self.people, self.layout = load_inputs()
        self.ap_of = {}
        for ap, spaces in self.layout["ap_coverage"].items():
            for s in spaces:
                if not s.startswith("corr-"):
                    self.ap_of[s] = ap
        self.aps = sorted(self.layout["ap_coverage"])
        self.events: list[dict] = []
        self.lab_busy: dict[date, list[tuple[datetime, datetime]]] = {}

    # ------------------------------------------------------------------ event builders
    def _ev(self, t, typ, device, room, actor, attrs, sfile, quote):
        self.events.append({
            "id": None,
            "t": ts(t),
            "type": typ,
            "person": None,
            "device": device,
            "room": room,
            "actor": actor,
            "attrs": attrs,
            "source": {"file": sfile, "line": None, "quote": quote, "sha256": None},
        })

    def badge(self, t, badge, room, direction):
        rdr = f"rdr-{room}"
        self._ev(t, "badge_in" if direction == "IN" else "badge_out", rdr, room,
                 {"kind": "badge", "value": badge}, {"reader": rdr, "result": "GRANTED"},
                 F_BADGE, f"{ts(t)},{badge},{rdr},{direction},GRANTED")

    def wifi(self, t, mac, ap, kind):
        rssi = self.rng.randint(-75, -45)
        typ = {"ASSOC": "wifi_assoc", "DISASSOC": "wifi_disassoc", "ROAM": "wifi_roam"}[kind]
        self._ev(t, typ, ap, self.devices[ap]["room"], {"kind": "mac", "value": mac},
                 {"ap": ap, "rssi": rssi, "ssid": SSID},
                 F_WIFI, f"{ts(t)},{ap},{mac},{kind},{rssi},{SSID}")

    def logon(self, t, acct):
        self._ev(t, "logon", LAB_HOST, LAB_ROOM, {"kind": "account", "value": acct},
                 {"event_id": 4624, "logon_type": 2, "host": LAB_HOST},
                 F_SEC, f"{ts(t)},4624,{LAB_HOST_RAW},{acct},2,,,C:\\Windows\\System32\\winlogon.exe")

    def logoff(self, t, acct):
        self._ev(t, "logoff", LAB_HOST, LAB_ROOM, {"kind": "account", "value": acct},
                 {"event_id": 4634, "host": LAB_HOST},
                 F_SEC, f"{ts(t)},4634,{LAB_HOST_RAW},{acct},2,,,")

    def file_read(self, t, acct, path, nbytes):
        self._ev(t, "file_read", LAB_HOST, LAB_ROOM, {"kind": "account", "value": acct},
                 {"path": path, "bytes": nbytes, "target_volume": None, "host": LAB_HOST},
                 F_AUDIT, f"{ts(t)},{LAB_HOST_RAW},{acct},READ,{path},{nbytes},")

    # ------------------------------------------------------------------ helpers
    def sec(self, a, b):
        return timedelta(seconds=self.rng.randint(a, b))

    def neighbour_ap(self, ap):
        i = self.aps.index(ap)
        options = [self.aps[j] for j in (i - 1, i + 1) if 0 <= j < len(self.aps)]
        return self.rng.choice(options)

    def flaps(self, mac, ap, start, end, rate_per_hour):
        """Occasional roam to a neighbouring AP and back while sitting still."""
        lo, hi = start + timedelta(minutes=6), end - timedelta(minutes=6)
        t = lo
        while True:
            t = t + timedelta(minutes=self.rng.randint(15, 70))
            back = t + self.sec(90, 720)
            if back >= hi:
                break
            if self.rng.random() < rate_per_hour:
                self.wifi(t, mac, self.neighbour_ap(ap), "ROAM")
                self.wifi(back, mac, ap, "ROAM")
                t = back

    def lab_free(self, day, s, e):
        pad = timedelta(minutes=3)
        return all(e + pad <= bs or s - pad >= be for bs, be in self.lab_busy.get(day, []))

    def lab_paths(self, day, acct, before_revoke):
        mmdd = day.strftime("%m%d")
        prev = (day - timedelta(days=1)).strftime("%m%d")
        lab = [
            (f"C:\\Projects\\Lab\\calib_run_{mmdd}.csv", 40_000, 2_500_000),
            (f"C:\\Projects\\Lab\\calib_run_{prev}.csv", 40_000, 2_500_000),
            (f"C:\\Projects\\Lab\\thermal_vac_log_{mmdd}.csv", 200_000, 9_000_000),
            ("C:\\Projects\\Lab\\sop\\chamber_checklist.pdf", 180_000, 420_000),
            ("C:\\Projects\\Lab\\sensor_cal\\pt_sensor_cal.xlsx", 60_000, 300_000),
            ("C:\\Projects\\Lab\\sensor_cal\\load_cell_cal.xlsx", 60_000, 300_000),
            ("C:\\Projects\\Lab\\reports\\weekly_lab_summary.docx", 90_000, 600_000),
            ("C:\\Projects\\Lab\\fixtures\\test_stand_rev3.pdf", 1_000_000, 6_000_000),
        ]
        n = self.rng.randint(2, 6)
        picks = self.rng.sample(lab, n)
        if acct == "hgibson" and before_revoke and self.rng.random() < 0.75:
            titan = [
                ("C:\\Projects\\Titan\\thruster_v3.step", 30_000_000, 46_000_000),
                ("C:\\Projects\\Titan\\thruster_v4.step", 48_211_968, 48_211_968),
                ("C:\\Projects\\Titan\\docs\\design_review_0219.docx", 300_000, 900_000),
                ("C:\\Projects\\Titan\\test\\hotfire_summary.xlsx", 150_000, 600_000),
            ]
            picks += self.rng.sample(titan, self.rng.randint(1, 2))
        out = []
        for path, lo, hi in picks:
            out.append((path, lo if lo == hi else self.rng.randint(lo, hi)))
        return out

    # ------------------------------------------------------------------ planning
    def at(self, day, h, m=0, s=0):
        return datetime(day.year, day.month, day.day, h, m, s, tzinfo=EST)

    def place(self, free, dur, margin):
        """Pick a [s, e) of length dur inside one of the free intervals; split it. None if no room."""
        fits = [(a, b) for a, b in free if (b - a) >= dur + 2 * margin]
        if not fits:
            return None
        weights = [((b - a) - dur - 2 * margin).total_seconds() + 1 for a, b in fits]
        a, b = self.rng.choices(fits, weights=weights)[0]
        span = int(((b - a) - dur - 2 * margin).total_seconds())
        s = a + margin + timedelta(seconds=self.rng.randint(0, span))
        e = s + dur
        free.remove((a, b))
        free.extend([(a, s), (e, b)])
        free.sort()
        return s, e

    def run(self):
        badged = [p for p in self.people if p["badge"]]
        day = START
        while day <= END:
            weekend = day.weekday() >= 5
            if weekend:
                pool = [p for p in badged if p["person_id"] != "p_frederik"]
                k = self.rng.randint(2, 5)
                todays = sorted(self.rng.sample(pool, k), key=badged.index)
            else:
                todays = badged
            for p in todays:
                self.person_day(p, day, weekend)
            day += timedelta(days=1)

    def person_day(self, p, day, weekend):
        pid = p["person_id"]
        if pid == "p_frederik" and day == INCIDENT_DAY:
            return
        truncated = pid in STORY_PEOPLE and day == INCIDENT_DAY
        rng = self.rng
        badge, mac, acct = p["badge"], p["laptop_mac"], p["local_account"]
        auth = [r for r in p["authorized_rooms"].split(";") if r]
        revoked = parse_revoked(p["revoked"])
        frederik = pid == "p_frederik"
        home = p["home_room"] or (auth[0] if auth else None)
        if not home:
            return

        # attendance
        if weekend:
            arrive = self.at(day, 9, 30) + self.sec(0, 150 * 60)
            depart = arrive + self.sec(100 * 60, 300 * 60)
        elif frederik:
            if rng.random() > 0.45:
                return
            arrive = self.at(day, 9, 30) + self.sec(0, 270 * 60)
            depart = arrive + self.sec(25 * 60, 100 * 60)
        else:
            if rng.random() < 0.07:  # sick day / remote
                return
            arrive = self.at(day, 8, 0) + timedelta(seconds=int(rng.triangular(0, 7200, 2400)))
            depart = self.at(day, 16, 30) + timedelta(seconds=int(rng.triangular(0, 9000, 3600)))
        if truncated:
            depart = INCIDENT_CUTOFF  # day continues in the story file; emit nothing from here on
        if any(ts(arrive) >= ts(rv) for rm, rv in revoked.items() if rm == home):
            return

        def may_use(room, s, e):
            if room not in auth:
                return False
            rv = revoked.get(room)
            return rv is None or e < rv

        margin = timedelta(minutes=10)
        free = [(arrive, depart - (timedelta(minutes=20) if truncated else timedelta(0)))]
        lunch = None
        if not weekend and not frederik and rng.random() < 0.72:
            ls = self.at(day, 11, 45) + self.sec(0, 90 * 60)
            le = ls + self.sec(25 * 60, 60 * 60)
            if arrive + margin < ls and le + margin < free[0][1]:
                lunch = (ls, le)
                free = [(arrive, ls), (le, free[0][1])]

        moves = []  # (s, e, target, lab)
        if not frederik:
            n = rng.choices([0, 1, 2, 3, 4], weights=[2, 4, 5, 3, 1])[0] if not weekend else rng.choice([0, 0, 1])
            for _ in range(n):
                lab_capable = acct in LAB_ACCOUNTS and LAB_ROOM in auth
                if LAB_ROOM in auth and LAB_ROOM != home and rng.random() < (0.6 if lab_capable else 0.2):
                    dur = self.sec(25 * 60, 110 * 60) if lab_capable else self.sec(8 * 60, 30 * 60)
                    for _try in range(6):
                        slot = self.place(list(free), dur, margin)
                        if not slot:
                            break
                        s, e = slot
                        if not may_use(LAB_ROOM, s, e):
                            continue
                        if lab_capable and not self.lab_free(day, s, e):
                            continue
                        self.place_exact(free, s, e)
                        moves.append((s, e, LAB_ROOM, lab_capable))
                        if lab_capable:
                            self.lab_busy.setdefault(day, []).append((s, e))
                        break
                else:
                    target = rng.choices(["lounge-2", "lobby-2", "stair-e"], weights=[6, 3, 1])[0]
                    slot = self.place(free, self.sec(8 * 60, 40 * 60), margin)
                    if slot:
                        moves.append((slot[0], slot[1], target, False))
        moves.sort()

        # ------------------------------------------------------------ emit
        home_ap = self.ap_of[home]
        stays = []  # (start, end, ap) for roam flaps

        def arrive_floor(t):
            self.badge(t, badge, home, "IN")
            self.wifi(t + self.sec(30, 240), mac, home_ap, "ASSOC")

        def leave_floor(t):
            self.wifi(t - self.sec(10, 90), mac, home_ap, "DISASSOC")
            self.badge(t, badge, home, "OUT")

        arrive_floor(arrive)
        cursor = arrive
        points = [("move", m) for m in moves]
        if lunch:
            points.append(("lunch", lunch))
        points.sort(key=lambda x: x[1][0])
        for kind, item in points:
            if kind == "lunch":
                ls, le = item
                stays.append((cursor, ls, home_ap))
                leave_floor(ls)
                arrive_floor(le)
                cursor = le
                continue
            s, e, target, lab = item
            stays.append((cursor, s, home_ap))
            self.badge(s, badge, home, "OUT")
            t_ap = self.ap_of[target]
            if target.isdigit():
                w = walk_s(home, target)
                t_in = s + timedelta(seconds=w + rng.randint(0, 15))
                self.badge(t_in, badge, target, "IN")
            else:
                t_in = s + self.sec(20, 60)
            if t_ap != home_ap:
                self.wifi(t_in + self.sec(15, 90), mac, t_ap, "ROAM")
            if lab:
                self.lab_session(day, acct, t_in, e, revoked)
            stays.append((t_in, e, t_ap))
            if target.isdigit():
                self.badge(e, badge, target, "OUT")
                back = e + timedelta(seconds=walk_s(home, target) + rng.randint(0, 15))
            else:
                back = e
            self.badge(back, badge, home, "IN")
            if t_ap != home_ap:
                self.wifi(back + self.sec(15, 90), mac, home_ap, "ROAM")
            cursor = back
        stays.append((cursor, depart, home_ap))
        if not truncated:
            leave_floor(depart)

        rate = 0.35 if frederik else 0.7
        for s, e, ap in stays:
            self.flaps(mac, ap, s, e, rate)

    def place_exact(self, free, s, e):
        for a, b in free:
            if a <= s and e <= b:
                free.remove((a, b))
                free.extend([(a, s), (e, b)])
                free.sort()
                return

    def lab_session(self, day, acct, t_in, t_out, revoked):
        on = t_in + self.sec(40, 180)
        off = t_out - self.sec(30, 120)
        rv = revoked.get(LAB_ROOM)
        before_revoke = rv is None or t_out < rv
        self.logon(on, acct)
        reads = self.lab_paths(day, acct, before_revoke)
        span = int((off - on).total_seconds()) - 120
        offsets = sorted(self.rng.sample(range(60, 60 + max(span, len(reads) + 1)), len(reads)))
        for (path, nbytes), off_s in zip(reads, offsets):
            self.file_read(on + timedelta(seconds=off_s), acct, path, nbytes)
        self.logoff(off, acct)


def main():
    g = Gen()
    g.run()
    events = [e for e in g.events
              if not (e["t"] >= ts(INCIDENT_CUTOFF) and e["t"][:10] == "2026-03-04"
                      and e["actor"]["value"] in _story_ids(g))]
    events.sort(key=lambda e: (e["t"], e["source"]["file"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"wrote {len(events)} events to {OUT.relative_to(ROOT).as_posix()}")


def _story_ids(g: Gen) -> set[str]:
    """Raw identifiers (badge, mac, account) of the story people: safety net for the 17:00 cut."""
    ids = set()
    for p in g.people:
        if p["person_id"] in STORY_PEOPLE:
            ids.update(v for v in (p["badge"], p["laptop_mac"], p["local_account"]) if v)
    return ids


if __name__ == "__main__":
    main()
