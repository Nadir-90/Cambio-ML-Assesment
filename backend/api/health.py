from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    """Liveness probe endpoint."""
    return {"status": "ok"}
