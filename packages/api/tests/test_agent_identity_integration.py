"""Integration tests for Agent Identity System (Round 11 — WU 2.2).

Tests cover:
  - Agent identity registration + retrieval (Module 1)
  - API key generation, verification, and rotation (Module 1)
  - Per-agent per-service rate limiting with overrides (Module 2)
  - Service access control matrix (Module 3)
  - Usage tracking and aggregation (Module 4)
  - Admin dashboard routes (Module 5)
  - End-to-end lifecycle flows
  - Multi-tenant organization scoping

Target: 20+ tests.
"""

from __future__ import annotations

import asyncio
from typing import Any, Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import create_app
from routes.admin_agents import set_test_stores
from schemas import agent_identity as agent_identity_module
from schemas.agent_identity import (
    AgentIdentitySchema,
    AgentIdentityStore,
    AgentServiceAccessSchema,
    api_key_prefix,
    generate_api_key,
    hash_api_key,
    reset_identity_store,
    verify_api_key,
)
from services.agent_access_control import AgentAccessControl, reset_agent_access_control
from services.agent_rate_limit import (
    AgentRateLimitChecker,
    reset_agent_rate_limit_checker,
)
from services.agent_usage_analytics import AgentUsageAnalytics, reset_usage_analytics
from services.proxy_rate_limit import RateLimiter


# ── Fixtures ─────────────────────────────────────────────────────────


def _run(coro):  # type: ignore[no-untyped-def]
    """Run an async coroutine synchronously for tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def _reset_singletons() -> Generator[None, None, None]:
    """Reset all singletons before each test."""
    reset_identity_store()
    reset_agent_rate_limit_checker()
    reset_agent_access_control()
    reset_usage_analytics()
    set_test_stores(None, None, None)
    yield
    reset_identity_store()
    reset_agent_rate_limit_checker()
    reset_agent_access_control()
    reset_usage_analytics()
    set_test_stores(None, None, None)


@pytest.fixture
def identity_store() -> AgentIdentityStore:
    """In-memory identity store (no Supabase)."""
    return AgentIdentityStore(supabase_client=None)


@pytest.fixture
def rate_limiter() -> RateLimiter:
    """In-memory rate limiter (no Redis)."""
    return RateLimiter(redis_client=None)


@pytest.fixture
def analytics(identity_store: AgentIdentityStore) -> AgentUsageAnalytics:
    """In-memory usage analytics."""
    return AgentUsageAnalytics(identity_store=identity_store)


@pytest.fixture
def acl(identity_store: AgentIdentityStore) -> AgentAccessControl:
    """Access control backed by in-memory store."""
    return AgentAccessControl(identity_store=identity_store)


@pytest.fixture
def rate_checker(
    identity_store: AgentIdentityStore, rate_limiter: RateLimiter
) -> AgentRateLimitChecker:
    """Rate limit checker wired to in-memory stores."""
    return AgentRateLimitChecker(
        identity_store=identity_store, rate_limiter=rate_limiter
    )


@pytest.fixture
def admin_client(
    identity_store: AgentIdentityStore,
    analytics: AgentUsageAnalytics,
    acl: AgentAccessControl,
) -> TestClient:
    """FastAPI TestClient wired to in-memory stores."""
    set_test_stores(identity_store, analytics, acl)
    app = create_app()
    # Admin routes require X-Rhumb-Admin-Key; use the test secret set in conftest.
    _ADMIN_SECRET = "rhumb_test_admin_secret_0000"
    return TestClient(app, headers={"X-Rhumb-Admin-Key": _ADMIN_SECRET})


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeSupabaseQuery:
    def __init__(self, client: "_FakeSupabaseClient", table_name: str) -> None:
        self._client = client
        self._table_name = table_name
        self._selected_columns = "*"
        self._filters: list[tuple[str, Any]] = []
        self._single = False
        self._insert_payload: dict[str, Any] | None = None
        self._update_payload: dict[str, Any] | None = None

    def select(self, columns: str) -> "_FakeSupabaseQuery":
        self._selected_columns = columns
        return self

    def eq(self, column: str, value: Any) -> "_FakeSupabaseQuery":
        self._filters.append((column, value))
        return self

    def single(self) -> "_FakeSupabaseQuery":
        self._single = True
        return self

    def insert(self, payload: dict[str, Any]) -> "_FakeSupabaseQuery":
        self._insert_payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "_FakeSupabaseQuery":
        self._update_payload = payload
        return self

    async def execute(self) -> _FakeResponse:
        return self._client.execute(self)


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self.access_rows: dict[str, dict[str, Any]] = {}
        self.get_service_access_queries = 0

    def table(self, table_name: str) -> _FakeSupabaseQuery:
        return _FakeSupabaseQuery(self, table_name)

    def execute(self, query: _FakeSupabaseQuery) -> _FakeResponse:
        if query._table_name != "agent_service_access":
            return _FakeResponse(None)

        if query._insert_payload is not None:
            payload = dict(query._insert_payload)
            self.access_rows[payload["access_id"]] = payload
            return _FakeResponse(payload)

        rows = [
            row
            for row in self.access_rows.values()
            if all(row.get(column) == value for column, value in query._filters)
        ]

        if query._update_payload is not None:
            for row in rows:
                row.update(query._update_payload)
            data: Any = rows[0] if query._single and rows else rows
            return _FakeResponse(data)

        if query._selected_columns == "*":
            self.get_service_access_queries += 1

        if query._selected_columns == "*":
            selected_rows = [dict(row) for row in rows]
        else:
            selected_columns = [
                column.strip() for column in query._selected_columns.split(",")
            ]
            selected_rows = [
                {column: row[column] for column in selected_columns if column in row}
                for row in rows
            ]

        data = selected_rows[0] if query._single else selected_rows
        if query._single and not selected_rows:
            data = None
        return _FakeResponse(data)


# ═══════════════════════════════════════════════════════════════════════
# MODULE 1: Agent Identity Schema + Store
# ═══════════════════════════════════════════════════════════════════════


class TestApiKeyUtils:
    """Test API key generation and hashing utilities."""

    def test_generate_api_key_format(self) -> None:
        """API key starts with 'rhumb_' prefix."""
        key = generate_api_key()
        assert key.startswith("rhumb_")
        assert len(key) > 20  # prefix + 64 hex chars

    def test_generate_api_key_unique(self) -> None:
        """Each generated key is unique."""
        keys = {generate_api_key() for _ in range(100)}
        assert len(keys) == 100

    def test_hash_and_verify(self) -> None:
        """SHA-256 hash + verify round-trip works."""
        key = generate_api_key()
        h = hash_api_key(key)
        assert verify_api_key(key, h) is True
        assert verify_api_key("wrong_key", h) is False

    def test_api_key_prefix_extraction(self) -> None:
        """Prefix extracts first 12 chars."""
        key = "rhumb_abc123def456"
        assert api_key_prefix(key) == "rhumb_abc123"


class TestAgentRegistration:
    """Test agent registration and retrieval."""

    def test_register_agent(self, identity_store: AgentIdentityStore) -> None:
        """Register creates agent with valid ID and API key."""
        agent_id, api_key = _run(
            identity_store.register_agent(
                name="test-agent",
                organization_id="org_acme",
                rate_limit_qpm=200,
                description="Test agent",
            )
        )
        assert agent_id  # UUID string
        assert api_key.startswith("rhumb_")

    def test_get_agent(self, identity_store: AgentIdentityStore) -> None:
        """Retrieve agent by ID returns correct fields."""
        agent_id, _ = _run(
            identity_store.register_agent(
                name="retrieval-test",
                organization_id="org_beta",
                rate_limit_qpm=50,
            )
        )
        agent = _run(identity_store.get_agent(agent_id))
        assert agent is not None
        assert agent.name == "retrieval-test"
        assert agent.organization_id == "org_beta"
        assert agent.rate_limit_qpm == 50
        assert agent.status == "active"

    def test_get_agent_not_found(self, identity_store: AgentIdentityStore) -> None:
        """Non-existent agent returns None."""
        agent = _run(identity_store.get_agent("nonexistent-id"))
        assert agent is None

    def test_list_agents_by_org(self, identity_store: AgentIdentityStore) -> None:
        """List agents filtered by organization."""
        _run(identity_store.register_agent("a1", "org_x"))
        _run(identity_store.register_agent("a2", "org_x"))
        _run(identity_store.register_agent("a3", "org_y"))

        org_x = _run(identity_store.list_agents(organization_id="org_x"))
        assert len(org_x) == 2

        org_y = _run(identity_store.list_agents(organization_id="org_y"))
        assert len(org_y) == 1


class TestApiKeyVerification:
    """Test API key verification and rotation."""

    def test_verify_valid_api_key(self, identity_store: AgentIdentityStore) -> None:
        """Valid API key returns agent_id."""
        agent_id, api_key = _run(
            identity_store.register_agent("key-test", "org_1")
        )
        verified_id = _run(identity_store.verify_api_key(api_key))
        assert verified_id == agent_id

    def test_verify_valid_api_key_with_agent(
        self, identity_store: AgentIdentityStore
    ) -> None:
        """Valid API key returns a hydrated active agent."""
        agent_id, api_key = _run(identity_store.register_agent("key-agent", "org_1"))

        agent = _run(identity_store.verify_api_key_with_agent(api_key))
        assert agent is not None
        assert agent.agent_id == agent_id
        assert agent.status == "active"

    def test_verify_invalid_api_key(self, identity_store: AgentIdentityStore) -> None:
        """Invalid API key returns None."""
        result = _run(identity_store.verify_api_key("rhumb_invalid_key"))
        assert result is None

    def test_rotate_api_key(self, identity_store: AgentIdentityStore) -> None:
        """Rotation: new key works, old key does not."""
        agent_id, old_key = _run(
            identity_store.register_agent("rotate-test", "org_1")
        )

        new_key = _run(identity_store.rotate_api_key(agent_id))
        assert new_key is not None
        assert new_key != old_key
        assert new_key.startswith("rhumb_")

        # New key works
        assert _run(identity_store.verify_api_key(new_key)) == agent_id
        # Old key doesn't
        assert _run(identity_store.verify_api_key(old_key)) is None

    def test_verify_disabled_agent_key(
        self, identity_store: AgentIdentityStore
    ) -> None:
        """Disabled agent's key is rejected."""
        agent_id, api_key = _run(
            identity_store.register_agent("disable-test", "org_1")
        )
        _run(identity_store.disable_agent(agent_id))
        assert _run(identity_store.verify_api_key(api_key)) is None


class TestAgentStatus:
    """Test agent enable/disable lifecycle."""

    def test_disable_and_enable(self, identity_store: AgentIdentityStore) -> None:
        """Agent can be disabled then re-enabled."""
        agent_id, _ = _run(identity_store.register_agent("status-test", "org_1"))

        # Disable
        assert _run(identity_store.disable_agent(agent_id)) is True
        agent = _run(identity_store.get_agent(agent_id))
        assert agent is not None
        assert agent.status == "disabled"

        # Enable
        assert _run(identity_store.enable_agent(agent_id)) is True
        agent = _run(identity_store.get_agent(agent_id))
        assert agent is not None
        assert agent.status == "active"


# ═══════════════════════════════════════════════════════════════════════
# MODULE 1 (cont.): Service Access Grants
# ═══════════════════════════════════════════════════════════════════════


class TestServiceAccessGrants:
    """Test granting and revoking service access."""

    def test_grant_service_access(self, identity_store: AgentIdentityStore) -> None:
        """Grant creates an active access record."""
        agent_id, _ = _run(identity_store.register_agent("grant-test", "org_1"))
        access_id = _run(identity_store.grant_service_access(agent_id, "stripe"))

        assert access_id  # UUID string

        services = _run(identity_store.get_agent_services(agent_id))
        assert len(services) == 1
        assert services[0].service == "stripe"
        assert services[0].status == "active"

    def test_revoke_service_access(self, identity_store: AgentIdentityStore) -> None:
        """Revoke marks access as revoked."""
        agent_id, _ = _run(identity_store.register_agent("revoke-test", "org_1"))
        access_id = _run(identity_store.grant_service_access(agent_id, "slack"))

        assert _run(identity_store.revoke_service_access(access_id)) is True

        services = _run(identity_store.get_agent_services(agent_id, active_only=True))
        assert len(services) == 0

    def test_get_agent_services_multiple(
        self, identity_store: AgentIdentityStore
    ) -> None:
        """Agent with multiple services lists all active ones."""
        agent_id, _ = _run(identity_store.register_agent("multi-svc", "org_1"))
        _run(identity_store.grant_service_access(agent_id, "stripe"))
        _run(identity_store.grant_service_access(agent_id, "slack"))
        _run(identity_store.grant_service_access(agent_id, "github"))

        services = _run(identity_store.get_agent_services(agent_id))
        assert len(services) == 3
        svc_names = {s.service for s in services}
        assert svc_names == {"stripe", "slack", "github"}

    def test_record_usage(self, identity_store: AgentIdentityStore) -> None:
        """Record usage updates last_used_* fields."""
        agent_id, _ = _run(identity_store.register_agent("usage-test", "org_1"))
        _run(identity_store.grant_service_access(agent_id, "stripe"))

        _run(identity_store.record_usage(agent_id, "stripe", "success"))

        access = _run(identity_store.get_service_access(agent_id, "stripe"))
        assert access is not None
        assert access.last_used_at is not None
        assert access.last_used_result == "success"


class TestServiceAccessCache:
    """Targeted tests for the ACL grant cache."""

    def test_cache_miss_queries_backend(self) -> None:
        client = _FakeSupabaseClient()
        store = AgentIdentityStore(supabase_client=client)
        access_id = _run(store.grant_service_access("agent-cache-miss", "stripe"))

        access = _run(store.get_service_access("agent-cache-miss", "stripe"))

        assert access is not None
        assert access.access_id == access_id
        assert client.get_service_access_queries == 1

    def test_cache_hit_avoids_backend_query(self) -> None:
        client = _FakeSupabaseClient()
        store = AgentIdentityStore(supabase_client=client)
        access_id = _run(store.grant_service_access("agent-cache-hit", "stripe"))

        first = _run(store.get_service_access("agent-cache-hit", "stripe"))
        second = _run(store.get_service_access("agent-cache-hit", "stripe"))

        assert first is not None
        assert second is not None
        assert first.access_id == access_id
        assert second.access_id == access_id
        assert client.get_service_access_queries == 1

    def test_cache_expiry_requeries_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _FakeSupabaseClient()
        store = AgentIdentityStore(supabase_client=client)
        _run(store.grant_service_access("agent-cache-expiry", "stripe"))
        now = [100.0]
        monkeypatch.setattr(agent_identity_module._time, "monotonic", lambda: now[0])

        first = _run(store.get_service_access("agent-cache-expiry", "stripe"))
        now[0] += store.ACL_CACHE_TTL_SECONDS + 1.0
        second = _run(store.get_service_access("agent-cache-expiry", "stripe"))

        assert first is not None
        assert second is not None
        assert client.get_service_access_queries == 2

    def test_negative_caching_avoids_repeat_backend_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeSupabaseClient()
        store = AgentIdentityStore(supabase_client=client)
        now = [200.0]
        monkeypatch.setattr(agent_identity_module._time, "monotonic", lambda: now[0])

        first = _run(store.get_service_access("agent-negative", "slack"))
        second = _run(store.get_service_access("agent-negative", "slack"))

        assert first is None
        assert second is None
        assert client.get_service_access_queries == 1

    def test_grant_service_access_invalidates_negative_cache(self) -> None:
        client = _FakeSupabaseClient()
        store = AgentIdentityStore(supabase_client=client)

        assert _run(store.get_service_access("agent-grant-invalidate", "github")) is None
        assert client.get_service_access_queries == 1

        access_id = _run(store.grant_service_access("agent-grant-invalidate", "github"))
        access = _run(store.get_service_access("agent-grant-invalidate", "github"))

        assert access is not None
        assert access.access_id == access_id
        assert client.get_service_access_queries == 2

    def test_revoke_service_access_invalidates_positive_cache(self) -> None:
        client = _FakeSupabaseClient()
        store = AgentIdentityStore(supabase_client=client)
        access_id = _run(store.grant_service_access("agent-revoke-id", "stripe"))

        assert _run(store.get_service_access("agent-revoke-id", "stripe")) is not None
        assert client.get_service_access_queries == 1

        assert _run(store.revoke_service_access(access_id)) is True
        assert _run(store.get_service_access("agent-revoke-id", "stripe")) is None
        assert client.get_service_access_queries == 2

    def test_revoke_by_agent_service_invalidates_positive_cache(self) -> None:
        client = _FakeSupabaseClient()
        store = AgentIdentityStore(supabase_client=client)
        _run(store.grant_service_access("agent-revoke-pair", "slack"))

        assert _run(store.get_service_access("agent-revoke-pair", "slack")) is not None
        assert client.get_service_access_queries == 1

        assert _run(store.revoke_service_access_by_agent_service("agent-revoke-pair", "slack"))
        assert _run(store.get_service_access("agent-revoke-pair", "slack")) is None
        assert client.get_service_access_queries == 2

    def test_clear_acl_cache(self) -> None:
        client = _FakeSupabaseClient()
        store = AgentIdentityStore(supabase_client=client)
        _run(store.grant_service_access("agent-clear-cache", "stripe"))

        assert _run(store.get_service_access("agent-clear-cache", "stripe")) is not None
        assert store._acl_cache

        store.clear_acl_cache()

        assert store._acl_cache == {}


# ═══════════════════════════════════════════════════════════════════════
# MODULE 2: Rate Limiting
# ═══════════════════════════════════════════════════════════════════════


class TestAgentRateLimiting:
    """Test per-agent per-service rate limiting."""

    def test_rate_limit_allowed(
        self,
        identity_store: AgentIdentityStore,
        rate_checker: AgentRateLimitChecker,
    ) -> None:
        """Request within limit is allowed."""
        agent_id, _ = _run(identity_store.register_agent("rl-ok", "org_1", rate_limit_qpm=100))
        _run(identity_store.grant_service_access(agent_id, "stripe"))

        result = _run(rate_checker.check_rate_limit(agent_id, "stripe"))
        assert result.allowed is True
        assert result.remaining > 0
        assert result.effective_limit_qpm == 100

    def test_rate_limit_exceeded(
        self,
        identity_store: AgentIdentityStore,
        rate_checker: AgentRateLimitChecker,
    ) -> None:
        """Requests exceeding limit are denied with rate_limited error."""
        agent_id, _ = _run(
            identity_store.register_agent("rl-exceed", "org_1", rate_limit_qpm=3)
        )
        _run(identity_store.grant_service_access(agent_id, "stripe"))

        # Use up the limit
        for _ in range(3):
            result = _run(rate_checker.check_rate_limit(agent_id, "stripe"))
            assert result.allowed is True

        # Next request should be denied
        result = _run(rate_checker.check_rate_limit(agent_id, "stripe"))
        assert result.allowed is False
        assert result.error == "rate_limited"

    def test_rate_limit_override_per_service(
        self,
        identity_store: AgentIdentityStore,
        rate_checker: AgentRateLimitChecker,
    ) -> None:
        """Per-service override takes precedence over global limit."""
        agent_id, _ = _run(
            identity_store.register_agent("rl-override", "org_1", rate_limit_qpm=2)
        )
        # Stripe gets higher limit (override=10)
        _run(identity_store.grant_service_access(agent_id, "stripe", rate_limit_override=10))
        # Slack uses global (2)
        _run(identity_store.grant_service_access(agent_id, "slack"))

        # Stripe: 3 requests should pass (override=10)
        for _ in range(3):
            result = _run(rate_checker.check_rate_limit(agent_id, "stripe"))
            assert result.allowed is True
            assert result.effective_limit_qpm == 10

        # Slack: after 2 requests, denied (global=2)
        for _ in range(2):
            result = _run(rate_checker.check_rate_limit(agent_id, "slack"))
            assert result.allowed is True
            assert result.effective_limit_qpm == 2

        result = _run(rate_checker.check_rate_limit(agent_id, "slack"))
        assert result.allowed is False

    def test_rate_limit_inactive_agent(
        self,
        identity_store: AgentIdentityStore,
        rate_checker: AgentRateLimitChecker,
    ) -> None:
        """Inactive agent gets denied."""
        agent_id, _ = _run(identity_store.register_agent("rl-inactive", "org_1"))
        _run(identity_store.disable_agent(agent_id))

        result = _run(rate_checker.check_rate_limit(agent_id, "stripe"))
        assert result.allowed is False
        assert result.error == "agent_inactive_or_not_found"

    def test_rate_limit_no_access(
        self,
        identity_store: AgentIdentityStore,
        rate_checker: AgentRateLimitChecker,
    ) -> None:
        """Agent without service access gets denied."""
        agent_id, _ = _run(identity_store.register_agent("rl-noaccess", "org_1"))

        result = _run(rate_checker.check_rate_limit(agent_id, "stripe"))
        assert result.allowed is False
        assert result.error == "no_service_access"

    def test_rate_limit_with_context(
        self,
        identity_store: AgentIdentityStore,
        rate_checker: AgentRateLimitChecker,
    ) -> None:
        """Resolved context path uses the pre-fetched agent + grant."""
        agent_id, _ = _run(
            identity_store.register_agent("rl-context", "org_1", rate_limit_qpm=2)
        )
        _run(identity_store.grant_service_access(agent_id, "stripe", rate_limit_override=7))

        agent = _run(identity_store.get_agent(agent_id))
        access = _run(identity_store.get_service_access(agent_id, "stripe"))
        assert agent is not None
        assert access is not None

        result = _run(rate_checker.check_rate_limit_with_context(agent, access, "stripe"))
        assert result.allowed is True
        assert result.effective_limit_qpm == 7


# ═══════════════════════════════════════════════════════════════════════
# MODULE 3: Access Control Matrix
# ═══════════════════════════════════════════════════════════════════════


class TestAccessControl:
    """Test service access matrix enforcement."""

    def test_access_allowed(
        self, identity_store: AgentIdentityStore, acl: AgentAccessControl
    ) -> None:
        """Agent with active grant can access service."""
        agent_id, _ = _run(identity_store.register_agent("acl-ok", "org_1"))
        _run(identity_store.grant_service_access(agent_id, "stripe"))

        allowed, reason = _run(acl.can_access_service(agent_id, "stripe"))
        assert allowed is True
        assert reason is None

    def test_access_allowed_across_canonical_and_runtime_aliases(
        self,
        identity_store: AgentIdentityStore,
        acl: AgentAccessControl,
    ) -> None:
        """Canonical service grants should satisfy runtime alias checks."""
        agent_id, _ = _run(identity_store.register_agent("acl-alias-ok", "org_1"))
        _run(identity_store.grant_service_access(agent_id, "people-data-labs"))

        allowed, reason = _run(acl.can_access_service(agent_id, "pdl"))
        assert allowed is True
        assert reason is None

        services = _run(acl.list_agent_services(agent_id))
        assert services == ["people-data-labs"]

    def test_access_denied_no_grant(
        self, identity_store: AgentIdentityStore, acl: AgentAccessControl
    ) -> None:
        """Agent without grant cannot access service."""
        agent_id, _ = _run(identity_store.register_agent("acl-no", "org_1"))

        allowed, reason = _run(acl.can_access_service(agent_id, "stripe"))
        assert allowed is False
        assert "no access" in reason.lower()

    def test_access_denied_revoked(
        self, identity_store: AgentIdentityStore, acl: AgentAccessControl
    ) -> None:
        """Agent with revoked access cannot use service."""
        agent_id, _ = _run(identity_store.register_agent("acl-revoked", "org_1"))
        access_id = _run(identity_store.grant_service_access(agent_id, "stripe"))
        _run(identity_store.revoke_service_access(access_id))

        allowed, reason = _run(acl.can_access_service(agent_id, "stripe"))
        assert allowed is False

    def test_access_denied_agent_not_found(
        self, acl: AgentAccessControl
    ) -> None:
        """Non-existent agent is denied."""
        allowed, reason = _run(acl.can_access_service("ghost", "stripe"))
        assert allowed is False
        assert "not found" in reason.lower()

    def test_list_agent_services(
        self, identity_store: AgentIdentityStore, acl: AgentAccessControl
    ) -> None:
        """Lists all active services for an agent."""
        agent_id, _ = _run(identity_store.register_agent("acl-list", "org_1"))
        _run(identity_store.grant_service_access(agent_id, "stripe"))
        _run(identity_store.grant_service_access(agent_id, "slack"))

        services = _run(acl.list_agent_services(agent_id))
        assert set(services) == {"stripe", "slack"}

    def test_resolve_service_access_returns_grant(
        self, identity_store: AgentIdentityStore, acl: AgentAccessControl
    ) -> None:
        """Resolved ACL path returns the active grant for reuse downstream."""
        agent_id, _ = _run(identity_store.register_agent("acl-resolve", "org_1"))
        _run(identity_store.grant_service_access(agent_id, "stripe"))
        agent = _run(identity_store.get_agent(agent_id))
        assert agent is not None

        allowed, reason, access = _run(acl.resolve_service_access(agent, "stripe"))
        assert allowed is True
        assert reason is None
        assert access is not None
        assert access.service == "stripe"


# ═══════════════════════════════════════════════════════════════════════
# MODULE 4: Usage Analytics
# ═══════════════════════════════════════════════════════════════════════


class TestUsageAnalytics:
    """Test usage tracking and aggregation."""

    def test_record_and_summarize(
        self,
        identity_store: AgentIdentityStore,
        analytics: AgentUsageAnalytics,
    ) -> None:
        """Record events and retrieve usage summary."""
        agent_id, _ = _run(identity_store.register_agent("usage-1", "org_1"))
        _run(identity_store.grant_service_access(agent_id, "stripe"))

        _run(analytics.record_event(agent_id, "stripe", "success", 50.0))
        _run(analytics.record_event(agent_id, "stripe", "success", 70.0))
        _run(analytics.record_event(agent_id, "stripe", "error", 100.0))

        summary = _run(analytics.get_usage_summary(agent_id))
        assert summary["total_calls"] == 3
        assert summary["successful_calls"] == 2
        assert summary["failed_calls"] == 1
        assert summary["rate_limited_calls"] == 0
        assert summary["services"]["stripe"]["calls"] == 3
        assert summary["avg_latency_ms"] > 0

    def test_usage_summary_multiple_services(
        self,
        identity_store: AgentIdentityStore,
        analytics: AgentUsageAnalytics,
    ) -> None:
        """Aggregation across multiple services is correct."""
        agent_id, _ = _run(identity_store.register_agent("usage-multi", "org_1"))
        _run(identity_store.grant_service_access(agent_id, "stripe"))
        _run(identity_store.grant_service_access(agent_id, "slack"))

        _run(analytics.record_event(agent_id, "stripe", "success"))
        _run(analytics.record_event(agent_id, "stripe", "success"))
        _run(analytics.record_event(agent_id, "slack", "success"))
        _run(analytics.record_event(agent_id, "slack", "rate_limited"))

        summary = _run(analytics.get_usage_summary(agent_id))
        assert summary["total_calls"] == 4
        assert summary["successful_calls"] == 3
        assert summary["rate_limited_calls"] == 1
        assert "stripe" in summary["services"]
        assert "slack" in summary["services"]
        assert summary["services"]["stripe"]["calls"] == 2

    def test_usage_filter_by_service(
        self,
        identity_store: AgentIdentityStore,
        analytics: AgentUsageAnalytics,
    ) -> None:
        """Filtering by service returns only that service's events."""
        agent_id, _ = _run(identity_store.register_agent("usage-filter", "org_1"))
        _run(identity_store.grant_service_access(agent_id, "stripe"))
        _run(identity_store.grant_service_access(agent_id, "slack"))

        _run(analytics.record_event(agent_id, "stripe", "success"))
        _run(analytics.record_event(agent_id, "slack", "success"))

        summary = _run(analytics.get_usage_summary(agent_id, service="stripe"))
        assert summary["total_calls"] == 1
        assert "stripe" in summary["services"]
        assert "slack" not in summary["services"]

    def test_usage_filter_accepts_canonical_alias_for_runtime_service_rows(
        self,
        identity_store: AgentIdentityStore,
        analytics: AgentUsageAnalytics,
    ) -> None:
        """Canonical public service filters still match alias-backed metered rows."""
        agent_id, _ = _run(identity_store.register_agent("usage-alias-filter", "org_1"))
        _run(identity_store.grant_service_access(agent_id, "brave-search-api"))

        _run(analytics.record_event(agent_id, "brave-search", "success"))

        summary = _run(analytics.get_usage_summary(agent_id, service="Brave-Search-Api"))
        assert summary["total_calls"] == 1
        assert set(summary["services"].keys()) == {"brave-search-api"}
        assert summary["services"]["brave-search-api"]["calls"] == 1

    def test_organization_usage(
        self,
        identity_store: AgentIdentityStore,
        analytics: AgentUsageAnalytics,
    ) -> None:
        """Organization-level aggregation sums across agents."""
        a1, _ = _run(identity_store.register_agent("org-a1", "org_multi"))
        a2, _ = _run(identity_store.register_agent("org-a2", "org_multi"))
        _run(identity_store.grant_service_access(a1, "stripe"))
        _run(identity_store.grant_service_access(a2, "slack"))

        _run(analytics.record_event(a1, "stripe", "success"))
        _run(analytics.record_event(a1, "stripe", "success"))
        _run(analytics.record_event(a2, "slack", "success"))

        org_usage = _run(analytics.get_organization_usage("org_multi"))
        assert org_usage["total_calls"] == 3
        assert len(org_usage["agents"]) == 2


# ═══════════════════════════════════════════════════════════════════════
# MODULE 5: Admin Dashboard Routes
# ═══════════════════════════════════════════════════════════════════════


class TestAdminRoutes:
    """Test admin API endpoints via FastAPI TestClient."""

    def test_create_agent_route(self, admin_client: TestClient) -> None:
        """POST /v1/admin/agents creates agent and returns API key."""
        resp = admin_client.post(
            "/v1/admin/agents",
            json={
                "name": "route-test-agent",
                "organization_id": "org_admin",
                "rate_limit_qpm": 150,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["agent_id"]
        assert data["api_key"].startswith("rhumb_")

    def test_list_agents_route(self, admin_client: TestClient) -> None:
        """GET /v1/admin/agents returns created agents."""
        admin_client.post(
            "/v1/admin/agents",
            json={"name": "list-1", "organization_id": "org_list"},
        )
        admin_client.post(
            "/v1/admin/agents",
            json={"name": "list-2", "organization_id": "org_list"},
        )

        resp = admin_client.get("/v1/admin/agents?organization_id=org_list")
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) == 2

    def test_list_agents_route_normalizes_status_filter(
        self, admin_client: TestClient
    ) -> None:
        """GET /v1/admin/agents trims and lowercases valid status filters."""
        mock_store = AsyncMock()
        mock_store.list_agents = AsyncMock(return_value=[])

        with patch("routes.admin_agents._get_identity_store", return_value=mock_store):
            resp = admin_client.get("/v1/admin/agents?status=%20DiSaBlEd%20")

        assert resp.status_code == 200
        assert resp.json() == []
        mock_store.list_agents.assert_awaited_once_with(
            organization_id=None,
            status="disabled",
        )

    def test_list_agents_route_rejects_invalid_status_filter(
        self, admin_client: TestClient
    ) -> None:
        """GET /v1/admin/agents fails explicitly on unsupported status values."""
        mock_store = AsyncMock()
        mock_store.list_agents = AsyncMock(return_value=[])

        with patch("routes.admin_agents._get_identity_store", return_value=mock_store):
            resp = admin_client.get("/v1/admin/agents?status=offline")

        assert resp.status_code == 400
        assert (
            resp.json()["detail"]
            == "Invalid status: use one of active, disabled, deleted"
        )
        mock_store.list_agents.assert_not_awaited()

    def test_get_agent_details_route(self, admin_client: TestClient) -> None:
        """GET /v1/admin/agents/{id} returns full details."""
        create_resp = admin_client.post(
            "/v1/admin/agents",
            json={"name": "detail-agent", "organization_id": "org_detail"},
        )
        agent_id = create_resp.json()["agent_id"]

        resp = admin_client.get(f"/v1/admin/agents/{agent_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "detail-agent"
        assert data["organization_id"] == "org_detail"
        assert "usage" in data

    def test_get_agent_details_route_canonicalizes_alias_backed_usage(
        self,
        admin_client: TestClient,
        analytics: AgentUsageAnalytics,
    ) -> None:
        """Agent detail route should keep alias-backed services and usage on public ids."""
        create_resp = admin_client.post(
            "/v1/admin/agents",
            json={"name": "detail-alias-agent", "organization_id": "org_detail_alias"},
        )
        agent_id = create_resp.json()["agent_id"]

        grant_resp = admin_client.post(
            f"/v1/admin/agents/{agent_id}/grant-access",
            json={"service": "brave-search"},
        )
        assert grant_resp.status_code == 200

        _run(analytics.record_event(agent_id, "brave-search", "success"))

        resp = admin_client.get(f"/v1/admin/agents/{agent_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["services"] == ["brave-search-api"]
        assert set(data["usage"]["services"].keys()) == {"brave-search-api"}
        assert data["usage"]["services"]["brave-search-api"]["calls"] == 1
        assert "brave-search" not in data["usage"]["services"]

    def test_get_agent_details_route_recanonicalizes_mixed_usage_summary_at_route_boundary(
        self,
        admin_client: TestClient,
        identity_store: AgentIdentityStore,
        acl: AgentAccessControl,
    ) -> None:
        """Agent detail route should re-merge mixed upstream usage buckets onto public ids."""
        create_resp = admin_client.post(
            "/v1/admin/agents",
            json={"name": "detail-mixed-agent", "organization_id": "org_detail_mixed"},
        )
        agent_id = create_resp.json()["agent_id"]

        class _FakeBoundaryAnalytics:
            async def get_usage_summary(
                self,
                requested_agent_id: str,
                service: str | None = None,
                days: int = 30,
            ) -> dict[str, object]:
                assert requested_agent_id == agent_id
                assert service is None
                assert days == 30
                return {
                    "agent_id": requested_agent_id,
                    "period_days": days,
                    "total_calls": 6,
                    "successful_calls": 4,
                    "failed_calls": 2,
                    "rate_limited_calls": 0,
                    "services": {
                        "brave-search": {"calls": 2, "success_rate": 1.0},
                        "brave-search-api": {"calls": 1, "success_rate": 1.0},
                        "pdl": {"calls": 1, "success_rate": 0.0},
                        "people-data-labs": {"calls": 2, "success_rate": 1.0},
                    },
                    "avg_latency_ms": 12.3,
                }

        set_test_stores(identity_store, _FakeBoundaryAnalytics(), acl)

        resp = admin_client.get(f"/v1/admin/agents/{agent_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["usage"]["services"] == {
            "brave-search-api": {"calls": 3, "success_rate": 1.0},
            "people-data-labs": {"calls": 3, "success_rate": 0.6667},
        }

    def test_get_agent_usage_route_canonicalizes_alias_backed_service_filter(
        self,
        admin_client: TestClient,
        analytics: AgentUsageAnalytics,
    ) -> None:
        """Usage route should accept canonical filters for runtime alias usage rows."""
        create_resp = admin_client.post(
            "/v1/admin/agents",
            json={"name": "usage-alias-route", "organization_id": "org_usage_alias"},
        )
        agent_id = create_resp.json()["agent_id"]

        grant_resp = admin_client.post(
            f"/v1/admin/agents/{agent_id}/grant-access",
            json={"service": "brave-search-api"},
        )
        assert grant_resp.status_code == 200

        _run(analytics.record_event(agent_id, "brave-search", "success"))

        resp = admin_client.get(
            f"/v1/admin/agents/{agent_id}/usage?service=Brave-Search-Api"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_calls"] == 1
        assert set(data["services"].keys()) == {"brave-search-api"}
        assert data["services"]["brave-search-api"]["calls"] == 1
        assert "brave-search" not in data["services"]

    def test_get_agent_usage_route_recanonicalizes_mixed_usage_summary_at_route_boundary(
        self,
        admin_client: TestClient,
        identity_store: AgentIdentityStore,
        acl: AgentAccessControl,
    ) -> None:
        """Usage route should canonicalize forwarded filters and mixed upstream buckets."""
        create_resp = admin_client.post(
            "/v1/admin/agents",
            json={"name": "usage-mixed-route", "organization_id": "org_usage_mixed"},
        )
        agent_id = create_resp.json()["agent_id"]

        class _FakeBoundaryAnalytics:
            async def get_usage_summary(
                self,
                requested_agent_id: str,
                service: str | None = None,
                days: int = 30,
            ) -> dict[str, object]:
                assert requested_agent_id == agent_id
                assert service == "brave-search-api"
                assert days == 30
                return {
                    "agent_id": requested_agent_id,
                    "period_days": days,
                    "total_calls": 3,
                    "successful_calls": 2,
                    "failed_calls": 1,
                    "rate_limited_calls": 0,
                    "services": {
                        "brave-search": {"calls": 2, "success_rate": 0.5},
                        "brave-search-api": {"calls": 1, "success_rate": 1.0},
                    },
                    "avg_latency_ms": 8.0,
                }

        set_test_stores(identity_store, _FakeBoundaryAnalytics(), acl)

        resp = admin_client.get(
            f"/v1/admin/agents/{agent_id}/usage?service=Brave-Search-Api"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["services"] == {
            "brave-search-api": {"calls": 3, "success_rate": 0.6667},
        }

    def test_get_organization_usage_route_canonicalizes_alias_backed_runtime_rows(
        self,
        admin_client: TestClient,
        analytics: AgentUsageAnalytics,
    ) -> None:
        """Organization usage route should keep alias-backed runtime rows on public ids."""
        create_resp = admin_client.post(
            "/v1/admin/agents",
            json={"name": "org-usage-alias-route", "organization_id": "org_usage_rollup"},
        )
        agent_id = create_resp.json()["agent_id"]

        grant_resp = admin_client.post(
            f"/v1/admin/agents/{agent_id}/grant-access",
            json={"service": "people-data-labs"},
        )
        assert grant_resp.status_code == 200

        _run(analytics.record_event(agent_id, "pdl", "success"))

        resp = admin_client.get("/v1/admin/usage/organization/org_usage_rollup")
        assert resp.status_code == 200
        data = resp.json()
        assert data["organization_id"] == "org_usage_rollup"
        assert data["total_calls"] == 1
        assert set(data["agents"][agent_id]["services"].keys()) == {"people-data-labs"}
        assert data["agents"][agent_id]["services"]["people-data-labs"]["calls"] == 1
        assert "pdl" not in data["agents"][agent_id]["services"]

    def test_get_organization_usage_route_recanonicalizes_mixed_usage_summary_at_route_boundary(
        self,
        admin_client: TestClient,
        identity_store: AgentIdentityStore,
        acl: AgentAccessControl,
    ) -> None:
        """Organization route should re-merge mixed upstream per-agent usage buckets."""
        create_resp = admin_client.post(
            "/v1/admin/agents",
            json={"name": "org-usage-mixed-route", "organization_id": "org_usage_boundary"},
        )
        agent_id = create_resp.json()["agent_id"]

        class _FakeBoundaryAnalytics:
            async def get_organization_usage(
                self,
                organization_id: str,
                days: int = 30,
            ) -> dict[str, object]:
                assert organization_id == "org_usage_boundary"
                assert days == 30
                return {
                    "organization_id": organization_id,
                    "period_days": days,
                    "total_calls": 3,
                    "agents": {
                        agent_id: {
                            "agent_id": agent_id,
                            "period_days": days,
                            "total_calls": 3,
                            "successful_calls": 2,
                            "failed_calls": 1,
                            "rate_limited_calls": 0,
                            "services": {
                                "pdl": {"calls": 1, "success_rate": 0.0},
                                "people-data-labs": {"calls": 2, "success_rate": 1.0},
                            },
                            "avg_latency_ms": 4.0,
                        }
                    },
                }

        set_test_stores(identity_store, _FakeBoundaryAnalytics(), acl)

        resp = admin_client.get("/v1/admin/usage/organization/org_usage_boundary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agents"][agent_id]["services"] == {
            "people-data-labs": {"calls": 3, "success_rate": 0.6667},
        }

    def test_grant_and_revoke_access_route(self, admin_client: TestClient) -> None:
        """Grant then revoke service access via admin routes."""
        # Create agent
        create_resp = admin_client.post(
            "/v1/admin/agents",
            json={"name": "grant-revoke", "organization_id": "org_gr"},
        )
        agent_id = create_resp.json()["agent_id"]

        # Grant access
        grant_resp = admin_client.post(
            f"/v1/admin/agents/{agent_id}/grant-access",
            json={"service": "stripe", "rate_limit_override": 200},
        )
        assert grant_resp.status_code == 200
        assert grant_resp.json()["status"] == "success"

        # Verify agent has service
        detail_resp = admin_client.get(f"/v1/admin/agents/{agent_id}")
        assert "stripe" in detail_resp.json()["services"]

        # Revoke access
        revoke_resp = admin_client.post(
            f"/v1/admin/agents/{agent_id}/revoke-access",
            json={"service": "stripe"},
        )
        assert revoke_resp.status_code == 200

        # Verify revoked
        detail_resp2 = admin_client.get(f"/v1/admin/agents/{agent_id}")
        assert "stripe" not in detail_resp2.json()["services"]

    def test_alias_backed_grant_and_revoke_routes_stay_canonical(
        self,
        admin_client: TestClient,
    ) -> None:
        """Alias-backed admin access routes should round-trip canonical public ids."""
        create_resp = admin_client.post(
            "/v1/admin/agents",
            json={"name": "alias-grant", "organization_id": "org_alias"},
        )
        agent_id = create_resp.json()["agent_id"]

        grant_resp = admin_client.post(
            f"/v1/admin/agents/{agent_id}/grant-access",
            json={"service": "brave-search", "rate_limit_override": 25},
        )
        assert grant_resp.status_code == 200

        detail_resp = admin_client.get(f"/v1/admin/agents/{agent_id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["services"] == ["brave-search-api"]

        duplicate_resp = admin_client.post(
            f"/v1/admin/agents/{agent_id}/grant-access",
            json={"service": "Brave-Search-Api"},
        )
        assert duplicate_resp.status_code == 409
        assert duplicate_resp.json()["detail"] == "Agent already has active access to 'brave-search-api'"

        revoke_resp = admin_client.post(
            f"/v1/admin/agents/{agent_id}/revoke-access",
            json={"service": "Brave-Search-Api"},
        )
        assert revoke_resp.status_code == 200

        missing_resp = admin_client.post(
            f"/v1/admin/agents/{agent_id}/revoke-access",
            json={"service": "brave-search"},
        )
        assert missing_resp.status_code == 404
        assert missing_resp.json()["detail"] == (
            f"No active access found for agent '{agent_id}' to service 'brave-search-api'"
        )

    def test_rotate_key_route(self, admin_client: TestClient) -> None:
        """POST /v1/admin/agents/{id}/rotate-key returns new key."""
        create_resp = admin_client.post(
            "/v1/admin/agents",
            json={"name": "rotate-route", "organization_id": "org_rot"},
        )
        agent_id = create_resp.json()["agent_id"]
        old_key = create_resp.json()["api_key"]

        rotate_resp = admin_client.post(
            f"/v1/admin/agents/{agent_id}/rotate-key"
        )
        assert rotate_resp.status_code == 200
        data = rotate_resp.json()
        assert data["new_api_key"].startswith("rhumb_")
        assert data["new_api_key"] != old_key

    def test_disable_enable_route(self, admin_client: TestClient) -> None:
        """Disable and re-enable an agent via admin routes."""
        create_resp = admin_client.post(
            "/v1/admin/agents",
            json={"name": "disable-route", "organization_id": "org_dis"},
        )
        agent_id = create_resp.json()["agent_id"]

        # Disable
        dis_resp = admin_client.post(f"/v1/admin/agents/{agent_id}/disable")
        assert dis_resp.status_code == 200

        detail = admin_client.get(f"/v1/admin/agents/{agent_id}")
        assert detail.json()["status"] == "disabled"

        # Enable
        en_resp = admin_client.post(f"/v1/admin/agents/{agent_id}/enable")
        assert en_resp.status_code == 200

        detail2 = admin_client.get(f"/v1/admin/agents/{agent_id}")
        assert detail2.json()["status"] == "active"

    def test_agent_not_found_404(self, admin_client: TestClient) -> None:
        """Non-existent agent returns 404."""
        resp = admin_client.get("/v1/admin/agents/nonexistent-id")
        assert resp.status_code == 404

    def test_duplicate_grant_409(self, admin_client: TestClient) -> None:
        """Duplicate service grant returns 409."""
        create_resp = admin_client.post(
            "/v1/admin/agents",
            json={"name": "dup-grant", "organization_id": "org_dup"},
        )
        agent_id = create_resp.json()["agent_id"]

        # First grant
        admin_client.post(
            f"/v1/admin/agents/{agent_id}/grant-access",
            json={"service": "stripe"},
        )

        # Duplicate
        dup_resp = admin_client.post(
            f"/v1/admin/agents/{agent_id}/grant-access",
            json={"service": "stripe"},
        )
        assert dup_resp.status_code == 409


# ═══════════════════════════════════════════════════════════════════════
# E2E LIFECYCLE TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestE2ELifecycle:
    """End-to-end lifecycle tests combining all modules."""

    def test_full_agent_lifecycle(
        self,
        identity_store: AgentIdentityStore,
        acl: AgentAccessControl,
        rate_checker: AgentRateLimitChecker,
        analytics: AgentUsageAnalytics,
    ) -> None:
        """Complete lifecycle: create → grant → use → track → revoke → rotate."""
        # 1. Admin creates agent
        agent_id, api_key = _run(
            identity_store.register_agent("lifecycle-agent", "org_e2e", rate_limit_qpm=5)
        )
        assert _run(identity_store.verify_api_key(api_key)) == agent_id

        # 2. Grant access to stripe
        _run(identity_store.grant_service_access(agent_id, "stripe"))

        # 3. Verify access
        allowed, _ = _run(acl.can_access_service(agent_id, "stripe"))
        assert allowed is True

        # 4. Rate limit check passes
        rl_result = _run(rate_checker.check_rate_limit(agent_id, "stripe"))
        assert rl_result.allowed is True

        # 5. Record usage
        _run(analytics.record_event(agent_id, "stripe", "success", 42.0))
        summary = _run(analytics.get_usage_summary(agent_id))
        assert summary["total_calls"] == 1

        # 6. Revoke access
        _run(identity_store.revoke_service_access_by_agent_service(agent_id, "stripe"))
        allowed2, reason = _run(acl.can_access_service(agent_id, "stripe"))
        assert allowed2 is False

        # 7. Rotate key
        new_key = _run(identity_store.rotate_api_key(agent_id))
        assert _run(identity_store.verify_api_key(new_key)) == agent_id
        assert _run(identity_store.verify_api_key(api_key)) is None

    def test_multi_tenant_isolation(
        self,
        identity_store: AgentIdentityStore,
        analytics: AgentUsageAnalytics,
    ) -> None:
        """Agents in different orgs have isolated usage."""
        a1, _ = _run(identity_store.register_agent("tenant-a", "org_alpha"))
        a2, _ = _run(identity_store.register_agent("tenant-b", "org_beta"))
        _run(identity_store.grant_service_access(a1, "stripe"))
        _run(identity_store.grant_service_access(a2, "stripe"))

        _run(analytics.record_event(a1, "stripe", "success"))
        _run(analytics.record_event(a1, "stripe", "success"))
        _run(analytics.record_event(a2, "stripe", "success"))

        org_alpha = _run(analytics.get_organization_usage("org_alpha"))
        assert org_alpha["total_calls"] == 2

        org_beta = _run(analytics.get_organization_usage("org_beta"))
        assert org_beta["total_calls"] == 1
