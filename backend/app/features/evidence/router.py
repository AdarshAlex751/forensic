from fastapi import APIRouter

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"slice": "evidence", "status": "placeholder"}


from fastapi import UploadFile  # noqa: E402

from app.shared.config import CASE_ID  # noqa: E402


@router.post("/upload")
async def upload(file: UploadFile) -> dict[str, str]:
    # Placeholder: Person 1 streams the zip to disk and starts ingest.
    return {"case_id": CASE_ID, "filename": file.filename or "", "status": "placeholder"}
