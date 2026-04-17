"""Service access matrix enforcement (ACL).

Determines whether an agent is authorised to use a specific service.
Wraps the identity store's service access grants with explicit
allow/deny semantics and reason strings for API error messages.

Round 11 (WU 2.2): Access control layer on top of agent identity.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from schemas.agent_identity import (
    AgentIdentitySchema,
    AgentIdentityStore,
    AgentServiceAccessSchema,
    get_agent_identity_store,
)
from services.service_slugs import public_service_slug


class AgentAccessControl:
    """Service access matrix enforcement.

    A request is allowed **only** when all of the following hold:
      1. The agent exists.
      2. The agent's status is ``"active"``.
      3. An ``agent_service_access`` row exists for the agent + service
         with ``status == "active"``.
    """

    def __init__(
        self, identity_store: Optional[AgentIdentityStore] = None
    ) -> None:
        self._identity_store = identity_store

    @property
    def identity_store(self) -> AgentIdentityStore:
        if self._identity_store is None:
            self._identity_store = get_agent_identity_store()
        return self._identity_store

    # ── Core Check ───────────────────────────────────────────────────

    async def can_access_service(
        self,
        agent_id: str,
        service: str,
    ) -> Tuple[bool, Optional[str]]:
        """Check if an agent is authorised to use a service.

        Returns:
            ``(allowed, reason_if_denied)`` — *reason_if_denied* is ``None``
            when access is allowed.
        """
        # 1. Agent exists?
        agent = await self.identity_store.get_agent(agent_id)
        if agent is None:
            return False, f"Agent '{agent_id}' not found"

        allowed, reason, _access = await self.resolve_service_access(agent, service)
        return allowed, reason

    async def resolve_service_access(
        self,
        agent: AgentIdentitySchema,
        service: str,
    ) -> Tuple[bool, Optional[str], Optional[AgentServiceAccessSchema]]:
        """Resolve service access using a pre-hydrated agent context."""
        public_service = public_service_slug(service) or str(service).strip().lower()
        if agent.status != "active":
            return False, f"Agent '{agent.agent_id}' is {agent.status}", None

        access = await self.identity_store.get_service_access(agent.agent_id, service)
        if access is None:
            return (
                False,
                f"Agent '{agent.agent_id}' has no access to service '{public_service}'",
                None,
            )

        return True, None, access

    # ── Bulk Queries ─────────────────────────────────────────────────

    async def list_agent_services(self, agent_id: str) -> List[str]:
        """Return all service names the agent can currently access."""
        grants = await self.identity_store.get_agent_services(agent_id, active_only=True)
        return [g.service for g in grants]

    async def check_multiple_services(
        self,
        agent_id: str,
        services: List[str],
    ) -> dict[str, Tuple[bool, Optional[str]]]:
        """Check access for multiple services at once.

        Returns:
            Dict mapping service name to ``(allowed, reason_if_denied)``.
        """
        results: dict[str, Tuple[bool, Optional[str]]] = {}
        for service in services:
            allowed, reason = await self.can_access_service(agent_id, service)
            results[service] = (allowed, reason)
        return results


# ── Singleton ────────────────────────────────────────────────────────

_acl: Optional[AgentAccessControl] = None


def get_agent_access_control(
    identity_store: Optional[AgentIdentityStore] = None,
) -> AgentAccessControl:
    """Return (or create) the global :class:`AgentAccessControl`."""
    global _acl
    if _acl is None:
        _acl = AgentAccessControl(identity_store)
    return _acl


def reset_agent_access_control() -> None:
    """Reset the singleton (for tests)."""
    global _acl
    _acl = None
