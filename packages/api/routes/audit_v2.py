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
import uuid
from typing import Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.error_envelope import RhumbError
from services.audit_trail import (
    AUDIT_EVENT_CATEGORIES,
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


async def _require_org_or_401(raw_request: Request, api_key: str | None) -> str | JSONResponse:
    """Validate governed API key and return org_id, or a structured 401 response."""
    normalized_key = str(api_key or "").strip()
    if not normalized_key:
        return _missing_governed_key_response(raw_request)
    agent = await _get_identity_store().verify_api_key_with_agent(normalized_key)
    if agent is None:
        return _invalid_governed_key_response(raw_request)
    return agent.organization_id


def _validated_event_type(event_type: str | None) -> AuditEventType | None:
    if event_type is None:
        return None

    normalized = event_type.strip().lower()
    if not normalized:
        valid_types = ", ".join(t.value for t in AuditEventType)
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'event_type' filter.",
            detail=f"Use one of: {valid_types}.",
        )

    try:
        return AuditEventType(normalized)
    except ValueError as exc:
        valid_types = ", ".join(t.value for t in AuditEventType)
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'event_type' filter.",
            detail=f"Use one of: {valid_types}.",
        ) from exc


def _validated_severity(severity: str | None) -> AuditSeverity | None:
    if severity is None:
        return None

    normalized = severity.strip().lower()
    if not normalized:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'severity' filter.",
            detail="Use one of: info, warning, critical.",
        )

    try:
        return AuditSeverity(normalized)
    except ValueError as exc:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'severity' filter.",
            detail="Use one of: info, warning, critical.",
        ) from exc


def _validated_category(category: str | None) -> str | None:
    if category is None:
        return None

    normalized = category.strip()
    if not normalized:
        valid_categories = ", ".join(sorted(AUDIT_EVENT_CATEGORIES))
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'category' filter.",
            detail=f"Use one of: {valid_categories}.",
        )

    lowered = normalized.lower()
    if lowered not in AUDIT_EVENT_CATEGORIES:
        valid_categories = ", ".join(sorted(AUDIT_EVENT_CATEGORIES))
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'category' filter.",
            detail=f"Use one of: {valid_categories}.",
        )

    return lowered


def _validated_text_filter(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field_name}' filter.",
        detail=f"Provide a non-empty '{field_name}' value or omit the filter.",
    )


def _validated_event_path_id(event_id: str) -> str:
    normalized = str(event_id or "").strip()
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'event_id' path parameter.",
        detail="Provide a non-empty audit event id from GET /v2/audit/events.",
    )


def _validated_timestamp(ts: str | None, *, field_name: str) -> datetime | None:
    if ts is None:
        return None

    normalized = ts.strip()
    if not normalized:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message=f"Invalid '{field_name}' filter.",
            detail="Use an ISO 8601 timestamp (for example 2026-04-22T12:34:56+00:00).",
        )

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message=f"Invalid '{field_name}' filter.",
            detail="Use an ISO 8601 timestamp (for example 2026-04-22T12:34:56+00:00).",
        ) from exc

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _validated_time_window(
    since: datetime | None,
    until: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    if since is not None and until is not None and since > until:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid audit time window.",
            detail="The 'since' timestamp must be before or equal to the 'until' timestamp.",
        )
    return since, until


def _validated_export_format(format: str) -> str:
    normalized = format.strip().lower()
    if normalized in ("json", "csv"):
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'format' filter.",
        detail="Use one of: json, csv.",
    )


def _validated_events_limit(limit: int) -> int:
    if 1 <= limit <= 500:
        return limit

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'limit' filter.",
        detail="Provide an integer between 1 and 500.",
    )


def _validated_events_offset(offset: int) -> int:
    if offset >= 0:
        return offset

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'offset' filter.",
        detail="Provide an integer greater than or equal to 0.",
    )


@router.get("/events")
async def list_audit_events(
    raw_request: Request,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    event_type: str | None = Query(None, description="Filter by event type"),
    severity: str | None = Query(None, description="Filter by severity: info, warning, critical"),
    category: str | None = Query(None, description="Filter by category: admin, auth, billing, config, credential, execution, governance, identity, security, trust"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    resource_id: str | None = Query(None, description="Filter by resource ID"),
    since: str | None = Query(None, description="ISO 8601 timestamp — events after this time"),
    until: str | None = Query(None, description="ISO 8601 timestamp — events before this time"),
    limit: int = Query(50),
    offset: int = Query(0),
) -> dict[str, Any]:
    """Query audit events with filters and pagination.

    Returns events newest-first. Use offset/limit for pagination.
    """
    parsed_type = _validated_event_type(event_type)
    parsed_severity = _validated_severity(severity)
    parsed_category = _validated_category(category)
    parsed_resource_type = _validated_text_filter(resource_type, field_name="resource_type")
    parsed_resource_id = _validated_text_filter(resource_id, field_name="resource_id")
    parsed_since, parsed_until = _validated_time_window(
        _validated_timestamp(since, field_name="since"),
        _validated_timestamp(until, field_name="until"),
    )
    limit = _validated_events_limit(limit)
    offset = _validated_events_offset(offset)

    org_id = await _require_org_or_401(raw_request, x_rhumb_key)
    if isinstance(org_id, JSONResponse):
        return org_id

    trail = get_audit_trail()

    events = trail.query(
        org_id=org_id,
        event_type=parsed_type,
        severity=parsed_severity,
        category=parsed_category,
        resource_type=parsed_resource_type,
        resource_id=parsed_resource_id,
        since=parsed_since,
        until=parsed_until,
        limit=limit,
        offset=offset,
    )

    total = trail.count(
        org_id=org_id,
        event_type=parsed_type,
        severity=parsed_severity,
        category=parsed_category,
        resource_type=parsed_resource_type,
        resource_id=parsed_resource_id,
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
    raw_request: Request,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict[str, Any]:
    """Get a specific audit event by ID."""
    event_id = _validated_event_path_id(event_id)
    org_id = await _require_org_or_401(raw_request, x_rhumb_key)
    if isinstance(org_id, JSONResponse):
        return org_id
    trail = get_audit_trail()

    # Search for the event
    events = trail.query(org_id=org_id, limit=100_000)
    for event in events:
        if event.event_id == event_id:
            return {
                "data": _event_response(event),
                "error": None,
            }

    raise RhumbError(
        "AUDIT_EVENT_NOT_FOUND",
        message=f"Audit event '{event_id}' not found.",
        detail="Check the audit event id from GET /v2/audit/events, then retry.",
    )


@router.get("/status")
async def audit_status(
    raw_request: Request,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict[str, Any]:
    """Audit chain health and org-scoped statistics.

    Returns chain integrity status plus the authenticated org's visible event
    counts and latest visible chain head metadata.
    """
    org_id = await _require_org_or_401(raw_request, x_rhumb_key)
    if isinstance(org_id, JSONResponse):
        return org_id
    trail = get_audit_trail()
    chain_status = trail.status(org_id=org_id)

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
    raw_request: Request,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    format: str = Query("json", description="Export format: json or csv"),
    event_type: str | None = Query(None),
    severity: str | None = Query(None),
    category: str | None = Query(None),
    resource_type: str | None = Query(None),
    resource_id: str | None = Query(None),
    since: str | None = Query(None),
    until: str | None = Query(None),
) -> Any:
    """Export audit trail in JSON or CSV format.

    For SOC2 compliance — exports include chain verification status
    and all chain-hash fields for independent verification.
    """
    format = _validated_export_format(format)
    parsed_type = _validated_event_type(event_type)
    parsed_severity = _validated_severity(severity)
    parsed_category = _validated_category(category)
    parsed_resource_type = _validated_text_filter(resource_type, field_name="resource_type")
    parsed_resource_id = _validated_text_filter(resource_id, field_name="resource_id")
    parsed_since, parsed_until = _validated_time_window(
        _validated_timestamp(since, field_name="since"),
        _validated_timestamp(until, field_name="until"),
    )

    org_id = await _require_org_or_401(raw_request, x_rhumb_key)
    if isinstance(org_id, JSONResponse):
        return org_id

    trail = get_audit_trail()

    result = trail.export(
        format=format,
        org_id=org_id,
        event_type=parsed_type,
        severity=parsed_severity,
        category=parsed_category,
        resource_type=parsed_resource_type,
        resource_id=parsed_resource_id,
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
    raw_request: Request,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict[str, Any]:
    """Verify audit trail integrity without leaking other orgs' head metadata.

    Returns the underlying chain verification result plus only the authenticated
    org's visible event count and latest visible chain head metadata.
    """
    org_id = await _require_org_or_401(raw_request, x_rhumb_key)
    if isinstance(org_id, JSONResponse):
        return org_id
    trail = get_audit_trail()
    chain_status = trail.status(org_id=org_id)

    return {
        "data": {
            "chain_verified": chain_status.chain_verified,
            "events_checked": chain_status.total_events,
            "latest_hash": chain_status.latest_hash,
            "latest_sequence": chain_status.latest_sequence,
            "message": (
                "Chain integrity verified — no tampering detected."
                if chain_status.chain_verified
                else "Chain integrity BROKEN. Possible tampering."
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
