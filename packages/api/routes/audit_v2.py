"""v2 Audit Trail API — query, export, and verify audit events (WU-42.5).

Compliance-ready audit trail endpoints for SOC2 preparation.
All events are append-only and chain-hash verified.

Endpoints:
  GET  /v2/audit/events       — Query audit events (filtered, paginated)
  GET  /v2/audit/events/{id}  — Get a specific audit event by ID
  GET  /v2/audit/status       — Audit chain health + statistics
  POST /v2/audit/export       — Export audit trail (JSON or CSV)
  GET  /v2/audit/verify       — Verify chain-hash integrity
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse

from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.audit_trail import (
    AuditEventType,
    AuditSeverity,
    get_audit_trail,
)

router = APIRouter(prefix="/v2/audit", tags=["audit-v2"])
logger = logging.getLogger(__name__)

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


@router.get("/events")
async def list_audit_events(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    event_type: str | None = Query(None, description="Filter by event type"),
    severity: str | None = Query(None, description="Filter by severity: info, warning, critical"),
    category: str | None = Query(None, description="Filter by category: execution, security, governance, billing, trust, identity"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    resource_id: str | None = Query(None, description="Filter by resource ID"),
    since: str | None = Query(None, description="ISO 8601 timestamp — events after this time"),
    until: str | None = Query(None, description="ISO 8601 timestamp — events before this time"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Query audit events with filters and pagination.

    Returns events newest-first. Use offset/limit for pagination.
    """
    org_id = await _require_org(x_rhumb_key)
    trail = get_audit_trail()

    # Parse enum filters
    parsed_type = None
    if event_type:
        try:
            parsed_type = AuditEventType(event_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid event_type: {event_type}. Valid types: {[t.value for t in AuditEventType]}",
            )

    parsed_severity = None
    if severity:
        try:
            parsed_severity = AuditSeverity(severity)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid severity: {severity}. Valid: info, warning, critical",
            )

    # Parse timestamps
    parsed_since = _parse_timestamp(since) if since else None
    parsed_until = _parse_timestamp(until) if until else None

    events = trail.query(
        org_id=org_id,
        event_type=parsed_type,
        severity=parsed_severity,
        category=category,
        resource_type=resource_type,
        resource_id=resource_id,
        since=parsed_since,
        until=parsed_until,
        limit=limit,
        offset=offset,
    )

    total = trail.count(
        org_id=org_id,
        event_type=parsed_type,
        severity=parsed_severity,
        category=category,
        resource_type=resource_type,
        resource_id=resource_id,
        since=parsed_since,
        until=parsed_until,
    )

    return {
        "data": {
            "events": [_event_response(e) for e in events],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total,
            },
        },
        "error": None,
    }


@router.get("/events/{event_id}")
async def get_audit_event(
    event_id: str,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict[str, Any]:
    """Get a specific audit event by ID."""
    org_id = await _require_org(x_rhumb_key)
    trail = get_audit_trail()

    # Search for the event
    events = trail.query(org_id=org_id, limit=100_000)
    for event in events:
        if event.event_id == event_id:
            return {
                "data": _event_response(event),
                "error": None,
            }

    raise HTTPException(status_code=404, detail=f"Audit event {event_id} not found")


@router.get("/status")
async def audit_status(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict[str, Any]:
    """Audit chain health and statistics.

    Returns chain integrity status, event counts by type/severity/category,
    and the latest chain hash for verification.
    """
    await _require_org(x_rhumb_key)
    trail = get_audit_trail()
    chain_status = trail.status()

    return {
        "data": {
            "total_events": chain_status.total_events,
            "chain_verified": chain_status.chain_verified,
            "latest_hash": chain_status.latest_hash,
            "latest_sequence": chain_status.latest_sequence,
            "earliest_event": (
                chain_status.earliest_event.isoformat()
                if chain_status.earliest_event
                else None
            ),
            "latest_event": (
                chain_status.latest_event.isoformat()
                if chain_status.latest_event
                else None
            ),
            "events_by_type": chain_status.events_by_type,
            "events_by_severity": chain_status.events_by_severity,
            "events_by_category": chain_status.events_by_category,
        },
        "error": None,
    }


@router.post("/export")
async def export_audit_trail(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    format: str = Query("json", description="Export format: json or csv"),
    event_type: str | None = Query(None),
    severity: str | None = Query(None),
    category: str | None = Query(None),
    since: str | None = Query(None),
    until: str | None = Query(None),
) -> Any:
    """Export audit trail in JSON or CSV format.

    For SOC2 compliance — exports include chain verification status
    and all chain-hash fields for independent verification.
    """
    org_id = await _require_org(x_rhumb_key)
    trail = get_audit_trail()

    if format not in ("json", "csv"):
        raise HTTPException(status_code=400, detail="Format must be 'json' or 'csv'")

    # Parse filters
    parsed_type = None
    if event_type:
        try:
            parsed_type = AuditEventType(event_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid event_type: {event_type}")

    parsed_severity = None
    if severity:
        try:
            parsed_severity = AuditSeverity(severity)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")

    parsed_since = _parse_timestamp(since) if since else None
    parsed_until = _parse_timestamp(until) if until else None

    result = trail.export(
        format=format,
        org_id=org_id,
        event_type=parsed_type,
        severity=parsed_severity,
        category=category,
        since=parsed_since,
        until=parsed_until,
    )

    if format == "csv":
        return PlainTextResponse(
            content=result.data,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="rhumb-audit-export.csv"',
                "X-Rhumb-Chain-Verified": str(result.chain_verified).lower(),
                "X-Rhumb-Event-Count": str(result.event_count),
            },
        )

    return {
        "data": {
            "format": result.format,
            "event_count": result.event_count,
            "chain_verified": result.chain_verified,
            "exported_at": result.exported_at.isoformat(),
            "export": result.data,  # JSON string for parsing
        },
        "error": None,
    }


@router.get("/verify")
async def verify_audit_chain(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict[str, Any]:
    """Verify chain-hash integrity of the entire audit trail.

    Returns verification status and the number of events checked.
    Any chain break indicates potential tampering.
    """
    await _require_org(x_rhumb_key)
    trail = get_audit_trail()

    is_valid, events_checked = trail.verify_chain()

    return {
        "data": {
            "chain_verified": is_valid,
            "events_checked": events_checked,
            "latest_hash": trail.latest_hash,
            "latest_sequence": trail.latest_sequence,
            "message": (
                "Chain integrity verified — no tampering detected."
                if is_valid
                else f"Chain integrity BROKEN at event {events_checked}. Possible tampering."
            ),
        },
        "error": None,
    }


# ── Helpers ──────────────────────────────────────────────────────────


def _event_response(event: Any) -> dict[str, Any]:
    """Format an audit event for API response.

    Default-safe posture: external query surfaces should return the redacted,
    shape-bounded serialization unless a future internal-only path opts out
    explicitly.
    """
    serialized = get_audit_trail().serialize_event(event, redact=True)
    return {
        "event_id": serialized["event_id"],
        "event_type": serialized["event_type"],
        "severity": serialized["severity"],
        "category": serialized["category"],
        "timestamp": serialized["timestamp"],
        "org_id": serialized["org_id"],
        "agent_id": serialized["agent_id"],
        "principal": serialized["principal"],
        "resource_type": serialized["resource_type"],
        "resource_id": serialized["resource_id"],
        "action": serialized["action"],
        "detail": serialized["detail"],
        "receipt_id": serialized["receipt_id"],
        "execution_id": serialized["execution_id"],
        "provider_slug": serialized["provider_slug"],
        "chain_sequence": serialized["chain_sequence"],
        "chain_hash": serialized["chain_hash"],
    }


def _parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp string."""
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timestamp format: {ts}. Use ISO 8601.",
        )
