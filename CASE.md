# CASE.md — Case #1010F: "The Titan Files"

Source of truth for the synthetic case. Every generated file, parser, rule and test must agree with this document. If something here conflicts with code, this file wins; update the code. The scenario in docs/PLAN.md (Dana, Kelly, Tom, Houston) is only an example; this file is the current story.

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
| Floor | 2nd floor, covered by our Matterport scan |
| Real scan used for geometry | Matterport model `<MODEL_ID>` (fill in from our JRR scan) |
| Lat / lon | `<from the scan / CoStar record>` |
| Badge-controlled rooms | Rooms **210 to 230**. Each has a badge reader (`rdr-210` … `rdr-230`) that logs IN and OUT. Fake badge traffic is generated for all of them. |
| Crime scene | **Room 219 only.** A secure, badge-only room holding an isolated (air-gapped, no network) laptop `lt-219`. |
| Halvorsen suite | Room 214 (Hank's and Maggie's usual room) |
| Parking | A campus parking exit log (no named lot, not scanned; data only) |
| Event (fictional) | A campus AI summit, summit week 2026-03-02 to 2026-03-06 |
| Victim company (fictional) | Halvorsen Dynamics, small aerospace startup working from a sponsored project suite on the floor |
| Stolen asset | `Titan` folder: satellite thruster CAD files, stored only on `lt-219` |
| Time standard | **EST everywhere**: every file, the code and the UI. ISO 8601 with a fixed `-05:00` offset (e.g. `2026-03-04T18:16:40-05:00`). The offset stays `-05:00` for the whole case, including dates after the 2026-03-08 daylight-saving change. Never UTC, never EDT. |

Room numbers 210–230 come from the JRR floor plan. When the scan is mapped, keep 219 as the crime room and confirm the walk times in Section 5.

## 2. Key dates

| Date | Day | What |
|---|---|---|
| 2026-03-02 | Mon | Hank resigns. His badge access to room 219 is revoked that day. |
| 2026-03-04 | Wed | Incident night (summit welcome reception) |
| 2026-03-06 | Fri | Northline "signing bonus" lands in Hank's account |
| 2026-03-09 | Mon | Alma opens the case; evidence collected |

Background noise data covers 2026-02-23 to 2026-03-08.

## 3. Cast

| ID | Name | Role | Part in the story |
|---|---|---|---|
| `p_alma` | Alma Imhoff | Halvorsen head of security | Opens the case. The investigator using our tool. Not a suspect. |
| `p_hank` | Hank Gibson | Halvorsen senior engineer | The suspect. Resigned Monday, joining Northline Systems. |
| `p_maggie` | Maggie Price | Halvorsen engineer, Hank's friend | Gives Hank a false alibi. |
| `p_frederik` | Frederik Mendelssohn | IT admin for the floor (contractor) | Red herring. Flagged by anomaly scoring, then cleared. |
| `p_kim` | Dr. Kim Sayers | Northline Systems executive | In town for the summit. Hank's contact. Appears only in messages and payments. |
| `p_bg_17` | (background) | Halvorsen lab technician, authorized for room 219 | Their badge number is used at room 219 while they are at room 230. Innocent. |

Plus about 40 background people on the floor with normal activity (noise). All email domains are fictional (`halvorsen.example`, `northline.example`); never use real university addresses.

## 4. The story (what actually happened)

Hank resigns on Monday to join Northline, and his badge stops opening room 219. On Wednesday evening the summit's welcome reception starts at 18:15 and the floor empties toward it. Hank badges out of room 214 at 18:02 so he looks gone, but he stays on the floor and his laptop stays on the floor Wi-Fi. Weeks earlier he copied the badge of `p_bg_17`, a lab technician who is still authorized for 219. At 18:16:40 he opens room 219 with that copy. Thirty seconds earlier, the real `p_bg_17` badged into room 230 at the far end of the floor. The isolated laptop `lt-219` was never removed from Hank's local account, because it is offline and never syncs with deprovisioning. Hank logs on, mounts a USB drive and copies Titan. He leaves 219 at 18:31, his laptop drops off the Wi-Fi at 18:41, and his car passes the campus parking exit at 18:44. Two days later a Northline "signing bonus" lands in his account.

The badge copy is background story only. No evidence states it, and the system must never conclude it. The system can only report that one badge number was read in two places too far apart.

## 5. Ground-truth timeline (incident night, 2026-03-04, EST)

| Time | Actor | Event | Evidence source |
|---|---|---|---|
| 17:45:00 | Maggie | Badges OUT of room 214, alone | `access/badge_access.csv` |
| 18:02:00 | Hank | Badges OUT of room 214 | `access/badge_access.csv` |
| 18:05:00 | (system) | Camera `cam-03` (corridor outside room 219) goes offline | `cctv/index.csv` |
| 18:15:00 | (summit) | Welcome reception starts | `comms/` summit emails (noise) |
| 18:16:10 | `p_bg_17` | Badges IN at room 230 (the real card holder) | `access/badge_access.csv` |
| 18:16:40 | badge of `p_bg_17` | Badge IN at room 219 | `access/badge_access.csv` |
| 18:17:05 | account `hgibson` | Local logon on `lt-219` (event 4624) | `endpoint/security_log.csv` |
| 18:17:30 | (device) | USB mass storage mounts on `lt-219`; serial never seen before | `endpoint/usbstor.txt`, `endpoint/security_log.csv` |
| 18:17 to 18:31 | account `hgibson` | Reads Titan files and copies them to USB | `endpoint/file_audit.csv` (untampered), `endpoint/security_log.csv` (event 4663) |
| 18:30:00 | (system) | `cam-03` back online | `cctv/index.csv` |
| 18:31:20 | account `hgibson` | Logoff on `lt-219` (event 4634) | `endpoint/security_log.csv` |
| 18:31:40 | badge of `p_bg_17` | Badge OUT at room 219 | `access/badge_access.csv` |
| 18:41:00 | Hank | Laptop disconnects from floor Wi-Fi | `network/wifi_ap_logs.csv` |
| 18:44:00 | Hank | Car passes the campus parking exit (permit / plate read) | `access/parking_exit.csv` (released only when the agent requests it) |
| 19:00 to 21:30 | Frederik | Scheduled patch window on `lt-219`; badges into 219 with his own badge | `it/maintenance_calendar.csv`, `access/badge_access.csv`, `endpoint/security_log.csv` |

Walk time from room 230 to room 219 must be about 74 s on the real JRR floor plan. When the real rooms are mapped, keep the 18:16:10 → 18:16:40 gap (30 s) well under that walk time. If 230 is too close to 219, use the badge room farthest from 219 instead and update this table.

`lt-219` is isolated: it has no Wi-Fi or network logs. Its evidence (`usbstor.txt`, `security_log.csv`, `file_audit.csv`) comes from a forensic image of the laptop taken on 2026-03-09.

## 6. Statements (the lies)

| Speaker | Statement | Source file |
|---|---|---|
| Hank | "I went straight home at six." | `statements/hank_gibson.pdf` |
| Hank | "I never touched the Titan folder." | `comms/mailbox.mbox` (email to Alma) |
| Hank | "IT gave me that drive last year." | `statements/hank_gibson.pdf` |
| Maggie | "Hank and I left together around 6:30." | `statements/maggie_price.pdf` |
| Frederik | Honest account of the scheduled patch window | `statements/frederik_mendelssohn.pdf` |

## 7. Planted contradictions (answer key)

The system must never read this section or the answer key file. The machine copy is `data/evidence/answer_key.json`, outside the `CASE-1010F/` folder. Only the evaluator (Person 2) reads it. Match findings by source (file + line), not by event ID.

| ID | Evidence joined | Contradiction | Expected detector |
|---|---|---|---|
| C1 | Badge vs Wi-Fi | Hank's badge OUT at 214 at 18:02, his laptop on the floor Wi-Fi until 18:41, no later read of his badge | Rule engine |
| C2 | Badge + walk time | Badge of `p_bg_17` read at room 230 at 18:16:10 and at room 219 at 18:16:40; the walk takes ~74 s, so at least one read was not the card holder | Physics check (floor plan graph) |
| C3 | Hank's statement vs parking exit log | "Went straight home at six," but his car passes the parking exit at 18:44 | NLI + rules (after evidence request) |
| C4 | Maggie's statement vs her badge | "Left together around 6:30," but she badged out alone at 17:45 | NLI + rules |
| C5 | Hank's email vs file-access logs | "Never touched Titan," but account `hgibson` opened it on `lt-219`: `file_audit.csv` (untampered) and event 4663 in `security_log.csv` | NLI |
| C6 | Camera log vs IT work orders | `cam-03` offline 18:05 to 18:30, no work order | Rule engine |
| C7 | USB history vs Hank's statement | "IT gave me that drive last year," but its serial was first seen on `lt-219` that night | NLI + rules |
| C8 | Evidence manifest | `endpoint/security_log.csv` hash does not match `manifest.csv` | Custody check |

C2 is exculpatory for `p_bg_17`: it shows their badge number was used somewhere they could not be. Accusing `p_bg_17` counts as a false alarm.

### Tampering (C8)
After collection, the generator alters a random number of rows in `endpoint/security_log.csv` (changed timestamps, usernames, or deleted rows), chosen with a fixed random seed so every run produces the same file. `manifest.csv` holds the hash of the original, untampered file. The seed and the list of altered rows go in `data/evidence/answer_key.json`. Every fact that C5 needs also exists in `file_audit.csv`, so the case still holds when the system treats the tampered file as untrusted.

## 8. Red herrings

- **Frederik** badges into room 219 from 19:00 to 21:30 and works on `lt-219`. He has the highest after-hours anomaly score. `it/maintenance_calendar.csv` shows a scheduled patch window, so a correct system flags him and then clears him. Accusing Frederik counts as a false alarm.
- **`p_bg_17`**: their badge number opens room 219 during the theft, but C2 shows the real card holder was at room 230. Their own laptop on a Wi-Fi AP near room 230 supports this.

## 9. Motive trail

- Slack DMs between Hank and Kim Sayers during summit week (recruiting, "bring what you can" style hints, never an explicit confession).
- 2026-03-06: transfer from Northline Systems into Hank's account labeled as a signing bonus, then part of it moved to a crypto exchange.

## 10. Evidence folder layout (follows CONTRACTS.md)

```
data/evidence/
  devices.csv                   room and device IDs for the team (source of truth: rdr-210..rdr-230, lt-219, cam-03, APs)
  inventory.csv                 character ID to name, email, badge, laptop MAC, parking permit, local account
  answer_key.json               evaluator only (Person 2); never read by the system or Person 4
  CASE-1010F/                   the case folder, zipped for upload
    manifest.csv                filename, sha256, collected_by, collected_at
    brief.pdf                   Alma's incident summary (no answers, only the suspicion)
    facilities/devices.csv      evidence copy of the device map
    access/badge_access.csv     IN / OUT reads for rooms 210 to 230
    network/wifi_ap_logs.csv
    endpoint/usbstor.txt        RegRipper-style USB history from lt-219
    endpoint/security_log.csv   Windows events 4624, 4634, 4663 from lt-219 (tampered copy, see C8)
    endpoint/file_audit.csv     lt-219 local file-audit log, untampered; records Hank's Titan access
    comms/mailbox.mbox          includes summit emails as noise
    comms/slack_export/         Slack export format, one JSON per channel per day
    statements/*.pdf            hank_gibson, maggie_price, frederik_mendelssohn
    financial/transactions.csv
    cctv/index.csv              camera, window, status, clip ref
    cctv/stills/*.jpg           crops from real Matterport panoramas at camera positions
    it/maintenance_calendar.csv
  extra/
    parking_exit.csv            WITHHELD at start; added to the case as access/parking_exit.csv when the request is approved
  fake/                         hand-written JSON fakes for the other slices
```

## 11. Rules for generating the data

- One story, one clock. Every timestamp in every file is EST (`-05:00`) and agrees with Section 5.
- Badge traffic covers all badge rooms 210 to 230; the crime touches room 219 only.
- Use realistic formats: real Windows event IDs, Slack export JSON shape, RegRipper USBSTOR text, mbox.
- Bury the signal in noise: about 40 members, normal badge and Wi-Fi traffic all week, about 3,000 badge rows, 8,000 Wi-Fi rows, 300 emails, 600 Slack messages. The parking exit log also carries a week of normal entries and exits for other permits.
- Every person maps to aliases the system must resolve: name, email, badge number, laptop MAC address, parking permit / plate, local account.
- Room ids, device ids and walk times come from the real Matterport floor plan of our JRR scan. Until it is mapped, use placeholder positions and keep them in one config file.
- The parking exit log is data only: no scan, no floor plan, no named lot.
- All randomness (noise, tampering) uses fixed seeds, so the case regenerates byte for byte.
- Real building only as the setting; no real people, no real company data, no real personal information.
- Data generation and the answer key are owned by the evidence slice (Person 1), not by the story author.
