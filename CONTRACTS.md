# CONTRACTS.md
Four people, four slices. Each person edits only the folders listed under their own number.
Everything else is read-only. People connect only through JSON files, a few API routes and 3 tool functions.

## Who is who (fill in)
Person 1 (Case and evidence)      : ______
Person 2 (Spatial and scene)      : ______
Person 3 (Analysis)               : ______
Person 4 (Investigator and output): ______
Integrator (shared files, merging main, keeping the demo running): ______ (the skeleton person)

---------------------------------------------------------------
## Person 1: Case and evidence
Owns (any new files inside):
  backend/app/features/evidence/
  frontend/src/features/evidence/
  data/evidence/        (including data/evidence/fake/)
  tests/evidence/
  frontend/src/shared/sounds.ts   (built in hour 1, then read-only)
Writes: data/evidence/case.json, evidence.json, events.json
Also provides: data/evidence/devices.csv, inventory.csv (badge, laptop, MAC to person),
  answer_key.json, and data/evidence/extra/ (camera 3 footage, garage exit log; released only when a request is approved)
Does NOT write: the "verified" field on events (see rule 8)
Reads (never edits): nothing from other people's folders

## Person 2: Spatial and scene
Owns:
  backend/app/features/scene/
  frontend/src/features/scene/
  data/scene/           (including data/scene/fake/)
  tests/scene/
Writes: data/scene/devices.json, rooms.json, eval.json
Also owns the evaluator (backend/app/features/scene/evaluator.py) and Judge mode (frontend/src/features/scene/JudgeMode.tsx).
Provides in backend/app/features/scene/tools.py (signatures stay fixed):
  walk_time(room_a, room_b) -> { seconds, path }
  ap_covers(ap_id, room_id) -> bool
  camera_sees(camera_id, room_id) -> bool
Commits stubs with hard-coded answers in the first hour so Persons 3 and 4 are never blocked.
Reads (never edits): data/evidence/devices.csv, data/evidence/events.json, data/analysis/contradictions.json,
  data/evidence/answer_key.json (evaluator only)

## Person 3: Analysis
Owns:
  backend/app/features/analysis/
  frontend/src/features/analysis/
  data/analysis/        (including data/analysis/fake/)
  tests/analysis/
Writes: data/analysis/persons.json, edges.json, contradictions.json
Reads (never edits): data/evidence/events.json, evidence.json, devices.csv, inventory.csv,
  data/scene/devices.json, rooms.json
Calls: the three functions in scene/tools.py (nothing else from that folder)

## Person 4: Investigator and output
Owns:
  backend/app/features/investigator/
  frontend/src/features/investigator/
  data/investigator/    (including data/investigator/fake/)
  tests/investigator/
Writes: data/investigator/verification.json, hypotheses.json, requests.json, notes.json
Reads (never edits): data/evidence/case.json, evidence.json, events.json,
  data/scene/devices.json, rooms.json, data/analysis/*.json
Must never read data/evidence/answer_key.json or data/scene/eval.json.
Calls: the three functions in scene/tools.py

---------------------------------------------------------------
## Shared files (Integrator only; everyone may import FROM shared/, nobody else edits it)
  backend/app/pipeline.py             LangGraph wiring; calls each slice's run(case_id)
  backend/app/shared/llm_client.py    Groq client with retry on 429
  backend/app/shared/schema.py        data shapes (from the findings.json schema in docs/PLAN.md)
  backend/app/registry.py, frontend/src/registry.ts
  frontend/src/shared/ (except sounds.ts): store.ts, types.ts, useFindings, layout, global styles
  .env.example, .gitignore, CLAUDE.md, CONTRACTS.md, docs/PLAN.md
  the code that merges data/*/*.json into /api/case/1010F/findings
  (the eval part of findings comes from data/scene/eval.json)

## Ports and API routes
Backend runs on :8000. Frontend runs on :5173 and proxies /api to :8000.
Each slice's own routes start with /api/<slice>/ (evidence, scene, analysis, investigator).
Integrator-owned routes:
  GET  /api/case/1010F/findings         all data, merged
  GET  /api/pipeline/progress           live progress (SSE)
  POST /api/pipeline/rerun              reruns the pipeline from a stage on
Person 1: POST /api/evidence/upload
Person 4: POST /api/investigator/requests/<id>/approve  (then calls /api/pipeline/rerun)

## Screens that combine two people's work (slots)
The Integrator's layout mounts panels from the registry, so nobody imports another person's component.
  Scene page (Person 2): Red flags panel (Person 3)
  Yarn board page (Person 3): Memo panel (Person 4)
  Summary page (Person 1): contains the Evidence Locker itself
  Judge mode toggle (Person 2): mounted by the layout on every page
The skeleton registers these placeholders on day one. People replace the component inside their own folder only.

## Rules that prevent conflicts
1. Nobody edits files in another person's folders. Need a change? Message that person.
2. Imports: only from your own folder and from shared/. Never from another person's folder.
3. Each slice has run.py with run(case_id). That is the only thing pipeline.py calls.
4. One output file per section (listed above). Nobody writes into someone else's JSON.
5. Fake data lives inside each owner's own data folder (data/<slice>/fake/). Build against other people's fakes until
   the real file exists, then set USE_REAL_<SLICE>=true in .env.
6. Data shapes come from the schema in docs/PLAN.md and shared/schema.py. Adding a field is fine.
   Renaming or removing one needs the owner and the team to agree first.
7. Time: one timezone for the whole case, Houston local time with its offset
   (example 2026-03-04T18:18:00-06:00). Never mix with UTC. IDs: p1.., e1.., c1.., h1.., r1..
8. The "verified" flag on events is set by the merge code from verification.json (Person 4). Person 1 never writes it.
9. Every event, edge, contradiction and hypothesis carries source: file, line, quote, sha256.
10. Registries are never edited after the skeleton. Frontend state is shared only through store.ts keys:
    selectedEventId, selectedContradictionId, timelineTime, selectedPersonId.
    Styles stay inside your own folder, not in global styles.
11. Python packages go in backend/requirements/<slice>.txt, never a shared file.
12. Frontend packages are all installed in the skeleton. If someone truly needs a new one: tiny commit (only
    package.json and the lockfile), pushed right away. Nobody hand-edits package-lock.json.
    If it conflicts, run npm install and commit the result.
13. Secrets go in .env (never committed). New variable names go to the Integrator for .env.example.
14. Need a shared-file change? Message the Integrator. If there is no reply in 15 minutes, make a tiny separate commit
    on main for that change only, then tell the team.

## Git rules
- One branch per person: feat/evidence, feat/scene, feat/analysis, feat/investigator.
- Commit small. Merge to main at least every 1-2 hours.
- Before every merge: git pull --rebase origin main, start both apps, confirm they run.
- Never push a broken main. If main breaks, fixing it comes first.
- When someone merges, everyone else runs git pull --rebase origin main.
- Never force-push to main.

## Skeleton checklist (Integrator, first 45 minutes)
Both apps start. All four slice folders exist with run.py and a placeholder page or panel. Registries and slots
pre-filled. data/<slice>/fake/ files for every output. shared/schema.py, shared/types.ts, useFindings, store.ts,
llm_client.py, pipeline.py (stubs). backend/requirements/<slice>.txt. .env.example, .gitignore
(node_modules, .venv, __pycache__, .env, dist). The ports and routes above.
All frontend packages from the plan installed once: framer-motion, howler, page-flip, react-force-graph-2d,
leaflet, plus the Matterport SDK needs and the type packages. Lockfile committed.

## Schedule
14:00 Integration 1. 21:00 Integration 2. 03:00 Feature freeze (bug fixes only).