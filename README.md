# Case #1010F: The Princeton Files

A forensic tool that checks every claim against the original case files, finds where the records contradict each other,
and lets a human decide. It reports facts and contradictions only; it never names a culprit. The case is fictional.

Slices: **evidence** (parse the case files), **scene** (building tour and spatial checks), **analysis** (red flags and
contradictions), **investigator** (verifier and lead investigator). `CONTRACTS.md` has the rules between them.

## Setup

You need Python 3.11+ and Node 20+.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r backend/requirements/all.txt   # large: analysis pulls in PyTorch
cp .env.example .env                 # Windows: copy .env.example .env
cd frontend && npm install && cd ..
```

Edit `.env`:

- Set all four flags to `true` for the demo: `USE_REAL_EVIDENCE`, `USE_REAL_SCENE`, `USE_REAL_ANALYSIS`,
  `USE_REAL_INVESTIGATOR`. With `false`, a slice serves its stored `fake/` files instead.
- `GROQ_API_KEY`: your Groq key (the investigator's language model). Without a working key the investigator still runs,
  using plain rules instead of the model.
- Matterport, Vexcel and CoStar keys are for the scene pages; `VITE_MATTERPORT_*` are read by the browser.

## Run

Two terminals, from the repo root:

```bash
cd backend && uvicorn app.main:app --port 8000      # API on http://localhost:8000
cd frontend && npm run dev                           # app on http://localhost:5173
```

Open http://localhost:5173. The dev server proxies `/api` to port 8000.

## Demo flow

1. **Desk**: click the dashed slot (or drop a file) and upload `data/evidence/CASE-1010F.zip`. A case folder appears.
2. Drag the folder onto the marked spot, or press **Open case folder**. The camera pushes in on golden paper and lands on
   the **Scene**: the Matterport tour, the incident timeline and the handwritten note for each stop.
3. **Red flags**: people ranked by how unusual their day was, with the measures behind each score.
4. **Contradictions**: each conflict with both sides, the original file and line, and a VERIFIED seal where the record
   matches its source.
5. **Investigator memo**: the verified-claims counter, the ranked hypotheses and one pending evidence request (the parking
   log). Press **Approve**: the file is released, the pipeline reruns, and the contradiction about "I went straight home at
   six" now cites the parking exit.
6. **Feedback**: a typewritten letter of questions for the investigator, written by a second model that reads the analysis
   (it does not read the investigator's output). The text types in one character at a time; click the paper or `[skip]`
   to finish it at once. `[ Regenerate questions ]` asks the model again and retypes the letter. It is only a set of
   questions to sharpen the investigation, never a conclusion.

## Tests

```bash
python -m pytest tests                      # backend; use -p no:cacheprovider if a temp folder is locked
cd frontend && npm run typecheck && npm run build
```

## Troubleshooting

- **Changed `.env`?** Restart both the backend and `npm run dev`. They read it only at startup.
- **"Saved views could not load" on the Scene page, or `/api/scene/...` returns 404**: the backend is an old process.
  Stop it and start it again.
- **The memo shows the same numbers after a rerun**: the pipeline takes about 20 to 40 seconds (the model runs last).
  Wait for the pipeline to finish.
- **Groq errors or a model "not found"**: the investigator picks a model your key can use and falls back to rules if none
  works; check `GROQ_API_KEY`. Set `INVESTIGATOR_LEAD_MODEL` to force one.
- **Pages look empty**: confirm `http://localhost:8000/api/case/1010F/findings` returns JSON, and that the flags above are
  `true`. After a test upload, `git checkout -- data/evidence data/analysis data/investigator` and delete
  `data/evidence/work` and `data/evidence/released.json` to return to the starting state.
- **Port already in use**: stop the other process on 8000 or 5173.
