"""v2 Trust Dashboard API — agent visibility into execution trust metrics (WU-41.6).

Agents need visibility into their execution history, reliability, and spend.
These endpoints aggregate data from receipts, billing events, and score cache.

Endpoints:
  GET /v2/trust/summary      — Agent trust summary (executions, reliability, spend)
  GET /v2/trust/providers     — Provider distribution and trust metrics
  GET /v2/trust/costs         — Cost breakdown by provider and capability
  GET /v2/trust/reliability   — Reliability metrics (success rates, latencies)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.billing_events import (
    BillingEventType,
    get_billing_event_stream,
    normalize_period_filter,
    period_matches_timestamp,
)
from services.error_envelope import RhumbError
from services.score_cache import get_score_cache
from services.service_slugs import public_service_slug, public_service_slug_candidates

router = APIRouter(prefix="/v2/trust", tags=["trust-v2"])
logger = logging.getLogger(__name__)

_identity_store: AgentIdentityStore | None = None


def _get_identity_store() -> AgentIdentityStore:
    global _identity_store
    if _identity_store is None:
        _identity_store = get_agent_identity_store()
    return _identity_store


async def _require_org(api_key: str | None) -> str:
    """Validate API key and return org_id."""
    raise NotImplementedError("_require_org now requires a Request; call _require_org_or_401")


def _auth_handoff(*, reason: str, retry_url: str) -> dict[str, Any]:
    return {
        "reason": reason,
        "recommended_path": "governed_api_key",
        "retry_url": retry_url,
        "docs_url": "/docs#resolve-mental-model",
        "paths": [
            {
                "kind": "governed_api_key",
                "recommended": True,
                "setup_url": "/auth/login",
                "retry_header": "X-Rhumb-Key",
                "summary": "Default for dashboards and most repeat agent traffic.",
                "requires_human_setup": True,
                "automatic_after_setup": True,
            }
        ],
    }


def _missing_governed_key_response(raw_request: Request) -> JSONResponse:
    request_id = getattr(raw_request.state, "request_id", None) or str(uuid.uuid4())
    detail = "Missing X-Rhumb-Key header"
    retry_url = str(raw_request.url.path)
    return JSONResponse(
        status_code=401,
        content={
            "detail": detail,
            "error": "missing_api_key",
            "message": detail,
            "resolution": "Provide a funded governed API key via /auth/login, then retry.",
            "request_id": request_id,
            "auth_handoff": _auth_handoff(reason="missing_api_key", retry_url=retry_url),
        },
    )


def _invalid_governed_key_response(raw_request: Request) -> JSONResponse:
    request_id = getattr(raw_request.state, "request_id", None) or str(uuid.uuid4())
    detail = "Invalid or expired governed API key"
    retry_url = str(raw_request.url.path)
    return JSONResponse(
        status_code=401,
        content={
            "detail": detail,
            "error": "invalid_api_key",
            "message": detail,
            "resolution": "Create or use a funded governed API key via /auth/login, then retry.",
            "request_id": request_id,
            "auth_handoff": _auth_handoff(reason="invalid_api_key", retry_url=retry_url),
        },
    )


def _validated_period_filter(period: str | None) -> str | None:
    try:
        return normalize_period_filter(period)
    except ValueError as exc:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'period' filter.",
            detail="Use YYYY-MM or YYYY-MM-DD (for example 2026-04 or 2026-04-22).",
        ) from exc


async def _require_org_or_401(raw_request: Request, api_key: str | None) -> str | JSONResponse:
    """Validate governed API key and return org_id, or a structured 401 response."""
    normalized_key = str(api_key or "").strip()
    if not normalized_key:
        return _missing_governed_key_response(raw_request)
    agent = await _get_identity_store().verify_api_key_with_agent(normalized_key)
    if agent is None:
        return _invalid_governed_key_response(raw_request)
    return agent.organization_id


def _public_provider_totals(by_provider: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for slug, cents in by_provider.items():
        public_slug = public_service_slug(slug) or str(slug or "").strip()
        if not public_slug:
            continue
        merged[public_slug] = merged.get(public_slug, 0) + cents
    return merged


@router.get("/summary")
async def trust_summary(
    raw_request: Request,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    period: str | None = Query(None, description="Period filter: YYYY-MM or YYYY-MM-DD"),
) -> dict[str, Any]:
    """Agent trust summary — high-level view of execution history.

    Aggregates execution count, success rate, total spend, provider
    diversity, and trust posture for the authenticated org.
    """
    normalized_period = _validated_period_filter(period)
    org_id = await _require_org_or_401(raw_request, x_rhumb_key)
    if isinstance(org_id, JSONResponse):
        return org_id
    stream = get_billing_event_stream()
    summary = stream.summarize(org_id=org_id, period=normalized_period)

    # Compute success metrics from events
    all_events = stream.query(org_id=org_id, limit=100_000)
    if normalized_period:
        all_events = [
            e for e in all_events
            if period_matches_timestamp(e.timestamp, normalized_period)
        ]

    execution_events = [
        e for e in all_events
        if e.event_type in (
            BillingEventType.EXECUTION_CHARGED,
            BillingEventType.EXECUTION_FAILED_NO_CHARGE,
        )
    ]
    total_executions = len(execution_events)
    successful = sum(
        1 for e in execution_events
        if e.event_type == BillingEventType.EXECUTION_CHARGED
    )
    success_rate = (successful / total_executions * 100) if total_executions > 0 else 0.0

    unique_providers = set(
        public_service_slug(e.provider_slug)
        for e in execution_events
        if public_service_slug(e.provider_slug)
    )
    unique_capabilities = set(
        e.capability_id for e in execution_events if e.capability_id
    )

    return {
        "data": {
            "org_id": org_id,
            "period": normalized_period or "all",
            "total_executions": total_executions,
            "successful_executions": successful,
            "failed_executions": total_executions - successful,
            "success_rate_pct": round(success_rate, 1),
            "total_spend_usd": summary.total_charged_usd_cents / 100,
            "total_spend_usd_cents": summary.total_charged_usd_cents,
            "unique_providers_used": len(unique_providers),
            "unique_capabilities_used": len(unique_capabilities),
            "x402_payment_count": summary.x402_payment_count,
            "credit_purchase_count": summary.credit_purchase_count,
            "trust_posture": _compute_trust_posture(
                total_executions, success_rate, len(unique_providers),
            ),
        },
        "error": None,
    }


@router.get("/providers")
async def trust_providers(
    raw_request: Request,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    period: str | None = Query(None, description="Period filter"),
) -> dict[str, Any]:
    """Provider distribution and trust metrics.

    Shows which providers were used, their execution counts,
    success rates, and current AN Scores.
    """
    normalized_period = _validated_period_filter(period)
    org_id = await _require_org_or_401(raw_request, x_rhumb_key)
    if isinstance(org_id, JSONResponse):
        return org_id
    stream = get_billing_event_stream()
    cache = get_score_cache()

    all_events = stream.query(org_id=org_id, limit=100_000)
    if normalized_period:
        all_events = [
            e for e in all_events
            if period_matches_timestamp(e.timestamp, normalized_period)
        ]

    execution_events = [
        e for e in all_events
        if e.event_type in (
            BillingEventType.EXECUTION_CHARGED,
            BillingEventType.EXECUTION_FAILED_NO_CHARGE,
        )
    ]

    # Aggregate by provider
    provider_stats: dict[str, dict[str, Any]] = {}
    for event in execution_events:
        slug = public_service_slug(event.provider_slug) or "unknown"
        if slug not in provider_stats:
            provider_stats[slug] = {
                "provider_slug": slug,
                "execution_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_charged_usd_cents": 0,
            }
        stats = provider_stats[slug]
        stats["execution_count"] += 1
        if event.event_type == BillingEventType.EXECUTION_CHARGED:
            stats["success_count"] += 1
            stats["total_charged_usd_cents"] += event.amount_usd_cents
        else:
            stats["failure_count"] += 1

    # Enrich with AN scores from cache
    provider_list = []
    for slug, stats in sorted(
        provider_stats.items(),
        key=lambda x: -x[1]["execution_count"],
    ):
        total = stats["execution_count"]
        success_rate = (stats["success_count"] / total * 100) if total > 0 else 0.0
        cached_score = _score_for_provider_slug(cache, slug)

        provider_list.append({
            **stats,
            "success_rate_pct": round(success_rate, 1),
            "total_charged_usd": stats["total_charged_usd_cents"] / 100,
            "an_score": round(cached_score.an_score, 1) if cached_score else None,
            "tier": cached_score.tier if cached_score else None,
        })

    return {
        "data": {
            "org_id": org_id,
            "period": normalized_period or "all",
            "providers": provider_list,
            "total_providers": len(provider_list),
        },
        "error": None,
    }


@router.get("/costs")
async def trust_costs(
    raw_request: Request,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    period: str | None = Query(None, description="Period filter"),
) -> dict[str, Any]:
    """Cost breakdown by provider and capability.

    Shows where money is going — aggregated by provider and by capability.
    """
    normalized_period = _validated_period_filter(period)
    org_id = await _require_org_or_401(raw_request, x_rhumb_key)
    if isinstance(org_id, JSONResponse):
        return org_id
    stream = get_billing_event_stream()
    summary = stream.summarize(org_id=org_id, period=normalized_period)

    public_by_provider = _public_provider_totals(summary.by_provider)

    return {
        "data": {
            "org_id": org_id,
            "period": normalized_period or "all",
            "total_charged_usd_cents": summary.total_charged_usd_cents,
            "total_charged_usd": summary.total_charged_usd_cents / 100,
            "total_credited_usd_cents": summary.total_credited_usd_cents,
            "total_credited_usd": summary.total_credited_usd_cents / 100,
            "net_usd": (summary.total_charged_usd_cents - summary.total_credited_usd_cents) / 100,
            "by_provider": {
                slug: {
                    "charged_usd_cents": cents,
                    "charged_usd": cents / 100,
                    "pct_of_total": (
                        round(cents / summary.total_charged_usd_cents * 100, 1)
                        if summary.total_charged_usd_cents > 0
                        else 0.0
                    ),
                }
                for slug, cents in sorted(
                    public_by_provider.items(),
                    key=lambda x: -x[1],
                )
            },
            "by_capability": {
                cap: {
                    "charged_usd_cents": cents,
                    "charged_usd": cents / 100,
                    "pct_of_total": (
                        round(cents / summary.total_charged_usd_cents * 100, 1)
                        if summary.total_charged_usd_cents > 0
                        else 0.0
                    ),
                }
                for cap, cents in sorted(
                    summary.by_capability.items(),
                    key=lambda x: -x[1],
                )
            },
            "execution_count": summary.execution_count,
            "avg_cost_per_execution_usd": (
                round(summary.total_charged_usd_cents / summary.execution_count / 100, 4)
                if summary.execution_count > 0
                else 0.0
            ),
        },
        "error": None,
    }


@router.get("/reliability")
async def trust_reliability(
    raw_request: Request,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    period: str | None = Query(None, description="Period filter"),
) -> dict[str, Any]:
    """Reliability metrics — success rates, failure patterns, provider health.

    Helps agents understand which providers are reliable and which
    are causing failures.
    """
    normalized_period = _validated_period_filter(period)
    org_id = await _require_org_or_401(raw_request, x_rhumb_key)
    if isinstance(org_id, JSONResponse):
        return org_id
    stream = get_billing_event_stream()

    all_events = stream.query(org_id=org_id, limit=100_000)
    if normalized_period:
        all_events = [
            e for e in all_events
            if period_matches_timestamp(e.timestamp, normalized_period)
        ]

    execution_events = [
        e for e in all_events
        if e.event_type in (
            BillingEventType.EXECUTION_CHARGED,
            BillingEventType.EXECUTION_FAILED_NO_CHARGE,
        )
    ]

    # Per-provider reliability
    provider_reliability: dict[str, dict[str, int]] = {}
    for event in execution_events:
        slug = public_service_slug(event.provider_slug) or "unknown"
        if slug not in provider_reliability:
            provider_reliability[slug] = {"success": 0, "failure": 0}
        if event.event_type == BillingEventType.EXECUTION_CHARGED:
            provider_reliability[slug]["success"] += 1
        else:
            provider_reliability[slug]["failure"] += 1

    # Per-capability reliability
    capability_reliability: dict[str, dict[str, int]] = {}
    for event in execution_events:
        cap = event.capability_id or "unknown"
        if cap not in capability_reliability:
            capability_reliability[cap] = {"success": 0, "failure": 0}
        if event.event_type == BillingEventType.EXECUTION_CHARGED:
            capability_reliability[cap]["success"] += 1
        else:
            capability_reliability[cap]["failure"] += 1

    # Build provider reliability list
    providers = []
    for slug, counts in sorted(
        provider_reliability.items(),
        key=lambda x: -(x[1]["success"] + x[1]["failure"]),
    ):
        total = counts["success"] + counts["failure"]
        rate = (counts["success"] / total * 100) if total > 0 else 0.0
        providers.append({
            "provider_slug": slug,
            "total_executions": total,
            "successes": counts["success"],
            "failures": counts["failure"],
            "success_rate_pct": round(rate, 1),
            "health": _provider_health_label(rate, total),
        })

    # Build capability reliability list
    capabilities = []
    for cap, counts in sorted(
        capability_reliability.items(),
        key=lambda x: -(x[1]["success"] + x[1]["failure"]),
    ):
        total = counts["success"] + counts["failure"]
        rate = (counts["success"] / total * 100) if total > 0 else 0.0
        capabilities.append({
            "capability_id": cap,
            "total_executions": total,
            "successes": counts["success"],
            "failures": counts["failure"],
            "success_rate_pct": round(rate, 1),
        })

    total_executions = len(execution_events)
    total_success = sum(
        1 for e in execution_events
        if e.event_type == BillingEventType.EXECUTION_CHARGED
    )
    overall_rate = (total_success / total_executions * 100) if total_executions > 0 else 0.0

    return {
        "data": {
            "org_id": org_id,
            "period": normalized_period or "all",
            "overall": {
                "total_executions": total_executions,
                "successes": total_success,
                "failures": total_executions - total_success,
                "success_rate_pct": round(overall_rate, 1),
            },
            "by_provider": providers,
            "by_capability": capabilities,
        },
        "error": None,
    }


# ── Helpers ──────────────────────────────────────────────────────────


def _compute_trust_posture(
    total_executions: int,
    success_rate: float,
    provider_count: int,
) -> dict[str, Any]:
    """Compute a human-readable trust posture assessment."""
    if total_executions == 0:
        return {
            "level": "new",
            "label": "No execution history",
            "description": "Execute capabilities to build your trust profile.",
        }

    if success_rate >= 99.0 and provider_count >= 3:
        level = "excellent"
        label = "Excellent"
        description = "High reliability across multiple providers."
    elif success_rate >= 95.0:
        level = "good"
        label = "Good"
        description = "Strong execution reliability with room for provider diversity."
    elif success_rate >= 85.0:
        level = "fair"
        label = "Fair"
        description = "Some execution failures detected. Review provider reliability."
    else:
        level = "needs_attention"
        label = "Needs Attention"
        description = "Significant failure rate. Check provider health and capability configurations."

    return {
        "level": level,
        "label": label,
        "description": description,
    }


def _provider_health_label(success_rate: float, total_executions: int) -> str:
    """Assign a health label to a provider based on success rate."""
    if total_executions < 3:
        return "insufficient_data"
    if success_rate >= 99.0:
        return "healthy"
    if success_rate >= 95.0:
        return "degraded"
    if success_rate >= 80.0:
        return "unstable"
    return "unhealthy"


def _score_for_provider_slug(cache: Any, slug: str) -> Any | None:
    for candidate in public_service_slug_candidates(slug):
        cached_score = cache.get(candidate)
        if cached_score is not None:
            return cached_score
    return None
