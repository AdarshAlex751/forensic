import asyncio
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import pipeline
from app.registry import SLICES, STAGES
from app.shared.config import CASE_ID
from app.shared.merge import build_findings

app = FastAPI(title="Forensic case agent")
for _name, _run, _router, _stages in SLICES:
    app.include_router(_router)


@app.get("/api/case/{case_id}/findings")
def findings(case_id: str) -> dict:
    if case_id != CASE_ID:
        raise HTTPException(404, f"unknown case {case_id}")
    return build_findings()


async def _progress_stream():
    last = -1
    while True:
        snap = dict(pipeline.state)
        if snap["seq"] != last:
            last = snap["seq"]
            yield f"data: {json.dumps(snap)}\n\n"
        if not snap["running"] and snap["seq"] > 0 and last == snap["seq"]:
            return
        await asyncio.sleep(0.25)


@app.get("/api/pipeline/progress")
async def progress() -> StreamingResponse:
    return StreamingResponse(_progress_stream(), media_type="text/event-stream")


class RerunBody(BaseModel):
    from_stage: str = "ingest"


@app.post("/api/pipeline/rerun")
def rerun(body: RerunBody | None = None) -> dict:
    stage = (body or RerunBody()).from_stage
    if stage not in STAGES:
        raise HTTPException(422, f"from_stage must be one of {STAGES}")
    return {"started": pipeline.start(stage), "from_stage": stage}
