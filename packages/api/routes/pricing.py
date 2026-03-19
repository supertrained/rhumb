"""Public pricing contract endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from services.pricing import get_pricing_catalog

router = APIRouter()


@router.get("/pricing")
async def get_pricing() -> dict:
    """Return the machine-readable public pricing contract."""
    return {"data": get_pricing_catalog(), "error": None}
