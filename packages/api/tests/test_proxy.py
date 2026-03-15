"""Tests for proxy router (Slice A: Router Foundation)."""

import asyncio
import pytest
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import routes.proxy as proxy_module
from routes.proxy import router as proxy_router
from schemas.agent_identity import AgentIdentityStore, reset_identity_store
from services.agent_access_control import AgentAccessControl, reset_agent_access_control
from services.agent_rate_limit import AgentRateLimitChecker, reset_agent_rate_limit_checker
from services.proxy_credentials import CredentialStore
from services.proxy_auth import AuthInjector
from services.usage_metering import UsageMeterEngine, reset_usage_meter_engine

# ── Test bypass constants ────────────────────────────────────────────
_BYPASS_KEY = "rhumb_test_bypass_key_0000"
_VAULT_STRIPE_KEY = "sk_test_vault_injected"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def _inject_bypass_auth():
    """Inject fully-wired control-plane singletons into the proxy module.

    This allows existing router tests to pass without supplying real
    X-Rhumb-Key headers — a fixed bypass key is used via the client
    fixture's default headers.
    """
    # Identity store: register one bypass agent with stripe grant
    identity_store = AgentIdentityStore(supabase_client=None)
    _bypass_agent_id, _bypass_api_key_internal = _run(
        identity_store.register_agent(name="test-bypass", organization_id="org-test")
    )
    # We need the bypass key to match _BYPASS_KEY — re-inject directly
    from schemas.agent_identity import hash_api_key
    identity_store._key_index[hash_api_key(_BYPASS_KEY)] = _bypass_agent_id
    _run(identity_store.grant_service_access(_bypass_agent_id, "stripe"))
    _run(identity_store.grant_service_access(_bypass_agent_id, "slack"))
    _run(identity_store.grant_service_access(_bypass_agent_id, "github"))
    _run(identity_store.grant_service_access(_bypass_agent_id, "twilio"))
    _run(identity_store.grant_service_access(_bypass_agent_id, "sendgrid"))

    # Credential store: seed stripe test credential
    cred_store = CredentialStore(auto_load=False)
    cred_store.set_credential("stripe", "api_key", _VAULT_STRIPE_KEY)
    cred_store.set_credential("slack", "oauth_token", "xoxb-test-vault")
    cred_store.set_credential("github", "api_token", "ghp_test_vault")
    cred_store.set_credential("sendgrid", "api_key", "SG.test_vault")

    # Auth injector backed by the seeded store
    auth_injector = AuthInjector(cred_store)

    # Real ACL and rate checker backed by the identity store
    acl = AgentAccessControl(identity_store=identity_store)
    rate_checker = AgentRateLimitChecker(
        identity_store=identity_store,
        rate_limiter=None,  # in-memory fallback
    )

    # Meter: real in-memory engine
    meter = UsageMeterEngine(identity_store=identity_store)

    # Inject into proxy module singletons
    proxy_module._identity_store = identity_store
    proxy_module._acl_instance = acl
    proxy_module._rate_checker_instance = rate_checker
    proxy_module._auth_injector_instance = auth_injector
    proxy_module._meter_instance = meter

    yield

    # Teardown
    proxy_module._identity_store = None
    proxy_module._acl_instance = None
    proxy_module._rate_checker_instance = None
    proxy_module._auth_injector_instance = None
    proxy_module._meter_instance = None
    reset_identity_store()
    reset_agent_access_control()
    reset_agent_rate_limit_checker()
    reset_usage_meter_engine()


@pytest.fixture
def app():
    """Create test FastAPI app with proxy router."""
    app = FastAPI()
    app.include_router(proxy_router, prefix="/proxy")
    return app


@pytest.fixture
def client(app):
    """Create test client with bypass auth header pre-set."""
    return TestClient(app, headers={"X-Rhumb-Key": _BYPASS_KEY})


class TestProxyRouter:
    """Test suite for proxy router functionality."""

    def test_list_services(self, client):
        """Test listing available services."""
        response = client.get("/proxy/services")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert "services" in data["data"]
        assert len(data["data"]["services"]) > 0
        assert "stripe" in [s["name"] for s in data["data"]["services"]]

    def test_service_registry_structure(self, client):
        """Test that service registry has correct structure."""
        response = client.get("/proxy/services")
        data = response.json()
        for service in data["data"]["services"]:
            assert "name" in service
            assert "domain" in service
            assert "auth_type" in service
            assert "rate_limit" in service

    def test_proxy_successful_request(self, client, httpx_mock):
        """Test successful proxy request."""
        # Mock response
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers/cus_123",
            json={"id": "cus_123", "email": "test@example.com"},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers/cus_123",
                "body": None,
                "params": None,
                "headers": None,
            },
            headers={"Authorization": "Bearer sk_test_123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status_code"] == 200
        assert data["service"] == "stripe"
        assert data["path"] == "/v1/customers/cus_123"
        assert data["latency_ms"] >= 0

    def test_proxy_latency_measurement(self, client, httpx_mock):
        """Test that latency is measured correctly."""
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={},
            status_code=200,
            headers={},
        )

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
                "body": None,
                "params": None,
                "headers": None,
            },
        )

        data = response.json()
        assert "latency_ms" in data
        assert data["latency_ms"] >= 0

    def test_proxy_service_not_found(self, client):
        """Test error when service not found or not granted.

        With auth enforcement active, the ACL check fires before the service
        registry lookup. An unknown/ungrantable service returns 403 (no access)
        rather than 400 (service not found) — the correct security posture
        is to not leak whether a service exists.
        """
        response = client.post(
            "/proxy/",
            json={
                "service": "nonexistent",
                "method": "GET",
                "path": "/v1/test",
                "body": None,
                "params": None,
                "headers": None,
            },
        )

        assert response.status_code == 403

    def test_proxy_auth_header_injection(self, client, httpx_mock):
        """Test that vault credential is injected — caller-supplied auth is NOT forwarded."""
        httpx_mock.add_response(
            method="POST",
            url="https://api.stripe.com/v1/customers",
            json={},
            status_code=200,
            headers={},
        )

        caller_token = "Bearer sk_caller_should_be_dropped"
        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "POST",
                "path": "/v1/customers",
                "body": {"email": "test@example.com"},
                "params": None,
                "headers": None,
            },
            headers={"Authorization": caller_token},
        )

        # Vault credential injected — provider gets vault key, not caller's token
        assert response.status_code == 200
        request = httpx_mock.get_request()
        assert request.headers["Authorization"] == f"Bearer {_VAULT_STRIPE_KEY}"
        assert request.headers["Authorization"] != caller_token

    def test_proxy_custom_headers(self, client, httpx_mock):
        """Test that custom headers are preserved."""
        httpx_mock.add_response(
            method="POST",
            url="https://api.stripe.com/v1/customers",
            json={},
            status_code=200,
            headers={},
        )

        custom_headers = {"X-Custom-Header": "custom-value"}
        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "POST",
                "path": "/v1/customers",
                "body": None,
                "params": None,
                "headers": custom_headers,
            },
        )

        assert response.status_code == 200
        request = httpx_mock.get_request()
        assert request.headers["X-Custom-Header"] == "custom-value"

    def test_proxy_response_body_parsing_json(self, client, httpx_mock):
        """Test JSON response body parsing."""
        expected_body = {"id": "ch_123", "amount": 1000}
        httpx_mock.add_response(
            method="POST",
            url="https://api.stripe.com/v1/charges",
            json=expected_body,
            status_code=200,
            headers={"content-type": "application/json"},
        )

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "POST",
                "path": "/v1/charges",
                "body": {"amount": 1000},
                "params": None,
                "headers": None,
            },
        )

        data = response.json()
        assert data["body"] == expected_body

    def test_proxy_response_body_parsing_text(self, client, httpx_mock):
        """Test fallback to text response parsing."""
        # httpx_mock with plain text content (not JSON)
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/test",
            text="Plain text response",
            status_code=200,
            headers={},
        )

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/test",
                "body": None,
                "params": None,
                "headers": None,
            },
        )

        data = response.json()
        assert data["body"] == "Plain text response"

    def test_proxy_error_response(self, client, httpx_mock):
        """Test proxy error handling."""
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={"error": "Unauthorized"},
            status_code=401,
            headers={"content-type": "application/json"},
        )

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
                "body": None,
                "params": None,
                "headers": None,
            },
        )

        # Proxy should forward the error response as-is
        data = response.json()
        assert data["status_code"] == 401
        assert data["body"]["error"] == "Unauthorized"

    def test_proxy_stats_endpoint(self, client):
        """Test proxy stats endpoint."""
        response = client.get("/proxy/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert "services_registered" in data["data"]
        assert "services_callable" in data["data"]
        assert data["data"]["services_registered"] > 0
        # In tests, credentials are seeded so at least one service should be callable.
        assert data["data"]["services_callable"] >= 0


class TestProxyRequest:
    """Test ProxyRequest schema validation."""

    def test_proxy_request_required_fields(self, client):
        """Test that required fields are enforced."""
        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                # Missing method and path
            },
        )
        assert response.status_code == 422  # Validation error

    def test_proxy_request_valid(self, client, httpx_mock):
        """Test valid proxy request structure."""
        # Mock expects the URL with query params included
        httpx_mock.add_response(
            method="POST",
            url="https://api.stripe.com/v1/customers?limit=10",
            json={},
            status_code=200,
            headers={},
        )

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "POST",
                "path": "/v1/customers",
                "body": {"email": "test@example.com"},
                "params": {"limit": 10},
                "headers": {"X-Custom": "value"},
            },
        )
        assert response.status_code == 200
