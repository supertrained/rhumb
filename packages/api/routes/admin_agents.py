"""Admin routes for agent management.

CRUD operations for agent identity, service access grants,
API key rotation, and usage queries. Internal-only (v1).

Round 11 (WU 2.2): Admin dashboard routes.
"""

from __future__ import annotations

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

router = APIRouter(tags=["admin-agents"])


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


# ── Helper: get stores (overridable in tests) ───────────────────────

_test_identity_store: Optional[AgentIdentityStore] = None
_test_analytics: Optional[AgentUsageAnalytics] = None
_test_acl: Optional[AgentAccessControl] = None


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


def _get_identity_store() -> AgentIdentityStore:
    return _test_identity_store or get_agent_identity_store()


def _get_analytics() -> AgentUsageAnalytics:
    return _test_analytics or get_usage_analytics()


def _get_acl() -> AgentAccessControl:
    return _test_acl or get_agent_access_control()


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
                service_count=len(services),
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
    usage = await analytics.get_usage_summary(agent_id)

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
        services=[s.service for s in services],
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
        raise HTTPException(
            status_code=409,
            detail=f"Agent already has active access to '{body.service}'",
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
        raise HTTPException(
            status_code=404,
            detail=f"No active access found for agent '{agent_id}' to service '{body.service}'",
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
    return await analytics.get_usage_summary(agent_id, service=service, days=days)


@router.get("/usage/organization/{organization_id}")
async def get_organization_usage(
    organization_id: str,
    days: int = Query(default=30),
) -> Dict[str, Any]:
    """Get aggregated usage for an entire organization."""
    analytics = _get_analytics()
    return await analytics.get_organization_usage(organization_id, days=days)
