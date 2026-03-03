"""Leaderboard route skeletons."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/leaderboard/{category}")
async def get_leaderboard(category: str) -> dict:
    """Fetch top-ranked services by category."""
    return {"data": {"category": category, "items": []}, "error": None}
