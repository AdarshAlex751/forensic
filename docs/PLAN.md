System architecture
The pipeline is a LangGraph graph of deterministic stages with ML at the core, and a deepagents lead investigator on top that only ever sees verified facts. Code does the math; the LLM decides what to check and explains why.
Only verified facts reach the lead investigator, and its evidence requests loop back into the case folder after human approval.
1.  Ingest and custody. Unzip, sniff each file's type, route it to a parser (pandas, mailbox, pdfplumber, Slack JSON, vision model for stills). Hash every file and compare against manifest.csv. Every row becomes a raw record with file, line and sha256.
2.  Extractor agent (Llama 4 Scout on Groq). Reads unstructured files (emails, Slack, statements, brief) and returns facts in a fixed JSON schema: who, what, when, where, plus an exact quote and its source ID. Structured logs skip the LLM and map straight to events.
3.  Entity resolution (embeddings + rules). Merge "Dana Reyes", "dreyes@halvorsen.com", badge 40417 and laptop MAC 3C:22:FB:... into one person node. Use the device inventory for hard links and all-MiniLM-L6-v2 similarity plus fuzzy matching for names and aliases.
4.  Fact graph (NetworkX). Nodes: persons, devices, rooms, files, accounts, events. Edges: used, located_in, accessed, sent, paid, said. Run betweenness centrality and Louvain community detection; feed both into the UI and the anomaly features.
5.  Spatial model (Matterport). Pull sweeps and their neighbor links from the Showcase SDK, build a walkable graph, compute shortest walking time per room pair at 1.4 m/s. Map readers, APs and cameras to rooms and camera view cones from devices.csv.
6.  Anomaly scorer (scikit-learn). Per person per day features: after-hours badge minutes, distinct rooms, files touched, bytes copied, USB mounts, deviation from their own 30-day baseline, graph centrality. Isolation Forest ranks people; embedding outliers flag unusual messages.
7.  Contradiction finder (rules + NLI). Rules catch hard conflicts: same person in two places, impossible walk, Wi-Fi presence after badge-out, camera gap without maintenance, hash mismatch. The NLI cross-encoder scores statement pairs (a person's claim vs an event rendered as a sentence) and keeps high-contradiction pairs.
8.  Verifier (code, not LLM). For every claim: the cited quote must appear verbatim (after whitespace normalization) in the cited file, and for CSV rows the cited row and fields must match. Failures are rejected and counted. The UI shows the verified percentage.
9.  Lead investigator (deepagents, Llama 3.3 70B on Groq). Plans with the deepagents to-do tool, delegates to subagents (timeline, physics, comms, money), ranks hypotheses with what would disprove each, and calls request_evidence, which pauses for human approval, ingests the new evidence and replans.
10.  Evaluator (code). Compares contradictions found against the hidden answer key: recall, false alarms, time to finish. Hidden from the agent, shown in judge mode.
Tools the agents can call: query_timeline(person, start, end), walk_time(room_a, room_b), ap_covers(ap, room), camera_sees(cam, room), search_comms(query), graph_neighbors(node), request_evidence(ask, why). Each returns facts with source IDs.
UI walkthrough
The walkthrough follows the whiteboard: drop in the case, the folder opens to the summary and evidence locker, click through to the aerial view, into Matterport with CoStar tenant labels, scrub the night on the timeline with red pins, then land on the red yarn board with people, notes and what to check next. Visual language: a dark detective desk, manila paper, typewriter type, red stamps and red string. Sound on every major transition.
Step 0. The desk (drop in)
Looks like: Top-down dark walnut desk, desk lamp glow in one corner, a closed manila folder stamped CASE #1010F. Dashed outline reads "drop case folder here".
Interaction: Drag in CASE-1010F.zip. The folder lifts, a red CONFIDENTIAL stamp thuds onto the cover, and the folder opens with a page-turn sound.
Under the hood: Upload streams to FastAPI; ingest starts at once and pushes progress over Server-Sent Events, so the UI is never faking a loading bar.
Step 1. Summary page and evidence locker
Looks like: An open two-page spread. Left page: case summary typed out live with a typewriter sound. Right page: polaroid cards for persons of interest (illustrated avatars, not real faces), each with role, suite, and an anomaly score bar that fills as scoring finishes. Paper-clipped to the corner: the Evidence Locker box from the whiteboard.
Evidence Locker: One row per file: filename, parser used, rows or facts extracted, sha256 prefix, and a custody badge (green verified, or red MISMATCH for security_log.csv). A pipeline strip across the bottom lights stage by stage: Ingest, Extract, Resolve, Graph, Detect, Verify, Analyze. Click any file to open it in a side viewer with highlighted rows that produced facts.
What judges see: Raw data to insight is visible, chain of custody is enforced, and one tampered file is caught before any AI reasoning. Arlequin's "clear pipeline" and "results you can trust" in one screen.
Step 2. Aerial view (Vexcel)
Looks like: Click "Go to scene". The page slides away and the camera starts above Houston, then zooms onto the Vexcel aerial of the tower. Overlays: entrances, parking garage, loading dock, and the exterior camera positions with their view cones.
Under the hood: Address from the brief goes to the CoStar toolkit, which returns the property record, tenant roster and the matching Vexcel and Matterport IDs.
Step 3. Matterport with CoStar tenant labels
Looks like: The aerial cross-fades into the Matterport dollhouse of the same building. Floating labels per floor from CoStar: "Floor 4: Halvorsen Dynamics, Suite 410". Click floor 4 and the camera flies into the floor plan view; tags appear on every badge reader, Wi-Fi AP, camera and the file server room 412, colored by device type.
Under the hood: Showcase SDK: Mode.moveTo for dollhouse and floor plan, Tag.add for devices, Sweep.data already used in the backend to compute walking times.
Step 4. The night of: timeline, tags and person tokens
Looks like: The scan fills the screen with a film-strip timeline slider along the bottom from 17:00 to 22:00. Event ticks are color coded by source; flagged events are red pins on the strip and in the scan.
Interaction:
• Scrub or press play. Tags light up as each device fires, and a token per person moves room to room along the walkable path.
• Click any tick and the log message slides in, as on the whiteboard: the raw line, file, line number, hash, and a green VERIFIED seal.
• The camera follows with Sweep.moveTo to the room where the event happened.
• Toggle persons on and off to compare Dana, Kelly and Tom.
What judges see: CoStar's spatial layer doing real work, and a timeline rebuilt from scattered traces, which is one of Arlequin's own example ideas.
Step 5. Red flags
Looks like: A slide-out panel of contradiction cards, each with a type chip (Physical, Temporal, Statement, Custody), severity and confidence. Clicking a card flies the camera to the room and shows both sides of the conflict side by side.
Hero example: "Lobby reader 18:16:10. USB mount in room 412 at 18:16:40. Shortest walk is 74 s." The walking path draws in red through the scan, with the 30 second gap labeled IMPOSSIBLE. Statement cards show the NLI score: Dana's "went straight home" vs the Wi-Fi log, contradiction 0.94.
What judges see: AI finding what a keyword search would miss, with the evidence behind every finding.
Step 6. Red yarn board
Looks like: Switch to a corkboard. Polaroids of people, index cards for devices, files and transactions, pinned and linked with red yarn. Node size is betweenness centrality; card tint is Louvain community. Sticky notes carry "notes to take care of" and "suggestions of what to check next", exactly as on the whiteboard.
Interaction:
• Drag cards around; the yarn stays attached (force layout with a paper skin).
• Click a yarn strand to see the evidence behind that edge.
• Click Dana's polaroid to see her anomaly features: badge minutes after hours, files touched vs baseline, USB mounts.
• Tom's card shows a high anomaly score with a yellow note "cleared: patch window on IT calendar", which shows the system can clear people, not only accuse them.
Step 7. Lead investigator
Looks like: A typed memo clipped over the board: ranked hypotheses with confidence bars, the supporting evidence for each, and "what would disprove this". A live trace shows the deepagent's to-do list and which subagent is working.
The agentic moment: The agent asks: "Pull camera 3 badge-area footage and the parking garage exit log, 18:10 to 18:45. Disproves H1 if Dana's car left before 18:16." The investigator clicks Approve, the new evidence lands in the locker with a stamp sound, the pipeline reruns on the delta, and the confidence bars move live.
Counter in the corner: "212 claims made, 207 verified, 5 rejected." Click Rejected to see what the verifier threw out and why.
Step 8. Case report, judge mode and text
Looks like: A clean case report: timeline, contradictions, hypotheses, every sentence footnoted to file, line and hash. Export to PDF.
Judge mode toggle: Reveals the evaluator against the hidden answer key: "7 of 8 planted contradictions found, 1 false alarm, 3 min 40 s end to end." Lists which one was missed and why. Honest numbers beat a perfect claim.

Sound and motion list
Page turn (folder open, step changes), typewriter (summary, memo), stamp thud (custody check, new evidence), camera shutter (evidence click), soft paper slide (panels). Keep all under 400 ms and add a mute toggle for judging rooms.
Tech stack
Everything runs on laptop CPUs; no model training, no GPU.
Layer
Choice
Used for
Frontend
React + Vite + TypeScript, Tailwind
App shell
Motion and pages
Framer Motion, page-flip (StPageFlip)
Folder open, page turns, panel slides
Sound
Howler.js
Page turn, typewriter, stamp, shutter
3D scene
Matterport Showcase SDK (iframe + MP_SDK.connect)
Dollhouse, floor plan, tags, Sweep.moveTo, sweep graph
Aerial
Mapbox GL JS or Leaflet with Vexcel tiles from the CoStar toolkit
Zoom from city to building, entrance and camera overlays
Yarn board
react-force-graph-2d or Cytoscape.js with custom paper and string rendering
Evidence graph
Backend
Python 3.11, FastAPI, Server-Sent Events
API, live pipeline progress
Pipeline orchestration
LangGraph
Deterministic stages with state and retries
Lead agent
deepagents (LangChain)
Planning, subagents, evidence requests
LLMs
Groq free tier via langchain-groq (ChatGroq): llama-3.3-70b-versatile (lead, best tool calling), meta-llama/llama-4-scout-17b-16e-instruct (extractor, subagents, JSON), llama-3.1-8b-instant (cheap classification)
Reasoning, extraction
Embeddings
sentence-transformers all-MiniLM-L6-v2
Entity resolution, message clustering, comms search
Contradictions
cross-encoder/nli-deberta-v3-small
Statement vs event contradiction scores
Anomalies
scikit-learn IsolationForest
Per person behavior scoring
Graph
NetworkX (betweenness, louvain_communities, shortest paths)
Fact graph and walking times
Parsing
pandas, mailbox, pdfplumber, json, rapidfuzz
Files to records, quote verification
Vision
Llama 4 Scout vision on Groq, CCTV stills
Describe frames as facts with citations
Data
CoStar toolkit (SDKs, MCP servers, OpenAPI)
Property, tenants, Vexcel and Matterport IDs
Messaging
Photon 2.0 beta
Text the case agent
Storage
JSON files + SQLite
findings.json, cached runs
Data contract: findings.json
The backend writes one findings.json and the UI only reads it, so frontend and backend can build in parallel from a hand-written fake. Freeze this schema in the first hour.
{
  "case": { "id": "1010F", "title": "", "address": "", "summary": "", "costar_property_id": "", "matterport_model_id": "" },
  "evidence": [{ "file": "access/badge_access.csv", "sha256": "", "manifest_match": true, "parser": "pandas", "records": 3012 }],
  "persons": [{ "id": "p1", "name": "Dana Reyes", "role": "", "suite": "410", "aliases": ["dreyes@...", "badge:40417", "mac:3C:22:FB:..."], "anomaly": 0.91, "features": {}, "community": 2 }],
  "devices": [{ "id": "AP-4-East", "type": "wifi_ap", "room": "410", "sweep": "abc123", "tag_xyz": [0, 0, 0] }],
  "events": [{ "id": "e12", "t": "2026-03-04T18:18:00", "type": "usb_mount", "person": "p1", "device": "fs-412", "room": "412", "source": { "file": "endpoint/usbstor.txt", "line": 88, "quote": "", "sha256": "" }, "verified": true }],
  "edges": [{ "from": "p1", "to": "fs-412", "type": "accessed", "events": ["e12"] }],
  "contradictions": [{ "id": "c2", "kind": "physical", "events": ["e9", "e12"], "score": 0.98, "explanation": "", "path": ["lobby", "elev-B", "412"], "walk_s": 74, "gap_s": 30 }],
  "hypotheses": [{ "id": "h1", "text": "", "confidence": 0.71, "supports": ["c1", "c2"], "disproved_by": "" }],
  "requests": [{ "id": "r1", "ask": "", "why": "", "status": "pending" }],
  "notes": [{ "text": "", "kind": "check_next" }],
  "verification": { "claims": 212, "verified": 207, "rejected": [{ "claim": "", "reason": "quote not found" }] },
  "eval": { "planted": 8, "found": 7, "false_alarms": 1, "runtime_s": 220 }
}
Rules: every event, edge, contradiction and hypothesis must trace back to a source with file, line and quote. The eval block is written by the evaluator only, never readable by the agents.


## Team split (matches CONTRACTS.md)
Four people, four slices. Read your own section, then look at the "Reads" files of the people you depend on.
Everything you need to build is in your folders. Branches: feat/evidence, feat/scene, feat/analysis, feat/investigator.
Until another person's real output exists, build against their fake files in data/<slice>/fake/.

---------------------------------------------------------------
### Person 1: Case and evidence   (branch feat/evidence)
Turns raw files into trusted facts. Every other slice starts from your output.

Builds (from the pipeline): stage 1 ingest and custody, stage 2 extractor.
Also builds: the synthetic case, the hidden answer key, and the case files.
Screens: Step 0 (the desk and folder drop), Step 1 (summary page and Evidence Locker).

Files:
    data/evidence/devices.csv             room and device IDs (source of truth for everyone)
    data/evidence/inventory.csv           which badge, laptop and MAC belong to which person
    data/evidence/answer_key.json         hidden planted contradictions
    data/evidence/CASE-1010F/access/badge_access.csv
    data/evidence/CASE-1010F/endpoint/usbstor.txt
    data/evidence/CASE-1010F/security_log.csv        (the one tampered file)
    data/evidence/CASE-1010F/manifest.csv
    data/evidence/CASE-1010F/   also: Wi-Fi log, emails, Slack, statements, transactions, CCTV stills
    data/evidence/extra/                  camera 3 footage and garage exit log, released when a request is approved
    backend/app/features/evidence/ingest.py       unzip, detect file type, route to a parser
    backend/app/features/evidence/parsers.py      pandas, mailbox, pdfplumber, Slack JSON, vision for stills
    backend/app/features/evidence/custody.py      hash every file, compare to manifest.csv
    backend/app/features/evidence/extractor.py    LLM turns emails, Slack and statements into facts with quotes
    backend/app/features/evidence/router.py       POST /api/evidence/upload
    backend/app/features/evidence/run.py          run(case_id)
    frontend/src/features/evidence/Desk.tsx
    frontend/src/features/evidence/FolderOpen.tsx
    frontend/src/features/evidence/SummaryPage.tsx
    frontend/src/features/evidence/EvidenceLocker.tsx
    frontend/src/features/evidence/FileViewer.tsx
    frontend/src/features/evidence/PipelineStrip.tsx
    frontend/src/shared/sounds.ts         the one shared file you build, in hour 1, then read-only
    tests/evidence/

Writes: data/evidence/case.json, evidence.json, events.json
Reads: nothing from other people's folders.
Do not write the "verified" field on events. Person 4's verifier decides it.
First hour: story paragraph, devices.csv, then sounds.ts. Everyone depends on the IDs in devices.csv.
Done when: dropping the zip fills evidence.json and events.json (every event has file, line, quote, sha256)
and security_log.csv shows a red MISMATCH in the locker.

---------------------------------------------------------------
### Person 2: Spatial and scene   (branch feat/scene)
Puts every event inside the real building and computes the physics.

Builds: stage 5 spatial model, stage 10 evaluator.
Screens: Step 2 (aerial view), Step 3 (Matterport with tenant labels), Step 4 (timeline, tags, person tokens),
and Judge mode.

Files:
    backend/app/features/scene/costar.py          address to property, tenants, Vexcel and Matterport IDs
    backend/app/features/scene/vexcel.py          aerial view, entrances, exterior cameras
    backend/app/features/scene/sweep_graph.py     walkable graph from Matterport sweeps
    backend/app/features/scene/tools.py           walk_time, ap_covers, camera_sees
    backend/app/features/scene/devices.py         readers, APs and cameras mapped to rooms and view cones
    backend/app/features/scene/evaluator.py       compares found contradictions to the answer key
    backend/app/features/scene/run.py
    frontend/src/features/scene/AerialView.tsx
    frontend/src/features/scene/MatterportScene.tsx
    frontend/src/features/scene/TenantLabels.tsx
    frontend/src/features/scene/DeviceTags.tsx
    frontend/src/features/scene/Timeline.tsx          film-strip slider
    frontend/src/features/scene/PersonTokens.tsx
    frontend/src/features/scene/RedPath.tsx
    frontend/src/features/scene/eventCameraSync.ts
    frontend/src/features/scene/JudgeMode.tsx
    tests/scene/

Writes: data/scene/devices.json, rooms.json, eval.json
Provides (signatures never change):
    walk_time(room_a, room_b) -> { seconds, path }
    ap_covers(ap_id, room_id) -> bool
    camera_sees(camera_id, room_id) -> bool
Reads: data/evidence/devices.csv, events.json, data/analysis/contradictions.json,
data/evidence/answer_key.json (evaluator only).
First hour: commit tools.py with hard-coded stub answers so Persons 3 and 4 are never blocked.
Done when: walk_time returns real numbers (lobby to 412 including elevator time, or the hand-traced floor 4 fallback),
device tags show in the scan, scrubbing the timeline moves tokens, and the red path draws for the impossible walk.

---------------------------------------------------------------
### Person 3: Analysis   (branch feat/analysis)
Finds who is who, what is unusual, and what contradicts what.

Builds: stage 3 entity resolution, stage 4 fact graph, stage 6 anomaly scorer, stage 7 contradiction finder.
Screens: Step 5 (red flags panel) and Step 6 (red yarn board).

Files:
    backend/app/features/analysis/entity_resolution.py   merge badge, MAC, email and names into one person
    backend/app/features/analysis/fact_graph.py          NetworkX graph, centrality, communities
    backend/app/features/analysis/anomaly_features.py    per person per day features
    backend/app/features/analysis/anomaly_scorer.py      Isolation Forest
    backend/app/features/analysis/rules.py               hard conflicts: impossible walk, Wi-Fi after badge-out, hash mismatch
    backend/app/features/analysis/nli.py                 statement vs event contradiction scores
    backend/app/features/analysis/run.py
    frontend/src/features/analysis/RedFlagsPanel.tsx
    frontend/src/features/analysis/ContradictionCard.tsx
    frontend/src/features/analysis/YarnBoard.tsx
    frontend/src/features/analysis/PersonPolaroid.tsx
    frontend/src/features/analysis/AnomalyDetail.tsx
    tests/analysis/

Writes: data/analysis/persons.json, edges.json, contradictions.json
Reads: data/evidence/events.json, evidence.json, devices.csv, inventory.csv, data/scene/devices.json, rooms.json.
Calls: the three functions in scene/tools.py, and nothing else from that folder.
First hour: build against the fake events.json from Person 1's fake folder. Do not wait for real data.
Done when: Dana's identifiers merge into one person, contradictions.json contains the hero impossible walk plus the
other planted conflicts, and the yarn board shows people with anomaly scores.

---------------------------------------------------------------
### Person 4: Investigator and output   (branch feat/investigator)
The agent that reasons over verified facts, and the proof that they are verified.

Builds: stage 8 verifier, stage 9 lead investigator (deepagents).
Screens: Step 7 (memo, evidence request and approval, verified counter) and Step 8 (case report).

Files:
    backend/app/features/investigator/verifier.py       quote must appear verbatim in the cited file
    backend/app/features/investigator/lead_agent.py     deepagents lead, ranks hypotheses, says what disproves each
    backend/app/features/investigator/subagents.py      timeline, physics, comms, money
    backend/app/features/investigator/agent_tools.py    query_timeline, search_comms, graph_neighbors, request_evidence
    backend/app/features/investigator/run.py
    frontend/src/features/investigator/InvestigatorMemo.tsx
    frontend/src/features/investigator/HypothesisBar.tsx
    frontend/src/features/investigator/AgentTrace.tsx
    frontend/src/features/investigator/EvidenceRequestCard.tsx   the Approve step
    frontend/src/features/investigator/VerifiedCounter.tsx
    frontend/src/features/investigator/RejectedClaims.tsx
    frontend/src/features/investigator/CaseReport.tsx            PDF export
    tests/investigator/

Writes: data/investigator/verification.json, hypotheses.json, requests.json, notes.json
Reads: data/evidence/case.json, evidence.json, events.json, data/scene/devices.json, rooms.json, data/analysis/*.json.
Must never read answer_key.json or eval.json. The agent only sees verified facts.
Calls: the three functions in scene/tools.py. The other agent tools read the JSON files above.
Approve flow: POST /api/investigator/requests/<id>/approve, then POST /api/pipeline/rerun.
First hour: build the verifier against fake events, then the agent against fake contradictions.
Done when: the verified counter is accurate, the agent returns ranked hypotheses with "what would disprove this",
and approving a request reruns the pipeline and moves the confidence bars.

---------------------------------------------------------------
### Integrator (the skeleton person)   (works on main, small commits)
Owns the shared files. Builds the skeleton in the first 45 minutes, then merges, unblocks and keeps the demo running.
Files:
    backend/app/pipeline.py               wiring: calls each slice's run(case_id) in order
    backend/app/shared/llm_client.py      Groq client with retry on 429
    backend/app/shared/schema.py
    backend/app/registry.py
    frontend/src/registry.ts
    frontend/src/shared/ (store.ts, types.ts, useFindings, layout, global styles)
    .env.example, .gitignore, CLAUDE.md, CONTRACTS.md, docs/PLAN.md
    the code that merges all data/*/*.json into GET /api/case/1010F/findings
Done when: both apps start, all slots are filled with placeholders, and fake data flows to every screen.

Sat 5:30 to 8:00
Story paragraph, answer key, devices.csv
Freeze findings.json schema, write fake findings.json
Embed one Houston Matterport model, get Sweep.moveTo working
Vite app, desk and folder open with sound
8:00 to 11:00
Generate badge, Wi-Fi, USB, security log, manifest
Ingest, parsers, hashing, custody check
CoStar and Vexcel calls for the address; find Arlequin and Matterport mentors
Summary page, evidence locker against fake data
11:00 to 14:00
Emails, Slack, statements, transactions, CCTV, noise rows
Extractor agent, entity resolution, fact graph
Sweep graph, walking times, device tags in the scan
Aerial zoom, dollhouse with tenant labels
14:00
Integration 1: real ingest output drives the locker and scan



14:00 to 21:00
Rule engine for contradictions 1, 2, 4, 6, 8; evaluator
Isolation Forest, NLI, verifier; first nap block
Timeline to camera sync, red path drawing; first nap block
Timeline slider, red flags panel, yarn board
21:00
Integration 2: full end-to-end run on the real case, first eval score



21:00 to 3:00
Tune rules, check misses, prep camera 3 evidence for the request loop
deepagents lead, subagents, request_evidence replan loop
Photon agent, scan screenshots for replies
Lead investigator memo, counters, judge mode, report
3:00
Feature freeze. Only bug fixes after this



3:00 to 6:00
Peri write-up and evidence, Devpost text
Cache a complete run, stability fixes
Bug bash on scan sync
Polish, mute toggle, record 2 min video
6:00 to 7:30
Rehearse demo x3
README, repo cleanup
Upload video
Submit on Devpost with Discord names
Saturday morning check-ins: ask Arlequin what investigators struggle with most and whether the case looks realistic; ask Matterport engineers what the SDK exposes for sweeps, rooms and tags; ask CoStar how the toolkit maps an address to Matterport and Vexcel IDs.
Demo script (2 minutes)
For every judge, lead with what they score. Arlequin: the anomaly score and the cited contradiction. CoStar: the impossible walk in the scan. deepagents and Amazon: the evidence request and replan.
Time
Show
Say
0:00 to 0:15
The closed folder
"Insider theft cases mean weeks of cross-referencing logs. We do it in minutes and prove every step."
0:15 to 0:35
Drop zip, locker fills, red MISMATCH
"50 files, 6 formats. Chain of custody checked first, one file was tampered with."
0:35 to 0:50
Aerial into dollhouse with tenant labels
"CoStar, Vexcel and Matterport for the real building at this address."
0:50 to 1:15
Scrub timeline, click red pin, red path IMPOSSIBLE
"Badge in the lobby 30 seconds before a USB mount four floors up. The walk takes 74."
1:15 to 1:35
Yarn board, Dana high, Tom cleared
"Isolation Forest flags behavior. It also clears the IT admin, his after-hours work was scheduled."
1:35 to 1:50
Agent requests garage log, approve, bars move
"The agent asks for the evidence that would disprove its own theory."
1:50 to 2:00
Verified counter, judge mode score
"207 of 212 claims verified by code. 7 of 8 planted contradictions found."
Risks and fallbacks
Risk
Fallback
Matterport SDK does not expose sweep neighbors or room labels
Hand-trace a room graph on the floor plan image for floor 4 only and say so in the README
CoStar toolkit has no Matterport model for the chosen address
Pick the address from the toolkit's list of buildings that have all 3 layers, before writing the story
Agent is slow or flaky on stage
Play the cached run from findings.json; keep the live run for the request and replan step only
NLI scores are noisy
Render events as short plain sentences before scoring; keep only pairs above 0.85 and back them with a rule where possible
Synthetic data feels fake
A owns every timestamp; include noise rows and one honest miss in the eval
UI polish eats backend time
D builds against the fake findings.json only; no new animations after 3:00
Too many special tracks to demo
Prioritize Arlequin, CoStar, deepagents in person; Photon and Amazon ride on the same demo
Peri requires real consultation evidence
Only enter if the forensics firm gives a quote; never share real case data
Groq free-tier limits. Free Groq is capped per minute and per day, per model, and the caps are lower than they look for agents: roughly 12,000 tokens per minute on Llama 3.3 70B and 30,000 on Llama 4 Scout (check the limits page in the Groq console for your exact numbers). A deepagents loop resends its system prompt and tool definitions on every call, so it burns tokens fast.
• Spread work across models, since each model has its own limit: Scout for extraction, 70B only for the lead.
• Keep the lead's context small: it sees verified facts and tool results, never raw files.
• Add retry with exponential backoff on 429 errors in one shared client wrapper.
• Cache the full run in findings.json and replay it for most of the demo.
• If limits bite, one teammate adds a card to unlock Groq's Developer tier, which raises limits roughly 10x with pay-per-token pricing.

Photon is a later feature. Dependent on time scrap it for now

Few points/inputs we got from the ceo of arlequin(IMPORTANT): 

1. can’t provide analysis, you are only doing facts 
2. whatever you can disprove from facts to contradict makes ur claim stronger but its still entirely FACTUAL

3. feedback loop: challenge the investigator 
“what facts tell u that this person A would be here” 

4. AI can not put label, basically cant claim that this person is the perpetrator/role in crime fully, human is responsible for labelling.