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
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.billing_events import (
    BillingEvent,
    BillingEventSummary,
    BillingEventType,
    get_billing_event_stream,
)

router = APIRouter(prefix="/v2/billing", tags=["billing-v2"])

_identity_store: AgentIdentityStore | None = None


def _get_identity_store() -> AgentIdentityStore:
    global _identity_store
    if _identity_store is None:
        _identity_store = get_agent_identity_store()
    return _identity_store


async def _require_org(api_key: str | None) -> str:
    """Validate API key and return org_id."""
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-Rhumb-Key header")
    agent = await _get_identity_store().verify_api_key_with_agent(api_key)
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    return agent.organization_id


def _event_to_response(event: BillingEvent) -> dict[str, Any]:
    """Format a billing event for API response."""
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
        "provider_slug": event.provider_slug,
        "metadata": event.metadata,
        "chain_hash": event.chain_hash,
    }


def _summary_to_response(summary: BillingEventSummary) -> dict[str, Any]:
    """Format a billing summary for API response."""
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
            for slug, cents in summary.by_provider.items()
        },
        "by_capability": {
            cap: {"charged_usd_cents": cents, "charged_usd": cents / 100}
            for cap, cents in summary.by_capability.items()
        },
        "events_count": summary.events_count,
    }


@router.get("/events")
async def query_billing_events(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    event_type: str | None = Query(None, description="Filter by event type"),
    limit: int = Query(50, ge=1, le=200),
    since: str | None = Query(None, description="ISO timestamp filter"),
) -> dict[str, Any]:
    """Query billing events for the authenticated org.

    Returns events from the structured billing event stream,
    newest first.
    """
    org_id = await _require_org(x_rhumb_key)
    stream = get_billing_event_stream()

    # Parse filters
    parsed_type: BillingEventType | None = None
    if event_type:
        try:
            parsed_type = BillingEventType(event_type)
        except ValueError:
            valid_types = [t.value for t in BillingEventType]
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "INVALID_EVENT_TYPE",
                    "message": f"Unknown event type: {event_type}",
                    "valid_types": valid_types,
                },
            )

    parsed_since: datetime | None = None
    if since:
        try:
            parsed_since = datetime.fromisoformat(since)
            if parsed_since.tzinfo is None:
                parsed_since = parsed_since.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid 'since' timestamp. Use ISO format.",
            )

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


@router.get("/summary")
async def billing_summary(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    period: str | None = Query(None, description="Period filter: YYYY-MM or YYYY-MM-DD"),
) -> dict[str, Any]:
    """Get aggregate billing summary for the authenticated org.

    Includes totals, breakdowns by provider and capability,
    and event counts.
    """
    org_id = await _require_org(x_rhumb_key)
    stream = get_billing_event_stream()
    summary = stream.summarize(org_id=org_id, period=period)

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
