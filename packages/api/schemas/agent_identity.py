"""Agent identity schema and identity store.

Defines the extended agent identity model with API key management,
organization scoping, service access matrix, and lifecycle operations.

Round 11 (WU 2.2): Extends the Round 10 schema with full identity
registration, API key generation/rotation, and service access grants.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time as _time
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC now (avoids deprecated ``datetime.utcnow()``)."""
    return datetime.now(tz=UTC)


# ── Schemas ──────────────────────────────────────────────────────────


class AgentIdentitySchema(BaseModel):
    """Complete agent identity record (mirrors ``agents`` Supabase table)."""

    agent_id: str = Field(..., description="UUID agent identifier")
    name: str = Field(..., description="Human-readable agent name")
    organization_id: str = Field(
        ..., description="Organization that owns this agent"
    )

    # Authentication
    api_key_hash: str = Field(default="", description="SHA-256 hash of the API key")
    api_key_prefix: str = Field(
        default="", description="First 8 chars of the API key (for identification)"
    )
    api_key_created_at: Optional[datetime] = Field(default=None)
    api_key_rotated_at: Optional[datetime] = Field(default=None)

    # Status
    status: str = Field(default="active", description="active | disabled | deleted")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    disabled_at: Optional[datetime] = Field(default=None)

    # Configuration
    rate_limit_qpm: int = Field(
        default=100, description="Queries per minute (global across services)"
    )
    timeout_seconds: int = Field(default=30, description="Request timeout")
    retry_policy: Dict[str, Any] = Field(
        default_factory=lambda: {"max_retries": 3, "backoff_ms": 100}
    )

    # Metadata
    description: Optional[str] = Field(default=None)
    tags: List[str] = Field(default_factory=list)
    custom_attributes: Dict[str, Any] = Field(default_factory=dict)


class AgentServiceAccessSchema(BaseModel):
    """Which services an agent can access (mirrors ``agent_service_access`` table)."""

    access_id: str = Field(..., description="UUID access grant identifier")
    agent_id: str = Field(..., description="Agent this grant belongs to")
    service: str = Field(..., description="Service name (e.g. 'stripe')")

    status: str = Field(default="active", description="active | revoked")
    granted_at: datetime = Field(default_factory=_utcnow)
    revoked_at: Optional[datetime] = Field(default=None)

    # Per-service rate limit override (0 = use agent's global limit)
    rate_limit_qpm_override: int = Field(
        default=0, description="Override QPM for this service (0 = use global)"
    )

    # Credential source
    credential_account_id: Optional[str] = Field(default=None)

    # Last used
    last_used_at: Optional[datetime] = Field(default=None)
    last_used_result: Optional[str] = Field(
        default=None, description="success | rate_limited | auth_failed | error"
    )


# ── API Key Utilities ────────────────────────────────────────────────


_API_KEY_PREFIX = "rhumb_"
_API_KEY_BYTES = 32


def generate_api_key() -> str:
    """Generate a new API key with ``rhumb_`` prefix.

    Returns:
        API key string (e.g. ``rhumb_a1b2c3d4...``).
    """
    token = secrets.token_hex(_API_KEY_BYTES)
    return f"{_API_KEY_PREFIX}{token}"


def hash_api_key(api_key: str) -> str:
    """SHA-256 hash an API key for secure storage.

    Using SHA-256 (not bcrypt) because we need to look up by hash
    for O(1) verification — bcrypt requires iterating all agents.
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def verify_api_key(api_key: str, stored_hash: str) -> bool:
    """Constant-time comparison of API key against stored hash."""
    computed = hash_api_key(api_key)
    return hmac.compare_digest(computed, stored_hash)


def api_key_prefix(api_key: str) -> str:
    """Extract the first 12 characters of the key for identification."""
    return api_key[:12] if len(api_key) >= 12 else api_key


# ── Identity Store ───────────────────────────────────────────────────


class AgentIdentityStore:
    """Manage complete agent lifecycle with Supabase persistence.

    Supports in-memory mode (``supabase_client=None``) for testing —
    all operations work against ``_mem_agents`` and ``_mem_access`` dicts.
    """

    def __init__(self, supabase_client: Any = None) -> None:
        self.supabase = supabase_client
        # In-memory stores for testing
        self._mem_agents: Dict[str, Dict[str, Any]] = {}
        self._mem_access: Dict[str, Dict[str, Any]] = {}
        # Hash → hydrated agent cache (legacy tests may still seed agent_id strings).
        self._key_index: Dict[str, AgentIdentitySchema | str] = {}
        self.ACL_CACHE_TTL_SECONDS: float = 60.0
        self._acl_cache: Dict[
            Tuple[str, str], Tuple[Optional[AgentServiceAccessSchema], float]
        ] = {}

    def _cache_agent_key(self, agent: AgentIdentitySchema) -> None:
        """Cache a hydrated agent for warm API-key verification."""
        if agent.api_key_hash:
            self._key_index[agent.api_key_hash] = agent

    def _cache_updated_agent(
        self,
        agent: AgentIdentitySchema,
        update: Dict[str, Any],
    ) -> None:
        """Refresh the cached API-key entry after a lifecycle update."""
        merged = agent.model_dump(mode="json")
        merged.update(update)
        self._cache_agent_key(self._row_to_schema(merged))

    # ── Registration ─────────────────────────────────────────────────

    async def register_agent(
        self,
        name: str,
        organization_id: str,
        rate_limit_qpm: int = 100,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Tuple[str, str]:
        """Register a new agent.

        Returns:
            ``(agent_id, api_key)`` — the unhashed API key is returned
            only once and must be saved by the caller.
        """
        agent_id = str(uuid.uuid4())
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        key_pref = api_key_prefix(api_key)
        now = _utcnow()

        agent_row: Dict[str, Any] = {
            "agent_id": agent_id,
            "name": name,
            "organization_id": organization_id,
            "api_key_hash": key_hash,
            "api_key_prefix": key_pref,
            "api_key_created_at": now.isoformat(),
            "api_key_rotated_at": None,
            "status": "active",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "disabled_at": None,
            "rate_limit_qpm": rate_limit_qpm,
            "timeout_seconds": 30,
            "retry_policy": json.dumps({"max_retries": 3, "backoff_ms": 100}),
            "description": description,
            "tags": json.dumps(tags or []),
            "custom_attributes": json.dumps({}),
        }

        if self.supabase is not None:
            await self.supabase.table("agents").insert(agent_row).execute()
        else:
            self._mem_agents[agent_id] = agent_row

        self._cache_agent_key(self._row_to_schema(agent_row))

        return agent_id, api_key

    # ── Retrieval ────────────────────────────────────────────────────

    async def get_agent(self, agent_id: str) -> Optional[AgentIdentitySchema]:
        """Retrieve agent by ID."""
        row: Optional[Dict[str, Any]] = None

        if self.supabase is not None:
            try:
                response = await (
                    self.supabase.table("agents")
                    .select("*")
                    .eq("agent_id", agent_id)
                    .single()
                    .execute()
                )
                row = response.data
            except Exception:
                return None
        else:
            row = self._mem_agents.get(agent_id)

        if row is None:
            return None

        agent = self._row_to_schema(row)
        self._cache_agent_key(agent)
        return agent

    async def list_agents(
        self,
        organization_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[AgentIdentitySchema]:
        """List agents with optional filters."""
        if self.supabase is not None:
            query = self.supabase.table("agents").select("*")
            if organization_id:
                query = query.eq("organization_id", organization_id)
            if status:
                query = query.eq("status", status)
            response = await query.execute()
            rows = response.data or []
        else:
            rows = list(self._mem_agents.values())
            if organization_id:
                rows = [r for r in rows if r["organization_id"] == organization_id]
            if status:
                rows = [r for r in rows if r["status"] == status]

        return [self._row_to_schema(r) for r in rows]

    # ── API Key Verification ─────────────────────────────────────────

    async def verify_api_key_with_agent(
        self, api_key: str
    ) -> Optional[AgentIdentitySchema]:
        """Verify an API key and return the hydrated agent when valid.

        Uses SHA-256 hash index for O(1) lookup instead of iterating
        all agents.

        Returns:
            Active :class:`AgentIdentitySchema` if valid, else ``None``.
        """
        key_hash = hash_api_key(api_key)

        # Check in-memory index first
        if key_hash in self._key_index:
            cached = self._key_index[key_hash]
            if isinstance(cached, AgentIdentitySchema):
                if cached.status == "active":
                    return cached
                return None

            agent = await self.get_agent(cached)
            if agent and agent.status == "active":
                self._cache_agent_key(agent)
                return agent
            return None

        # Supabase lookup by hash (O(1) with index)
        if self.supabase is not None:
            try:
                response = await (
                    self.supabase.table("agents")
                    .select("*")
                    .eq("api_key_hash", key_hash)
                    .eq("status", "active")
                    .single()
                    .execute()
                )
                if response.data:
                    agent = self._row_to_schema(response.data)
                    self._cache_agent_key(agent)
                    return agent
            except Exception:
                pass

        return None

    async def verify_api_key(self, api_key: str) -> Optional[str]:
        """Verify an API key and return the agent_id if valid."""
        agent = await self.verify_api_key_with_agent(api_key)
        return agent.agent_id if agent is not None else None

    # ── Key Rotation ─────────────────────────────────────────────────

    async def rotate_api_key(self, agent_id: str) -> Optional[str]:
        """Rotate an agent's API key.

        Invalidates the old key immediately and returns the new unhashed key.

        Returns:
            New API key string, or ``None`` if agent not found.
        """
        agent = await self.get_agent(agent_id)
        if agent is None:
            return None

        # Remove old hash from index
        old_hash = agent.api_key_hash
        self._key_index.pop(old_hash, None)

        new_api_key = generate_api_key()
        new_hash = hash_api_key(new_api_key)
        new_prefix = api_key_prefix(new_api_key)
        now = _utcnow()

        update = {
            "api_key_hash": new_hash,
            "api_key_prefix": new_prefix,
            "api_key_created_at": now.isoformat(),
            "api_key_rotated_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        if self.supabase is not None:
            await self.supabase.table("agents").update(update).eq(
                "agent_id", agent_id
            ).execute()
        else:
            if agent_id in self._mem_agents:
                self._mem_agents[agent_id].update(update)

        self._cache_updated_agent(agent, update)

        return new_api_key

    # ── Agent Status ─────────────────────────────────────────────────

    async def disable_agent(self, agent_id: str) -> bool:
        """Disable an agent (soft delete)."""
        agent = await self.get_agent(agent_id)
        now = _utcnow()
        update = {
            "status": "disabled",
            "disabled_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        if self.supabase is not None:
            await self.supabase.table("agents").update(update).eq(
                "agent_id", agent_id
            ).execute()
        else:
            if agent_id not in self._mem_agents:
                return False
            self._mem_agents[agent_id].update(update)

        if agent is not None:
            self._cache_updated_agent(agent, update)

        return True

    async def enable_agent(self, agent_id: str) -> bool:
        """Re-enable a disabled agent."""
        agent = await self.get_agent(agent_id)
        update = {
            "status": "active",
            "disabled_at": None,
            "updated_at": _utcnow().isoformat(),
        }

        if self.supabase is not None:
            await self.supabase.table("agents").update(update).eq(
                "agent_id", agent_id
            ).execute()
        else:
            if agent_id not in self._mem_agents:
                return False
            self._mem_agents[agent_id].update(update)

        if agent is not None:
            self._cache_updated_agent(agent, update)

        return True

    # ── Service Access Grants ────────────────────────────────────────

    async def grant_service_access(
        self,
        agent_id: str,
        service: str,
        rate_limit_override: int = 0,
        credential_account_id: Optional[str] = None,
    ) -> str:
        """Grant an agent access to a service.

        Returns:
            ``access_id`` (UUID).
        """
        access_id = str(uuid.uuid4())
        now = _utcnow()

        access_row: Dict[str, Any] = {
            "access_id": access_id,
            "agent_id": agent_id,
            "service": service,
            "status": "active",
            "granted_at": now.isoformat(),
            "revoked_at": None,
            "rate_limit_qpm_override": rate_limit_override,
            "credential_account_id": credential_account_id,
            "last_used_at": None,
            "last_used_result": None,
        }

        if self.supabase is not None:
            await self.supabase.table("agent_service_access").insert(access_row).execute()
        else:
            self._mem_access[access_id] = access_row

        self._acl_cache.pop((agent_id, service), None)
        return access_id

    async def revoke_service_access(self, access_id: str) -> bool:
        """Revoke an agent's access to a service."""
        now = _utcnow()
        update = {
            "status": "revoked",
            "revoked_at": now.isoformat(),
        }
        cache_key: Optional[Tuple[str, str]] = None

        if self.supabase is not None:
            try:
                response = await (
                    self.supabase.table("agent_service_access")
                    .select("agent_id, service")
                    .eq("access_id", access_id)
                    .single()
                    .execute()
                )
                if response.data:
                    cache_key = (response.data["agent_id"], response.data["service"])
            except Exception:
                pass
            await self.supabase.table("agent_service_access").update(update).eq(
                "access_id", access_id
            ).execute()
        else:
            row = self._mem_access.get(access_id)
            if row is None:
                return False
            cache_key = (row["agent_id"], row["service"])
            row.update(update)

        if cache_key is not None:
            self._acl_cache.pop(cache_key, None)
        return True

    async def revoke_service_access_by_agent_service(
        self, agent_id: str, service: str
    ) -> bool:
        """Revoke access by agent_id + service name."""
        if self.supabase is not None:
            response = await (
                self.supabase.table("agent_service_access")
                .select("access_id")
                .eq("agent_id", agent_id)
                .eq("service", service)
                .eq("status", "active")
                .execute()
            )
            if not response.data:
                self._acl_cache.pop((agent_id, service), None)
                return False
            for row in response.data:
                await self.revoke_service_access(row["access_id"])
            self._acl_cache.pop((agent_id, service), None)
            return True
        else:
            found = False
            for _access_id, row in self._mem_access.items():
                if (
                    row["agent_id"] == agent_id
                    and row["service"] == service
                    and row["status"] == "active"
                ):
                    row["status"] = "revoked"
                    row["revoked_at"] = _utcnow().isoformat()
                    found = True
            self._acl_cache.pop((agent_id, service), None)
            return found

    async def get_agent_services(
        self, agent_id: str, active_only: bool = True
    ) -> List[AgentServiceAccessSchema]:
        """List all service access grants for an agent."""
        if self.supabase is not None:
            query = (
                self.supabase.table("agent_service_access")
                .select("*")
                .eq("agent_id", agent_id)
            )
            if active_only:
                query = query.eq("status", "active")
            response = await query.execute()
            rows = response.data or []
        else:
            rows = [
                r
                for r in self._mem_access.values()
                if r["agent_id"] == agent_id
                and (not active_only or r["status"] == "active")
            ]

        return [AgentServiceAccessSchema(**r) for r in rows]

    async def get_service_access(
        self, agent_id: str, service: str
    ) -> Optional[AgentServiceAccessSchema]:
        """Get a specific service access grant for an agent."""
        cache_key = (agent_id, service)
        now = _time.monotonic()
        cached = self._acl_cache.get(cache_key)
        if cached is not None:
            value, expires_at = cached
            if now < expires_at:
                return value
            del self._acl_cache[cache_key]

        result: Optional[AgentServiceAccessSchema] = None
        if self.supabase is not None:
            try:
                response = await (
                    self.supabase.table("agent_service_access")
                    .select("*")
                    .eq("agent_id", agent_id)
                    .eq("service", service)
                    .eq("status", "active")
                    .single()
                    .execute()
                )
                if response.data:
                    result = AgentServiceAccessSchema(**response.data)
            except Exception:
                pass
        else:
            for row in self._mem_access.values():
                if (
                    row["agent_id"] == agent_id
                    and row["service"] == service
                    and row["status"] == "active"
                ):
                    result = AgentServiceAccessSchema(**row)
                    break

        self._acl_cache[cache_key] = (result, now + self.ACL_CACHE_TTL_SECONDS)
        return result

    def clear_acl_cache(self) -> None:
        """Clear the ACL grant cache."""
        self._acl_cache.clear()

    # ── Usage Recording ──────────────────────────────────────────────

    async def record_usage(
        self,
        agent_id: str,
        service: str,
        result: str,
    ) -> None:
        """Record that an agent used a service (updates last_used_*)."""
        now = _utcnow()
        update = {
            "last_used_at": now.isoformat(),
            "last_used_result": result,
        }
        cache_key = (agent_id, service)
        updated_row: Optional[Dict[str, Any]] = None

        if self.supabase is not None:
            await self.supabase.table("agent_service_access").update(update).eq(
                "agent_id", agent_id
            ).eq("service", service).eq("status", "active").execute()
        else:
            for row in self._mem_access.values():
                if (
                    row["agent_id"] == agent_id
                    and row["service"] == service
                    and row["status"] == "active"
                ):
                    row.update(update)
                    updated_row = row
                    break

        cached = self._acl_cache.get(cache_key)
        if cached is None:
            return

        access, expires_at = cached
        if access is None:
            return

        if updated_row is not None:
            self._acl_cache[cache_key] = (
                AgentServiceAccessSchema(**updated_row),
                expires_at,
            )
            return

        self._acl_cache[cache_key] = (
            access.model_copy(
                update={
                    "last_used_at": now,
                    "last_used_result": result,
                }
            ),
            expires_at,
        )

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _row_to_schema(row: Dict[str, Any]) -> AgentIdentitySchema:
        """Convert a DB row dict to an AgentIdentitySchema."""
        # Handle JSON string fields
        tags = row.get("tags", [])
        if isinstance(tags, str):
            tags = json.loads(tags)

        retry_policy = row.get("retry_policy", {"max_retries": 3, "backoff_ms": 100})
        if isinstance(retry_policy, str):
            retry_policy = json.loads(retry_policy)

        custom_attrs = row.get("custom_attributes", {})
        if isinstance(custom_attrs, str):
            custom_attrs = json.loads(custom_attrs)

        return AgentIdentitySchema(
            agent_id=row["agent_id"],
            name=row["name"],
            organization_id=row["organization_id"],
            api_key_hash=row.get("api_key_hash", ""),
            api_key_prefix=row.get("api_key_prefix", ""),
            api_key_created_at=row.get("api_key_created_at"),
            api_key_rotated_at=row.get("api_key_rotated_at"),
            status=row.get("status", "active"),
            created_at=row.get("created_at", _utcnow()),
            updated_at=row.get("updated_at", _utcnow()),
            disabled_at=row.get("disabled_at"),
            rate_limit_qpm=row.get("rate_limit_qpm", 100),
            timeout_seconds=row.get("timeout_seconds", 30),
            retry_policy=retry_policy,
            description=row.get("description"),
            tags=tags,
            custom_attributes=custom_attrs,
        )


# ── Backward Compatibility (Round 10) ────────────────────────────────
# The Round 10 tests and proxy code reference ``AgentIdentityVerifier``
# and an ``AgentIdentitySchema`` with ``operator_id`` / ``api_token`` /
# ``is_active`` / ``allowed_services``.  We provide a thin shim so
# existing tests keep working while new code uses the Round 11 API.


class _LegacyAgentIdentitySchema(BaseModel):
    """Round 10 compatible agent identity schema."""

    agent_id: str
    operator_id: str = ""
    allowed_services: List[str] = Field(default_factory=list)
    rate_limit_qpm: int = 100
    api_token: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    is_active: bool = True


class AgentIdentityVerifier:
    """Backward-compatible Bearer-token verifier from Round 10.

    Used by existing proxy_slice_c tests. New code should use
    :class:`AgentIdentityStore`.
    """

    def __init__(self, supabase_client: Any = None) -> None:
        self.supabase = supabase_client
        self._cache: Dict[str, _LegacyAgentIdentitySchema] = {}

    async def verify_bearer_token(
        self, token: str
    ) -> Optional[_LegacyAgentIdentitySchema]:
        if token in self._cache:
            cached = self._cache[token]
            if cached.is_active:
                return cached
            return None
        return None

    async def verify_service_access(self, agent_id: str, service: str) -> bool:
        for identity in self._cache.values():
            if identity.agent_id == agent_id:
                return service in identity.allowed_services
        return False

    def cache_identity(self, identity: _LegacyAgentIdentitySchema) -> None:
        self._cache[identity.api_token] = identity

    def clear_cache(self) -> None:
        self._cache.clear()


_verifier: Optional[AgentIdentityVerifier] = None


def get_agent_verifier(supabase_client: Any = None) -> AgentIdentityVerifier:
    """Return (or create) the global :class:`AgentIdentityVerifier` singleton."""
    global _verifier
    if _verifier is None:
        _verifier = AgentIdentityVerifier(supabase_client)
    return _verifier


# ── Singleton ────────────────────────────────────────────────────────

_identity_store: Optional[AgentIdentityStore] = None


def get_agent_identity_store(
    supabase_client: Any = None,
) -> AgentIdentityStore:
    """Return (or create) the global :class:`AgentIdentityStore` singleton."""
    global _identity_store
    if _identity_store is None:
        _identity_store = AgentIdentityStore(supabase_client)
    return _identity_store


def reset_identity_store() -> None:
    """Reset the singleton (for tests)."""
    global _identity_store
    _identity_store = None
