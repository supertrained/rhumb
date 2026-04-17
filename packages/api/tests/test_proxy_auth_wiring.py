"""Tests for GAP-1 proxy auth enforcement wiring.

Covers the five control-plane insertions in proxy_request():
  1. X-Rhumb-Key authentication
  2. ACL check (AgentAccessControl.can_access_service)
  3. Rate limit check (AgentRateLimitChecker.check_rate_limit)
  4. Vault credential injection (AuthInjector.inject)
  5. Usage metering on success and failure paths
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import routes.proxy as proxy_module
from routes.proxy import router as proxy_router
from schemas.agent_identity import (
    AgentIdentityStore,
    reset_identity_store,
)
from services.agent_access_control import AgentAccessControl, reset_agent_access_control
from services.agent_rate_limit import (
    AgentRateLimitChecker,
    AgentRateLimitResult,
    reset_agent_rate_limit_checker,
)
from services.proxy_auth import AuthInjector, AuthMethod
from services.proxy_credentials import CredentialStore
from services.proxy_finalizer import reset_proxy_finalizer
from services.proxy_rate_limit import RateLimiter
from services.usage_metering import UsageMeterEngine, reset_usage_meter_engine


def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singletons() -> Generator[None, None, None]:
    """Reset all proxy-module and service singletons before each test."""
    proxy_module._pool_manager = None
    proxy_module._breaker_registry = None
    proxy_module._latency_tracker = None
    proxy_module._http_client = None
    proxy_module._schema_detector = None
    proxy_module._schema_alert_dispatcher = None
    proxy_module._identity_store = None
    proxy_module._acl_instance = None
    proxy_module._rate_checker_instance = None
    proxy_module._auth_injector_instance = None
    proxy_module._meter_instance = None
    proxy_module._proxy_finalizer = None
    reset_identity_store()
    reset_agent_access_control()
    reset_agent_rate_limit_checker()
    reset_usage_meter_engine()
    reset_proxy_finalizer()
    yield
    proxy_module._pool_manager = None
    proxy_module._breaker_registry = None
    proxy_module._latency_tracker = None
    proxy_module._http_client = None
    proxy_module._schema_detector = None
    proxy_module._schema_alert_dispatcher = None
    proxy_module._identity_store = None
    proxy_module._acl_instance = None
    proxy_module._rate_checker_instance = None
    proxy_module._auth_injector_instance = None
    proxy_module._meter_instance = None
    proxy_module._proxy_finalizer = None
    reset_identity_store()
    reset_agent_access_control()
    reset_agent_rate_limit_checker()
    reset_usage_meter_engine()
    reset_proxy_finalizer()


@pytest.fixture
def identity_store() -> AgentIdentityStore:
    """In-memory identity store."""
    return AgentIdentityStore(supabase_client=None)


@pytest.fixture
def rate_limiter() -> RateLimiter:
    """In-memory rate limiter."""
    return RateLimiter(redis_client=None)


@pytest.fixture
def credential_store() -> CredentialStore:
    """Credential store that does NOT call 1Password on init."""
    return CredentialStore(auto_load=False)


@pytest.fixture
def auth_injector(credential_store: CredentialStore) -> AuthInjector:
    """AuthInjector backed by the test credential store."""
    return AuthInjector(credential_store)


@pytest.fixture
def acl(identity_store: AgentIdentityStore) -> AgentAccessControl:
    return AgentAccessControl(identity_store=identity_store)


@pytest.fixture
def rate_checker(
    identity_store: AgentIdentityStore,
    rate_limiter: RateLimiter,
) -> AgentRateLimitChecker:
    return AgentRateLimitChecker(identity_store=identity_store, rate_limiter=rate_limiter)


@pytest.fixture
def meter(identity_store: AgentIdentityStore) -> UsageMeterEngine:
    return UsageMeterEngine(identity_store=identity_store)


def _register_agent_with_grant(
    identity_store: AgentIdentityStore,
    *,
    agent_name: str = "test-agent",
    service: str = "stripe",
) -> tuple[str, str]:
    """Register an agent and grant it service access.

    Returns (agent_id, raw_api_key).
    """
    agent_id, api_key = _run(identity_store.register_agent(name=agent_name, organization_id="org-test"))
    _run(identity_store.grant_service_access(agent_id, service))
    return agent_id, api_key


class _CountingIdentityStore(AgentIdentityStore):
    def __init__(self) -> None:
        super().__init__(supabase_client=None)
        self.get_agent_calls = 0
        self.get_service_access_calls = 0

    async def get_agent(self, agent_id: str):  # type: ignore[override]
        self.get_agent_calls += 1
        return await super().get_agent(agent_id)

    async def get_service_access(self, agent_id: str, service: str):  # type: ignore[override]
        self.get_service_access_calls += 1
        return await super().get_service_access(agent_id, service)


@pytest.fixture
def registered_agent(
    identity_store: AgentIdentityStore,
) -> tuple[str, str]:
    """Register an agent with a stripe grant. Returns (agent_id, api_key)."""
    return _register_agent_with_grant(identity_store, service="stripe")


@pytest.fixture
def wired_app(
    identity_store: AgentIdentityStore,
    acl: AgentAccessControl,
    rate_checker: AgentRateLimitChecker,
    auth_injector: AuthInjector,
    meter: UsageMeterEngine,
) -> FastAPI:
    """FastAPI app with all control-plane singletons injected."""
    proxy_module._identity_store = identity_store
    proxy_module._acl_instance = acl
    proxy_module._rate_checker_instance = rate_checker
    proxy_module._auth_injector_instance = auth_injector
    proxy_module._meter_instance = meter

    test_app = FastAPI()
    test_app.include_router(proxy_router, prefix="/v1/proxy")
    return test_app


@pytest.fixture
def client(wired_app: FastAPI) -> TestClient:
    return TestClient(wired_app)


# ── Helpers ─────────────────────────────────────────────────────────

PROXY_URL = "/v1/proxy/"
STRIPE_REQUEST = {
    "service": "stripe",
    "method": "GET",
    "path": "/v1/customers",
}

PDL_REQUEST = {
    "service": "PDL",
    "method": "GET",
    "path": "/v1/person/enrich",
}


# ── Tests ───────────────────────────────────────────────────────────


class TestProxyAuthWiring:
    """GAP-1 proxy auth enforcement tests."""

    def test_missing_key_returns_401(self, client: TestClient) -> None:
        """POST /v1/proxy/ with no X-Rhumb-Key header → 401."""
        resp = client.post(PROXY_URL, json=STRIPE_REQUEST)
        assert resp.status_code == 401
        assert "X-Rhumb-Key header required" in resp.json()["detail"]

    def test_invalid_key_returns_401(self, client: TestClient) -> None:
        """POST /v1/proxy/ with a bogus key → 401."""
        resp = client.post(
            PROXY_URL,
            json=STRIPE_REQUEST,
            headers={"X-Rhumb-Key": "rk_bogus_000000"},
        )
        assert resp.status_code == 401
        assert "Invalid or expired" in resp.json()["detail"]

    def test_valid_key_no_service_grant_returns_403(
        self,
        client: TestClient,
        identity_store: AgentIdentityStore,
    ) -> None:
        """Registered agent with no service grant → 403."""
        _agent_id, api_key = _run(identity_store.register_agent(name="no-grant-agent", organization_id="org-test"))

        resp = client.post(
            PROXY_URL,
            json=STRIPE_REQUEST,
            headers={"X-Rhumb-Key": api_key},
        )
        assert resp.status_code == 403
        assert "no access to service" in resp.json()["detail"]

    def test_alias_backed_no_service_grant_returns_canonical_403(
        self,
        client: TestClient,
        identity_store: AgentIdentityStore,
    ) -> None:
        """Alias-backed proxy requests should deny on canonical public service ids."""
        agent_id, api_key = _run(
            identity_store.register_agent(name="no-alias-grant-agent", organization_id="org-test")
        )

        resp = client.post(
            PROXY_URL,
            json=PDL_REQUEST,
            headers={"X-Rhumb-Key": api_key},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == (
            f"Agent '{agent_id}' has no access to service 'people-data-labs'"
        )

    def test_rate_limited_returns_429(
        self,
        client: TestClient,
        identity_store: AgentIdentityStore,
        rate_checker: AgentRateLimitChecker,
    ) -> None:
        """Agent over rate limit → 429."""
        agent_id, api_key = _register_agent_with_grant(identity_store, service="stripe")

        # Monkey-patch rate checker to always deny
        original_check = rate_checker.check_rate_limit_with_context

        async def _deny(agent, access, service: str) -> AgentRateLimitResult:
            return AgentRateLimitResult(
                allowed=False,
                agent_id=agent.agent_id,
                service=service,
                effective_limit_qpm=10,
                remaining=0,
                error="rate_limited",
                retry_after_seconds=30,
            )

        rate_checker.check_rate_limit_with_context = _deny  # type: ignore[assignment]
        try:
            resp = client.post(
                PROXY_URL,
                json=STRIPE_REQUEST,
                headers={"X-Rhumb-Key": api_key},
            )
            assert resp.status_code == 429
            assert "Rate limit exceeded" in resp.json()["detail"]
            assert resp.headers.get("Retry-After") == "30"
        finally:
            rate_checker.check_rate_limit_with_context = original_check  # type: ignore[assignment]

    def test_no_vault_credential_returns_503(
        self,
        client: TestClient,
        identity_store: AgentIdentityStore,
    ) -> None:
        """Valid key + ACL pass, but CredentialStore has no cred → 503."""
        agent_id, api_key = _register_agent_with_grant(identity_store, service="stripe")

        # credential_store was created with auto_load=False, so no creds exist
        resp = client.post(
            PROXY_URL,
            json=STRIPE_REQUEST,
            headers={"X-Rhumb-Key": api_key},
        )
        assert resp.status_code == 503
        assert "Credential unavailable" in resp.json()["detail"]

    def test_valid_request_injects_credential(
        self,
        client: TestClient,
        identity_store: AgentIdentityStore,
        credential_store: CredentialStore,
        httpx_mock,
    ) -> None:
        """Valid key + grant → provider receives vault credential, not caller-supplied."""
        agent_id, api_key = _register_agent_with_grant(identity_store, service="stripe")

        # Seed a credential in the vault
        credential_store.set_credential("stripe", "api_key", "sk_test_vault_secret")

        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={"data": []},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        resp = client.post(
            PROXY_URL,
            json=STRIPE_REQUEST,
            headers={"X-Rhumb-Key": api_key},
        )
        assert resp.status_code == 200

        # Verify the provider received the vault credential
        proxied = httpx_mock.get_request()
        assert proxied is not None
        assert proxied.headers["Authorization"] == "Bearer sk_test_vault_secret"

    def test_metering_effects_land_on_success(
        self,
        client: TestClient,
        identity_store: AgentIdentityStore,
        credential_store: CredentialStore,
        meter: UsageMeterEngine,
        httpx_mock,
    ) -> None:
        """Successful proxy calls still land usage + last_used effects."""
        agent_id, api_key = _register_agent_with_grant(identity_store, service="stripe")
        credential_store.set_credential("stripe", "api_key", "sk_test_123")

        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={"data": []},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        resp = client.post(
            PROXY_URL,
            json=STRIPE_REQUEST,
            headers={"X-Rhumb-Key": api_key},
        )
        assert resp.status_code == 200

        snapshot = _run(meter.get_usage_snapshot(agent_id, "stripe", 1))
        assert snapshot is not None
        assert snapshot.call_count == 1
        assert snapshot.success_count == 1

        access = _run(identity_store.get_service_access(agent_id, "stripe"))
        assert access is not None
        assert access.last_used_result == "success"
        assert access.last_used_at is not None

    def test_metering_effects_land_on_failure(
        self,
        client: TestClient,
        identity_store: AgentIdentityStore,
        credential_store: CredentialStore,
        meter: UsageMeterEngine,
        httpx_mock,
    ) -> None:
        """Failure path still records metering durably/in-memory."""
        agent_id, api_key = _register_agent_with_grant(identity_store, service="stripe")
        credential_store.set_credential("stripe", "api_key", "sk_test_123")

        # Make httpx raise an exception to trigger the error path
        httpx_mock.add_exception(
            Exception("connection reset"),
            method="GET",
            url="https://api.stripe.com/v1/customers",
        )

        resp = client.post(
            PROXY_URL,
            json=STRIPE_REQUEST,
            headers={"X-Rhumb-Key": api_key},
        )
        assert resp.status_code == 500

        snapshot = _run(meter.get_usage_snapshot(agent_id, "stripe", 1))
        assert snapshot is not None
        assert snapshot.call_count == 1
        assert snapshot.failed_count == 1

    def test_proxy_request_dedupes_agent_and_access_reads(
        self,
        client: TestClient,
        credential_store: CredentialStore,
        httpx_mock,
    ) -> None:
        identity_store = _CountingIdentityStore()
        proxy_module._identity_store = identity_store
        proxy_module._acl_instance = AgentAccessControl(identity_store=identity_store)
        proxy_module._rate_checker_instance = AgentRateLimitChecker(
            identity_store=identity_store,
            rate_limiter=RateLimiter(redis_client=None),
        )
        proxy_module._meter_instance = UsageMeterEngine(identity_store=identity_store)

        _agent_id, api_key = _register_agent_with_grant(identity_store, service="stripe")
        credential_store.set_credential("stripe", "api_key", "sk_test_vault_secret")
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={"data": []},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        resp = client.post(
            PROXY_URL,
            json=STRIPE_REQUEST,
            headers={"X-Rhumb-Key": api_key},
        )

        assert resp.status_code == 200
        assert identity_store.get_agent_calls == 0
        assert identity_store.get_service_access_calls == 1

    def test_full_path_timing_log_includes_control_plane_phases(
        self,
        client: TestClient,
        identity_store: AgentIdentityStore,
        credential_store: CredentialStore,
        httpx_mock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _agent_id, api_key = _register_agent_with_grant(identity_store, service="stripe")
        credential_store.set_credential("stripe", "api_key", "sk_test_vault_secret")
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={"data": []},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        caplog.set_level(logging.INFO, logger=proxy_module.logger.name)
        resp = client.post(
            PROXY_URL,
            json=STRIPE_REQUEST,
            headers={"X-Rhumb-Key": api_key},
        )

        assert resp.status_code == 200
        full_path_logs = [
            record.getMessage()
            for record in caplog.records
            if "proxy full-path timings" in record.getMessage()
        ]
        assert full_path_logs
        log_line = full_path_logs[-1]
        assert "auth_ms=" in log_line
        assert "acl_ms=" in log_line
        assert "rate_limit_ms=" in log_line
        assert "total_route_ms=" in log_line
        assert "status_code=200" in log_line
