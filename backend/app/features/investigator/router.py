from fastapi import APIRouter

router = APIRouter(prefix="/api/investigator", tags=["investigator"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"slice": "investigator", "status": "placeholder"}


@router.post("/requests/{request_id}/approve")
def approve(request_id: str) -> dict[str, str]:
    # Placeholder: Person 4 marks the request approved, releases data/evidence/extra/, then reruns.
    from app import pipeline  # lazy: pipeline imports the registry, which imports this router

    pipeline.start("extract")
    return {"request_id": request_id, "status": "approved", "rerun": "started"}
