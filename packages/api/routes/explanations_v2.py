"""Route explanation query endpoint (WU-41.3).

Provides:
- ``GET /v2/explanations/{explanation_id}`` — retrieve a full route explanation
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from services.error_envelope import RhumbError
from services.route_explanation import get_explanation, get_persisted_explanation

router = APIRouter()


@router.get("/explanations/{explanation_id}")
async def get_route_explanation(explanation_id: str) -> dict[str, Any]:
    """Retrieve a stored route explanation by ID.

    Explanations are created during Layer 2 routing decisions and stored
    in-memory for query.  Layer 1 explanations are trivial (agent pinned)
    and also queryable here.
    """
    explanation = get_explanation(explanation_id)
    if explanation is None:
        explanation = await get_persisted_explanation(explanation_id)
    if explanation is None:
        raise RhumbError(
            "CAPABILITY_NOT_FOUND",
            message=f"Explanation '{explanation_id}' not found.",
            detail=(
                "Explanations are stored in-memory and may expire. "
                "The explanation_id is returned in execution responses."
            ),
        )

    return {
        "error": None,
        "data": explanation.to_dict(),
    }
