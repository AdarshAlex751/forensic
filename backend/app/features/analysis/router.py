from fastapi import APIRouter

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"slice": "analysis", "status": "placeholder"}
