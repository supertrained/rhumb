"""v2 Score endpoints — read-only public surface for AN Scores (WU-41.4).

These endpoints serve scores ONLY from the read-only score cache.
They have no write access to the Score DB.

Endpoints:
  GET /v2/scores/{provider_id}         — published AN Score
  GET /v2/scores/{provider_id}/history — AN Score change log (audit chain)
  GET /v2/scores/cache/status          — cache health / refresh info
"""

from __future__ import annotations

import math
from datetime import timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from services.score_cache import (
    CachedScore,
    ScoreAuditEntry,
    get_audit_chain,
    get_score_cache,
)

router = APIRouter(prefix="/v2/scores", tags=["scores-v2"])


def _score_to_response(entry: CachedScore) -> dict[str, Any]:
    """Format a CachedScore into the public response shape."""
    return {
        "service_slug": entry.service_slug,
        "an_score": round(entry.an_score, 1),
        "execution_score": round(entry.execution_score, 1),
        "access_readiness_score": (
            round(entry.access_readiness_score, 1)
            if entry.access_readiness_score is not None
            else None
        ),
        "autonomy_score": (
            round(entry.autonomy_score, 1) if entry.autonomy_score is not None else None
        ),
        "confidence": round(entry.confidence, 2),
        "tier": entry.tier,
        "source": "score_cache",
        "cache_note": "Read-only snapshot. Score computation is structurally independent.",
    }


def _audit_entry_to_response(entry: ScoreAuditEntry) -> dict[str, Any]:
    """Format an audit entry for the public history endpoint."""
    return {
        "entry_id": entry.entry_id,
        "service_slug": entry.service_slug,
        "old_score": entry.old_score,
        "new_score": round(entry.new_score, 1),
        "change_reason": entry.change_reason,
        "timestamp": entry.timestamp.isoformat(),
        "chain_hash": entry.chain_hash,
        "prev_hash": entry.prev_hash,
    }


@router.get("/{provider_id}")
async def get_provider_score(provider_id: str) -> dict[str, Any]:
    """Get the current AN Score for a provider.

    Reads exclusively from the score cache — no direct DB access.
    """
    cache = get_score_cache()
    entry = cache.get(provider_id)

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "SCORE_NOT_FOUND",
                "message": f"No cached AN Score for provider '{provider_id}'.",
                "hint": "Score may not be computed yet, or cache may need a refresh.",
            },
        )

    return {"data": _score_to_response(entry), "error": None}


@router.get("/{provider_id}/history")
async def get_provider_score_history(
    provider_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Get the AN Score change audit trail for a provider.

    Returns chain-hashed audit entries for verifiable score history.
    """
    safe_limit = max(1, min(limit, 200))
    chain = get_audit_chain()
    entries = chain.history(service_slug=provider_id, limit=safe_limit)

    return {
        "data": {
            "service_slug": provider_id,
            "entries": [_audit_entry_to_response(e) for e in entries],
            "chain_verified": chain.verify_chain(),
            "total_chain_length": chain.length,
        },
        "error": None,
    }


@router.get("/cache/status")
async def cache_status() -> dict[str, Any]:
    """Score cache health and metadata.

    Public diagnostic — shows cache size, age, and structural guarantees.
    """
    cache = get_score_cache()
    chain = get_audit_chain()

    refresh_age = cache.last_refresh_age_seconds
    refresh_attempt_age = cache.last_refresh_attempt_age_seconds

    return {
        "data": {
            "cache_size": cache.size,
            "last_refresh_age_seconds": (
                None if math.isinf(refresh_age) else round(refresh_age, 1)
            ),
            "last_refresh_attempt_age_seconds": (
                None if math.isinf(refresh_attempt_age) else round(refresh_attempt_age, 1)
            ),
            "last_refresh_status": cache.last_refresh_status,
            "last_refresh_error": cache.last_refresh_error,
            "audit_chain_length": chain.length,
            "audit_chain_verified": chain.verify_chain(),
            "latest_chain_hash": chain.latest_hash,
            "structural_guarantees": [
                "Routing engine reads from cache only — no Score DB write access",
                "Score changes are chain-hashed and immutable",
                "Commercial data is in a separate namespace — no joins to Score DB",
                "Cache is a read-only snapshot refreshed on TTL",
            ],
        },
        "error": None,
    }
