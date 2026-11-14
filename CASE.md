# CASE.md — Case #1010F: "The Titan Files"

Source of truth for the synthetic case. Every generated file, parser, rule and test must agree with this document. If something here conflicts with code, this file wins; update the code.

The people, companies and events are fictional. The building is a real Princeton University building, used only as a backdrop for its geometry. Nothing here describes real Princeton staff, students, systems or incidents.

Character IDs (`p_hank`, `p_maggie`, …) identify people in the story. They are unrelated to the developer task split (Person 1–4) in CONTRACTS.md.

---

## 1. Setting

| Field | Value |
|---|---|
| Case ID | `1010F` |
| Title | The Titan Files |
| Location (real) | Princeton University, Princeton, NJ |
| Building (real) | Julis Romo Rabinowitz (JRR) Building |
| Floor | The floor covered by our Matterport scan; Halvorsen uses a project suite on it |
| Real scan used for geometry | Matterport model `<MODEL_ID>` (fill in from our JRR scan) |
| Lat / lon | `<from the scan / CoStar record>` |
| Parking | A campus parking exit log (no named lot, not scanned; data only) |
| Event (fictional) | A campus AI summit, summit week 2026-03-02 to 2026-03-06 |
| Victim company (fictional) | Halvorsen Dynamics, small aerospace startup working from a sponsored project suite in the building |
| Stolen asset | `Titan` folder: satellite thruster CAD files |
| Asset location | File server `fs-titan` in the floor's locked IT closet |
| Time standard | **All timestamps in all files are UTC**, ISO 8601 with `Z` (e.g. `2026-03-04T23:16:40Z`). Local time (America/New_York, UTC-05:00 on these dates) appears only in this document, in what people say, and in the UI. |

## 2. Key dates

| Date (local) | Day | What |
|---|---|---|
| 2026-03-02 | Mon | Hank resigns |
| 2026-03-04 | Wed | Incident night (summit welcome reception) |
| 2026-03-06 | Fri | Northline "signing bonus" lands in Hank's account |
| 2026-03-09 | Mon | Alma opens the case; evidence collected |

Background noise data covers 2026-02-23 to 2026-03-08 (stored in UTC, so the US daylight-saving change on 03-08 needs no special handling in the files).

## 3. Cast

| ID | Name | Role | Part in the story |
|---|---|---|---|
| `p_alma` | Alma Imhoff | Halvorsen head of security | Opens the case. The investigator using our tool. Not a suspect. |
| `p_hank` | Hank Gibson | Halvorsen senior engineer | The suspect. Resigned Monday, joining Northline Systems. |
| `p_maggie` | Maggie Price | Halvorsen engineer, Hank's friend | Gives Hank a false alibi. |
| `p_frederik` | Frederik Mendelssohn | IT admin for the floor (contractor) | Red herring. Flagged by anomaly scoring, then cleared. |
| `p_kim` | Dr. Kim Sayers | Northline Systems executive | In town for the summit. Hank's contact. Appears only in messages and payments. |

Plus about 40 background people on the floor with normal activity (noise), including `p_bg_17`, the person who badges in at 18:16:10. All email domains are fictional (`halvorsen.example`, `northline.example`); never use real university addresses.

## 4. The story (what actually happened)

Hank resigns on Monday to join Northline. On Wednesday evening the summit's welcome reception starts at 18:15 local, and the floor empties toward it. Hank badges out at 18:02 so he looks gone, but his laptop stays on the floor Wi-Fi. At 18:12 he slips back in behind a group of attendees who badge through the main entrance, so no badge record shows him. He walks to the IT closet and at 18:16:40 copies Titan to a USB drive. Just before that, at 18:16:10, an unrelated floor member (`p_bg_17`) badges in at the main entrance on the way back from the reception. That person could not physically have reached the closet by 18:16:40. Hank leaves at 18:41, and his car passes the campus parking exit at 18:44. Two days later a Northline "signing bonus" lands in his account.

## 5. Ground-truth timeline (incident night, 2026-03-04)

| Local (EST) | UTC (as stored) | Actor | Event | Evidence source |
|---|---|---|---|---|
| 17:45:00 | 22:45:00Z | Maggie | Badges out at main entrance, alone | `access/badge_access.csv` |
| 18:02:00 | 23:02:00Z | Hank | Badges out at main entrance | `access/badge_access.csv` |
| 18:05:00 | 23:05:00Z | (system) | Corridor camera `cam-03` (covers IT closet corridor) goes offline | `cctv/index.csv` |
| 18:12:30 | 23:12:30Z | 3 background members | Badge in at main entrance as a group; Hank tailgates behind them (no badge for Hank) | `access/badge_access.csv` |
| 18:15:00 | 23:15:00Z | (summit) | Welcome reception starts | `comms/` summit emails (noise) |
| 18:16:10 | 23:16:10Z | `p_bg_17` | Badges in at main entrance (unrelated to the theft) | `access/badge_access.csv` |
| 18:16:40 | 23:16:40Z | Hank | USB mass storage mounts on `fs-titan` in IT closet | `endpoint/usbstor.txt`, `endpoint/security_log.csv` |
| 18:16 to 18:31 | 23:16 to 23:31Z | Hank's account | Reads Titan files and copies them to USB | `endpoint/fileserver_audit.csv` (untampered), `endpoint/security_log.csv` (event 4663) |
| 18:30:00 | 23:30:00Z | (system) | `cam-03` back online | `cctv/index.csv` |
| 18:41:00 | 23:41:00Z | Hank | Laptop disconnects from floor Wi-Fi | `network/wifi_ap_logs.csv` |
| 18:44:00 | 23:44:00Z | Hank | Car passes the campus parking exit (plate / permit read) | `access/parking_exit.csv` (released only when the agent requests it) |
| 19:00 to 21:30 | 03-05 00:00 to 02:30Z | Frederik | Scheduled patch window, touches `fs-titan` | `it/maintenance_calendar.csv`, `endpoint/security_log.csv` |

Walk time from the main entrance to the IT closet must be about 74 s on the real JRR floor plan. When the real rooms are mapped, pick an entrance and closet that fit, and keep:
- the 18:16:10 → 18:16:40 gap (30 s) well under the walk time, so `p_bg_17` is physically ruled out;
- the 18:12:30 → 18:16:40 gap (250 s) well over the walk time, so Hank's path is physically possible.

## 6. Statements (the lies)

People speak in local time. When events are rendered as sentences for comparison (NLI), render them in local time too ("badged out at 6:02 pm"), never in UTC.

| Speaker | Statement | Source file |
|---|---|---|
| Hank | "I went straight home at six." | `statements/hank_gibson.pdf` |
| Hank | "I never touched the Titan folder." | `comms/mailbox.mbox` (email to Alma) |
| Hank | "IT gave me that drive last year." | `statements/hank_gibson.pdf` |
| Maggie | "Hank and I left together around 6:30." | `statements/maggie_price.pdf` |
| Frederik | Honest account of the scheduled patch window | `statements/frederik_mendelssohn.pdf` |

## 7. Planted contradictions (answer key)

The system must never read this section or the answer key file. It is for the evaluator only. Store a machine copy at `case/answer_key.json`, outside the evidence folder. Match findings by source (file + line), not by event ID.

| ID | Evidence joined | Contradiction | Expected detector |
|---|---|---|---|
| C1 | Badge vs Wi-Fi | Hank badged out 18:02, laptop online until 18:41, no badge back in | Rule engine |
| C2 | Badge + USB + walk time | `p_bg_17` swipes in at 18:16:10, USB mounts at 18:16:40, walk takes ~74 s: the only badge-in near the mount cannot explain it, so whoever mounted the drive was already inside | Physics check (floor plan graph) |
| C3 | Hank's statement vs parking exit log | "Went straight home at six," but his car passes the parking exit at 18:44 | NLI + rules (after evidence request) |
| C4 | Maggie's statement vs her badge | "Left together at 6:30," but she left alone at 17:45 | NLI + rules |
| C5 | Hank's email vs file-access logs | "Never touched Titan," but his account opened it: `fileserver_audit.csv` (untampered) and event 4663 in `security_log.csv` | NLI |
| C6 | Camera log vs IT work orders | `cam-03` offline 18:05 to 18:30, no work order | Rule engine |
| C7 | USB history vs Hank's statement | "IT gave me that drive last year," but its serial was first seen that night | NLI + rules |
| C8 | Evidence manifest | `endpoint/security_log.csv` hash does not match `manifest.csv` | Custody check |

C2 is exculpatory: it rules out `p_bg_17` instead of naming anyone. Accusing `p_bg_17` counts as a false alarm.

### Tampering (C8)
After collection, the generator alters a random number of rows in `endpoint/security_log.csv` (changed timestamps, usernames, or deleted rows), chosen with a fixed random seed so every run produces the same file. `manifest.csv` holds the hash of the original, untampered file. The seed and the list of altered rows go in `case/answer_key.json`. Every fact that C5 needs also exists in `fileserver_audit.csv`, so the case still holds when the system treats the tampered file as untrusted.

## 8. Red herrings

- **Frederik** is on the floor late (19:00 to 21:30) and touches `fs-titan`. He has the highest after-hours anomaly score. `it/maintenance_calendar.csv` shows a scheduled patch window, so a correct system flags him and then clears him. Accusing Frederik counts as a false alarm.
- **`p_bg_17`** badges in 30 s before the USB mount. The walk time rules them out (C2).

## 9. Motive trail

- Slack DMs between Hank and Kim Sayers during summit week (recruiting, "bring what you can" style hints, never an explicit confession).
- 2026-03-06: transfer from Northline Systems into Hank's account labeled as a signing bonus, then part of it moved to a crypto exchange.

## 10. Evidence folder layout

```
case/CASE-1010F/
  manifest.csv                  filename, sha256, collected_by, collected_at
  brief.pdf                     Alma's incident summary (no answers, only the suspicion)
  facilities/devices.csv        badge readers, Wi-Fi APs, cameras, servers mapped to room ids
  access/badge_access.csv
  access/parking_exit.csv       WITHHELD at start; released when the agent requests it
  network/wifi_ap_logs.csv
  endpoint/usbstor.txt          RegRipper-style USB history
  endpoint/security_log.csv     Windows events 4624, 4634, 4663 (tampered copy, see C8)
  endpoint/fileserver_audit.csv untampered; also records Hank's Titan access
  comms/mailbox.mbox            includes summit emails as noise
  comms/slack_export/           Slack export format, one JSON per channel per day
  statements/*.pdf              hank_gibson, maggie_price, frederik_mendelssohn
  financial/transactions.csv
  cctv/index.csv                camera, window, status, clip ref
  cctv/stills/*.jpg             crops from real Matterport panoramas at camera positions
  it/maintenance_calendar.csv
case/answer_key.json            evaluator only, never in the evidence folder
```

## 11. Rules for generating the data

- One story, one clock. Every timestamp in every file is UTC and agrees with Section 5.
- Business hours, "after hours" and anything a person says are local time (America/New_York). Convert at analysis and display time, never in the files.
- Use realistic formats: real Windows event IDs, Slack export JSON shape, RegRipper USBSTOR text, mbox.
- Bury the signal in noise: about 40 members, normal badge and Wi-Fi traffic all week, about 3,000 badge rows, 8,000 Wi-Fi rows, 300 emails, 600 Slack messages. The parking exit log also carries a week of normal entries and exits for other permits.
- Every person maps to aliases the system must resolve: name, email, badge number, laptop MAC address, parking permit / plate.
- Room ids, device ids and walk times come from the real Matterport floor plan of our JRR scan. Until it is mapped, use placeholder room names and keep them in one config file.
- The parking exit log is data only: no scan, no floor plan, no named lot.
- All randomness (noise, tampering) uses fixed seeds, so the case regenerates byte for byte.
- Real building only as the setting; no real people, no real company data, no real personal information.
- Data generation and the answer key are owned by the evidence slice, not by the story author.
