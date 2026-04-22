"""v2 Billing endpoints — event stream, summaries, and billing health (WU-41.5).

These endpoints expose the structured billing event stream for
agents and the trust dashboard.

Endpoints:
  GET /v2/billing/events          — query billing events (filtered)
  GET /v2/billing/summary         — aggregate billing summary for an org
  GET /v2/billing/stream/status   — event stream health and integrity
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid
from typing import Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.error_envelope import RhumbError
from services.billing_events import (
    BillingEvent,
    BillingEventSummary,
    BillingEventType,
    get_billing_event_stream,
    normalize_period_filter,
)
from services.service_slugs import CANONICAL_TO_PROXY, public_service_slug, public_service_slug_candidates

router = APIRouter(prefix="/v2/billing", tags=["billing-v2"])

_identity_store: AgentIdentityStore | None = None

_PROVIDER_VALUE_FIELDS = {
    "provider",
    "provider_id",
    "provider_slug",
    "provider_used",
    "fallback_provider",
    "selected_provider",
    "service",
    "service_slug",
}
_PROVIDER_LIST_FIELDS = {
    "allow_only",
    "fallback_providers",
    "provider_deny",
    "provider_ids",
    "provider_preference",
    "providers",
    "service_slugs",
}
_PROVIDER_TEXT_FIELDS = {
    "detail",
    "error",
    "error_message",
    "message",
    "reason",
}


def _get_identity_store() -> AgentIdentityStore:
    global _identity_store
    if _identity_store is None:
        _identity_store = get_agent_identity_store()
    return _identity_store


async def _require_org(api_key: str | None) -> str:
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
    detail = "Invalid or expired API key"
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


def _validated_event_type(event_type: str | None) -> BillingEventType | None:
    if event_type is None:
        return None

    try:
        return BillingEventType(event_type)
    except ValueError as exc:
        valid_types = ", ".join(t.value for t in BillingEventType)
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'event_type' filter.",
            detail=f"Use one of: {valid_types}.",
        ) from exc


def _validated_since_timestamp(since: str | None) -> datetime | None:
    if since is None:
        return None

    try:
        parsed_since = datetime.fromisoformat(since)
    except ValueError as exc:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'since' filter.",
            detail="Use an ISO 8601 timestamp (for example 2026-04-22T12:34:56+00:00).",
        ) from exc

    if parsed_since.tzinfo is None:
        parsed_since = parsed_since.replace(tzinfo=timezone.utc)
    return parsed_since


async def _require_org_or_401(raw_request: Request, api_key: str | None) -> str | JSONResponse:
    """Validate governed API key and return org_id, or a structured 401 response."""
    if not api_key:
        return _missing_governed_key_response(raw_request)
    agent = await _get_identity_store().verify_api_key_with_agent(api_key)
    if agent is None:
        return _invalid_governed_key_response(raw_request)
    return agent.organization_id


def _canonicalize_provider_value(value: Any) -> Any:
    if isinstance(value, str):
        return public_service_slug(value) or value
    return value


def _canonicalize_known_provider_aliases(text: Any) -> str | None:
    if text is None:
        return None

    replacements: dict[str, str] = {}
    for canonical in CANONICAL_TO_PROXY:
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


def _canonicalize_provider_text(text: Any, provider_slugs: set[str]) -> str | None:
    if text is None:
        return None

    canonicalized = str(text)
    for provider_slug in provider_slugs:
        canonical = public_service_slug(provider_slug)
        if canonical is None:
            continue
        for candidate in sorted(public_service_slug_candidates(canonical), key=len, reverse=True):
            if not candidate or candidate == canonical:
                continue
            canonicalized = re.sub(
                rf"(?<![a-z0-9-]){re.escape(candidate)}(?![a-z0-9-])",
                canonical,
                canonicalized,
                flags=re.IGNORECASE,
            )
    return _canonicalize_known_provider_aliases(canonicalized)


def _collect_provider_contexts(value: Any, *, provider_slugs: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _PROVIDER_VALUE_FIELDS and isinstance(item, str):
                provider_slugs.add(item)
                continue
            if key in _PROVIDER_LIST_FIELDS and isinstance(item, list):
                for entry in item:
                    if isinstance(entry, str):
                        provider_slugs.add(entry)
                    else:
                        _collect_provider_contexts(entry, provider_slugs=provider_slugs)
                continue
            _collect_provider_contexts(item, provider_slugs=provider_slugs)
        return

    if isinstance(value, list):
        for item in value:
            _collect_provider_contexts(item, provider_slugs=provider_slugs)


def _canonicalize_provider_payload(value: Any, *, provider_slugs: set[str]) -> Any:
    if isinstance(value, dict):
        canonicalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in _PROVIDER_VALUE_FIELDS:
                canonicalized[key] = _canonicalize_provider_value(item)
            elif key in _PROVIDER_LIST_FIELDS and isinstance(item, list):
                canonicalized[key] = [
                    _canonicalize_provider_value(entry)
                    if isinstance(entry, str)
                    else _canonicalize_provider_payload(entry, provider_slugs=provider_slugs)
                    for entry in item
                ]
            elif key in _PROVIDER_TEXT_FIELDS and not isinstance(item, (dict, list)):
                canonicalized[key] = _canonicalize_provider_text(item, provider_slugs)
            else:
                canonicalized[key] = _canonicalize_provider_payload(item, provider_slugs=provider_slugs)
        return canonicalized

    if isinstance(value, list):
        return [_canonicalize_provider_payload(item, provider_slugs=provider_slugs) for item in value]

    return value


def _event_provider_contexts(event: BillingEvent) -> set[str]:
    provider_slugs: set[str] = set()
    if event.provider_slug:
        provider_slugs.add(event.provider_slug)
    _collect_provider_contexts(event.metadata, provider_slugs=provider_slugs)
    return provider_slugs


def _event_to_response(event: BillingEvent) -> dict[str, Any]:
    """Format a billing event for API response."""
    provider_contexts = _event_provider_contexts(event)
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "org_id": event.org_id,
        "timestamp": event.timestamp.isoformat(),
        "amount_usd_cents": event.amount_usd_cents,
        "amount_usd": event.amount_usd_cents / 100,
        "balance_after_usd_cents": event.balance_after_usd_cents,
        "balance_after_usd": (
            event.balance_after_usd_cents / 100
            if event.balance_after_usd_cents is not None
            else None
        ),
        "receipt_id": event.receipt_id,
        "execution_id": event.execution_id,
        "capability_id": event.capability_id,
        "provider_slug": public_service_slug(event.provider_slug),
        "metadata": _canonicalize_provider_payload(event.metadata, provider_slugs=provider_contexts),
        "chain_hash": event.chain_hash,
    }


def _public_provider_totals(by_provider: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for slug, cents in by_provider.items():
        public_slug = public_service_slug(slug) or str(slug or "").strip()
        if not public_slug:
            continue
        merged[public_slug] = merged.get(public_slug, 0) + cents
    return merged


def _summary_to_response(summary: BillingEventSummary) -> dict[str, Any]:
    """Format a billing summary for API response."""
    public_by_provider = _public_provider_totals(summary.by_provider)
    return {
        "org_id": summary.org_id,
        "period": summary.period,
        "total_charged_usd_cents": summary.total_charged_usd_cents,
        "total_charged_usd": summary.total_charged_usd_cents / 100,
        "total_credited_usd_cents": summary.total_credited_usd_cents,
        "total_credited_usd": summary.total_credited_usd_cents / 100,
        "net_usd": (summary.total_charged_usd_cents - summary.total_credited_usd_cents) / 100,
        "execution_count": summary.execution_count,
        "x402_payment_count": summary.x402_payment_count,
        "credit_purchase_count": summary.credit_purchase_count,
        "by_provider": {
            slug: {"charged_usd_cents": cents, "charged_usd": cents / 100}
            for slug, cents in public_by_provider.items()
        },
        "by_capability": {
            cap: {"charged_usd_cents": cents, "charged_usd": cents / 100}
            for cap, cents in summary.by_capability.items()
        },
        "events_count": summary.events_count,
    }


@router.get("/events", response_model=None)
async def query_billing_events(
    raw_request: Request,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    event_type: str | None = Query(None, description="Filter by event type"),
    limit: int = Query(50, ge=1, le=200),
    since: str | None = Query(None, description="ISO timestamp filter"),
) -> dict[str, Any] | JSONResponse:
    """Query billing events for the authenticated org.

    Returns events from the structured billing event stream,
    newest first.
    """
    org_id = await _require_org_or_401(raw_request, x_rhumb_key)
    if isinstance(org_id, JSONResponse):
        return org_id
    stream = get_billing_event_stream()

    # Parse filters
    parsed_type = _validated_event_type(event_type)
    parsed_since = _validated_since_timestamp(since)

    events = stream.query(
        org_id=org_id,
        event_type=parsed_type,
        limit=limit,
        since=parsed_since,
    )

    return {
        "data": {
            "events": [_event_to_response(e) for e in events],
            "count": len(events),
            "org_id": org_id,
        },
        "error": None,
    }


@router.get("/summary", response_model=None)
async def billing_summary(
    raw_request: Request,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    period: str | None = Query(None, description="Period filter: YYYY-MM or YYYY-MM-DD"),
) -> dict[str, Any] | JSONResponse:
    """Get aggregate billing summary for the authenticated org.

    Includes totals, breakdowns by provider and capability,
    and event counts.
    """
    org_id = await _require_org_or_401(raw_request, x_rhumb_key)
    if isinstance(org_id, JSONResponse):
        return org_id
    normalized_period = _validated_period_filter(period)
    stream = get_billing_event_stream()
    summary = stream.summarize(org_id=org_id, period=normalized_period)

    return {
        "data": _summary_to_response(summary),
        "error": None,
    }


@router.get("/stream/status")
async def billing_stream_status() -> dict[str, Any]:
    """Billing event stream health and integrity.

    Public diagnostic — no auth required.
    """
    stream = get_billing_event_stream()

    return {
        "data": {
            "stream_length": stream.length,
            "chain_verified": stream.verify_chain(),
            "latest_chain_hash": stream.latest_hash,
            "event_types": [t.value for t in BillingEventType],
            "structural_guarantees": [
                "All billing events are immutable and chain-hashed",
                "Event stream is append-only with SHA-256 chain integrity",
                "Events capture full execution context (provider, capability, receipt)",
                "Summaries aggregate across providers and capabilities",
            ],
        },
        "error": None,
    }
