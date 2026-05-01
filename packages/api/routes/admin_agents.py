"""Admin routes for agent management.

CRUD operations for agent identity, service access grants,
API key rotation, and usage queries. Internal-only (v1).

Round 11 (WU 2.2): Admin dashboard routes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from schemas.agent_identity import (
    AgentIdentityStore,
    get_agent_identity_store,
    reset_identity_store,
)
from services.agent_access_control import AgentAccessControl, get_agent_access_control
from services.agent_usage_analytics import AgentUsageAnalytics, get_usage_analytics
from services.evidence_ingestion import EvidenceIngestionAdapter
from services.error_envelope import RhumbError
from services.service_slugs import public_service_slug

router = APIRouter(tags=["admin-agents"])

_AGENT_STATUSES = {"active", "disabled", "deleted"}


def _validated_optional_text_filter(value: Optional[str], field: str) -> Optional[str]:
    """Trim optional text filters and reject blanks before any broad read runs."""
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message=f"Invalid '{field}' filter.",
            detail=f"Provide a non-empty '{field}' value or omit the filter.",
        )
    return normalized


def _validated_required_body_text(value: str, field: str) -> str:
    """Trim required body strings and reject blanks before admin writes."""
    normalized = str(value or "").strip()
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field}' field.",
        detail=f"Provide a non-empty '{field}' value.",
    )


def _normalized_optional_body_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalized_optional_tags(tags: Any) -> Optional[List[str]]:
    if tags is None:
        return None
    if not isinstance(tags, list):
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'tags' field.",
            detail="Provide 'tags' as a list of strings or omit the field.",
        )
    normalized_tags = [str(tag).strip() for tag in tags]
    return [tag for tag in normalized_tags if tag]


def _validated_qpm_field(
    value: Any,
    field: str,
    *,
    minimum: int,
    maximum: int = 1000,
) -> int:
    """Validate admin QPM fields before opening identity-store writes."""
    normalized: int | None = None
    if isinstance(value, int) and not isinstance(value, bool):
        normalized = value
    elif isinstance(value, str):
        cleaned = value.strip()
        if cleaned.isdecimal():
            normalized = int(cleaned)

    if normalized is None:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message=f"Invalid '{field}' field.",
            detail=f"Provide an integer between {minimum} and {maximum}.",
        )

    if minimum <= normalized <= maximum:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field}' field.",
        detail=f"Provide an integer between {minimum} and {maximum}.",
    )


def _validated_body_object(body: Any, *, endpoint: str) -> dict[str, Any]:
    """Reject malformed admin JSON bodies before route-owned writes run."""
    if isinstance(body, dict):
        return body

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid request body.",
        detail=f"{endpoint} requires a JSON object payload.",
    )


def _validated_required_path_value(value: str, field: str) -> str:
    """Trim required path values and reject blanks before admin store reads/writes."""
    normalized = str(value or "").strip()
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field}' path parameter.",
        detail=f"Provide a non-empty '{field}' value.",
    )


def _validated_agent_status(status: Optional[str]) -> Optional[str]:
    """Normalize and validate the public admin agent-status filter."""
    normalized = _validated_optional_text_filter(status, "status")
    if normalized is None:
        return None
    normalized = normalized.lower()
    if normalized not in _AGENT_STATUSES:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'status' filter.",
            detail="Use one of: active, disabled, deleted.",
        )
    return normalized


def _public_service_label(service: str) -> str:
    """Normalize admin-facing service ids onto canonical public slugs."""
    cleaned = str(service).strip().lower()
    return public_service_slug(cleaned) or cleaned


def _validated_access_service_field(service: str) -> str:
    """Normalize admin access-grant services and reject blanks before store reads/writes."""
    normalized = _public_service_label(service)
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'service' field.",
        detail="Provide a non-empty service value.",
    )


def _validated_public_service_filter(service: Optional[str]) -> Optional[str]:
    """Normalize optional usage service filters and reject blanks before broad reads."""
    cleaned = _validated_optional_text_filter(service, "service")
    if cleaned is None:
        return None
    return _public_service_label(cleaned)


def _parse_integer_filter(value: Any) -> int | None:
    if not isinstance(value, int):
        value = getattr(value, "default", value)

    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.isdigit():
            return int(normalized)
    return None


def _validated_usage_days(days: Any) -> int:
    """Reject invalid usage windows before opening usage aggregation reads."""
    parsed_days = _parse_integer_filter(days)
    if parsed_days is not None and 1 <= parsed_days <= 365:
        return parsed_days
    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'days' filter.",
        detail="Provide an integer between 1 and 365.",
    )


def _validated_ingest_limit(limit: int) -> int:
    """Reject invalid evidence-ingest windows before opening ingestion state."""
    normalized = int(limit)
    if 1 <= normalized <= 1000:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'limit' field.",
        detail="Provide an integer between 1 and 1000.",
    )


def _canonicalize_usage_summary(summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge alias-backed usage buckets onto canonical public service ids."""
    normalized = dict(summary or {})
    raw_services = normalized.get("services")
    if not isinstance(raw_services, dict):
        normalized["services"] = {}
        return normalized

    merged_services: Dict[str, Dict[str, Any]] = {}
    success_weights: Dict[str, float] = {}
    success_weight_seen: set[str] = set()

    for raw_service, raw_info in raw_services.items():
        service = _public_service_label(str(raw_service or ""))
        if not service:
            continue

        info = raw_info if isinstance(raw_info, dict) else {}
        calls = int(info.get("calls") or 0)
        bucket = merged_services.setdefault(service, {"calls": 0})
        bucket["calls"] = int(bucket.get("calls") or 0) + calls

        success_rate = info.get("success_rate")
        if success_rate is not None:
            success_weight_seen.add(service)
            success_weights[service] = success_weights.get(service, 0.0) + (
                float(success_rate) * calls
            )

        for key, value in info.items():
            if key in {"calls", "success_rate"}:
                continue
            if key not in bucket or bucket[key] in (None, ""):
                bucket[key] = value

    for service, bucket in merged_services.items():
        calls = int(bucket.get("calls") or 0)
        if service in success_weight_seen:
            bucket["success_rate"] = round(
                success_weights.get(service, 0.0) / calls if calls > 0 else 0.0,
                4,
            )

    normalized["services"] = merged_services
    return normalized


def _canonicalize_organization_usage(usage: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge alias-backed per-agent usage buckets onto canonical public service ids."""
    normalized = dict(usage or {})
    raw_agents = normalized.get("agents")
    if not isinstance(raw_agents, dict):
        normalized["agents"] = {}
        return normalized

    normalized["agents"] = {
        agent_id: _canonicalize_usage_summary(summary if isinstance(summary, dict) else {})
        for agent_id, summary in raw_agents.items()
    }
    return normalized


# ── Request / Response Schemas ───────────────────────────────────────


class CreateAgentRequest(BaseModel):
    """Request body for creating a new agent."""

    name: str = Field(..., description="Agent display name")
    organization_id: str = Field(..., description="Organization that owns the agent")
    rate_limit_qpm: int = Field(default=100, description="Global QPM limit")
    description: Optional[str] = Field(default=None)
    tags: Optional[List[str]] = Field(default=None)


class CreateAgentResponse(BaseModel):
    """Response after creating an agent."""

    status: str = "success"
    agent_id: str
    api_key: str
    message: str = "Save API key securely. It won't be shown again."


class GrantAccessRequest(BaseModel):
    """Request body for granting service access."""

    service: str = Field(..., description="Service name (e.g. 'stripe')")
    rate_limit_override: int = Field(
        default=0, description="Per-service QPM override (0 = use global)"
    )
    credential_account_id: Optional[str] = Field(default=None)


class GrantAccessResponse(BaseModel):
    """Response after granting service access."""

    status: str = "success"
    access_id: str


class RevokeAccessRequest(BaseModel):
    """Request body for revoking service access."""

    service: str = Field(..., description="Service name to revoke")


class RotateKeyResponse(BaseModel):
    """Response after rotating an API key."""

    status: str = "success"
    new_api_key: str
    message: str = "Old API key is now invalid. Update your clients."


class AgentDetailResponse(BaseModel):
    """Detailed agent info with services and usage."""

    agent_id: str
    name: str
    organization_id: str
    status: str
    rate_limit_qpm: int
    description: Optional[str]
    tags: List[str]
    created_at: str
    updated_at: str
    api_key_prefix: str
    services: List[str]
    usage: Dict[str, Any]


class AgentListItem(BaseModel):
    """Summary item for agent listing."""

    agent_id: str
    name: str
    organization_id: str
    status: str
    rate_limit_qpm: int
    api_key_prefix: str
    created_at: str
    service_count: int


class EvidenceIngestRequest(BaseModel):
    """Request body for triggering evidence ingestion."""

    since: Optional[datetime] = Field(
        default=None,
        description="Only ingest source rows observed on or after this timestamp",
    )
    limit: int = Field(default=100)


# ── Helper: get stores (overridable in tests) ───────────────────────

_test_identity_store: Optional[AgentIdentityStore] = None
_test_analytics: Optional[AgentUsageAnalytics] = None
_test_acl: Optional[AgentAccessControl] = None
_test_evidence_adapter: Optional[EvidenceIngestionAdapter] = None


def set_test_stores(
    identity_store: Optional[AgentIdentityStore] = None,
    analytics: Optional[AgentUsageAnalytics] = None,
    acl: Optional[AgentAccessControl] = None,
) -> None:
    """Inject test stores (call with ``None`` to reset)."""
    global _test_identity_store, _test_analytics, _test_acl
    _test_identity_store = identity_store
    _test_analytics = analytics
    _test_acl = acl


def set_test_evidence_ingestion_adapter(
    adapter: Optional[EvidenceIngestionAdapter] = None,
) -> None:
    """Inject a test evidence adapter."""
    global _test_evidence_adapter
    _test_evidence_adapter = adapter


def _get_identity_store() -> AgentIdentityStore:
    return _test_identity_store or get_agent_identity_store()


def _get_analytics() -> AgentUsageAnalytics:
    return _test_analytics or get_usage_analytics()


def _get_acl() -> AgentAccessControl:
    return _test_acl or get_agent_access_control()


async def _get_evidence_adapter() -> EvidenceIngestionAdapter:
    if _test_evidence_adapter is not None:
        return _test_evidence_adapter

    from db.client import get_supabase_client

    supabase = await get_supabase_client()
    return EvidenceIngestionAdapter(supabase)


# ── Routes ───────────────────────────────────────────────────────────


@router.post("/agents", response_model=CreateAgentResponse)
async def create_agent(body: Any = Body(default=None)) -> CreateAgentResponse:
    """Create a new agent and return its API key (shown once)."""
    payload = _validated_body_object(body, endpoint="POST /v1/admin/agents")
    name = _validated_required_body_text(payload.get("name"), "name")
    organization_id = _validated_required_body_text(
        payload.get("organization_id"), "organization_id"
    )
    description = _normalized_optional_body_text(payload.get("description"))
    tags = _normalized_optional_tags(payload.get("tags"))
    rate_limit_qpm = _validated_qpm_field(
        payload.get("rate_limit_qpm", 100),
        "rate_limit_qpm",
        minimum=1,
    )
    store = _get_identity_store()
    agent_id, api_key = await store.register_agent(
        name=name,
        organization_id=organization_id,
        rate_limit_qpm=rate_limit_qpm,
        description=description,
        tags=tags,
    )
    return CreateAgentResponse(agent_id=agent_id, api_key=api_key)


@router.get("/agents", response_model=List[AgentListItem])
async def list_agents(
    organization_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
) -> List[AgentListItem]:
    """List all agents with optional org/status filters."""
    normalized_organization_id = _validated_optional_text_filter(
        organization_id, "organization_id"
    )
    normalized_status = _validated_agent_status(status)
    store = _get_identity_store()
    agents = await store.list_agents(
        organization_id=normalized_organization_id,
        status=normalized_status,
    )

    items: List[AgentListItem] = []
    for agent in agents:
        services = await store.get_agent_services(agent.agent_id)
        items.append(
            AgentListItem(
                agent_id=agent.agent_id,
                name=agent.name,
                organization_id=agent.organization_id,
                status=agent.status,
                rate_limit_qpm=agent.rate_limit_qpm,
                api_key_prefix=agent.api_key_prefix,
                created_at=agent.created_at.isoformat()
                if hasattr(agent.created_at, "isoformat")
                else str(agent.created_at),
                service_count=len({s.service for s in services}),
            )
        )
    return items


@router.get("/agents/{agent_id}", response_model=AgentDetailResponse)
async def get_agent_details(agent_id: str) -> AgentDetailResponse:
    """Get full agent details including services and usage."""
    agent_id = _validated_required_path_value(agent_id, "agent_id")
    store = _get_identity_store()
    agent = await store.get_agent(agent_id)

    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    services = await store.get_agent_services(agent_id)
    analytics = _get_analytics()
    usage = _canonicalize_usage_summary(await analytics.get_usage_summary(agent_id))

    return AgentDetailResponse(
        agent_id=agent.agent_id,
        name=agent.name,
        organization_id=agent.organization_id,
        status=agent.status,
        rate_limit_qpm=agent.rate_limit_qpm,
        description=agent.description,
        tags=agent.tags,
        created_at=agent.created_at.isoformat()
        if hasattr(agent.created_at, "isoformat")
        else str(agent.created_at),
        updated_at=agent.updated_at.isoformat()
        if hasattr(agent.updated_at, "isoformat")
        else str(agent.updated_at),
        api_key_prefix=agent.api_key_prefix,
        services=list(dict.fromkeys(s.service for s in services)),
        usage=usage,
    )


@router.post("/agents/{agent_id}/grant-access", response_model=GrantAccessResponse)
async def grant_service_access(
    agent_id: str, body: GrantAccessRequest
) -> GrantAccessResponse:
    """Grant an agent access to a service."""
    agent_id = _validated_required_path_value(agent_id, "agent_id")
    service = _validated_access_service_field(body.service)
    rate_limit_override = _validated_qpm_field(
        body.rate_limit_override,
        "rate_limit_override",
        minimum=0,
    )
    credential_account_id = _normalized_optional_body_text(body.credential_account_id)
    store = _get_identity_store()

    # Verify agent exists
    agent = await store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check for existing active access
    existing = await store.get_service_access(agent_id, service)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Agent already has active access to '{service}'",
        )

    access_id = await store.grant_service_access(
        agent_id=agent_id,
        service=service,
        rate_limit_override=rate_limit_override,
        credential_account_id=credential_account_id,
    )
    return GrantAccessResponse(access_id=access_id)


@router.post("/agents/{agent_id}/revoke-access")
async def revoke_service_access(
    agent_id: str, body: RevokeAccessRequest
) -> Dict[str, str]:
    """Revoke an agent's access to a service."""
    agent_id = _validated_required_path_value(agent_id, "agent_id")
    service = _validated_access_service_field(body.service)
    store = _get_identity_store()

    revoked = await store.revoke_service_access_by_agent_service(
        agent_id, service
    )
    if not revoked:
        raise HTTPException(
            status_code=404,
            detail=f"No active access found for agent '{agent_id}' to service '{service}'",
        )

    return {"status": "success"}


@router.post("/agents/{agent_id}/rotate-key", response_model=RotateKeyResponse)
async def rotate_api_key(agent_id: str) -> RotateKeyResponse:
    """Rotate an agent's API key. Old key becomes invalid immediately."""
    agent_id = _validated_required_path_value(agent_id, "agent_id")
    store = _get_identity_store()
    new_key = await store.rotate_api_key(agent_id)

    if new_key is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    return RotateKeyResponse(new_api_key=new_key)


@router.post("/agents/{agent_id}/disable")
async def disable_agent(agent_id: str) -> Dict[str, str]:
    """Disable an agent (soft delete)."""
    agent_id = _validated_required_path_value(agent_id, "agent_id")
    store = _get_identity_store()
    success = await store.disable_agent(agent_id)

    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {"status": "success", "agent_id": agent_id}


@router.post("/agents/{agent_id}/enable")
async def enable_agent(agent_id: str) -> Dict[str, str]:
    """Re-enable a disabled agent."""
    agent_id = _validated_required_path_value(agent_id, "agent_id")
    store = _get_identity_store()
    success = await store.enable_agent(agent_id)

    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {"status": "success", "agent_id": agent_id}


@router.get("/agents/{agent_id}/usage")
async def get_agent_usage(
    agent_id: str,
    service: Optional[str] = Query(default=None),
    days: Any = Query(default=30),
) -> Dict[str, Any]:
    """Get usage summary for an agent."""
    agent_id = _validated_required_path_value(agent_id, "agent_id")
    effective_days = _validated_usage_days(days)
    canonical_service = _validated_public_service_filter(service)

    store = _get_identity_store()
    agent = await store.get_agent(agent_id)

    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    analytics = _get_analytics()
    return _canonicalize_usage_summary(
        await analytics.get_usage_summary(
            agent_id,
            service=canonical_service,
            days=effective_days,
        )
    )


@router.get("/usage/organization/{organization_id}")
async def get_organization_usage(
    organization_id: str,
    days: Any = Query(default=30),
) -> Dict[str, Any]:
    """Get aggregated usage for an entire organization."""
    organization_id = _validated_required_path_value(organization_id, "organization_id")
    effective_days = _validated_usage_days(days)
    analytics = _get_analytics()
    return _canonicalize_organization_usage(
        await analytics.get_organization_usage(
            organization_id,
            days=effective_days,
        )
    )


@router.post("/evidence/ingest")
async def ingest_evidence(body: Optional[EvidenceIngestRequest] = None) -> Dict[str, Any]:
    """Trigger evidence ingestion from operational facts and usage events."""
    since = body.since if body is not None else None
    limit = _validated_ingest_limit(body.limit if body is not None else 100)
    adapter = await _get_evidence_adapter()
    operational_result = await adapter.ingest_operational_facts(
        since=since,
        limit=limit,
    )
    usage_result = await adapter.ingest_usage_summaries(
        since=since,
        limit=limit,
    )
    return operational_result.merge(usage_result).to_dict()
