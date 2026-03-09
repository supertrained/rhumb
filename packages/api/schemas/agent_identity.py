"""Agent identity schema and Bearer token verification.

Defines the agent identity record stored in Supabase and provides
verification of Bearer tokens + per-agent service access control.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentIdentitySchema(BaseModel):
    """Agent identity record (mirrors the ``agents`` Supabase table)."""

    agent_id: str = Field(..., description="Unique agent identifier (e.g. 'rhumb-lead')")
    operator_id: str = Field(..., description="Operator who owns this agent (e.g. 'tom')")
    allowed_services: List[str] = Field(
        default_factory=list,
        description="Services the agent may access (e.g. ['stripe', 'slack'])",
    )
    rate_limit_qpm: int = Field(
        default=100,
        description="Requests per minute across all services",
    )
    api_token: str = Field(..., description="Bearer token for authentication")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)


class AgentIdentityVerifier:
    """Verify agent identity from Bearer token and enforce service access."""

    def __init__(self, supabase_client: Any = None) -> None:
        self.supabase = supabase_client
        self._cache: Dict[str, AgentIdentitySchema] = {}

    # ------------------------------------------------------------------
    # Bearer token verification
    # ------------------------------------------------------------------

    async def verify_bearer_token(self, token: str) -> Optional[AgentIdentitySchema]:
        """Verify a Bearer token and return the associated agent identity.

        Args:
            token: Bearer token value (without the ``Bearer `` prefix).

        Returns:
            :class:`AgentIdentitySchema` if the token is valid and the agent
            is active, else ``None``.
        """
        # Cache hit
        if token in self._cache:
            cached = self._cache[token]
            if cached.is_active:
                return cached
            return None

        # Query Supabase
        if self.supabase is None:
            return None

        try:
            response = (
                self.supabase.table("agents")
                .select(
                    "agent_id, operator_id, allowed_services, rate_limit_qpm, "
                    "api_token, created_at, updated_at, is_active"
                )
                .eq("api_token", token)
                .eq("is_active", True)
                .single()
                .execute()
            )
            if response.data:
                identity = AgentIdentitySchema(**response.data)
                self._cache[token] = identity
                return identity
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------
    # Service access verification
    # ------------------------------------------------------------------

    async def verify_service_access(self, agent_id: str, service: str) -> bool:
        """Check whether *agent_id* is allowed to access *service*.

        Looks up the agent's ``allowed_services`` list in cache first,
        then falls back to a Supabase query.

        Returns:
            ``True`` if the agent is allowed, ``False`` otherwise.
        """
        # Check cache (iterate values keyed by token)
        for identity in self._cache.values():
            if identity.agent_id == agent_id:
                return service in identity.allowed_services

        if self.supabase is None:
            return False

        try:
            response = (
                self.supabase.table("agents")
                .select("allowed_services")
                .eq("agent_id", agent_id)
                .single()
                .execute()
            )
            if response.data:
                return service in response.data.get("allowed_services", [])
        except Exception:
            pass

        return False

    # ------------------------------------------------------------------
    # Cache helpers (for tests and admin)
    # ------------------------------------------------------------------

    def cache_identity(self, identity: AgentIdentitySchema) -> None:
        """Manually cache an identity (used by tests)."""
        self._cache[identity.api_token] = identity

    def clear_cache(self) -> None:
        """Clear the in-memory identity cache."""
        self._cache.clear()


# ------------------------------------------------------------------
# Singleton accessor
# ------------------------------------------------------------------

_verifier: Optional[AgentIdentityVerifier] = None


def get_agent_verifier(supabase_client: Any = None) -> AgentIdentityVerifier:
    """Return (or create) the global :class:`AgentIdentityVerifier` singleton."""
    global _verifier
    if _verifier is None:
        _verifier = AgentIdentityVerifier(supabase_client)
    return _verifier
