from fastapi import APIRouter

router = APIRouter(prefix="/api/scene", tags=["scene"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"slice": "scene", "status": "placeholder"}
