# FORMAT.md — Evidence slice output format (Person 1)

This is the exact format of every file the evidence slice gives the team. The hand-written fakes in
`data/evidence/fake/` and the real parser output in `data/evidence/` follow it field for field, so switching
`USE_REAL_EVIDENCE=true` changes the contents, never the shape.

Builds on `backend/app/shared/schema.py` and `frontend/src/shared/types.ts`. Existing fields keep their names;
this file only adds fields (CONTRACTS rule 6). Story facts come from CASE.md.

Status: **draft for team review.** Items marked *proposed* need a yes from the team before the fakes are written.

---

## 1. Files

| File | Fake location | Real location | Who reads it |
|---|---|---|---|
| `case.json` | `fake/case.json` | `case.json` | everyone, UI |
| `evidence.json` | `fake/evidence.json` | `evidence.json` | Person 3, Person 4, UI (Evidence Locker) |
| `events.json` | `fake/events.json` | `events.json` | everyone |
| `events_baseline.json` | `fake/events_baseline.json` | merged into `events.json` | Person 3 (two weeks of background behavior) |
| `events_extra.json` | `fake/events_extra.json` | appended to `events.json` after approval | Person 4 (approval and rerun) |
| `devices.csv` | — (real from day one) | `devices.csv` | everyone |
| `inventory.csv` | — (real from day one) | `inventory.csv` | Person 3 |
| `answer_key.json` | `fake/answer_key.json` (matches the fake lines) | `answer_key.json` (written by the case generator; identical to `truth/answer_key.json`) | Person 2's evaluator only. Never the system, never Person 4 |
| `truth/events_expected.json` | — | `truth/events_expected.json` | Person 1's parser tests: every event a correct parser extracts from `CASE-1010F/` and `extra/` |

In the real run, `events.json` holds every event: story, background and (after approval) extra. The fake splits
them into three files only so each is small enough to read; every event in all three has the same shape. Event IDs
are unique across the three fake files and each file is sorted by `t`, but IDs only increase with time inside the
combined story + baseline set (extra events are numbered after them, as after an approval).

The fakes are rebuilt with `python backend/app/features/evidence/fakes/make_baseline.py` then
`python backend/app/features/evidence/fakes/finalize.py`, and checked with `python -m pytest tests/evidence`.

## 2. Rules for every file

- **Encoding:** UTF-8, no BOM. JSON files are a single top-level array or object, 2-space indent.
- **Time:** ISO 8601, to the second, fixed `-05:00` offset: `2026-03-04T18:16:40-05:00`. Never `Z`, never
  `-04:00`, never without seconds, never without the offset (CONTRACTS rule 7).
- **IDs:** characters from `inventory.csv` (`p_hank`, `p_bg_17`); rooms and devices from `devices.csv`
  (`"219"`, `rdr-219`, `lt-219`, `cam-03`); events `e1`, `e2`, …
- **Empty values:** a missing scalar is `null`, never `""`. `attrs` is always an object (`{}` if empty).
- **Ordering:** `events.json` is sorted by `t`, then `source.file`, then `source.line`.
- **Line endings (case files):** the raw files in `CASE-1010F/` use LF and must be byte-exact on every
  machine, or every sha256 and the manifest break. Git currently converts line endings on Windows
  (`core.autocrlf=true`), so the repo needs a `.gitattributes` entry marking `data/evidence/CASE-1010F/**`
  and `data/evidence/extra/**` as `-text` (*proposed*, root file, Integrator).

## 3. `events.json`

Array of event objects.

| Field | Type | Status | Rule |
|---|---|---|---|
| `id` | string | existing | `e1`, `e2`, … in sorted order. Append-only: events added later (extra evidence) get the next numbers; existing IDs never change |
| `t` | string | existing | When it happened (rule above). For statements and emails: when the statement was given or the email sent |
| `type` | string | existing | One value from the list in section 3.1. Nothing else ever appears |
| `person` | string or null | existing | **Always `null` in evidence output.** The merge step fills it from the `persons.json` aliases matched against `actor` (same pattern as `verified`) |
| `device` | string or null | existing | A `device_id` from `devices.csv`: the badge reader, the Wi-Fi AP, the camera, or `lt-219` for laptop events. `null` for email, chat, statements, transactions and parking |
| `room` | string or null | existing | A room ID from `devices.csv` (`"219"`, a string), or `null` |
| `source` | object | existing | See section 3.2 |
| `actor` | object or null | **new** | The raw identifier the record contains: `{"kind": …, "value": …}`. `kind` is one of `badge`, `mac`, `account`, `email`, `slack`, `permit`, `name`. `null` only for events with no person identifier in the record (`camera_*`, `usb_mount`) |
| `attrs` | object | **new** | Type-specific fields, section 3.1 |
| `verified` | — | existing | **Never written by the evidence slice.** The merge step sets it from `verification.json` |

### 3.1 Event types and their `attrs`

| `type` | Source file | `actor.kind` | `attrs` keys |
|---|---|---|---|
| `badge_in` | `access/badge_access.csv` | `badge` | `reader`, `result` (`GRANTED` / `DENIED`) |
| `badge_out` | `access/badge_access.csv` | `badge` | `reader`, `result` |
| `wifi_assoc` | `network/wifi_ap_logs.csv` | `mac` | `ap`, `rssi` (int, dBm), `ssid` |
| `wifi_disassoc` | `network/wifi_ap_logs.csv` | `mac` | `ap`, `rssi`, `ssid` |
| `wifi_roam` | `network/wifi_ap_logs.csv` | `mac` | `ap`, `rssi`, `ssid` |
| `logon` | `endpoint/security_log.csv` | `account` | `event_id` (int, 4624), `logon_type` (int), `host` |
| `logoff` | `endpoint/security_log.csv` | `account` | `event_id` (int, 4634), `host` |
| `file_access` | `endpoint/security_log.csv` | `account` | `event_id` (int, 4663), `path`, `access_mask`, `host` |
| `file_read` | `endpoint/file_audit.csv` | `account` | `path`, `bytes` (int), `target_volume` (null), `host` |
| `file_copy` | `endpoint/file_audit.csv` | `account` | `path`, `bytes` (int), `target_volume` (e.g. `"E:"`), `host` |
| `usb_mount` | `endpoint/usbstor.txt` | `null` | `serial`, `vendor`, `product`, `first_seen` (time), `host` |
| `camera_offline` | `cctv/index.csv` | `null` | `camera`, `clip_ref` (null) |
| `camera_online` | `cctv/index.csv` | `null` | `camera`, `clip_ref` |
| `maintenance_window` | `it/maintenance_calendar.csv` | `name` | `start`, `end` (times), `asset`, `work_order`, `technician` |
| `email` | `comms/mailbox.mbox` | `email` | `from`, `to` (list), `subject`, `message_id` |
| `chat` | `comms/slack_export/…` | `slack` | `channel`, `ts` (Slack epoch string, as in the export) |
| `statement` | `statements/*.pdf` | `name` | `speaker`, `page` (int) |
| `transaction` | `financial/transactions.csv` | `account` (the bank account, e.g. `CHK-7731`; `inventory.csv` `bank_account` resolves it) | `account`, `amount` (number, credits positive), `counterparty`, `description` |
| `parking_entry` | `access/parking_exit.csv` | `permit` | `plate`, `lane` |
| `parking_exit` | `access/parking_exit.csv` | `permit` | `plate`, `lane` |

`host` is a device ID (`lt-219`). `path` is the full Windows path as logged (`C:\Projects\Titan\thruster_v4.step`).

### 3.2 `source`

| Field | Type | Rule |
|---|---|---|
| `file` | string | Path inside the case folder, forward slashes: `access/badge_access.csv` |
| `line` | int | 1-based physical line in the file; a CSV header is line 1. PDFs: line in the text pdfplumber extracts, all pages joined with `\n`. Slack: the line of the message's `"text"` entry |
| `quote` | string | Exact text, never cleaned up (never `strip()`: the usbstor `S/N:` line keeps its two leading spaces). CSV and log lines: the whole raw line without the newline. Email, chat, statements: see "One event per line" below |

**One event per line (emails and statements).** A parser emits:
- **email:** one `email` event for **every non-empty body line** of every message (all with that message's `t` and `attrs`); `quote` = the whole body line, `line` = its line in `mailbox.mbox`.
- **chat:** one `chat` event per Slack message; `quote` = the message text, `line` = the line of its `"text"` entry.
- **statement:** one `statement` event for **every answer line** of the statement, i.e. every pdfplumber line between the first `Q:` line and the closing line `I confirm that this statement ...`, except lines starting with `Q:` and interviewer notes in square brackets `[...]`; `quote` = the whole line.
- **usbstor:** one `usb_mount` event per device block; `quote` = its `S/N:` line.
- Paths of withheld evidence are relative to `extra/` (`extra/access/parking_exit.csv` → `source.file = "access/parking_exit.csv"`).
| `sha256` | string | Lowercase hex sha256 of the file's bytes as stored in the case folder |

### 3.3 Example

```json
{
  "id": "e214",
  "t": "2026-03-04T18:16:40-05:00",
  "type": "badge_in",
  "person": null,
  "device": "rdr-219",
  "room": "219",
  "actor": { "kind": "badge", "value": "40417" },
  "attrs": { "reader": "rdr-219", "result": "GRANTED" },
  "source": {
    "file": "access/badge_access.csv",
    "line": 2207,
    "quote": "2026-03-04T18:16:40-05:00,40417,rdr-219,IN,GRANTED",
    "sha256": "<sha256 of badge_access.csv>"
  }
}
```

## 4. `evidence.json`

Array, one object per file in the case folder (the extra file appears only after it is released).

| Field | Type | Status | Rule |
|---|---|---|---|
| `file` | string | existing | Path inside the case folder |
| `sha256` | string | existing | Hash of the file as received |
| `manifest_sha256` | string or null | **new** | Hash listed in `manifest.csv`; `null` if the file is not in the manifest |
| `manifest_match` | bool | existing | `sha256 == manifest_sha256` |
| `parser` | string | existing | One of `csv`, `text`, `mbox`, `slack_json`, `pdf`, `image` |
| `records` | int | existing | Events extracted from this file |

## 5. `case.json`

One object, existing fields only.

| Field | Value |
|---|---|
| `id` | `"1010F"` |
| `title` | `"The Titan Files"` |
| `address` | `"Julis Romo Rabinowitz Building, Princeton University, Princeton, NJ"` |
| `summary` | Alma's suspicion in two or three sentences, no answers |
| `costar_property_id` | string, `""` until Person 2 has it |
| `matterport_model_id` | string, `""` until the JRR model ID is known |

## 6. `devices.csv`

Header: `device_id,type,room,floor,sweep`

| Column | Rule |
|---|---|
| `device_id` | `rdr-210` … `rdr-230`, `ap-2-01` …, `cam-01` …, `lt-219` |
| `type` | `badge_reader`, `wifi_ap`, `camera`, `laptop` |
| `room` | room ID string (`"219"`); corridors and shared spaces use placeholder IDs until the scan is mapped |
| `floor` | int (`2`) |
| `sweep` | Matterport sweep ID; empty until Person 2 maps the scan |

## 7. `inventory.csv`

Header: `person_id,name,role,home_room,email,badge,laptop_mac,parking_permit,plate,local_account,bank_account,slack_handle,authorized_rooms,revoked`

`bank_account` is the account number that appears in `financial/transactions.csv` (Hank: `CHK-7731`), empty for others.

| Column | Rule |
|---|---|
| `person_id` | `p_alma`, `p_hank`, …, `p_bg_01` … |
| `badge`, `laptop_mac`, … | the raw identifiers that appear in the logs; empty if the person has none (e.g. Kim has no badge) |
| `authorized_rooms` | room IDs separated by `;` (`217;219`) |
| `revoked` | `room@time` entries separated by `;` (`219@2026-03-02T17:00:00-05:00`), empty if none |

## 8. `answer_key.json` (evaluator only)

```json
{
  "case_id": "1010F",
  "planted": [
    {
      "id": "C2",
      "kind": "physical",
      "detector": "physics",
      "sources": [
        { "file": "access/badge_access.csv", "line": 2203 },
        { "file": "access/badge_access.csv", "line": 2207 }
      ],
      "persons": ["p_bg_17"]
    }
  ],
  "false_alarm_persons": ["p_frederik", "p_bg_17"],
  "tamper": { "file": "endpoint/security_log.csv", "seed": 1010, "altered_lines": [118, 402],
              "changes": [ { "line": 118, "original": "<row as collected>", "altered": "<row as received>" } ] }
}
```

- `kind` uses the existing contradiction kinds: `physical`, `temporal`, `statement`, `custody`.
- Matching is by `sources` (file and line), never by event ID.
- `planted` holds C1 to C8 from CASE.md section 7.

## 9. Same in fake and real, different in fake and real

**Identical (safe to depend on):** file names and paths, every field name and type, timestamp format, the event
type list, `attrs` keys, `actor.kind` values, character, room and device IDs, story facts and quote wording.

**Different (never hard-code):** `source.line`, `source.sha256`, `records`, the number of events, and which `e#`
an event gets. Find events by `type`, `t`, `device`, `room` or `actor`, never by `e12` or a line number.

## 10. Checking it

`tests/evidence/test_format.py` checks every rule above (required fields, timestamp pattern, type list, `attrs`
keys per type, IDs existing in `devices.csv` and `inventory.csv`). The same test runs on the fakes now and on the
real output later; when both pass, they are interchangeable.

## 11. Open items for the team

1. **`person` filled by the merge step** from `persons.json` aliases (section 3): *done*, `fill_persons` in
   `backend/app/shared/merge.py` (an event that already has a person keeps it; an alias shared by two people stays null).
2. **New fields** `actor`, `attrs` on events and `manifest_sha256` on evidence: *done* in `schema.py` and `types.ts`.
3. **`.gitattributes`** keeping case files byte-exact (section 2): *done*.
4. **`answer_key.json` shape** (section 8) replaces the current `k1`/event-ID version: Person 2 to confirm.

## 12. Parser conventions (learned while matching the generated case exactly)

- **Values:** actor values stay strings (`"40417"`); `rssi`, `bytes`, `logon_type`, `event_id` are ints; `amount` is
  always a float (`25000.0`); `access_mask` stays a string (`"0x1"`); empty CSV fields become `null`.
- **Devices:** `device` is the raw reader / AP / camera id; `host` and laptop `device` are the log's host name mapped
  through `facilities/devices.csv` (`LT-219` -> `lt-219`); `room` is that device's room. Maintenance `device` is the
  asset only if it is in `devices.csv` (else `null`), but `attrs.asset` always keeps the raw asset.
- **Per type:** `logoff` has no `logon_type`; `camera_offline` and `camera_online` carry the same attrs and
  `clip_ref` is `null` (the OFFLINE row has none); RECORDING rows give no events; `maintenance_window.t` = `start`;
  the bank `balance` column is not kept.
- **usbstor:** `serial` keeps the `&0` suffix; `vendor` / `product` come from the `Disk&Ven_..&Prod_..` line with
  underscores kept; the host is the case's single laptop in `devices.csv`.
- **Email:** `to` holds the `To:` addresses only (not `Cc:`); quoted reply lines (`> ...`) are body lines too.
- **Statements:** lines are numbered over all pages joined with `\n` (footers included); bracketed interviewer notes
  can wrap over several lines and give no events.
- **case.json:** `title` = the brief's document title after `Incident brief: `; `address` = its `Location.` paragraph.

Pipeline: `run()` ingests the uploaded case (`data/evidence/work/CASE-1010F/`) or, if none, the built-in
`data/evidence/CASE-1010F/`, plus released extra files (`release.py`); `tests/evidence/ingest/test_end_to_end.py`
checks the result equals `truth/events_expected.json` exactly.
