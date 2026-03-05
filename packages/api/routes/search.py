"""Search route skeletons."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/search")
async def search_services(q: str, limit: int = 10) -> dict:
    """Semantic search endpoint."""
    bounded_limit = max(1, min(limit, 50))
    return {"data": {"query": q, "limit": bounded_limit, "results": []}, "error": None}
