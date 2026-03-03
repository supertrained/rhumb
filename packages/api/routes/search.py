"""Search route skeletons."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/search")
async def search_services(q: str) -> dict:
    """Semantic search endpoint."""
    return {"data": {"query": q, "results": []}, "error": None}
