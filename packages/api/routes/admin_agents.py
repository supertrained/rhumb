"""Admin routes for agent management.

CRUD operations for agent identity, service access grants,
API key rotation, and usage queries. Internal-only (v1).

Round 11 (WU 2.2): Admin dashboard routes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from schemas.agent_identity import (
    AgentIdentityStore,
    get_agent_identity_store,
    reset_identity_store,
)
from services.agent_access_control import AgentAccessControl, get_agent_access_control
from services.agent_usage_analytics import AgentUsageAnalytics, get_usage_analytics
from services.evidence_ingestion import EvidenceIngestionAdapter
from services.service_slugs import public_service_slug

router = APIRouter(tags=["admin-agents"])


def _public_service_label(service: str) -> str:
    """Normalize admin-facing service ids onto canonical public slugs."""
    cleaned = str(service).strip().lower()
    return public_service_slug(cleaned) or cleaned


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
    limit: int = Field(default=100, ge=1, le=1000)


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
async def create_agent(body: CreateAgentRequest) -> CreateAgentResponse:
    """Create a new agent and return its API key (shown once)."""
    store = _get_identity_store()
    agent_id, api_key = await store.register_agent(
        name=body.name,
        organization_id=body.organization_id,
        rate_limit_qpm=body.rate_limit_qpm,
        description=body.description,
        tags=body.tags,
    )
    return CreateAgentResponse(agent_id=agent_id, api_key=api_key)


@router.get("/agents", response_model=List[AgentListItem])
async def list_agents(
    organization_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
) -> List[AgentListItem]:
    """List all agents with optional org/status filters."""
    store = _get_identity_store()
    agents = await store.list_agents(
        organization_id=organization_id,
        status=status,
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
    store = _get_identity_store()

    # Verify agent exists
    agent = await store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check for existing active access
    existing = await store.get_service_access(agent_id, body.service)
    if existing is not None:
        public_service = _public_service_label(body.service)
        raise HTTPException(
            status_code=409,
            detail=f"Agent already has active access to '{public_service}'",
        )

    access_id = await store.grant_service_access(
        agent_id=agent_id,
        service=body.service,
        rate_limit_override=body.rate_limit_override,
        credential_account_id=body.credential_account_id,
    )
    return GrantAccessResponse(access_id=access_id)


@router.post("/agents/{agent_id}/revoke-access")
async def revoke_service_access(
    agent_id: str, body: RevokeAccessRequest
) -> Dict[str, str]:
    """Revoke an agent's access to a service."""
    store = _get_identity_store()

    revoked = await store.revoke_service_access_by_agent_service(
        agent_id, body.service
    )
    if not revoked:
        public_service = _public_service_label(body.service)
        raise HTTPException(
            status_code=404,
            detail=f"No active access found for agent '{agent_id}' to service '{public_service}'",
        )

    return {"status": "success"}


@router.post("/agents/{agent_id}/rotate-key", response_model=RotateKeyResponse)
async def rotate_api_key(agent_id: str) -> RotateKeyResponse:
    """Rotate an agent's API key. Old key becomes invalid immediately."""
    store = _get_identity_store()
    new_key = await store.rotate_api_key(agent_id)

    if new_key is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    return RotateKeyResponse(new_api_key=new_key)


@router.post("/agents/{agent_id}/disable")
async def disable_agent(agent_id: str) -> Dict[str, str]:
    """Disable an agent (soft delete)."""
    store = _get_identity_store()
    success = await store.disable_agent(agent_id)

    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {"status": "success", "agent_id": agent_id}


@router.post("/agents/{agent_id}/enable")
async def enable_agent(agent_id: str) -> Dict[str, str]:
    """Re-enable a disabled agent."""
    store = _get_identity_store()
    success = await store.enable_agent(agent_id)

    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {"status": "success", "agent_id": agent_id}


@router.get("/agents/{agent_id}/usage")
async def get_agent_usage(
    agent_id: str,
    service: Optional[str] = Query(default=None),
    days: int = Query(default=30),
) -> Dict[str, Any]:
    """Get usage summary for an agent."""
    store = _get_identity_store()
    agent = await store.get_agent(agent_id)

    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    analytics = _get_analytics()
    canonical_service = _public_service_label(service) if service else None
    return _canonicalize_usage_summary(
        await analytics.get_usage_summary(agent_id, service=canonical_service, days=days)
    )


@router.get("/usage/organization/{organization_id}")
async def get_organization_usage(
    organization_id: str,
    days: int = Query(default=30),
) -> Dict[str, Any]:
    """Get aggregated usage for an entire organization."""
    analytics = _get_analytics()
    return _canonicalize_organization_usage(
        await analytics.get_organization_usage(organization_id, days=days)
    )


@router.post("/evidence/ingest")
async def ingest_evidence(body: Optional[EvidenceIngestRequest] = None) -> Dict[str, Any]:
    """Trigger evidence ingestion from operational facts and usage events."""
    adapter = await _get_evidence_adapter()
    since = body.since if body is not None else None
    limit = body.limit if body is not None else 100
    operational_result = await adapter.ingest_operational_facts(
        since=since,
        limit=limit,
    )
    usage_result = await adapter.ingest_usage_summaries(
        since=since,
        limit=limit,
    )
    return operational_result.merge(usage_result).to_dict()
