"""Tests for capability execute routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.agent_identity import AgentIdentitySchema

FAKE_RHUMB_KEY = "rhumb_test_key_cap_exec"


def _mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_cap_exec_test",
        name="cap-exec-test",
        organization_id="org_cap_exec_test",
    )


@pytest.fixture
def app():
    """Create test app with lifespan disabled."""
    return create_app()


@pytest.fixture(autouse=True)
def _mock_identity_store():
    """Bypass API key verification for execute/estimate route tests."""
    mock_store = MagicMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with patch("routes.capability_execute._get_identity_store", return_value=mock_store):
        yield mock_store


# ── Sample data ─────────────────────────────────────────────

SAMPLE_CAP = [
    {"id": "email.send", "domain": "email", "action": "send",
     "description": "Send transactional email"},
]

SAMPLE_MAPPINGS = [
    {"service_slug": "sendgrid", "credential_modes": ["byo"],
     "auth_method": "api_key", "endpoint_pattern": "POST /v3/mail/send",
     "cost_per_call": "0.01", "cost_currency": "USD", "free_tier_calls": 100},
    {"service_slug": "resend", "credential_modes": ["byo"],
     "auth_method": "api_key", "endpoint_pattern": "POST /emails",
     "cost_per_call": None, "cost_currency": "USD", "free_tier_calls": 100},
]

SAMPLE_SCORES = [
    {"service_slug": "resend", "aggregate_recommendation_score": 7.79},
    {"service_slug": "sendgrid", "aggregate_recommendation_score": 6.35},
]

SAMPLE_SERVICE_DOMAIN = [
    {"slug": "sendgrid", "api_domain": "api.sendgrid.com"},
    {"slug": "resend", "api_domain": "api.resend.com"},
]


def _mock_supabase(path: str):
    """Route supabase_fetch calls to sample data."""
    if path.startswith("capabilities?"):
        if "id=eq.email.send" in path:
            return SAMPLE_CAP
        if "id=eq.nonexistent" in path:
            return []
        return SAMPLE_CAP
    if path.startswith("capability_services?"):
        if "capability_id=eq.email.send" in path:
            return SAMPLE_MAPPINGS
        if "capability_id=eq.nonexistent" in path:
            return []
        return SAMPLE_MAPPINGS
    if path.startswith("scores?"):
        return SAMPLE_SCORES
    if path.startswith("services?"):
        if "slug=eq.sendgrid" in path:
            return [SAMPLE_SERVICE_DOMAIN[0]]
        if "slug=eq.resend" in path:
            return [SAMPLE_SERVICE_DOMAIN[1]]
        return SAMPLE_SERVICE_DOMAIN
    if path.startswith("capability_executions?"):
        # Default: no existing execution (idempotency check)
        return []
    return []


def _mock_supabase_with_existing_exec(path: str):
    """Same as _mock_supabase but returns an existing execution for idempotency check."""
    if path.startswith("capability_executions?"):
        return [{"id": "exec_existing123", "upstream_status": 202, "cost_estimate_usd": 0.01}]
    return _mock_supabase(path)


def _make_mock_response(status_code: int = 202, json_body: dict | None = None):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body or {"message": "accepted"}
    resp.text = '{"message": "accepted"}'
    return resp


def _build_patches():
    """Return common patches used across tests."""
    mock_response = _make_mock_response()

    # Mock pool manager: acquire returns a mock client, release is a no-op
    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response

    mock_pool = MagicMock()
    mock_pool.acquire = AsyncMock(return_value=mock_client)
    mock_pool.release = AsyncMock()

    return mock_response, mock_pool


# ── Tests ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_execute_explicit_provider(app):
    """POST /v1/capabilities/email.send/execute with explicit provider proxies correctly."""
    _, mock_pool = _build_patches()

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True) as mock_insert,
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "provider": "sendgrid",
                    "method": "POST",
                    "path": "/v3/mail/send",
                    "body": {"to": "test@example.com"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["capability_id"] == "email.send"
    assert data["provider_used"] == "sendgrid"
    assert data["upstream_status"] == 202
    assert data["cost_estimate_usd"] == 0.01
    assert data["execution_id"].startswith("exec_")
    assert data["fallback_attempted"] is False
    assert resp.json()["error"] is None


@pytest.mark.anyio
async def test_unknown_capability_returns_404_before_payment_flow(app):
    """Unknown capabilities should return 404 before any x402/payment flow."""
    with patch(
        "routes.capability_execute.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/nonexistent/execute",
                json={},
                headers={"X-Request-ID": "req-capability-404"},
            )

    assert resp.status_code == 404
    assert resp.json() == {
        "error": "capability_not_found",
        "message": "No capability found with id 'nonexistent'",
        "resolution": (
            "Browse capabilities at GET /v1/capabilities or use "
            "discover_capabilities MCP tool"
        ),
        "request_id": "req-capability-404",
    }


@pytest.mark.anyio
async def test_billable_execution_checks_billing_health_before_execute(app):
    """Billable execution proceeds when billing health check succeeds."""
    _, mock_pool = _build_patches()

    with (
        patch("routes.capability_execute.check_billing_health", new_callable=AsyncMock, return_value=(True, "ok")) as mock_billing_health,
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "provider": "sendgrid",
                    "method": "POST",
                    "path": "/v3/mail/send",
                    "body": {"to": "test@example.com"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    mock_billing_health.assert_awaited_once()
    mock_pool.acquire.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("billing_reason", ["timeout", "connection_error"])
async def test_billable_execution_blocks_when_billing_health_fails(app, billing_reason):
    """Billable execution returns 503 and does not execute when billing is unavailable."""
    _, mock_pool = _build_patches()

    with (
        patch("routes.capability_execute.check_billing_health", new_callable=AsyncMock, return_value=(False, billing_reason)),
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True) as mock_insert,
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "provider": "sendgrid",
                    "method": "POST",
                    "path": "/v3/mail/send",
                    "body": {"to": "test@example.com"},
                },
                headers={
                    "X-Rhumb-Key": FAKE_RHUMB_KEY,
                    "X-Request-ID": f"req-{billing_reason}",
                },
            )

    assert resp.status_code == 503
    assert resp.json() == {
        "error": "billing_unavailable",
        "message": "Billing system temporarily unavailable. Execution blocked for safety.",
        "resolution": "Retry in 30 seconds. If persistent, check https://rhumb.dev/status",
        "request_id": f"req-{billing_reason}",
    }
    mock_pool.acquire.assert_not_awaited()
    mock_insert.assert_not_awaited()


@pytest.mark.anyio
async def test_execute_auto_select_provider(app):
    """POST execute without provider auto-selects best by AN score."""
    _, mock_pool = _build_patches()

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        # resend is NOT in SERVICE_REGISTRY, so it takes the httpx.AsyncClient path
        patch("httpx.AsyncClient") as MockHttpxClient,
    ):
        mock_ctx = AsyncMock()
        mock_ctx.request.return_value = _make_mock_response()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        MockHttpxClient.return_value = mock_ctx

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "method": "POST",
                    "path": "/emails",
                    "body": {"to": "test@example.com"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    # resend has higher AN score (7.79 vs 6.35) so auto-select picks it
    assert data["provider_used"] == "resend"


@pytest.mark.anyio
async def test_execute_unknown_capability(app):
    """POST execute with unknown capability returns 404."""
    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/nonexistent/execute",
                json={"method": "POST", "path": "/foo", "body": {}},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 404
    body = resp.json()
    assert body == {
        "error": "capability_not_found",
        "message": "No capability found with id 'nonexistent'",
        "resolution": (
            "Browse capabilities at GET /v1/capabilities or use "
            "discover_capabilities MCP tool"
        ),
        "request_id": body["request_id"],
    }


@pytest.mark.anyio
async def test_execute_unavailable_provider(app):
    """POST execute with open circuit returns 503."""
    from services.proxy_breaker import BreakerRegistry, BreakerState

    broken_registry = BreakerRegistry()
    breaker = broken_registry.get("sendgrid", "agent_cap_exec_test")
    # Force circuit open
    for _ in range(10):
        breaker.record_failure(status_code=500)

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.get_breaker_registry", return_value=broken_registry),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "provider": "sendgrid",
                    "method": "POST",
                    "path": "/v3/mail/send",
                    "body": {},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    assert "circuit" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_estimate_endpoint(app):
    """GET estimate returns cost and provider without executing."""
    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/execute/estimate",
                params={"provider": "sendgrid", "credential_mode": "byo"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["capability_id"] == "email.send"
    assert data["provider"] == "sendgrid"
    assert data["cost_estimate_usd"] == 0.01
    assert data["circuit_state"] == "closed"
    assert data["credential_mode"] == "byo"
    assert resp.json()["error"] is None


@pytest.mark.anyio
async def test_execution_logging(app):
    """Execute inserts a row into capability_executions."""
    _, mock_pool = _build_patches()
    insert_payloads: list[dict] = []

    async def capture_insert(table: str, payload: dict) -> bool:
        insert_payloads.append({"table": table, "payload": payload})
        return True

    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
        patch("routes.capability_execute.supabase_insert", new_callable=AsyncMock, side_effect=capture_insert),
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, h: h),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "provider": "sendgrid",
                    "method": "POST",
                    "path": "/v3/mail/send",
                    "body": {"to": "test@example.com"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert len(insert_payloads) == 1
    entry = insert_payloads[0]
    assert entry["table"] == "capability_executions"
    payload = entry["payload"]
    assert payload["capability_id"] == "email.send"
    assert payload["provider_used"] == "sendgrid"
    assert payload["method"] == "POST"
    assert payload["success"] is True
    assert payload["upstream_status"] == 202


@pytest.mark.anyio
async def test_idempotency_prevents_duplicate(app):
    """Idempotency key returns existing execution without re-executing."""
    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase_with_existing_exec),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "provider": "sendgrid",
                    "method": "POST",
                    "path": "/v3/mail/send",
                    "body": {},
                    "idempotency_key": "dedup-key-123",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["deduplicated"] is True
    assert data["execution_id"] == "exec_existing123"


@pytest.mark.anyio
async def test_execute_requires_auth_header(app):
    """POST execute without auth returns x402 payment instructions."""
    with patch(
        "routes.capability_execute.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={"method": "POST", "path": "/foo", "body": {}},
            )
    assert resp.status_code == 402
    assert resp.headers["x-payment"] == "required"


@pytest.mark.anyio
async def test_estimate_auto_select(app):
    """GET estimate without provider auto-selects best."""
    with (
        patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/execute/estimate",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    # resend has higher AN score → auto-selected
    assert data["provider"] == "resend"
    assert data["cost_estimate_usd"] is None  # resend has no cost_per_call
