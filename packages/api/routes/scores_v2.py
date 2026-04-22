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
import re
from datetime import timezone
from typing import Any

from fastapi import APIRouter

from services.error_envelope import RhumbError
from services.score_cache import (
    CachedScore,
    ScoreAuditEntry,
    get_audit_chain,
    get_score_cache,
)
from services.service_slugs import CANONICAL_TO_PROXY, public_service_slug, public_service_slug_candidates

router = APIRouter(prefix="/v2/scores", tags=["scores-v2"])


def _public_provider_slug(provider_id: str | None) -> str:
    return public_service_slug(provider_id) or str(provider_id or "").strip().lower()


def _canonicalize_known_provider_aliases(
    text: Any,
    *,
    preserve_canonical: str | None = None,
) -> str | None:
    if text is None:
        return None

    preserved = str(preserve_canonical or "").strip().lower() or None
    replacements: dict[str, str] = {}
    for canonical in CANONICAL_TO_PROXY:
        if preserved and canonical.lower() == preserved:
            continue
        for candidate in public_service_slug_candidates(canonical):
            cleaned = str(candidate or "").strip()
            if not cleaned or cleaned.lower() == canonical.lower():
                continue
            replacements[cleaned.lower()] = canonical

    if not replacements:
        return str(text)

    pattern = re.compile(
        rf"(?<![a-z0-9-])(?:{'|'.join(re.escape(candidate) for candidate in sorted(replacements, key=len, reverse=True))})(?![a-z0-9-])",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: replacements[match.group(0).lower()], str(text))



def _canonicalize_provider_text(
    text: Any,
    response_provider_id: str | None,
    stored_provider_id: str | None,
) -> str | None:
    if text is None:
        return None

    canonical = public_service_slug(response_provider_id)
    if canonical is None:
        return str(text)

    raw_stored_provider_id = str(stored_provider_id).strip().lower() if stored_provider_id else None
    preserve_human_shorthand = raw_stored_provider_id == canonical.lower()

    canonicalized = str(text)
    for candidate in sorted(public_service_slug_candidates(canonical), key=len, reverse=True):
        cleaned = str(candidate or "").strip()
        if not cleaned or cleaned.lower() == canonical.lower():
            continue

        pattern = re.compile(
            rf"(?<![a-z0-9-]){re.escape(cleaned)}(?![a-z0-9-])",
            re.IGNORECASE,
        )

        def _replace(match: re.Match[str]) -> str:
            matched = match.group(0)
            if preserve_human_shorthand and cleaned.isalpha() and matched == cleaned.upper():
                return matched
            return canonical

        canonicalized = pattern.sub(_replace, canonicalized)

    return _canonicalize_known_provider_aliases(
        canonicalized,
        preserve_canonical=canonical if preserve_human_shorthand else None,
    )


def _score_to_response(entry: CachedScore) -> dict[str, Any]:
    """Format a CachedScore into the public response shape."""
    return {
        "service_slug": public_service_slug(entry.service_slug) or entry.service_slug,
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


def _audit_entry_to_response(entry: ScoreAuditEntry, *, response_provider_id: str | None) -> dict[str, Any]:
    """Format an audit entry for the public history endpoint."""
    return {
        "entry_id": entry.entry_id,
        "service_slug": public_service_slug(entry.service_slug) or entry.service_slug,
        "old_score": entry.old_score,
        "new_score": round(entry.new_score, 1),
        "change_reason": _canonicalize_provider_text(
            entry.change_reason,
            response_provider_id,
            entry.service_slug,
        ),
        "timestamp": entry.timestamp.isoformat(),
        "chain_hash": entry.chain_hash,
        "prev_hash": entry.prev_hash,
    }


def _cached_score_for_provider_id(provider_id: str) -> CachedScore | None:
    cache = get_score_cache()
    for candidate in public_service_slug_candidates(provider_id):
        entry = cache.get(candidate)
        if entry is not None:
            return entry
    return None


@router.get("/{provider_id}")
async def get_provider_score(provider_id: str) -> dict[str, Any]:
    """Get the current AN Score for a provider.

    Reads exclusively from the score cache — no direct DB access.
    """
    entry = _cached_score_for_provider_id(provider_id)

    if entry is None:
        public_provider_id = _public_provider_slug(provider_id)
        raise RhumbError(
            "SCORE_NOT_FOUND",
            message=f"No cached AN Score for provider '{public_provider_id}'.",
            detail=(
                "Check GET /v2/scores/cache/status to confirm the score cache is warm, "
                "or retry with a provider_id returned by the provider catalog."
            ),
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
    entries = chain.history(service_slug=public_service_slug_candidates(provider_id), limit=safe_limit)
    cached_score = _cached_score_for_provider_id(provider_id)

    if cached_score is None and not entries:
        public_provider_id = _public_provider_slug(provider_id)
        raise RhumbError(
            "SCORE_NOT_FOUND",
            message=f"No cached AN Score for provider '{public_provider_id}'.",
            detail=(
                "Check GET /v2/scores/cache/status to confirm the score cache is warm, "
                "or retry with a provider_id returned by the provider catalog."
            ),
        )

    return {
        "data": {
            "service_slug": _public_provider_slug(provider_id),
            "entries": [
                _audit_entry_to_response(e, response_provider_id=provider_id)
                for e in entries
            ],
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
