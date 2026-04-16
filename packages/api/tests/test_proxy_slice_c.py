"""Tests for Round 10 Slice C — Credential injection, agent identity, auth, rate limiting.

    Covers:
      - CredentialStore (load, cache, refresh, expiration, audit)
      - AgentIdentityVerifier (Bearer token, service access, cache)
      - AuthInjector (provider auth patterns, error paths)
  - RateLimiter (sliding window, 429 semantics, fail-open)
  - Integration: full pipeline (auth → inject → rate-limit → proxy)

Target: 20+ tests
"""

from __future__ import annotations

import asyncio
import base64
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas.agent_identity import (
    AgentIdentityVerifier,
    _LegacyAgentIdentitySchema as AgentIdentitySchema,
)
from services.proxy_auth import AuthInjectionRequest, AuthInjector, AuthMethod
from services.proxy_credentials import CredentialEntry, CredentialStore, ProviderCredentials
from services.proxy_rate_limit import RateLimiter, RateLimitStatus


def _utcnow() -> datetime:
    return datetime.now(tz=UTC).replace(tzinfo=None)


# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture
def credential_store() -> CredentialStore:
    """CredentialStore with auto_load disabled (no 1Password calls)."""
    store = CredentialStore(auto_load=False)
    # Seed with test credentials for the provider auth patterns under test.
    store.set_credential("stripe", "api_key", "sk_test_stripe_key_123")
    store.set_credential("slack", "oauth_token", "xoxb-slack-token-456")
    store.set_credential("github", "api_token", "ghp_github_token_789")
    store.set_credential("twilio", "basic_auth", "AC_sid:auth_token_abc")
    store.set_credential("sendgrid", "api_key", "SG.sendgrid_key_xyz")
    store.set_credential("e2b", "api_key", "e2b_test_key_123")
    return store


@pytest.fixture
def auth_injector(credential_store: CredentialStore) -> AuthInjector:
    """AuthInjector wired to the test credential store."""
    return AuthInjector(credential_store)


@pytest.fixture
def rate_limiter() -> RateLimiter:
    """In-memory rate limiter (no Redis)."""
    return RateLimiter(redis_client=None)


@pytest.fixture
def agent_verifier() -> AgentIdentityVerifier:
    """Verifier with pre-cached identities (no Supabase)."""
    verifier = AgentIdentityVerifier(supabase_client=None)
    verifier.cache_identity(
        AgentIdentitySchema(
            agent_id="rhumb-lead",
            operator_id="tom",
            allowed_services=["stripe", "slack", "github", "twilio", "sendgrid"],
            rate_limit_qpm=500,
            api_token="rhumb_lead_token_xyz",
        )
    )
    verifier.cache_identity(
        AgentIdentitySchema(
            agent_id="snowy",
            operator_id="tom",
            allowed_services=["stripe", "slack"],
            rate_limit_qpm=100,
            api_token="snowy_token_def",
        )
    )
    verifier.cache_identity(
        AgentIdentitySchema(
            agent_id="inactive-agent",
            operator_id="tom",
            allowed_services=["stripe"],
            rate_limit_qpm=50,
            api_token="inactive_token",
            is_active=False,
        )
    )
    return verifier


# =====================================================================
# 1. CredentialStore tests
# =====================================================================


class TestCredentialStore:
    """Credential loading, caching, expiration, refresh, and audit."""

    def test_load_stripe_credential(self, credential_store: CredentialStore) -> None:
        """Stripe API key is loaded and retrievable."""
        val = credential_store.get_credential("stripe", "api_key")
        assert val == "sk_test_stripe_key_123"

    def test_load_all_seeded_providers(self, credential_store: CredentialStore) -> None:
        """All seeded provider credentials are present."""
        assert credential_store.get_credential("stripe", "api_key") is not None
        assert credential_store.get_credential("slack", "oauth_token") is not None
        assert credential_store.get_credential("github", "api_token") is not None
        assert credential_store.get_credential("twilio", "basic_auth") is not None
        assert credential_store.get_credential("sendgrid", "api_key") is not None
        assert credential_store.get_credential("e2b", "api_key") is not None

    def test_credential_not_found_unknown_service(
        self, credential_store: CredentialStore
    ) -> None:
        """Unknown service returns None."""
        assert credential_store.get_credential("unknown_svc", "key") is None

    def test_credential_not_found_unknown_key(
        self, credential_store: CredentialStore
    ) -> None:
        """Known service but unknown key returns None."""
        assert credential_store.get_credential("stripe", "nonexistent_key") is None

    def test_credential_expired(self, credential_store: CredentialStore) -> None:
        """Expired credential returns None."""
        past = _utcnow() - timedelta(hours=1)
        credential_store.set_credential("stripe", "api_key", "old_key", expires_at=past)
        assert credential_store.get_credential("stripe", "api_key") is None

    def test_credential_not_expired(self, credential_store: CredentialStore) -> None:
        """Credential within TTL is returned."""
        future = _utcnow() + timedelta(hours=1)
        credential_store.set_credential("stripe", "api_key", "fresh_key", expires_at=future)
        assert credential_store.get_credential("stripe", "api_key") == "fresh_key"

    @pytest.mark.asyncio
    async def test_credential_refresh_when_stale(
        self, credential_store: CredentialStore
    ) -> None:
        """Stale provider triggers a refresh (force last_refreshed into the past)."""
        credential_store.set_credential("stripe", "api_key", "original", ttl_minutes=1)
        # Force staleness by backdating last_refreshed
        credential_store._cache["stripe"].last_refreshed = _utcnow() - timedelta(hours=1)
        with patch.object(credential_store, "_load_service") as mock_load:
            await credential_store.refresh_if_stale("stripe")
            mock_load.assert_called_once_with("stripe")

    @pytest.mark.asyncio
    async def test_credential_no_refresh_when_fresh(
        self, credential_store: CredentialStore
    ) -> None:
        """Fresh credentials skip the refresh call."""
        with patch.object(credential_store, "_load_service") as mock_load:
            await credential_store.refresh_if_stale("stripe")
            mock_load.assert_not_called()

    def test_audit_log_written(self, credential_store: CredentialStore) -> None:
        """Audit entries are recorded on credential usage."""
        credential_store.audit_log("stripe", "rhumb-lead", "used")
        credential_store.audit_log("slack", "rhumb-lead", "auth_injected")
        entries = credential_store.audit_entries
        assert len(entries) == 2
        assert entries[0]["service"] == "stripe"
        assert entries[0]["agent_id"] == "rhumb-lead"
        assert entries[1]["action"] == "auth_injected"


# =====================================================================
# 2. AgentIdentityVerifier tests
# =====================================================================


class TestAgentIdentityVerifier:
    """Bearer token verification and service access control."""

    @pytest.mark.asyncio
    async def test_verify_bearer_token_valid(
        self, agent_verifier: AgentIdentityVerifier
    ) -> None:
        """Valid token returns the correct identity."""
        identity = await agent_verifier.verify_bearer_token("rhumb_lead_token_xyz")
        assert identity is not None
        assert identity.agent_id == "rhumb-lead"
        assert identity.rate_limit_qpm == 500

    @pytest.mark.asyncio
    async def test_verify_bearer_token_invalid(
        self, agent_verifier: AgentIdentityVerifier
    ) -> None:
        """Invalid token returns None."""
        identity = await agent_verifier.verify_bearer_token("totally_bogus_token")
        assert identity is None

    @pytest.mark.asyncio
    async def test_verify_bearer_token_inactive_agent(
        self, agent_verifier: AgentIdentityVerifier
    ) -> None:
        """Token for an inactive agent returns None."""
        identity = await agent_verifier.verify_bearer_token("inactive_token")
        assert identity is None

    @pytest.mark.asyncio
    async def test_verify_service_access_allowed(
        self, agent_verifier: AgentIdentityVerifier
    ) -> None:
        """Agent with access to the service returns True."""
        assert await agent_verifier.verify_service_access("rhumb-lead", "stripe") is True
        assert await agent_verifier.verify_service_access("rhumb-lead", "twilio") is True

    @pytest.mark.asyncio
    async def test_verify_service_access_denied(
        self, agent_verifier: AgentIdentityVerifier
    ) -> None:
        """Agent without access returns False."""
        # snowy only has stripe + slack
        assert await agent_verifier.verify_service_access("snowy", "github") is False
        assert await agent_verifier.verify_service_access("snowy", "twilio") is False

    @pytest.mark.asyncio
    async def test_cache_hit(
        self, agent_verifier: AgentIdentityVerifier
    ) -> None:
        """Subsequent lookups use the cache (no Supabase call)."""
        id1 = await agent_verifier.verify_bearer_token("rhumb_lead_token_xyz")
        id2 = await agent_verifier.verify_bearer_token("rhumb_lead_token_xyz")
        assert id1 is id2  # Same object reference = cache hit


# =====================================================================
# 3. AuthInjector tests
# =====================================================================


class TestAuthInjector:
    """Auth header injection for all 5 providers + error paths."""

    def test_inject_stripe_api_key(self, auth_injector: AuthInjector) -> None:
        """Stripe gets Bearer header with API key."""
        req = AuthInjectionRequest(
            service="stripe",
            agent_id="rhumb-lead",
            auth_method=AuthMethod.API_KEY,
            existing_headers={"Content-Type": "application/json"},
        )
        headers = auth_injector.inject(req)
        assert headers["Authorization"] == "Bearer sk_test_stripe_key_123"
        assert headers["Content-Type"] == "application/json"  # preserved

    def test_inject_slack_oauth_token(self, auth_injector: AuthInjector) -> None:
        """Slack gets Bearer header with OAuth token."""
        req = AuthInjectionRequest(
            service="slack",
            agent_id="rhumb-lead",
            auth_method=AuthMethod.OAUTH_TOKEN,
        )
        headers = auth_injector.inject(req)
        assert headers["Authorization"] == "Bearer xoxb-slack-token-456"

    def test_inject_github_api_token(self, auth_injector: AuthInjector) -> None:
        """GitHub gets Bearer header with personal access token."""
        req = AuthInjectionRequest(
            service="github",
            agent_id="rhumb-lead",
            auth_method=AuthMethod.API_TOKEN,
        )
        headers = auth_injector.inject(req)
        assert headers["Authorization"] == "Bearer ghp_github_token_789"

    def test_inject_twilio_basic_auth(self, auth_injector: AuthInjector) -> None:
        """Twilio gets Basic auth with base64-encoded sid:token."""
        req = AuthInjectionRequest(
            service="twilio",
            agent_id="rhumb-lead",
            auth_method=AuthMethod.BASIC_AUTH,
        )
        headers = auth_injector.inject(req)
        expected_b64 = base64.b64encode(b"AC_sid:auth_token_abc").decode()
        assert headers["Authorization"] == f"Basic {expected_b64}"

    def test_inject_sendgrid_api_key(self, auth_injector: AuthInjector) -> None:
        """SendGrid gets Bearer header with API key."""
        req = AuthInjectionRequest(
            service="sendgrid",
            agent_id="rhumb-lead",
            auth_method=AuthMethod.API_KEY,
        )
        headers = auth_injector.inject(req)
        assert headers["Authorization"] == "Bearer SG.sendgrid_key_xyz"

    def test_inject_brave_search_api_key(
        self,
        credential_store: CredentialStore,
        auth_injector: AuthInjector,
    ) -> None:
        """Brave Search gets the provider-native X-Subscription-Token header."""
        credential_store.set_credential("brave-search", "api_key", "brave_test_key_123")
        req = AuthInjectionRequest(
            service="brave-search",
            agent_id="rhumb-lead",
            auth_method=AuthMethod.API_KEY,
        )
        headers = auth_injector.inject(req)
        assert headers["X-Subscription-Token"] == "brave_test_key_123"
        assert "Authorization" not in headers

    def test_inject_unsupported_service(self, auth_injector: AuthInjector) -> None:
        """Unknown service raises ValueError."""
        req = AuthInjectionRequest(
            service="unknown_provider",
            agent_id="rhumb-lead",
            auth_method=AuthMethod.API_KEY,
        )
        with pytest.raises(ValueError, match="not supported"):
            auth_injector.inject(req)

    def test_inject_unsupported_method(self, auth_injector: AuthInjector) -> None:
        """Unsupported auth method for a known service raises ValueError."""
        req = AuthInjectionRequest(
            service="stripe",
            agent_id="rhumb-lead",
            auth_method=AuthMethod.BASIC_AUTH,  # stripe doesn't support basic
        )
        with pytest.raises(ValueError, match="not supported for"):
            auth_injector.inject(req)

    def test_inject_credential_not_found(self) -> None:
        """Missing credential raises RuntimeError."""
        empty_store = CredentialStore(auto_load=False)
        injector = AuthInjector(empty_store)
        req = AuthInjectionRequest(
            service="stripe",
            agent_id="rhumb-lead",
            auth_method=AuthMethod.API_KEY,
        )
        with pytest.raises(RuntimeError, match="Credential not found"):
            injector.inject(req)

    def test_inject_preserves_existing_headers(self, auth_injector: AuthInjector) -> None:
        """Existing headers are preserved; Authorization is added."""
        req = AuthInjectionRequest(
            service="stripe",
            agent_id="rhumb-lead",
            auth_method=AuthMethod.API_KEY,
            existing_headers={"X-Custom": "keep-me", "Accept": "application/json"},
        )
        headers = auth_injector.inject(req)
        assert headers["X-Custom"] == "keep-me"
        assert headers["Accept"] == "application/json"
        assert "Authorization" in headers

    def test_inject_e2b_api_key_header(self, auth_injector: AuthInjector) -> None:
        """E2B uses X-API-Key instead of Authorization."""
        req = AuthInjectionRequest(
            service="e2b",
            agent_id="rhumb-lead",
            auth_method=AuthMethod.API_KEY,
            existing_headers={"Accept": "application/json"},
        )
        headers = auth_injector.inject(req)
        assert headers["Accept"] == "application/json"
        assert headers["X-API-Key"] == "e2b_test_key_123"
        assert "Authorization" not in headers

    def test_inject_writes_audit_entry(
        self, credential_store: CredentialStore, auth_injector: AuthInjector
    ) -> None:
        """Auth injection records an audit entry."""
        req = AuthInjectionRequest(
            service="stripe",
            agent_id="rhumb-lead",
            auth_method=AuthMethod.API_KEY,
        )
        auth_injector.inject(req)
        entries = credential_store.audit_entries
        assert len(entries) == 1
        assert entries[0]["action"] == "auth_injected"
        assert entries[0]["agent_id"] == "rhumb-lead"

    def test_default_method_for_service(self) -> None:
        """default_method_for returns the primary auth method for each provider."""
        assert AuthInjector.default_method_for("stripe") == AuthMethod.API_KEY
        assert AuthInjector.default_method_for("slack") == AuthMethod.OAUTH_TOKEN
        assert AuthInjector.default_method_for("github") == AuthMethod.API_TOKEN
        assert AuthInjector.default_method_for("twilio") == AuthMethod.BASIC_AUTH
        assert AuthInjector.default_method_for("sendgrid") == AuthMethod.API_KEY
        assert AuthInjector.default_method_for("brave-search") == AuthMethod.API_KEY
        assert AuthInjector.default_method_for("e2b") == AuthMethod.API_KEY
        assert AuthInjector.default_method_for("nonexistent") is None


# =====================================================================
# 4. RateLimiter tests
# =====================================================================


class TestRateLimiter:
    """Sliding-window rate limiting with in-memory fallback."""

    @pytest.mark.asyncio
    async def test_allow_under_limit(self, rate_limiter: RateLimiter) -> None:
        """Requests under the limit are allowed."""
        allowed, status = await rate_limiter.check_rate_limit("agent-a", "stripe", 100)
        assert allowed is True
        # remaining reflects the count *before* this request is recorded
        assert status.remaining == 100
        assert status.is_limited is False

        # After recording, the next check should show 99
        allowed2, status2 = await rate_limiter.check_rate_limit("agent-a", "stripe", 100)
        assert allowed2 is True
        assert status2.remaining == 99

    @pytest.mark.asyncio
    async def test_deny_over_limit(self, rate_limiter: RateLimiter) -> None:
        """Requests over the limit are denied."""
        # Exhaust the limit
        for _ in range(5):
            await rate_limiter.check_rate_limit("agent-b", "stripe", 5)

        allowed, status = await rate_limiter.check_rate_limit("agent-b", "stripe", 5)
        assert allowed is False
        assert status.remaining == 0
        assert status.is_limited is True

    @pytest.mark.asyncio
    async def test_rate_limit_per_service_isolation(self, rate_limiter: RateLimiter) -> None:
        """Rate limits are per-service — exhausting one doesn't affect another."""
        # Exhaust stripe
        for _ in range(3):
            await rate_limiter.check_rate_limit("agent-c", "stripe", 3)
        allowed_stripe, _ = await rate_limiter.check_rate_limit("agent-c", "stripe", 3)
        assert allowed_stripe is False

        # slack should still be open (remaining = 3 because 0 prior requests on slack)
        allowed_slack, status = await rate_limiter.check_rate_limit("agent-c", "slack", 3)
        assert allowed_slack is True
        assert status.remaining == 3

    @pytest.mark.asyncio
    async def test_rate_limit_per_agent_isolation(self, rate_limiter: RateLimiter) -> None:
        """Rate limits are per-agent — one agent's usage doesn't affect another."""
        for _ in range(5):
            await rate_limiter.check_rate_limit("agent-d", "stripe", 5)
        blocked, _ = await rate_limiter.check_rate_limit("agent-d", "stripe", 5)
        assert blocked is False

        # Different agent is fine
        allowed, status = await rate_limiter.check_rate_limit("agent-e", "stripe", 5)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_rate_limit_headers_429_semantics(self, rate_limiter: RateLimiter) -> None:
        """Denied requests produce correct values for 429 response headers."""
        for _ in range(2):
            await rate_limiter.check_rate_limit("agent-f", "stripe", 2)

        _, status = await rate_limiter.check_rate_limit("agent-f", "stripe", 2)
        assert status.is_limited is True
        assert status.limit == 2
        assert status.remaining == 0
        # reset_at should be in the future (within ~60s)
        assert status.reset_at > datetime.now(tz=UTC) - timedelta(seconds=5)

    @pytest.mark.asyncio
    async def test_redis_failure_fail_open(self) -> None:
        """When Redis raises an exception, requests are still allowed (fail-open)."""

        class BrokenRedis:
            async def zcount(self, *a: Any, **kw: Any) -> int:
                raise ConnectionError("Redis down")

            async def zadd(self, *a: Any, **kw: Any) -> None:
                raise ConnectionError("Redis down")

            async def expire(self, *a: Any, **kw: Any) -> None:
                raise ConnectionError("Redis down")

        limiter = RateLimiter(redis_client=BrokenRedis())
        allowed, status = await limiter.check_rate_limit("agent-g", "stripe", 10)
        assert allowed is True  # fail-open


# =====================================================================
# 5. Integration tests — full pipeline
# =====================================================================


class TestSliceCIntegration:
    """End-to-end: agent authenticates → service access → auth injection → rate limit."""

    @pytest.mark.asyncio
    async def test_e2e_agent_authenticates_and_accesses_stripe(
        self,
        agent_verifier: AgentIdentityVerifier,
        credential_store: CredentialStore,
        rate_limiter: RateLimiter,
    ) -> None:
        """Full pipeline: Bearer verified → service allowed → cred injected → under rate limit."""
        # Step 1: Verify bearer
        identity = await agent_verifier.verify_bearer_token("rhumb_lead_token_xyz")
        assert identity is not None

        # Step 2: Service access
        allowed = await agent_verifier.verify_service_access(identity.agent_id, "stripe")
        assert allowed is True

        # Step 3: Auth injection
        injector = AuthInjector(credential_store)
        method = AuthInjector.default_method_for("stripe")
        assert method is not None
        headers = injector.inject(
            AuthInjectionRequest(
                service="stripe",
                agent_id=identity.agent_id,
                auth_method=method,
            )
        )
        assert "Authorization" in headers

        # Step 4: Rate limit
        ok, status = await rate_limiter.check_rate_limit(
            identity.agent_id, "stripe", identity.rate_limit_qpm
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_e2e_agent_denied_unauthorized_service(
        self,
        agent_verifier: AgentIdentityVerifier,
    ) -> None:
        """Agent attempts access to a service not in its allowed list → denied."""
        identity = await agent_verifier.verify_bearer_token("snowy_token_def")
        assert identity is not None

        # snowy doesn't have github
        allowed = await agent_verifier.verify_service_access(identity.agent_id, "github")
        assert allowed is False

    @pytest.mark.asyncio
    async def test_e2e_agent_hits_rate_limit(
        self,
        agent_verifier: AgentIdentityVerifier,
        rate_limiter: RateLimiter,
    ) -> None:
        """Agent exceeds QPM → 429 with Retry-After semantics."""
        identity = await agent_verifier.verify_bearer_token("snowy_token_def")
        assert identity is not None

        # Exhaust snowy's 100 QPM
        for _ in range(identity.rate_limit_qpm):
            ok, _ = await rate_limiter.check_rate_limit(
                identity.agent_id, "stripe", identity.rate_limit_qpm
            )
            assert ok is True

        # 101st request
        ok, status = await rate_limiter.check_rate_limit(
            identity.agent_id, "stripe", identity.rate_limit_qpm
        )
        assert ok is False
        assert status.is_limited is True
        assert status.remaining == 0

        # Verify Retry-After semantics
        retry_after = (status.reset_at - datetime.now(tz=UTC)).total_seconds()
        assert retry_after > -1  # reset is roughly now or in the near future

    @pytest.mark.asyncio
    async def test_e2e_credential_refresh_on_stale(
        self, credential_store: CredentialStore
    ) -> None:
        """Stale credentials trigger a refresh before the next request."""
        credential_store.set_credential("stripe", "api_key", "old_key", ttl_minutes=1)
        # Force staleness
        credential_store._cache["stripe"].last_refreshed = _utcnow() - timedelta(hours=1)
        with patch.object(credential_store, "_load_service") as mock:
            await credential_store.refresh_if_stale("stripe")
            mock.assert_called_once_with("stripe")

    @pytest.mark.asyncio
    async def test_e2e_audit_trail(
        self,
        credential_store: CredentialStore,
    ) -> None:
        """Audit entries are produced for credential usage and auth injection."""
        injector = AuthInjector(credential_store)
        injector.inject(
            AuthInjectionRequest(
                service="stripe",
                agent_id="rhumb-lead",
                auth_method=AuthMethod.API_KEY,
            )
        )
        injector.inject(
            AuthInjectionRequest(
                service="slack",
                agent_id="rhumb-lead",
                auth_method=AuthMethod.OAUTH_TOKEN,
            )
        )

        entries = credential_store.audit_entries
        assert len(entries) == 2
        services_logged = {e["service"] for e in entries}
        assert services_logged == {"stripe", "slack"}
