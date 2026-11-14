# CASE.md — Case #1010F: "The Titan Files"

Source of truth for the synthetic case. Every generated file, parser, rule and test must agree with this document. If something here conflicts with code, this file wins; update the code.

The case is fully fictional. All people, companies and the hotel are invented.

---

## 1. Setting

| Field | Value |
|---|---|
| Case ID | `1010F` |
| Title | The Titan Files |
| Location (fictional) | Hotel Taj, Houston |
| Floor | Taj Business Floor (2nd floor coworking floor) |
| Real scan used for geometry | Matterport model `CHUheq99ibg` (Industrious, The Ion, 2nd Floor, 4201 Main St, Houston) |
| Lat / lon | 29.734191, -95.382153 |
| Event | Houston AI Summit 2026 (summit week) |
| Victim company | Halvorsen Dynamics, small aerospace startup renting a private suite on the floor |
| Stolen asset | `Titan` folder: satellite thruster CAD files |
| Asset location | File server `fs-titan` in the floor's locked IT closet |
| Timezone | All timestamps in Houston local time, `America/Chicago` (UTC-06:00 in March). Never mix zones. |

## 2. Key dates

| Date | Day | What |
|---|---|---|
| 2026-03-02 | Mon | Hank resigns |
| 2026-03-04 | Wed | Incident night (summit welcome reception) |
| 2026-03-06 | Fri | Northline "signing bonus" lands in Hank's account |
| 2026-03-09 | Mon | Alma opens the case; evidence collected |

Background noise data should cover 2026-02-23 to 2026-03-08.

## 3. Cast

| ID | Name | Role | Part in the story |
|---|---|---|---|
| `p_alma` | Alma Imhoff | Halvorsen head of security | Opens the case. The investigator using our tool. Not a suspect. |
| `p_hank` | Hank Gibson | Halvorsen senior engineer | The suspect. Resigned Monday, joining Northline Systems. |
| `p_maggie` | Maggie Price | Halvorsen engineer, Hank's friend | Gives Hank a false alibi. |
| `p_frederik` | Frederik Mendelssohn | Hotel Taj IT admin | Red herring. Flagged by anomaly scoring, then cleared. |
| `p_kim` | Dr. Kim Sayers | Northline Systems executive | In town for the summit. Hank's contact. Appears only in messages and payments. |

Plus about 40 background members of the Taj Business Floor with normal activity (noise).

## 4. The story (what actually happened)

Hank resigns on Monday to join Northline. On Wednesday evening the summit's welcome reception starts in the atrium at 18:15 and the whole floor empties toward it. Hank badges out at 18:02 so he looks gone, but his laptop stays on the floor Wi-Fi. He slips back in with the crowd behind another member, walks to the IT closet, and copies Titan to a USB drive. He leaves at 18:41 and his car exits the garage at 18:44. Two days later a Northline "signing bonus" lands in his account.

## 5. Ground-truth timeline (incident night, 2026-03-04)

| Time | Actor | Event | Evidence source |
|---|---|---|---|
| 17:45:00 | Maggie | Badges out at main entrance, alone | `access/badge_access.csv` |
| 18:02:00 | Hank | Badges out at main entrance | `access/badge_access.csv` |
| 18:05:00 | (system) | Corridor camera `cam-03` (covers IT closet corridor) goes offline | `cctv/index.csv` |
| 18:15:00 | (summit) | Welcome reception starts in the atrium | `comms/` summit emails (noise) |
| 18:16:10 | Background member | Badges in at main entrance; Hank tailgates behind them (no badge for Hank) | `access/badge_access.csv` |
| 18:16:40 | Hank | USB mass storage mounts on `fs-titan` in IT closet | `endpoint/usbstor.txt`, `endpoint/security_log.csv` |
| 18:16 to 18:31 | Hank's account | Reads Titan files and copies them to USB | `endpoint/fileserver_audit.csv`, `endpoint/security_log.csv` (event 4663) |
| 18:30:00 | (system) | `cam-03` back online | `cctv/index.csv` |
| 18:41:00 | Hank | Laptop disconnects from floor Wi-Fi | `network/wifi_ap_logs.csv` |
| 18:44:00 | Hank | Car exits hotel garage | `access/garage_exit.csv` (released only when the agent requests it) |
| 19:00 to 21:30 | Frederik | Scheduled patch window, touches `fs-titan` | `it/maintenance_calendar.csv`, `endpoint/security_log.csv` |

Walk time from main entrance to IT closet must be about 74 s on the real floor plan. When the real rooms are mapped, pick an entrance and closet that fit, and adjust the 18:16:10 / 18:16:40 gap so it stays clearly impossible (gap well under walk time).

## 6. Statements (the lies)

| Speaker | Statement | Source file |
|---|---|---|
| Hank | "I went straight home at six." | `statements/hank_gibson.pdf` |
| Hank | "I never touched the Titan folder." | `comms/mailbox.mbox` (email to Alma) |
| Hank | "IT gave me that drive last year." | `statements/hank_gibson.pdf` |
| Maggie | "Hank and I left together around 6:30." | `statements/maggie_price.pdf` |
| Frederik | Honest account of the scheduled patch window | `statements/frederik_mendelssohn.pdf` |

## 7. Planted contradictions (answer key)

The system must never read this section or the answer key file. It is for the evaluator only. Store a machine copy at `case/answer_key.json`, outside the evidence folder.

| ID | Evidence joined | Contradiction | Expected detector |
|---|---|---|---|
| C1 | Badge vs Wi-Fi | Hank badged out 18:02, laptop online until 18:41, no badge back in | Rule engine |
| C2 | Badge + USB + walk time | Someone else swipes in at 18:16:10, USB mounts at 18:16:40, walk takes ~74 s | Physics check (floor plan graph) |
| C3 | Hank's statement vs garage exit log | "Went straight home at six," but car leaves 18:44 | NLI + rules (after evidence request) |
| C4 | Maggie's statement vs her badge | "Left together at 6:30," but she left alone at 17:45 | NLI + rules |
| C5 | Hank's email vs file-access log | "Never touched Titan," but his account opened it (event 4663) | NLI |
| C6 | Camera log vs IT work orders | `cam-03` offline 18:05 to 18:30, no work order | Rule engine |
| C7 | USB history vs Hank's statement | "IT gave me that drive last year," but its serial was first seen that night | NLI + rules |
| C8 | Evidence manifest | `endpoint/security_log.csv` hash does not match `manifest.csv` (edited after collection) | Custody check |

## 8. Red herring

Frederik is on the floor late (19:00 to 21:30) and touches `fs-titan`. He has the highest after-hours anomaly score. `it/maintenance_calendar.csv` shows a scheduled patch window, so a correct system flags him and then clears him. Accusing Frederik counts as a false alarm.

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
  access/garage_exit.csv        WITHHELD at start; released when the agent requests it
  network/wifi_ap_logs.csv
  endpoint/usbstor.txt          RegRipper-style USB history
  endpoint/security_log.csv     Windows events 4624, 4634, 4663 (tampered copy, see C8)
  endpoint/fileserver_audit.csv
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

- One story, one clock. Every timestamp across every file must agree with Section 5.
- Use realistic formats: real Windows event IDs, Slack export JSON shape, RegRipper USBSTOR text, mbox.
- Bury the signal in noise: about 40 members, normal badge and Wi-Fi traffic all week, about 3,000 badge rows, 8,000 Wi-Fi rows, 300 emails, 600 Slack messages.
- Every person maps to aliases the system must resolve: name, email, badge number, laptop MAC address.
- Room ids, device ids and walk times come from the real Matterport floor plan for `CHUheq99ibg`. Until it is mapped, use placeholder room names and keep them in one config file.
- No real people, no real company data, no real personal information.