"""Tests for capability execute routes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import json
import os
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from routes import capability_execute
from schemas.agent_identity import AgentIdentitySchema
from routes._supabase import SupabaseWriteUnavailable
from services.durable_idempotency import IdempotencyUnavailable
from services.durable_replay_guard import ReplayGuardUnavailable

FAKE_RHUMB_KEY = "rhumb_test_key_cap_exec"

DIRECT_AUTH_CASES = [
    ("crm.object.describe", "X-Rhumb-Key header required for CRM capability execution"),
    (
        "workflow_run.list",
        "X-Rhumb-Key header required for GitHub Actions capability execution",
    ),
    ("db.query.read", "X-Rhumb-Key header required for database capability execution"),
    (
        "warehouse.query.read",
        "X-Rhumb-Key header required for warehouse capability execution",
    ),
    ("deployment.list", "X-Rhumb-Key header required for deployment capability execution"),
    ("object.list", "X-Rhumb-Key header required for storage capability execution"),
    ("ticket.search", "X-Rhumb-Key header required for support capability execution"),
]


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


@pytest.fixture(autouse=True)
def _mock_rate_limiter():
    """Keep execute-route tests off the real Supabase-backed limiter path."""
    mock_limiter = MagicMock()
    mock_limiter.check_and_increment = AsyncMock(return_value=(True, 29))
    with patch(
        "routes.capability_execute._get_rate_limiter",
        new_callable=AsyncMock,
        return_value=mock_limiter,
    ):
        yield mock_limiter


@pytest.fixture(autouse=True)
def _mock_kill_switch_registry():
    """Default execute-route tests to an authoritative non-blocking kill-switch registry."""
    mock_registry = MagicMock()
    mock_registry.is_blocked.return_value = (False, None)
    with patch(
        "routes.capability_execute.init_kill_switch_registry",
        new_callable=AsyncMock,
        return_value=mock_registry,
    ):
        yield mock_registry


@pytest.fixture(autouse=True)
def _mock_billing_health():
    """Default billable execute-route tests to a healthy billing/outbox control plane."""
    with patch(
        "routes.capability_execute.check_billing_health",
        new_callable=AsyncMock,
        return_value=(True, "ok"),
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_required_execution_insert():
    """Default required execution-record insert to success for focused route tests."""
    with patch(
        "routes.capability_execute.supabase_insert_required",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_required_execution_patch():
    """Default required execution-record patch to success for focused route tests."""
    with patch(
        "routes.capability_execute.supabase_patch_required",
        new_callable=AsyncMock,
        return_value=[{}],
    ):
        yield


def test_x402_interop_trace_canonicalizes_alias_backed_provider_ids():
    request = MagicMock()
    request.state = SimpleNamespace(request_id="req_cap_exec_alias_trace")
    request.method = "POST"
    request.url = SimpleNamespace(path="/v1/capabilities/search.query/execute")
    request.headers = {
        "user-agent": "pytest",
        "content-type": "application/json",
    }
    request.client = SimpleNamespace(host="127.0.0.1")

    with patch.object(capability_execute.logger, "info") as mock_info:
        capability_execute._log_x402_interop_trace(
            request,
            capability_id="search.query",
            x_payment="proof",
            payment_trace={"parse_mode": "json", "top_level_keys": ["proof"]},
            outcome="executed",
            response_status=200,
            provider="brave-search",
            execution_id="exec_alias_trace",
        )

    payload = mock_info.call_args.kwargs["extra"]["x402_interop"]
    assert payload["provider"] == "brave-search-api"
    assert payload["execution_id"] == "exec_alias_trace"
    assert payload["capability_id"] == "search.query"


# ── Sample data ─────────────────────────────────────────────

SAMPLE_CAP = [
    {
        "id": "email.send",
        "domain": "email",
        "action": "send",
        "description": "Send transactional email",
    },
]

SAMPLE_MAPPINGS = [
    {
        "capability_id": "email.send",
        "service_slug": "sendgrid",
        "credential_modes": ["byo"],
        "auth_method": "api_key",
        "endpoint_pattern": "POST /v3/mail/send",
        "cost_per_call": "0.01",
        "cost_currency": "USD",
        "free_tier_calls": 100,
    },
    {
        "capability_id": "email.send",
        "service_slug": "resend",
        "credential_modes": ["byo"],
        "auth_method": "api_key",
        "endpoint_pattern": "POST /emails",
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": 100,
    },
]

SAMPLE_SCORES = [
    {"service_slug": "resend", "aggregate_recommendation_score": 7.79},
    {"service_slug": "sendgrid", "aggregate_recommendation_score": 6.35},
]

SAMPLE_SERVICE_DOMAIN = [
    {"slug": "sendgrid", "api_domain": "api.sendgrid.com"},
    {"slug": "resend", "api_domain": "api.resend.com"},
]

MANAGED_SAMPLE_MAPPINGS = [
    {
        "capability_id": "email.send",
        "service_slug": "sendgrid",
        "credential_modes": ["byo"],
        "auth_method": "api_key",
        "endpoint_pattern": "POST /v3/mail/send",
        "cost_per_call": "0.01",
        "cost_currency": "USD",
        "free_tier_calls": 100,
    },
    {
        "capability_id": "email.send",
        "service_slug": "resend",
        "credential_modes": ["byo", "rhumb_managed"],
        "auth_method": "api_key",
        "endpoint_pattern": "POST /emails",
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": 100,
    },
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


def _mock_supabase_with_managed_option(path: str):
    """Return sample mappings that advertise rhumb_managed for resend."""
    if path.startswith("capability_services?") and "capability_id=eq.email.send" in path:
        return MANAGED_SAMPLE_MAPPINGS
    return _mock_supabase(path)


@pytest.mark.anyio
async def test_get_service_domain_accepts_canonical_alias_for_runtime_service_row():
    """Exact service-domain lookups should fall back to runtime alias rows."""
    seen_paths: list[str] = []

    async def _mock_fetch(path: str):
        seen_paths.append(path)
        if path == "services?slug=eq.brave-search-api&select=slug,api_domain&limit=1":
            return []
        if path == "services?slug=eq.brave-search&select=slug,api_domain&limit=1":
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        return []

    with patch(
        "routes.capability_execute.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_fetch,
    ):
        from routes.capability_execute import _get_service_domain

        api_domain = await _get_service_domain("brave-search-api")

    assert api_domain == "api.search.brave.com"
    assert seen_paths == [
        "services?slug=eq.brave-search-api&select=slug,api_domain&limit=1",
        "services?slug=eq.brave-search&select=slug,api_domain&limit=1",
    ]


@pytest.mark.anyio
async def test_resolve_managed_provider_mapping_synthesizes_when_catalog_mapping_lags():
    """Enabled managed configs should not be blocked by stale capability_services rows."""
    mock_executor = MagicMock()
    mock_executor.get_managed_config = AsyncMock(
        return_value={
            "capability_id": "data.enrich",
            "service_slug": "ipinfo",
            "default_method": "GET",
            "default_path": "/{ip}",
        }
    )

    with patch("services.rhumb_managed.get_managed_executor", return_value=mock_executor):
        mapping = await capability_execute._resolve_managed_provider_mapping(
            capability_id="data.enrich",
            mappings=[
                {
                    "capability_id": "data.enrich",
                    "service_slug": "people-data-labs",
                    "credential_modes": ["byok"],
                    "endpoint_pattern": "GET /v5/person/enrich",
                    "cost_per_call": "0.10",
                }
            ],
            requested_provider="ipinfo",
        )

    assert mapping == {
        "capability_id": "data.enrich",
        "service_slug": "ipinfo",
        "credential_modes": ["rhumb_managed"],
        "auth_method": "rhumb_managed",
        "endpoint_pattern": "GET /{ip}",
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
    }


@pytest.mark.anyio
async def test_resolve_managed_provider_mapping_prefers_existing_catalog_mapping():
    """Fresh capability_services metadata should win when it already exists."""
    existing_mapping = {
        "capability_id": "scrape.extract",
        "service_slug": "scraperapi",
        "credential_modes": ["byok", "rhumb_managed"],
        "auth_method": "api_key",
        "endpoint_pattern": "GET /",
        "cost_per_call": "0.001",
    }
    mock_executor = MagicMock()
    mock_executor.get_managed_config = AsyncMock(
        return_value={
            "capability_id": "scrape.extract",
            "service_slug": "scraperapi",
            "default_method": "GET",
            "default_path": "/",
        }
    )

    with patch("services.rhumb_managed.get_managed_executor", return_value=mock_executor):
        mapping = await capability_execute._resolve_managed_provider_mapping(
            capability_id="scrape.extract",
            mappings=[existing_mapping],
            requested_provider="scraperapi",
        )

    assert mapping is existing_mapping


def _mock_supabase_with_stale_direct_db_mapping(path: str):
    """Return a stale proxy row for a direct DB capability."""
    if path.startswith("capabilities?") and "id=eq.db.query.read" in path:
        return []
    if path.startswith("capability_services?") and "capability_id=eq.db.query.read" in path:
        return [
            {
                "capability_id": "db.query.read",
                "service_slug": "stale-db-proxy",
                "credential_modes": ["byo"],
                "auth_method": "api_key",
                "endpoint_pattern": "/proxy/stale-db",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": None,
            }
        ]
    return _mock_supabase(path)


def _mock_tool_alias_supabase(path: str):
    """Return a minimal capability set that lets tool-name aliases suggest canonical capabilities."""
    if path.startswith("capabilities?"):
        if "id=eq.Nano%20Banana%20Pro" in path:
            return []
        if "select=id,domain,action,description,input_hint,outcome" in path:
            return [
                {
                    "id": "ai.generate_image",
                    "domain": "ai",
                    "action": "generate_image",
                    "description": "Generate images from prompts",
                    "input_hint": "Prompt or reference image",
                    "outcome": "Generated image",
                }
            ]
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
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ) as mock_insert,
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
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
async def test_execute_rejects_explicit_byok_missing_path_before_mapping_reads(
    app,
    _mock_rate_limiter,
):
    seen_paths: list[str] = []

    async def mock_fetch(path: str):
        seen_paths.append(path)
        return _mock_supabase(path)

    with patch(
        "routes.capability_execute.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=mock_fetch,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "credential_mode": "byok",
                    "provider": "sendgrid",
                    "method": "POST",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "method and path are required for byok credential mode."
    assert any(path.startswith("capabilities?") for path in seen_paths)
    assert not any(path.startswith("capability_services?") for path in seen_paths)
    _mock_rate_limiter.check_and_increment.assert_not_awaited()


@pytest.mark.anyio
async def test_execute_rejects_agent_vault_missing_token_before_mapping_reads(
    app,
    _mock_rate_limiter,
):
    seen_paths: list[str] = []

    async def mock_fetch(path: str):
        seen_paths.append(path)
        return _mock_supabase(path)

    with patch(
        "routes.capability_execute.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=mock_fetch,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "credential_mode": "agent_vault",
                    "provider": "sendgrid",
                    "method": "POST",
                    "path": "/v3/mail/send",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "X-Agent-Token header required for agent_vault credential mode."
    assert any(path.startswith("capabilities?") for path in seen_paths)
    assert not any(path.startswith("capability_services?") for path in seen_paths)
    _mock_rate_limiter.check_and_increment.assert_not_awaited()


@pytest.mark.anyio
async def test_execute_rejects_blank_provider_field_before_mapping_reads(
    app,
    _mock_rate_limiter,
):
    seen_paths: list[str] = []

    async def mock_fetch(path: str):
        seen_paths.append(path)
        return _mock_supabase(path)

    with patch(
        "routes.capability_execute.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=mock_fetch,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "credential_mode": "byok",
                    "provider": "   ",
                    "method": "POST",
                    "path": "/v3/mail/send",
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'provider' field."
    assert any(path.startswith("capabilities?") for path in seen_paths)
    assert not any(path.startswith("capability_services?") for path in seen_paths)
    _mock_rate_limiter.check_and_increment.assert_not_awaited()


@pytest.mark.anyio
async def test_execute_blocks_when_kill_switch_active(app):
    mock_registry = MagicMock()
    mock_registry.is_blocked.return_value = (
        True,
        "Global kill switch active: security incident",
    )

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.init_kill_switch_registry",
            new_callable=AsyncMock,
            return_value=mock_registry,
        ),
        patch("routes.capability_execute.get_pool_manager") as mock_pool,
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

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "kill_switch_active"
    assert "kill switch" in body["message"].lower()
    assert "security incident" in body["detail"].lower()
    mock_registry.is_blocked.assert_called_once_with(
        agent_id="agent_cap_exec_test",
        provider_slug="sendgrid",
        operation_class="financial",
        require_authoritative=True,
    )
    mock_pool.assert_not_called()


@pytest.mark.anyio
async def test_execute_supports_query_envelope_and_top_level_body(app):
    """POST execute should honor query-string envelope fields and wrap raw JSON as body."""
    _, mock_pool = _build_patches()

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                params={
                    "provider": "sendgrid",
                    "credential_mode": "byok",
                    "method": "POST",
                    "path": "/v3/mail/send",
                },
                json={"to": "test@example.com"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "sendgrid"
    assert data["credential_mode"] == "byok"
    assert data["upstream_status"] == 202

    request_call = mock_pool.acquire.return_value.request.await_args
    assert request_call.kwargs["json"] == {"to": "test@example.com"}


@pytest.mark.anyio
async def test_twilio_lookup_uses_lookups_domain(app):
    """Twilio Lookup paths should route to lookups.twilio.com, not api.twilio.com."""
    _, mock_pool = _build_patches()

    async def mock_fetch(path: str):
        if path.startswith("capabilities?") and "id=eq.phone.lookup" in path:
            return [
                {
                    "id": "phone.lookup",
                    "domain": "phone",
                    "action": "lookup",
                    "description": "Lookup phone metadata",
                }
            ]
        if path.startswith("capability_services?") and "capability_id=eq.phone.lookup" in path:
            return [
                {
                    "service_slug": "twilio",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /v2/PhoneNumbers/{number}?Fields=carrier",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": None,
                }
            ]
        if path.startswith("services?") and "slug=eq.twilio" in path:
            return [{"slug": "twilio", "api_domain": "api.twilio.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/phone.lookup/execute",
                json={
                    "provider": "twilio",
                    "credential_mode": "byo",
                    "method": "GET",
                    "path": "/v2/PhoneNumbers/+14155552671",
                    "params": {"Fields": "carrier"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    mock_pool.acquire.assert_awaited_once()
    assert mock_pool.acquire.await_args.kwargs["base_url"] == "https://lookups.twilio.com"


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
    body = resp.json()
    assert body["error"] == "capability_not_found"
    assert body["message"] == "No capability found with id 'nonexistent'"
    assert body["request_id"] == "req-capability-404"
    assert body["search_url"] == "/v1/capabilities?search=nonexistent"


@pytest.mark.anyio
async def test_post_execute_unknown_capability_ignores_stale_direct_provider_alias_rows(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            if "id=eq.Resend" in path:
                return []
            if "select=id,domain,action,description,input_hint,outcome" in path:
                return [
                    {
                        "id": "email.send",
                        "domain": "email",
                        "action": "send",
                        "description": "Send transactional email",
                        "input_hint": "Email payload",
                        "outcome": "Email accepted",
                    },
                    {
                        "id": "db.query.read",
                        "domain": "database",
                        "action": "query_read",
                        "description": "Run read-only SQL queries",
                        "input_hint": "SQL query and connection_ref",
                        "outcome": "Rows returned",
                    },
                ]
        if path.startswith("capability_services?"):
            if "select=capability_id,service_slug" in path:
                return [
                    {"capability_id": "email.send", "service_slug": "resend"},
                    {"capability_id": "db.query.read", "service_slug": "resend"},
                ]
            return []
        if path.startswith("services?"):
            return [{"slug": "resend", "name": "Resend"}]
        return []

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
        patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/Resend/execute",
                json={},
                headers={"X-Request-ID": "req-stale-direct-alias"},
            )

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "capability_not_found"
    assert body["request_id"] == "req-stale-direct-alias"
    assert body["search_url"] == "/v1/capabilities?search=Resend"
    assert body["suggested_capabilities"][0]["id"] == "email.send"
    assert all(item["id"] != "db.query.read" for item in body["suggested_capabilities"])


@pytest.mark.anyio
async def test_billable_execution_checks_billing_health_before_execute(app):
    """Billable execution proceeds when billing health check succeeds."""
    _, mock_pool = _build_patches()

    with (
        patch(
            "routes.capability_execute.check_billing_health",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ) as mock_billing_health,
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
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
        patch(
            "routes.capability_execute.check_billing_health",
            new_callable=AsyncMock,
            return_value=(False, billing_reason),
        ),
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ) as mock_insert,
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
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
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
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
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/nonexistent/execute",
                json={"method": "POST", "path": "/foo", "body": {}},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "capability_not_found"
    assert body["message"] == "No capability found with id 'nonexistent'"
    assert body["search_url"] == "/v1/capabilities?search=nonexistent"


@pytest.mark.anyio
async def test_execute_unknown_capability_suggests_capability_for_tool_alias(app):
    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_tool_alias_supabase,
        ),
        patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_tool_alias_supabase,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/Nano%20Banana%20Pro/execute",
                json={"method": "POST", "path": "/foo", "body": {}},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "capability_not_found"
    assert body["search_url"] == "/v1/capabilities?search=Nano%20Banana%20Pro"
    assert body["suggested_capabilities"][0]["id"] == "ai.generate_image"


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
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
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
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/execute/estimate",
                params={"provider": "sendgrid", "credential_mode": "byok"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["capability_id"] == "email.send"
    assert data["provider"] == "sendgrid"
    assert data["cost_estimate_usd"] == 0.01
    assert data["circuit_state"] == "closed"
    assert data["credential_mode"] == "byok"
    assert resp.json()["error"] is None


@pytest.mark.anyio
async def test_estimate_rejects_invalid_credential_mode_parameter(app):
    with patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/execute/estimate",
                params={"credential_mode": "offline"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'credential_mode' filter."
    assert mock_fetch.await_count == 0


@pytest.mark.anyio
async def test_estimate_rejects_blank_credential_mode_before_auth_or_reads(app, _mock_identity_store):
    with patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/execute/estimate",
                params={"credential_mode": "   "},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'credential_mode' filter."
    _mock_identity_store.verify_api_key_with_agent.assert_not_awaited()
    assert mock_fetch.await_count == 0


@pytest.mark.anyio
async def test_estimate_rejects_blank_provider_filter_before_reads(app):
    with patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/execute/estimate",
                params={"provider": "   ", "credential_mode": "byok"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'provider' filter."
    assert mock_fetch.await_count == 0


@pytest.mark.anyio
async def test_estimate_rejects_blank_capability_id_before_auth_or_reads(app, _mock_identity_store):
    with patch("routes.capability_execute.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/%20%20%20/execute/estimate",
                params={"credential_mode": "byok"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'capability_id' path parameter."
    assert body["error"]["detail"] == "Provide a non-empty capability id from GET /v1/capabilities."
    _mock_identity_store.verify_api_key_with_agent.assert_not_awaited()
    assert mock_fetch.await_count == 0


@pytest.mark.anyio
async def test_estimate_accepts_canonical_alias_for_proxy_mapped_provider(app):
    """Estimate should accept canonical aliases like brave-search-api."""

    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["byo", "rhumb_managed"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": "0.003",
                    "cost_currency": "USD",
                    "free_tier_calls": 2000,
                }
            ]
        return []

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/search.query/execute/estimate",
                params={"provider": "brave-search-api", "credential_mode": "byo"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider"] == "brave-search-api"
    assert data["credential_mode"] == "byok"
    assert data["endpoint_pattern"] == "GET /res/v1/web/search"
    assert resp.json()["error"] is None


@pytest.mark.anyio
async def test_estimate_provider_unavailable_error_uses_canonical_public_provider_id(app):
    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/execute/estimate",
                params={"provider": "pdl", "credential_mode": "byok"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Provider 'people-data-labs' not available for capability 'email.send'"


@pytest.mark.anyio
async def test_estimate_auto_resolves_to_managed_when_config_exists(app):
    """GET estimate defaults auto to rhumb_managed when a managed config exists."""
    managed_mapping = MANAGED_SAMPLE_MAPPINGS[1]

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_with_managed_option,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            return_value=managed_mapping,
        ) as mock_resolve_managed,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/execute/estimate",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider"] == "resend"
    assert data["credential_mode"] == "rhumb_managed"
    mock_resolve_managed.assert_awaited_once()


@pytest.mark.anyio
async def test_estimate_explicit_rhumb_managed_uses_managed_mapping(app):
    """Explicit rhumb_managed estimates should only return a managed-capable provider."""
    managed_mapping = MANAGED_SAMPLE_MAPPINGS[1]

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_with_managed_option,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            return_value=managed_mapping,
        ) as mock_resolve_managed,
        patch(
            "routes.capability_execute._auto_select_provider",
            new_callable=AsyncMock,
        ) as mock_auto_select,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/execute/estimate",
                params={"credential_mode": "rhumb_managed"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider"] == "resend"
    assert data["credential_mode"] == "rhumb_managed"
    mock_resolve_managed.assert_awaited_once()
    mock_auto_select.assert_not_awaited()


@pytest.mark.anyio
async def test_estimate_explicit_rhumb_managed_rejects_unmanaged_provider(app):
    """Explicit rhumb_managed estimates should fail fast for non-managed providers."""

    managed_mapping = MANAGED_SAMPLE_MAPPINGS[1]

    async def mock_resolve_managed(capability_id: str, mappings: list[dict], requested_provider: str | None):
        if requested_provider is None:
            return managed_mapping
        return None

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_with_managed_option,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            side_effect=mock_resolve_managed,
        ) as mock_resolve_managed,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/execute/estimate",
                params={"credential_mode": "rhumb_managed", "provider": "sendgrid"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "provider_not_available"
    assert body["credential_mode"] == "rhumb_managed"
    assert body["requested_provider"] == "sendgrid"
    assert body["requested_provider_credential_modes"] == ["byok"]
    assert body["available_providers"][0]["provider"] == "resend"
    assert body["resolve_url"] == "/v1/capabilities/email.send/resolve?credential_mode=rhumb_managed"
    assert mock_resolve_managed.await_count == 2


@pytest.mark.anyio
async def test_estimate_explicit_rhumb_managed_alias_backed_unmanaged_provider_stays_canonical(app):
    """Managed estimate errors should keep alias-backed provider ids on canonical public slugs."""

    capability = {
        "id": "search.query",
        "domain": "search",
        "action": "query",
        "description": "Web search",
    }
    mappings = [
        {
            "capability_id": "search.query",
            "service_slug": "pdl",
            "credential_modes": ["byo"],
            "auth_method": "api_key",
            "endpoint_pattern": "POST /person/enrich",
            "cost_per_call": "0.01",
            "cost_currency": "USD",
            "free_tier_calls": 0,
        },
        {
            "capability_id": "search.query",
            "service_slug": "brave-search",
            "credential_modes": ["byo", "rhumb_managed"],
            "auth_method": "api_key",
            "endpoint_pattern": "GET /res/v1/web/search",
            "cost_per_call": "0.003",
            "cost_currency": "USD",
            "free_tier_calls": 0,
        },
    ]

    async def mock_fetch(path: str):
        if path.startswith("capabilities?") and "id=eq.search.query" in path:
            return [capability]
        if path.startswith("capability_services?") and "capability_id=eq.search.query" in path:
            return mappings
        if path.startswith("capability_executions?"):
            return []
        return []

    async def mock_resolve_managed(
        capability_id: str,
        mappings: list[dict],
        requested_provider: str | None,
    ):
        if capability_id == "search.query" and requested_provider is None:
            return mappings[1]
        return None

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            side_effect=mock_resolve_managed,
        ) as mock_resolve_managed,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/search.query/execute/estimate",
                params={"credential_mode": "rhumb_managed", "provider": "pdl"},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "provider_not_available"
    assert "people-data-labs" in body["message"]
    assert body["requested_provider"] == "people-data-labs"
    assert body["requested_provider_credential_modes"] == ["byok"]
    assert body["available_providers"] == [
        {"provider": "brave-search-api", "credential_modes": ["byok", "rhumb_managed"]}
    ]
    assert body["resolve_url"] == "/v1/capabilities/search.query/resolve?credential_mode=rhumb_managed"
    assert mock_resolve_managed.await_count == 2


@pytest.mark.anyio
async def test_execute_explicit_rhumb_managed_rejects_unmanaged_provider_with_alternatives(app):
    """Explicit managed execute should surface the available managed fallback provider."""

    managed_mapping = MANAGED_SAMPLE_MAPPINGS[1]

    async def mock_resolve_managed(capability_id: str, mappings: list[dict], requested_provider: str | None):
        if requested_provider is None:
            return managed_mapping
        return None

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_with_managed_option,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            side_effect=mock_resolve_managed,
        ) as mock_resolve_managed,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "provider": "sendgrid",
                    "credential_mode": "rhumb_managed",
                    "body": {"to": "test@example.com"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "provider_not_available"
    assert body["credential_mode"] == "rhumb_managed"
    assert body["requested_provider"] == "sendgrid"
    assert body["requested_provider_credential_modes"] == ["byok"]
    assert body["available_providers"][0]["provider"] == "resend"
    assert body["resolve_url"] == "/v1/capabilities/email.send/resolve?credential_mode=rhumb_managed"
    assert mock_resolve_managed.await_count == 2


@pytest.mark.anyio
async def test_execute_explicit_rhumb_managed_alias_backed_unmanaged_provider_stays_canonical(app):
    """Managed execute errors should keep alias-backed provider ids on canonical public slugs."""

    capability = {
        "id": "search.query",
        "domain": "search",
        "action": "query",
        "description": "Web search",
    }
    mappings = [
        {
            "capability_id": "search.query",
            "service_slug": "pdl",
            "credential_modes": ["byo"],
            "auth_method": "api_key",
            "endpoint_pattern": "POST /person/enrich",
            "cost_per_call": "0.01",
            "cost_currency": "USD",
            "free_tier_calls": 0,
        },
        {
            "capability_id": "search.query",
            "service_slug": "brave-search",
            "credential_modes": ["byo", "rhumb_managed"],
            "auth_method": "api_key",
            "endpoint_pattern": "GET /res/v1/web/search",
            "cost_per_call": "0.003",
            "cost_currency": "USD",
            "free_tier_calls": 0,
        },
    ]

    async def mock_fetch(path: str):
        if path.startswith("capabilities?") and "id=eq.search.query" in path:
            return [capability]
        if path.startswith("capability_services?") and "capability_id=eq.search.query" in path:
            return mappings
        if path.startswith("capability_executions?"):
            return []
        return []

    async def mock_resolve_managed(
        capability_id: str,
        mappings: list[dict],
        requested_provider: str | None,
    ):
        if capability_id == "search.query" and requested_provider is None:
            return mappings[1]
        return None

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            side_effect=mock_resolve_managed,
        ) as mock_resolve_managed,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "pdl",
                    "credential_mode": "rhumb_managed",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "provider_not_available"
    assert body["credential_mode"] == "rhumb_managed"
    assert "people-data-labs" in body["message"]
    assert body["requested_provider"] == "people-data-labs"
    assert body["requested_provider_credential_modes"] == ["byok"]
    assert body["available_providers"] == [
        {"provider": "brave-search-api", "credential_modes": ["byok", "rhumb_managed"]}
    ]
    assert body["resolve_url"] == "/v1/capabilities/search.query/resolve?credential_mode=rhumb_managed"
    assert mock_resolve_managed.await_count == 2


@pytest.mark.anyio
async def test_execute_explicit_rhumb_managed_without_any_config_surfaces_byo_fallback(app):
    """Explicit managed execute should fail honestly when no managed path exists at all."""

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "credential_mode": "rhumb_managed",
                    "body": {"to": "test@example.com"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "managed_provider_unavailable"
    assert body["credential_mode"] == "rhumb_managed"
    assert body["available_providers"] == []
    assert body["resolve_url"] == "/v1/capabilities/email.send/resolve?credential_mode=rhumb_managed"


@pytest.mark.anyio
async def test_execution_logging(app):
    """Execute pre-logs then patches the same capability_executions row."""
    _, mock_pool = _build_patches()
    insert_payloads: list[dict] = []
    patch_calls: list[dict] = []

    async def capture_insert(table: str, payload: dict) -> None:
        insert_payloads.append({"table": table, "payload": payload})
        return None

    async def capture_patch(path: str, payload: dict):
        patch_calls.append({"path": path, "payload": payload})
        return [payload]

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_insert_required",
            new_callable=AsyncMock,
            side_effect=capture_insert,
        ),
        patch(
            "routes.capability_execute.supabase_patch_required",
            new_callable=AsyncMock,
            side_effect=capture_patch,
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
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
    placeholder = entry["payload"]
    assert placeholder["capability_id"] == "email.send"
    assert placeholder["provider_used"] == "sendgrid"
    assert placeholder["method"] == "POST"
    assert placeholder["billing_status"] == "pending"

    assert len(patch_calls) == 1
    payload = patch_calls[0]["payload"]
    assert payload["provider_used"] == "sendgrid"
    assert payload["method"] == "POST"
    assert payload["success"] is True
    assert payload["upstream_status"] == 202
    assert payload["billing_status"] == "billed"


@pytest.mark.anyio
async def test_byo_4xx_marks_execution_failed_and_refunded(app):
    """4xx upstream responses should not be marked as successful executions."""
    mock_response, mock_pool = _build_patches()
    mock_response.status_code = 422
    mock_response.json.return_value = {"detail": "missing required field"}
    mock_response.text = '{"detail":"missing required field"}'

    patch_calls = []

    async def capture_patch(path: str, payload: dict):
        patch_calls.append({"path": path, "payload": payload})
        return [payload]

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_patch_required",
            new_callable=AsyncMock,
            side_effect=capture_patch,
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
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
    payload = patch_calls[-1]["payload"]
    assert payload["success"] is False
    assert payload["upstream_status"] == 422
    assert payload["billing_status"] == "refunded"


@pytest.mark.anyio
async def test_byo_get_promotes_body_to_query_params(app):
    """GET executions should promote body fields to params and accept canonical aliases."""
    captured: dict = {}

    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": "0.10",
                    "cost_currency": "USD",
                    "free_tier_calls": 0,
                }
            ]
        if path.startswith("services?"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"status": 200, "ok": True}

        text = '{"status": 200, "ok": true}'

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["json"] = json
            captured["params"] = params
            return DummyResponse()

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute.supabase_patch", new_callable=AsyncMock, return_value=[{}]
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch("routes.capability_execute.httpx.AsyncClient", DummyAsyncClient),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search-api",
                    "credential_mode": "byo",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    assert captured["method"] == "GET"
    assert captured["json"] is None
    assert captured["params"] == {"q": "Rhumb API agent infrastructure"}


@pytest.mark.anyio
async def test_execute_canonicalizes_alias_backed_provider_ids_on_response_and_persistence(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": "0.10",
                    "cost_currency": "USD",
                    "free_tier_calls": 0,
                }
            ]
        if path.startswith("services?"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"status": 200, "ok": True}

        text = '{"status": 200, "ok": true}'

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            return DummyResponse()

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch(
            "routes.capability_execute.supabase_insert_required",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_insert_required,
        patch(
            "routes.capability_execute.supabase_patch_required",
            new_callable=AsyncMock,
            return_value=[{}],
        ) as mock_patch_required,
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch("routes.capability_execute.httpx.AsyncClient", DummyAsyncClient),
        patch("routes.capability_execute._should_skip_receipt", return_value=True),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search-api",
                    "credential_mode": "byo",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["fallback_provider"] is None
    assert mock_insert_required.await_args.args[1]["provider_used"] == "brave-search-api"
    assert mock_patch_required.await_args.args[1]["provider_used"] == "brave-search-api"
    assert mock_patch_required.await_args.args[1]["fallback_provider"] is None


def test_execute_recovery_hints_canonicalize_alias_backed_provider_slugs():
    from routes.capability_execute import _execute_recovery_hints

    mappings = [
        {
            "service_slug": "pdl",
            "credential_modes": ["byo"],
        },
        {
            "service_slug": "brave-search",
            "credential_modes": ["byo"],
        },
    ]

    hints = _execute_recovery_hints(
        capability_id="search.query",
        mappings=mappings,
        credential_mode="byo",
        requested_provider="pdl",
        selected_mapping=mappings[0],
    )

    assert hints["requested_provider"] == "people-data-labs"
    assert hints["estimate_url"].startswith("/v1/capabilities/search.query/execute/estimate")
    assert "provider=people-data-labs" in hints["estimate_url"]
    assert hints["available_providers"] == [
        {"provider": "people-data-labs", "credential_modes": ["byok"]},
        {"provider": "brave-search-api", "credential_modes": ["byok"]},
    ]


def test_managed_provider_unavailable_response_canonicalizes_requested_provider():
    from routes.capability_execute import _managed_provider_unavailable_response

    dummy_request = MagicMock()
    dummy_request.state = MagicMock(request_id="req_test")

    resp = _managed_provider_unavailable_response(
        dummy_request,
        capability_id="search.query",
        mappings=[{"service_slug": "pdl", "credential_modes": ["byo"]}],
        requested_provider="pdl",
        available_managed_mappings=[{"service_slug": "brave-search", "credential_modes": ["byo"]}],
    )

    assert resp.status_code == 503
    body = json.loads(resp.body)
    assert body["requested_provider"] == "people-data-labs"
    assert "people-data-labs" in body["message"]
    assert body["available_providers"][0]["provider"] == "brave-search-api"


@pytest.mark.anyio
async def test_execute_no_api_domain_error_uses_canonical_public_provider_id(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": "0.10",
                    "cost_currency": "USD",
                    "free_tier_calls": 0,
                }
            ]
        if path.startswith("services?") or path.startswith("capability_executions?"):
            return []
        return []

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch.dict("routes.capability_execute.SERVICE_REGISTRY", {}, clear=True),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search-api",
                    "credential_mode": "byo",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "No API domain configured for provider 'brave-search-api'"


@pytest.mark.anyio
async def test_execute_credential_unavailable_error_uses_canonical_public_provider_id(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": "0.10",
                    "cost_currency": "USD",
                    "free_tier_calls": 0,
                }
            ]
        if path.startswith("services?"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    broken_injector = MagicMock()
    broken_injector.inject_request_parts.side_effect = RuntimeError("missing brave-search credential")

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch("routes.capability_execute.get_auth_injector", return_value=broken_injector),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search-api",
                    "credential_mode": "byo",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Credential unavailable for provider 'brave-search-api'"


@pytest.mark.anyio
async def test_execute_upstream_http_error_uses_canonical_public_provider_id(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": "0.10",
                    "cost_currency": "USD",
                    "free_tier_calls": 0,
                }
            ]
        if path.startswith("services?"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    from services.proxy_breaker import BreakerRegistry

    breaker_registry = BreakerRegistry()
    mock_pool = MagicMock()
    mock_client = AsyncMock()
    mock_client.request.side_effect = httpx.ConnectTimeout("brave-search upstream exploded")
    mock_pool.acquire = AsyncMock(return_value=mock_client)
    mock_pool.release = AsyncMock()

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch("routes.capability_execute.get_breaker_registry", return_value=breaker_registry),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search",
                    "credential_mode": "byo",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Upstream request failed for provider 'brave-search-api'"


@pytest.mark.anyio
async def test_execute_provider_unavailable_error_uses_canonical_public_provider_id(app):
    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "provider": "pdl",
                    "credential_mode": "byo",
                    "method": "POST",
                    "path": "/v3/mail/send",
                    "body": {},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Provider 'people-data-labs' not available for capability 'email.send'"


@pytest.mark.anyio
async def test_execute_circuit_open_error_uses_canonical_public_provider_id(app):
    from services.proxy_breaker import BreakerRegistry

    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": "0.10",
                    "cost_currency": "USD",
                    "free_tier_calls": 0,
                }
            ]
        if path.startswith("capability_executions?"):
            return []
        return []

    broken_registry = BreakerRegistry()
    breaker = broken_registry.get("brave-search", "agent_cap_exec_test")
    for _ in range(10):
        breaker.record_failure(status_code=500)

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch("routes.capability_execute.get_breaker_registry", return_value=broken_registry),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search",
                    "credential_mode": "byo",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Provider 'brave-search-api' circuit is open — try later"


@pytest.mark.anyio
async def test_execute_agent_vault_no_api_domain_error_uses_canonical_public_provider_id(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["agent_vault"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                }
            ]
        if path.startswith("services?") or path.startswith("capability_executions?"):
            return []
        return []

    mock_validator = MagicMock()
    mock_validator.get_ceremony = AsyncMock(return_value=None)

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch("services.agent_vault.get_vault_validator", return_value=mock_validator),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search",
                    "credential_mode": "agent_vault",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={
                    "X-Rhumb-Key": FAKE_RHUMB_KEY,
                    "X-Agent-Token": "agent_vault_test_token",
                },
            )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "No API domain for provider 'brave-search-api'"


@pytest.mark.anyio
async def test_execute_agent_vault_upstream_http_error_uses_canonical_public_provider_id(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["agent_vault"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                }
            ]
        if path.startswith("services?slug=eq.brave-search&"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    class ExplodingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            raise httpx.ConnectTimeout("brave-search upstream exploded")

    mock_validator = MagicMock()
    mock_validator.get_ceremony = AsyncMock(return_value=None)

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch("services.agent_vault.get_vault_validator", return_value=mock_validator),
        patch("routes.capability_execute.httpx.AsyncClient", ExplodingAsyncClient),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search",
                    "credential_mode": "agent_vault",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={
                    "X-Rhumb-Key": FAKE_RHUMB_KEY,
                    "X-Agent-Token": "agent_vault_test_token",
                },
            )

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Upstream request failed for provider 'brave-search-api'"


@pytest.mark.anyio
async def test_execute_agent_vault_canonicalizes_alias_backed_provider_ids_for_receipt_path(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["agent_vault"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                }
            ]
        if path.startswith("services?slug=eq.brave-search&"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"status": 200, "ok": True}

        text = '{"status": 200, "ok": true}'

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            return DummyResponse()

    mock_validator = MagicMock()
    mock_validator.get_ceremony = AsyncMock(return_value=None)
    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_agent_vault_alias")
    )

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch("services.agent_vault.get_vault_validator", return_value=mock_validator),
        patch("routes.capability_execute.httpx.AsyncClient", DummyAsyncClient),
        patch(
            "routes.capability_execute.get_receipt_service",
            return_value=mock_receipt_service,
        ),
        patch("routes.capability_execute._emit_execution_billing_event") as mock_billing_event,
        patch("routes.capability_execute._record_execution_audit_outcome") as mock_audit_outcome,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search",
                    "credential_mode": "agent_vault",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={
                    "X-Rhumb-Key": FAKE_RHUMB_KEY,
                    "X-Agent-Token": "agent_vault_test_token",
                },
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["receipt_id"] == "rcpt_agent_vault_alias"

    receipt_input = mock_receipt_service.create_receipt.await_args.args[0]
    assert receipt_input.provider_id == "brave-search-api"
    assert mock_billing_event.call_args.kwargs["provider_slug"] == "brave-search-api"
    assert mock_audit_outcome.call_args.kwargs["provider_slug"] == "brave-search-api"


@pytest.mark.anyio
async def test_execute_agent_vault_canonicalizes_alias_backed_provider_fields_in_upstream_response(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["agent_vault"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                }
            ]
        if path.startswith("services?slug=eq.brave-search&"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    raw_upstream_response = {
        "provider_used": "brave-search",
        "selected_provider": "brave-search",
        "fallback_provider": "pdl",
        "message": "brave-search-api upstream accepted after pdl fallback warmed",
        "detail": "Retry brave-search if the alias path drifts or choose pdl",
        "result": {
            "provider_slug": "brave-search",
            "fallback_provider": "pdl",
            "fallback_providers": ["pdl", "brave-search-api"],
            "error_message": "brave-search-api failed before pdl fallback",
        },
    }
    expected_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "fallback_provider": "people-data-labs",
        "message": "brave-search-api upstream accepted after people-data-labs fallback warmed",
        "detail": "Retry brave-search-api if the alias path drifts or choose people-data-labs",
        "result": {
            "provider_slug": "brave-search-api",
            "fallback_provider": "people-data-labs",
            "fallback_providers": ["people-data-labs", "brave-search-api"],
            "error_message": "brave-search-api failed before people-data-labs fallback",
        },
    }
    response_text = json.dumps(raw_upstream_response)

    class DummyResponse:
        status_code = 200

        def json(self):
            return raw_upstream_response

        text = response_text

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            return DummyResponse()

    mock_validator = MagicMock()
    mock_validator.get_ceremony = AsyncMock(return_value=None)
    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_agent_vault_payload_alias")
    )

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch("services.agent_vault.get_vault_validator", return_value=mock_validator),
        patch("routes.capability_execute.httpx.AsyncClient", DummyAsyncClient),
        patch(
            "routes.capability_execute.get_receipt_service",
            return_value=mock_receipt_service,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search",
                    "credential_mode": "agent_vault",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={
                    "X-Rhumb-Key": FAKE_RHUMB_KEY,
                    "X-Agent-Token": "agent_vault_test_token",
                },
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["upstream_response"] == expected_upstream_response

    receipt_input = mock_receipt_service.create_receipt.await_args.args[0]
    assert receipt_input.response_hash == capability_execute.hash_response_payload(
        expected_upstream_response
    )


@pytest.mark.anyio
async def test_execute_agent_vault_canonicalizes_alternate_provider_alias_text_when_structured_fields_are_already_canonical(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["agent_vault"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                }
            ]
        if path.startswith("services?slug=eq.brave-search&"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    raw_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "fallback_provider": "people-data-labs",
        "message": "brave-search-api upstream accepted after pdl fallback warmed",
        "detail": "Retry brave-search-api if the alias path drifts or choose pdl",
        "result": {
            "provider_slug": "brave-search-api",
            "fallback_provider": "people-data-labs",
            "fallback_providers": ["people-data-labs", "brave-search-api"],
            "error_message": "brave-search-api failed before pdl fallback",
        },
    }
    expected_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "fallback_provider": "people-data-labs",
        "message": "brave-search-api upstream accepted after people-data-labs fallback warmed",
        "detail": "Retry brave-search-api if the alias path drifts or choose people-data-labs",
        "result": {
            "provider_slug": "brave-search-api",
            "fallback_provider": "people-data-labs",
            "fallback_providers": ["people-data-labs", "brave-search-api"],
            "error_message": "brave-search-api failed before people-data-labs fallback",
        },
    }
    response_text = json.dumps(raw_upstream_response)

    class DummyResponse:
        status_code = 200

        def json(self):
            return raw_upstream_response

        text = response_text

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            return DummyResponse()

    mock_validator = MagicMock()
    mock_validator.get_ceremony = AsyncMock(return_value=None)
    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_agent_vault_canonical_context")
    )

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch("services.agent_vault.get_vault_validator", return_value=mock_validator),
        patch("routes.capability_execute.httpx.AsyncClient", DummyAsyncClient),
        patch(
            "routes.capability_execute.get_receipt_service",
            return_value=mock_receipt_service,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search-api",
                    "credential_mode": "agent_vault",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={
                    "X-Rhumb-Key": FAKE_RHUMB_KEY,
                    "X-Agent-Token": "agent_vault_test_token",
                },
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["upstream_response"] == expected_upstream_response

    receipt_input = mock_receipt_service.create_receipt.await_args.args[0]
    assert receipt_input.response_hash == capability_execute.hash_response_payload(
        expected_upstream_response
    )


@pytest.mark.anyio
async def test_execute_agent_vault_failure_canonicalizes_alternate_provider_alias_text_when_structured_fields_are_already_canonical(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["agent_vault"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                }
            ]
        if path.startswith("services?slug=eq.brave-search&"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    raw_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "fallback_provider": "people-data-labs",
        "message": "brave-search-api upstream failed after pdl fallback warmed",
        "error_message": "brave-search-api failed before pdl fallback",
        "result": {
            "provider_slug": "brave-search-api",
            "fallback_provider": "people-data-labs",
            "supported_provider_slugs": ["brave-search-api", "people-data-labs"],
            "detail": "Retry brave-search-api later or switch to pdl",
        },
    }
    expected_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "fallback_provider": "people-data-labs",
        "message": "brave-search-api upstream failed after people-data-labs fallback warmed",
        "error_message": "brave-search-api failed before people-data-labs fallback",
        "result": {
            "provider_slug": "brave-search-api",
            "fallback_provider": "people-data-labs",
            "supported_provider_slugs": ["brave-search-api", "people-data-labs"],
            "detail": "Retry brave-search-api later or switch to people-data-labs",
        },
    }
    response_text = json.dumps(raw_upstream_response)

    class DummyResponse:
        status_code = 502

        def json(self):
            return raw_upstream_response

        text = response_text

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            return DummyResponse()

    mock_validator = MagicMock()
    mock_validator.get_ceremony = AsyncMock(return_value=None)
    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_agent_vault_canonical_context_failure")
    )

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch("services.agent_vault.get_vault_validator", return_value=mock_validator),
        patch("routes.capability_execute.httpx.AsyncClient", DummyAsyncClient),
        patch(
            "routes.capability_execute.get_receipt_service",
            return_value=mock_receipt_service,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search-api",
                    "credential_mode": "agent_vault",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={
                    "X-Rhumb-Key": FAKE_RHUMB_KEY,
                    "X-Agent-Token": "agent_vault_test_token",
                },
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["upstream_status"] == 502
    assert data["upstream_response"] == expected_upstream_response

    receipt_input = mock_receipt_service.create_receipt.await_args.args[0]
    assert receipt_input.error_message == "brave-search-api failed before people-data-labs fallback"
    assert receipt_input.response_hash == capability_execute.hash_response_payload(
        expected_upstream_response
    )


@pytest.mark.anyio
async def test_execute_agent_vault_failure_canonicalizes_same_provider_alias_text_when_structured_fields_are_already_canonical(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["agent_vault"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                }
            ]
        if path.startswith("services?slug=eq.brave-search&"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    raw_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "message": "brave-search-api upstream failed after brave-search warmup drifted",
        "error_message": "brave-search failed before stabilization",
        "result": {
            "provider_slug": "brave-search-api",
            "supported_provider_slugs": ["brave-search-api"],
            "detail": "Retry brave-search later",
        },
    }
    expected_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "message": "brave-search-api upstream failed after brave-search-api warmup drifted",
        "error_message": "brave-search-api failed before stabilization",
        "result": {
            "provider_slug": "brave-search-api",
            "supported_provider_slugs": ["brave-search-api"],
            "detail": "Retry brave-search-api later",
        },
    }
    response_text = json.dumps(raw_upstream_response)

    class DummyResponse:
        status_code = 502

        def json(self):
            return raw_upstream_response

        text = response_text

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            return DummyResponse()

    mock_validator = MagicMock()
    mock_validator.get_ceremony = AsyncMock(return_value=None)
    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_agent_vault_same_provider_alias_failure")
    )

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch("services.agent_vault.get_vault_validator", return_value=mock_validator),
        patch("routes.capability_execute.httpx.AsyncClient", DummyAsyncClient),
        patch(
            "routes.capability_execute.get_receipt_service",
            return_value=mock_receipt_service,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search-api",
                    "credential_mode": "agent_vault",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={
                    "X-Rhumb-Key": FAKE_RHUMB_KEY,
                    "X-Agent-Token": "agent_vault_test_token",
                },
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["upstream_status"] == 502
    assert data["upstream_response"] == expected_upstream_response
    assert "brave-search-api-api" not in json.dumps(data["upstream_response"])

    receipt_input = mock_receipt_service.create_receipt.await_args.args[0]
    assert receipt_input.error_message == "brave-search-api failed before stabilization"
    assert receipt_input.response_hash == capability_execute.hash_response_payload(
        expected_upstream_response
    )


@pytest.mark.anyio
async def test_execute_byok_canonicalizes_alias_backed_provider_ids_for_receipt_path(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": "0.01",
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                }
            ]
        if path.startswith("scores?"):
            return [{"service_slug": "brave-search", "aggregate_recommendation_score": 8.9}]
        if path.startswith("services?slug=eq.brave-search&"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    _, mock_pool = _build_patches()
    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_byok_alias")
    )
    mock_attribution = MagicMock()
    mock_attribution.to_rhumb_block.return_value = {"provider": {"id": "brave-search-api"}}
    mock_attribution.to_response_headers.return_value = {"X-Rhumb-Provider": "brave-search-api"}

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch(
            "routes.capability_execute.get_receipt_service",
            return_value=mock_receipt_service,
        ),
        patch("routes.capability_execute._emit_execution_billing_event") as mock_billing_event,
        patch("routes.capability_execute._record_execution_audit_outcome") as mock_audit_outcome,
        patch(
            "routes.capability_execute.build_attribution",
            new_callable=AsyncMock,
            return_value=mock_attribution,
        ) as mock_build_attribution,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search",
                    "credential_mode": "byok",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["receipt_id"] == "rcpt_byok_alias"
    assert resp.headers["X-Rhumb-Provider"] == "brave-search-api"

    receipt_input = mock_receipt_service.create_receipt.await_args.args[0]
    assert receipt_input.provider_id == "brave-search-api"
    assert mock_billing_event.call_args.kwargs["provider_slug"] == "brave-search-api"
    assert mock_audit_outcome.call_args.kwargs["provider_slug"] == "brave-search-api"
    assert mock_build_attribution.await_args.kwargs["provider_slug"] == "brave-search-api"


@pytest.mark.anyio
async def test_execute_byok_canonicalizes_alias_backed_provider_fields_in_upstream_response(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": "0.01",
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                }
            ]
        if path.startswith("scores?"):
            return [{"service_slug": "brave-search", "aggregate_recommendation_score": 8.9}]
        if path.startswith("services?slug=eq.brave-search&"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    raw_upstream_response = {
        "provider_used": "brave-search",
        "provider_slug": "brave-search",
        "message": "brave-search upstream accepted",
        "result": {
            "selected_provider": "brave-search",
            "supported_provider_slugs": ["brave-search"],
        },
    }
    expected_upstream_response = {
        "provider_used": "brave-search-api",
        "provider_slug": "brave-search-api",
        "message": "brave-search-api upstream accepted",
        "result": {
            "selected_provider": "brave-search-api",
            "supported_provider_slugs": ["brave-search-api"],
        },
    }

    mock_response, mock_pool = _build_patches()
    mock_response.json.return_value = raw_upstream_response
    mock_response.text = json.dumps(raw_upstream_response)

    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_byok_payload_alias")
    )
    mock_attribution = MagicMock()
    mock_attribution.to_rhumb_block.return_value = {"provider": {"id": "brave-search-api"}}
    mock_attribution.to_response_headers.return_value = {"X-Rhumb-Provider": "brave-search-api"}

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch(
            "routes.capability_execute.get_receipt_service",
            return_value=mock_receipt_service,
        ),
        patch(
            "routes.capability_execute.build_attribution",
            new_callable=AsyncMock,
            return_value=mock_attribution,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search",
                    "credential_mode": "byok",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["upstream_response"] == expected_upstream_response

    receipt_input = mock_receipt_service.create_receipt.await_args.args[0]
    assert receipt_input.response_hash == capability_execute.hash_response_payload(
        expected_upstream_response
    )


@pytest.mark.anyio
async def test_execute_byok_failure_canonicalizes_alternate_provider_alias_text_when_structured_fields_are_already_canonical(app):
    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "brave-search",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "GET /res/v1/web/search",
                    "cost_per_call": "0.01",
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                }
            ]
        if path.startswith("scores?"):
            return [{"service_slug": "brave-search", "aggregate_recommendation_score": 8.9}]
        if path.startswith("services?slug=eq.brave-search&"):
            return [{"slug": "brave-search", "api_domain": "api.search.brave.com"}]
        if path.startswith("capability_executions?"):
            return []
        return []

    raw_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "fallback_provider": "people-data-labs",
        "message": "brave-search-api upstream failed after pdl fallback warmed",
        "error_message": "brave-search-api failed before pdl fallback",
        "result": {
            "provider_slug": "brave-search-api",
            "fallback_provider": "people-data-labs",
            "supported_provider_slugs": ["brave-search-api", "people-data-labs"],
            "detail": "Retry brave-search-api later or switch to pdl",
        },
    }
    expected_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "fallback_provider": "people-data-labs",
        "message": "brave-search-api upstream failed after people-data-labs fallback warmed",
        "error_message": "brave-search-api failed before people-data-labs fallback",
        "result": {
            "provider_slug": "brave-search-api",
            "fallback_provider": "people-data-labs",
            "supported_provider_slugs": ["brave-search-api", "people-data-labs"],
            "detail": "Retry brave-search-api later or switch to people-data-labs",
        },
    }

    mock_response, mock_pool = _build_patches()
    mock_response.status_code = 502
    mock_response.json.return_value = raw_upstream_response
    mock_response.text = json.dumps(raw_upstream_response)

    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_byok_canonical_context_failure")
    )
    mock_attribution = MagicMock()
    mock_attribution.to_rhumb_block.return_value = {"provider": {"id": "brave-search-api"}}
    mock_attribution.to_response_headers.return_value = {"X-Rhumb-Provider": "brave-search-api"}

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
        patch(
            "routes.capability_execute.get_receipt_service",
            return_value=mock_receipt_service,
        ),
        patch("routes.capability_execute._emit_execution_billing_event") as mock_billing_event,
        patch("routes.capability_execute._record_execution_audit_outcome") as mock_audit_outcome,
        patch(
            "routes.capability_execute.build_attribution",
            new_callable=AsyncMock,
            return_value=mock_attribution,
        ) as mock_build_attribution,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search-api",
                    "credential_mode": "byok",
                    "method": "GET",
                    "path": "/res/v1/web/search",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["upstream_status"] == 502
    assert data["upstream_response"] == expected_upstream_response
    assert data["receipt_id"] == "rcpt_byok_canonical_context_failure"
    assert resp.headers["X-Rhumb-Provider"] == "brave-search-api"

    receipt_input = mock_receipt_service.create_receipt.await_args.args[0]
    assert receipt_input.provider_id == "brave-search-api"
    assert receipt_input.error_message == "brave-search-api failed before people-data-labs fallback"
    assert receipt_input.response_hash == capability_execute.hash_response_payload(
        expected_upstream_response
    )
    assert mock_billing_event.call_args.kwargs["provider_slug"] == "brave-search-api"
    assert (
        mock_billing_event.call_args.kwargs["error_message"]
        == "brave-search-api failed before people-data-labs fallback"
    )
    assert mock_audit_outcome.call_args.kwargs["provider_slug"] == "brave-search-api"
    assert (
        mock_audit_outcome.call_args.kwargs["error_message"]
        == "brave-search-api failed before people-data-labs fallback"
    )
    assert mock_build_attribution.await_args.kwargs["provider_slug"] == "brave-search-api"


@pytest.mark.anyio
async def test_execute_agent_rate_limit_uses_durable_limiter(app):
    """Per-agent execute throttles should use the durable limiter, not in-memory dicts."""
    mock_limiter = MagicMock()
    mock_limiter.check_and_increment = AsyncMock(return_value=(False, 0))

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute._get_rate_limiter",
            new_callable=AsyncMock,
            return_value=mock_limiter,
        ),
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

    assert resp.status_code == 429
    assert resp.json()["detail"] == "Execution rate limit exceeded (30/min). Slow down."
    mock_limiter.check_and_increment.assert_awaited_once_with(
        "agent_exec:agent_cap_exec_test",
        30,
        60,
    )


@pytest.mark.anyio
async def test_execute_x402_wallet_rate_limit_uses_durable_limiter(app):
    """x402 wallet throttles should use the durable limiter before execution proceeds."""
    mock_limiter = MagicMock()
    mock_limiter.check_and_increment = AsyncMock(return_value=(False, 0))
    mock_replay_guard = MagicMock()
    mock_replay_guard.check_and_claim = AsyncMock(return_value=False)

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute._get_rate_limiter",
            new_callable=AsyncMock,
            return_value=mock_limiter,
        ),
        patch(
            "routes.capability_execute._get_replay_guard",
            new_callable=AsyncMock,
            return_value=mock_replay_guard,
        ),
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
                    "X-Payment": json.dumps(
                        {
                            "tx_hash": "0xabc123",
                            "wallet_address": "0xFEE123",
                            "network": "base",
                        }
                    ),
                },
            )

    assert resp.status_code == 429
    assert resp.json()["detail"] == "Rate limit exceeded for this wallet"
    mock_limiter.check_and_increment.assert_awaited_once_with(
        "wallet:0xfee123",
        60,
        60,
    )
    mock_replay_guard.check_and_claim.assert_awaited_once_with(
        "0xabc123",
        allow_fallback=False,
    )


@pytest.mark.anyio
async def test_execute_x402_replay_guard_failure_fails_closed(app):
    """Paid execution should fail closed if durable replay protection is unavailable."""
    mock_replay_guard = MagicMock()
    mock_replay_guard.check_and_claim = AsyncMock(side_effect=ReplayGuardUnavailable("DB down"))

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute._get_replay_guard",
            new_callable=AsyncMock,
            return_value=mock_replay_guard,
        ),
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
                    "X-Payment": json.dumps(
                        {
                            "tx_hash": "0xdeadbeef",
                            "wallet_address": "0xFEE123",
                            "network": "base",
                        }
                    ),
                },
            )

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Payment protection temporarily unavailable. Retry shortly."
    mock_replay_guard.check_and_claim.assert_awaited_once_with(
        "0xdeadbeef",
        allow_fallback=False,
    )


@pytest.mark.anyio
async def test_execute_x402_receipt_write_failure_fails_closed(app):
    """Paid execution should stop if the verified payment cannot be durably recorded."""
    mock_replay_guard = MagicMock()
    mock_replay_guard.check_and_claim = AsyncMock(return_value=False)

    with (
        patch.dict(os.environ, {"RHUMB_USDC_WALLET_ADDRESS": "0xRHUMB"}, clear=False),
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute._get_replay_guard",
            new_callable=AsyncMock,
            return_value=mock_replay_guard,
        ),
        patch(
            "routes.capability_execute.verify_usdc_payment",
            new_callable=AsyncMock,
            return_value={
                "valid": True,
                "tx_hash": "0xfeedface",
                "amount_atomic": "100",
                "from_address": "0xFEE123",
                "to_address": "0xRHUMB",
                "block_number": 123,
            },
        ),
        patch(
            "routes.capability_execute.supabase_insert_required",
            new_callable=AsyncMock,
            side_effect=SupabaseWriteUnavailable("down"),
        ),
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
                    "X-Payment": json.dumps(
                        {
                            "tx_hash": "0xfeedface",
                            "wallet_address": "0xFEE123",
                            "network": "base",
                        }
                    ),
                },
            )

    assert resp.status_code == 503
    assert resp.json()["detail"] == (
        "Payment may have been accepted, but durable recording is unavailable. "
        "Do not retry blindly; verify settlement first."
    )
    assert mock_replay_guard.check_and_claim.await_args_list[-1] == call(
        "0xfeedface",
        allow_fallback=False,
    )


@pytest.mark.anyio
async def test_execute_managed_daily_limit_uses_durable_limiter(app):
    """Managed daily throttles should use durable storage so limits survive restarts."""
    mock_limiter = MagicMock()
    mock_limiter.check_and_increment = AsyncMock(side_effect=[(True, 29), (False, 0)])
    managed_mapping = MANAGED_SAMPLE_MAPPINGS[1]

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_with_managed_option,
        ),
        patch(
            "routes.capability_execute._get_rate_limiter",
            new_callable=AsyncMock,
            return_value=mock_limiter,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            return_value=managed_mapping,
        ),
        patch(
            "services.upstream_budget.claim_provider_budget",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "provider": "resend",
                    "credential_mode": "rhumb_managed",
                    "body": {"to": "test@example.com"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 429
    assert "Daily managed execution limit exceeded" in resp.json()["detail"]
    assert mock_limiter.check_and_increment.await_args_list == [
        call("agent_exec:agent_cap_exec_test", 30, 60),
        call("managed_daily:agent_cap_exec_test", 200, 86400),
    ]


@pytest.mark.anyio
async def test_execute_managed_budget_authority_unavailable_is_honest(app):
    """Managed execute should surface authority outages distinctly from true provider exhaustion."""
    managed_mapping = MANAGED_SAMPLE_MAPPINGS[1]

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_with_managed_option,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            return_value=managed_mapping,
        ),
        patch(
            "services.upstream_budget.claim_provider_budget",
            new_callable=AsyncMock,
            return_value=(
                False,
                "Managed provider budget authority is temporarily unavailable. Retry once the durable budget store is healthy.",
            ),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "provider": "resend",
                    "credential_mode": "rhumb_managed",
                    "body": {"to": "test@example.com"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    data = resp.json()
    assert data["error"] == "managed_budget_authority_unavailable"
    assert "managed budget authority" in data["resolution"].lower()
    assert "temporarily unavailable" in data["message"].lower()


@pytest.mark.anyio
async def test_auto_resolves_to_managed_when_config_exists(app):
    """Execute defaults auto to rhumb_managed when a managed config exists."""
    managed_mapping = MANAGED_SAMPLE_MAPPINGS[1]

    async def mock_execute(
        self,
        capability_id,
        agent_id,
        body=None,
        params=None,
        service_slug=None,
        interface="rest",
        execution_id=None,
    ):
        return {
            "capability_id": capability_id,
            "provider_used": "resend",
            "credential_mode": "rhumb_managed",
            "upstream_status": 200,
            "upstream_response": {"id": "msg_auto_managed"},
            "latency_ms": 15.0,
            "execution_id": "exec_auto_managed",
        }

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_with_managed_option,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            return_value=managed_mapping,
        ) as mock_resolve_managed,
        patch(
            "services.upstream_budget.claim_provider_budget",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ) as mock_claim_budget,
        patch("services.rhumb_managed.RhumbManagedExecutor.execute", mock_execute),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={"body": {"to": "test@example.com"}},
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["credential_mode"] == "rhumb_managed"
    assert data["provider_used"] == "resend"
    mock_resolve_managed.assert_awaited_once()
    mock_claim_budget.assert_awaited_once_with("resend")


@pytest.mark.anyio
async def test_execute_managed_canonicalizes_alias_backed_provider_ids_for_receipt_path(app):
    managed_mapping = {
        "capability_id": "search.query",
        "service_slug": "brave-search",
        "credential_modes": ["byo", "rhumb_managed"],
        "auth_method": "api_key",
        "endpoint_pattern": "GET /res/v1/web/search",
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": 100,
    }

    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [managed_mapping]
        if path.startswith("capability_executions?"):
            return []
        return []

    async def mock_execute(
        self,
        capability_id,
        agent_id,
        body=None,
        params=None,
        service_slug=None,
        interface="rest",
        execution_id=None,
    ):
        return {
            "capability_id": capability_id,
            "provider_used": "brave-search",
            "credential_mode": "rhumb_managed",
            "upstream_status": 200,
            "upstream_response": {"ok": True},
            "latency_ms": 15.0,
            "execution_id": execution_id or "exec_managed_alias",
        }

    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_managed_alias")
    )

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch(
            "routes.capability_execute.supabase_insert_required",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "routes.capability_execute.supabase_patch_required",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            return_value=managed_mapping,
        ),
        patch(
            "services.upstream_budget.claim_provider_budget",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ),
        patch("services.rhumb_managed.RhumbManagedExecutor.execute", mock_execute),
        patch(
            "routes.capability_execute.get_receipt_service",
            return_value=mock_receipt_service,
        ),
        patch("routes.capability_execute._emit_execution_billing_event") as mock_billing_event,
        patch("routes.capability_execute._record_execution_audit_outcome") as mock_audit_outcome,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search",
                    "credential_mode": "rhumb_managed",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["receipt_id"] == "rcpt_managed_alias"

    receipt_input = mock_receipt_service.create_receipt.await_args.args[0]
    assert receipt_input.provider_id == "brave-search-api"
    assert mock_billing_event.call_args.kwargs["provider_slug"] == "brave-search-api"
    assert mock_audit_outcome.call_args.kwargs["provider_slug"] == "brave-search-api"


@pytest.mark.anyio
async def test_execute_managed_canonicalizes_alias_backed_provider_fields_in_result_payload(app):
    managed_mapping = {
        "capability_id": "search.query",
        "service_slug": "brave-search",
        "credential_modes": ["byo", "rhumb_managed"],
        "auth_method": "api_key",
        "endpoint_pattern": "GET /res/v1/web/search",
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": 100,
    }

    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [managed_mapping]
        if path.startswith("capability_executions?"):
            return []
        return []

    raw_upstream_response = {
        "provider_used": "brave-search",
        "message": "brave-search upstream accepted",
        "result": {
            "provider_slug": "brave-search",
            "fallback_providers": ["brave-search"],
        },
    }
    expected_upstream_response = {
        "provider_used": "brave-search-api",
        "message": "brave-search-api upstream accepted",
        "result": {
            "provider_slug": "brave-search-api",
            "fallback_providers": ["brave-search-api"],
        },
    }

    async def mock_execute(
        self,
        capability_id,
        agent_id,
        body=None,
        params=None,
        service_slug=None,
        interface="rest",
        execution_id=None,
    ):
        return {
            "capability_id": capability_id,
            "provider_used": "brave-search",
            "selected_provider": "brave-search",
            "credential_mode": "rhumb_managed",
            "upstream_status": 200,
            "upstream_response": raw_upstream_response,
            "latency_ms": 15.0,
            "execution_id": execution_id or "exec_managed_payload_alias",
        }

    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_managed_payload_alias")
    )

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch(
            "routes.capability_execute.supabase_insert_required",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "routes.capability_execute.supabase_patch_required",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            return_value=managed_mapping,
        ),
        patch(
            "services.upstream_budget.claim_provider_budget",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ),
        patch("services.rhumb_managed.RhumbManagedExecutor.execute", mock_execute),
        patch(
            "routes.capability_execute.get_receipt_service",
            return_value=mock_receipt_service,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search",
                    "credential_mode": "rhumb_managed",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["selected_provider"] == "brave-search-api"
    assert data["upstream_response"] == expected_upstream_response

    receipt_input = mock_receipt_service.create_receipt.await_args.args[0]
    assert receipt_input.response_hash == capability_execute.hash_response_payload(
        expected_upstream_response
    )


@pytest.mark.anyio
async def test_execute_managed_failure_canonicalizes_alternate_provider_alias_text_when_structured_fields_are_already_canonical(app):
    managed_mapping = {
        "capability_id": "search.query",
        "service_slug": "brave-search",
        "credential_modes": ["byo", "rhumb_managed"],
        "auth_method": "api_key",
        "endpoint_pattern": "GET /res/v1/web/search",
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": 100,
    }

    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [managed_mapping]
        if path.startswith("capability_executions?"):
            return []
        return []

    raw_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "fallback_provider": "people-data-labs",
        "message": "brave-search-api upstream failed after pdl fallback warmed",
        "error_message": "brave-search-api failed before pdl fallback",
        "result": {
            "provider_slug": "brave-search-api",
            "fallback_provider": "people-data-labs",
            "supported_provider_slugs": ["brave-search-api", "people-data-labs"],
            "detail": "Retry brave-search-api later or switch to pdl",
        },
    }
    expected_upstream_response = {
        "provider_used": "brave-search-api",
        "selected_provider": "brave-search-api",
        "fallback_provider": "people-data-labs",
        "message": "brave-search-api upstream failed after people-data-labs fallback warmed",
        "error_message": "brave-search-api failed before people-data-labs fallback",
        "result": {
            "provider_slug": "brave-search-api",
            "fallback_provider": "people-data-labs",
            "supported_provider_slugs": ["brave-search-api", "people-data-labs"],
            "detail": "Retry brave-search-api later or switch to people-data-labs",
        },
    }

    async def mock_execute(
        self,
        capability_id,
        agent_id,
        body=None,
        params=None,
        service_slug=None,
        interface="rest",
        execution_id=None,
    ):
        return {
            "capability_id": capability_id,
            "provider_used": "brave-search-api",
            "selected_provider": "brave-search-api",
            "credential_mode": "rhumb_managed",
            "upstream_status": 502,
            "upstream_response": raw_upstream_response,
            "latency_ms": 15.0,
            "execution_id": execution_id or "exec_managed_canonical_context_failure",
        }

    mock_receipt_service = MagicMock()
    mock_receipt_service.create_receipt = AsyncMock(
        return_value=MagicMock(receipt_id="rcpt_managed_canonical_context_failure")
    )
    mock_patch_required = AsyncMock(return_value=True)

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch(
            "routes.capability_execute.supabase_insert_required",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "routes.capability_execute.supabase_patch_required",
            mock_patch_required,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            return_value=managed_mapping,
        ),
        patch(
            "services.upstream_budget.claim_provider_budget",
            new_callable=AsyncMock,
            return_value=(True, "ok"),
        ),
        patch("services.rhumb_managed.RhumbManagedExecutor.execute", mock_execute),
        patch(
            "routes.capability_execute.get_receipt_service",
            return_value=mock_receipt_service,
        ),
        patch("routes.capability_execute._emit_execution_billing_event") as mock_billing_event,
        patch("routes.capability_execute._record_execution_audit_outcome") as mock_audit_outcome,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search-api",
                    "credential_mode": "rhumb_managed",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "brave-search-api"
    assert data["upstream_status"] == 502
    assert data["upstream_response"] == expected_upstream_response
    assert data["receipt_id"] == "rcpt_managed_canonical_context_failure"

    receipt_input = mock_receipt_service.create_receipt.await_args.args[0]
    assert receipt_input.provider_id == "brave-search-api"
    assert receipt_input.error_code == "502"
    assert receipt_input.error_message == "brave-search-api failed before people-data-labs fallback"
    assert receipt_input.response_hash == capability_execute.hash_response_payload(
        expected_upstream_response
    )

    final_patch = mock_patch_required.await_args_list[-1].args[1]
    assert final_patch["billing_status"] == "refunded"
    assert final_patch["error_message"] == "brave-search-api failed before people-data-labs fallback"
    assert mock_billing_event.call_args.kwargs["provider_slug"] == "brave-search-api"
    assert (
        mock_billing_event.call_args.kwargs["error_message"]
        == "brave-search-api failed before people-data-labs fallback"
    )
    assert mock_audit_outcome.call_args.kwargs["provider_slug"] == "brave-search-api"
    assert (
        mock_audit_outcome.call_args.kwargs["error_message"]
        == "brave-search-api failed before people-data-labs fallback"
    )


@pytest.mark.anyio
async def test_execute_managed_budget_exhaustion_keeps_canonical_public_provider_id(app):
    managed_mapping = {
        "capability_id": "search.query",
        "service_slug": "brave-search",
        "credential_modes": ["byo", "rhumb_managed"],
        "auth_method": "api_key",
        "endpoint_pattern": "GET /res/v1/web/search",
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": 100,
    }

    async def _mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [
                {
                    "id": "search.query",
                    "domain": "search",
                    "action": "query",
                    "description": "Web search",
                }
            ]
        if path.startswith("capability_services?"):
            return [managed_mapping]
        if path.startswith("capability_executions?"):
            return []
        return []

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_fetch,
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            return_value=managed_mapping,
        ),
        patch(
            "services.upstream_budget.claim_provider_budget",
            new_callable=AsyncMock,
            return_value=(
                False,
                "Provider 'brave-search' free-tier budget exhausted (2000/2000 requests). Use BYO credentials or try again after budget reset.",
            ),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/search.query/execute",
                json={
                    "provider": "brave-search-api",
                    "credential_mode": "rhumb_managed",
                    "body": {"q": "Rhumb API agent infrastructure"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 503
    data = resp.json()
    assert data["error"] == "provider_budget_exhausted"
    assert data["message"] == (
        "Provider 'brave-search-api' free-tier budget exhausted (2000/2000 requests). "
        "Use BYO credentials or try again after budget reset."
    )


@pytest.mark.anyio
async def test_auto_resolves_to_byo_when_no_config(app):
    """Execute defaults auto to byo when no managed config exists."""
    _, mock_pool = _build_patches()

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_with_managed_option,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_resolve_managed,
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch("httpx.AsyncClient") as MockHttpxClient,
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
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
    assert data["credential_mode"] == "byok"
    assert data["provider_used"] == "resend"
    mock_resolve_managed.assert_awaited_once()


@pytest.mark.anyio
async def test_explicit_byo_overrides_auto(app):
    """Explicit byo stays on byo even when a managed config exists."""
    _, mock_pool = _build_patches()

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_with_managed_option,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._resolve_managed_provider_mapping",
            new_callable=AsyncMock,
        ) as mock_resolve_managed,
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "credential_mode": "byo",
                    "provider": "sendgrid",
                    "method": "POST",
                    "path": "/v3/mail/send",
                    "body": {"to": "test@example.com"},
                },
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["credential_mode"] == "byok"
    assert data["provider_used"] == "sendgrid"
    mock_resolve_managed.assert_not_awaited()


@pytest.mark.anyio
async def test_idempotency_prevents_duplicate(app):
    """Idempotency key returns existing execution without re-executing."""
    mock_store = MagicMock()
    mock_store.claim = AsyncMock(return_value=MagicMock(execution_id="exec_existing123"))

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute._get_idempotency_store",
            new_callable=AsyncMock,
            return_value=mock_store,
        ),
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
    mock_store.claim.assert_awaited_once()


@pytest.mark.anyio
async def test_idempotency_unavailable_fails_closed(app):
    """Capability execute should reject when durable idempotency is unavailable."""
    mock_store = MagicMock()
    mock_store.claim = AsyncMock(side_effect=IdempotencyUnavailable("DB down"))

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute._get_idempotency_store",
            new_callable=AsyncMock,
            return_value=mock_store,
        ),
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

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Idempotency protection temporarily unavailable. Retry shortly."


@pytest.mark.anyio
async def test_execute_fails_when_execution_record_unavailable(app):
    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_insert_required",
            new_callable=AsyncMock,
            side_effect=SupabaseWriteUnavailable("down"),
        ),
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
    assert (
        resp.json()["detail"] == "Execution control plane temporarily unavailable. Retry shortly."
    )


@pytest.mark.anyio
async def test_execute_fails_when_final_execution_record_patch_unavailable(app):
    _, mock_pool = _build_patches()

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_patch_required",
            new_callable=AsyncMock,
            side_effect=SupabaseWriteUnavailable("down"),
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
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

    assert resp.status_code == 503
    assert resp.json()["detail"] == (
        "Execution may have completed, but durable recording failed. "
        "Do not retry blindly; verify side effects before retrying."
    )
    mock_pool.acquire.assert_awaited_once()


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
    body = resp.json()
    assert body["resolve_url"] == "/v1/capabilities/email.send/resolve"
    assert body["estimate_url"] == "/v1/capabilities/email.send/execute/estimate"
    assert body["available_providers"] == [
        {"provider": "sendgrid", "credential_modes": ["byok"]},
        {"provider": "resend", "credential_modes": ["byok"]},
    ]
    assert body["auth_handoff"]["recommended_path"] == "governed_api_key"
    auth_paths = {item["kind"]: item for item in body["auth_handoff"]["paths"]}
    assert auth_paths["governed_api_key"]["setup_url"] == "/auth/login"
    assert auth_paths["governed_api_key"]["retry_header"] == "X-Rhumb-Key"
    assert auth_paths["x402_per_call"]["setup_url"] == "/payments/agent"
    assert auth_paths["x402_per_call"]["retry_header"] == "X-Payment"


@pytest.mark.anyio
@pytest.mark.parametrize(("capability_id", "message"), DIRECT_AUTH_CASES)
async def test_direct_execute_requires_api_key_handoff(app, capability_id, message):
    """Direct AUD-18 execute rails return a structured API-key handoff when auth is missing."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/v1/capabilities/{capability_id}/execute", json={})

    assert resp.status_code == 401
    assert "x-payment" not in resp.headers
    body = resp.json()
    assert body["error"] == "authentication_required"
    assert body["message"] == message
    assert body["resolution"].startswith("Create or use a funded governed API key at /auth/login")
    assert "X-Rhumb-Key" in body["resolution"]
    assert body["resolve_url"] == f"/v1/capabilities/{capability_id}/resolve"
    assert body["credential_modes_url"] == f"/v1/capabilities/{capability_id}/credential-modes"
    assert body["auth_handoff"]["reason"] == "auth_required"
    assert body["auth_handoff"]["recommended_path"] == "governed_api_key"
    assert body["auth_handoff"]["retry_url"] == f"/v1/capabilities/{capability_id}/execute"
    auth_paths = {item["kind"]: item for item in body["auth_handoff"]["paths"]}
    assert set(auth_paths) == {"governed_api_key"}
    assert auth_paths["governed_api_key"]["retry_header"] == "X-Rhumb-Key"


@pytest.mark.anyio
@pytest.mark.parametrize(("capability_id", "message"), DIRECT_AUTH_CASES)
async def test_direct_execute_get_requires_api_key_handoff(app, capability_id, message):
    """Direct AUD-18 GET /execute stays auth-only and does not advertise x402."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/capabilities/{capability_id}/execute")

    assert resp.status_code == 401
    assert "x-payment" not in resp.headers
    body = resp.json()
    assert body["error"] == "authentication_required"
    assert body["message"] == message
    assert body["execute_url"] == f"/v1/capabilities/{capability_id}/execute"
    assert body["auth_handoff"]["reason"] == "auth_required"
    assert body["auth_handoff"]["recommended_path"] == "governed_api_key"
    auth_paths = {item["kind"]: item for item in body["auth_handoff"]["paths"]}
    assert set(auth_paths) == {"governed_api_key"}


@pytest.mark.anyio
async def test_direct_execute_get_with_api_key_returns_post_only_guidance(app):
    """Authenticated direct GET /execute should not fall back to x402 discovery."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/v1/capabilities/crm.object.describe/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
        )

    assert resp.status_code == 405
    assert "x-payment" not in resp.headers
    assert resp.headers.get("allow") == "POST"
    body = resp.json()
    assert body["error"] == "method_not_allowed"
    assert body["execute_url"] == "/v1/capabilities/crm.object.describe/execute"
    assert body["resolve_url"] == "/v1/capabilities/crm.object.describe/resolve"
    assert body["credential_modes_url"] == "/v1/capabilities/crm.object.describe/credential-modes"
    assert body["auth_handoff"]["reason"] == "post_required"
    assert body["auth_handoff"]["recommended_path"] == "governed_api_key"
    auth_paths = {item["kind"]: item for item in body["auth_handoff"]["paths"]}
    assert set(auth_paths) == {"governed_api_key"}


@pytest.mark.anyio
async def test_direct_execute_invalid_key_uses_governed_language(app, _mock_identity_store):
    """Direct execute invalid-key auth should use governed-key wording."""
    _mock_identity_store.verify_api_key_with_agent.return_value = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/v1/capabilities/crm.object.describe/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
        )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired governed API key"


@pytest.mark.anyio
async def test_execute_invalid_key_uses_governed_language(app, _mock_identity_store):
    """Execute invalid-key auth should use governed-key wording before any upstream work."""
    _mock_identity_store.verify_api_key_with_agent.return_value = None

    with patch(
        "routes.capability_execute.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_with_managed_option,
    ):
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

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired governed API key"


@pytest.mark.anyio
async def test_execute_invalid_key_surfaces_structured_handoff(app, _mock_identity_store):
    """Invalid governed keys should still include machine-readable next steps."""
    _mock_identity_store.verify_api_key_with_agent.return_value = None

    with patch(
        "routes.capability_execute.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_with_managed_option,
    ):
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

    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"] == "Invalid or expired governed API key"
    assert body["error"] == "invalid_api_key"
    assert body["execute_url"] == "/v1/capabilities/email.send/execute"
    assert body["auth_handoff"]["reason"] == "invalid_api_key"


@pytest.mark.anyio
async def test_direct_execute_with_payment_header_still_requires_api_key(app):
    """Direct AUD-18 execute rails should not reinterpret payment headers as x402 auth."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/capabilities/crm.object.describe/execute",
            json={},
            headers={"X-Payment": "fake-proof"},
        )

    assert resp.status_code == 401
    assert "x-payment" not in resp.headers
    body = resp.json()
    assert body["error"] == "authentication_required"
    assert body["auth_handoff"]["reason"] == "auth_required"
    auth_paths = {item["kind"]: item for item in body["auth_handoff"]["paths"]}
    assert set(auth_paths) == {"governed_api_key"}


@pytest.mark.anyio
@pytest.mark.parametrize(("capability_id", "message"), DIRECT_AUTH_CASES)
async def test_direct_execute_estimate_surfaces_auth_readiness_when_anonymous(app, capability_id, message):
    """Anonymous direct estimates should still carry the next auth step for execute."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/capabilities/{capability_id}/execute/estimate")

    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert body["error"] is None
    assert data["capability_id"] == capability_id
    assert data["execute_readiness"]["status"] == "auth_required"
    assert data["execute_readiness"]["message"] == message
    assert data["execute_readiness"]["resolve_url"] == f"/v1/capabilities/{capability_id}/resolve"
    assert data["execute_readiness"]["credential_modes_url"] == f"/v1/capabilities/{capability_id}/credential-modes"
    assert data["execute_readiness"]["auth_handoff"]["reason"] == "auth_required"
    assert data["execute_readiness"]["auth_handoff"]["retry_url"] == f"/v1/capabilities/{capability_id}/execute"
    auth_paths = {item["kind"]: item for item in data["execute_readiness"]["auth_handoff"]["paths"]}
    assert set(auth_paths) == {"governed_api_key"}


@pytest.mark.anyio
async def test_direct_execute_estimate_ignores_stale_catalog_mapping_rows(app):
    """Direct estimate should stay on synthetic provider truth even if stale catalog rows exist."""
    with patch(
        "routes.capability_execute.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_with_stale_direct_db_mapping,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/db.query.read/execute/estimate")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["capability_id"] == "db.query.read"
    assert data["provider"] == "postgresql"
    assert data["endpoint_pattern"] == "POST /v1/capabilities/db.query.read/execute"
    assert data["execute_readiness"]["status"] == "auth_required"
    assert data["execute_readiness"]["resolve_url"] == "/v1/capabilities/db.query.read/resolve"


@pytest.mark.anyio
async def test_execute_get_returns_x402_discovery(app):
    """GET execute acts as x402 discovery preflight instead of 405."""
    with patch(
        "routes.capability_execute.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/execute")

    assert resp.status_code == 402
    assert resp.headers["x-payment"] == "required"
    body = resp.json()
    assert body["x402Version"] == 1
    assert "resource" in body
    assert "accepts" in body
    assert body["resolve_url"] == "/v1/capabilities/email.send/resolve"
    assert body["estimate_url"] == "/v1/capabilities/email.send/execute/estimate"
    assert body["auth_handoff"]["recommended_path"] == "governed_api_key"


@pytest.mark.anyio
async def test_execute_post_raw_json_without_content_type_returns_x402_discovery(app):
    """POST execute should still return x402 discovery when JSON body lacks Content-Type."""
    with patch(
        "routes.capability_execute.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                content=json.dumps(
                    {
                        "provider": "sendgrid",
                        "method": "POST",
                        "path": "/v3/mail/send",
                        "body": {"to": "test@example.com"},
                    }
                ),
            )

    assert resp.status_code == 402
    assert resp.headers["x-payment"] == "required"
    body = resp.json()
    assert body["x402Version"] == 1
    assert "resource" in body
    assert "accepts" in body
    assert body["resolve_url"] == "/v1/capabilities/email.send/resolve"
    assert body["estimate_url"] == "/v1/capabilities/email.send/execute/estimate"
    assert body["auth_handoff"]["recommended_path"] == "governed_api_key"


@pytest.mark.anyio
async def test_execute_post_raw_json_without_content_type_accepts_authenticated_execute(app):
    """Authenticated execute should accept raw JSON bodies without Content-Type."""
    _, mock_pool = _build_patches()

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
        patch(
            "routes.capability_execute.supabase_insert", new_callable=AsyncMock, return_value=True
        ),
        patch(
            "routes.capability_execute._inject_auth_request_parts",
            side_effect=lambda slug, auth, h, body, params: (h, body, params),
        ),
        patch("routes.capability_execute.get_pool_manager", return_value=mock_pool),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/capabilities/email.send/execute",
                content=json.dumps(
                    {
                        "provider": "sendgrid",
                        "method": "POST",
                        "path": "/v3/mail/send",
                        "body": {"to": "test@example.com"},
                    }
                ),
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider_used"] == "sendgrid"
    assert data["upstream_status"] == 202


@pytest.mark.anyio
async def test_execute_get_unknown_capability_404(app):
    """GET execute keeps capability-not-found behavior for unknown ids."""
    with patch(
        "routes.capability_execute.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/nonexistent/execute")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "capability_not_found"
    assert body["search_url"] == "/v1/capabilities?search=nonexistent"


@pytest.mark.anyio
async def test_estimate_unknown_capability_suggests_capability_for_tool_alias(app):
    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_tool_alias_supabase,
        ),
        patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_tool_alias_supabase,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/Nano%20Banana%20Pro/execute/estimate")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "capability_not_found"
    assert body["search_url"] == "/v1/capabilities?search=Nano%20Banana%20Pro"
    assert body["suggested_capabilities"][0]["id"] == "ai.generate_image"


@pytest.mark.anyio
async def test_estimate_unknown_capability_suggests_capability_for_provider_alias(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?id=eq.Resend"):
            return []
        return _mock_supabase(path)

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
        patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/Resend/execute/estimate")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "capability_not_found"
    assert body["search_url"] == "/v1/capabilities?search=Resend"
    assert body["suggested_capabilities"][0]["id"] == "email.send"


@pytest.mark.anyio
async def test_execute_unknown_capability_ignores_stale_direct_provider_alias_rows(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            if "id=eq.Resend" in path:
                return []
            if "select=id,domain,action,description,input_hint,outcome" in path:
                return [
                    {
                        "id": "email.send",
                        "domain": "email",
                        "action": "send",
                        "description": "Send transactional email",
                        "input_hint": "Email payload",
                        "outcome": "Email accepted",
                    },
                    {
                        "id": "db.query.read",
                        "domain": "database",
                        "action": "query_read",
                        "description": "Run read-only SQL queries",
                        "input_hint": "SQL query and connection_ref",
                        "outcome": "Rows returned",
                    },
                ]
        if path.startswith("capability_services?"):
            if "select=capability_id,service_slug" in path:
                return [
                    {"capability_id": "email.send", "service_slug": "resend"},
                    {"capability_id": "db.query.read", "service_slug": "resend"},
                ]
            return []
        if path.startswith("services?"):
            return [{"slug": "resend", "name": "Resend"}]
        return []

    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
        patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            execute_resp = await client.get("/v1/capabilities/Resend/execute")
            estimate_resp = await client.get("/v1/capabilities/Resend/execute/estimate")

    for resp in (execute_resp, estimate_resp):
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "capability_not_found"
        assert body["search_url"] == "/v1/capabilities?search=Resend"
        assert body["suggested_capabilities"][0]["id"] == "email.send"
        assert all(item["id"] != "db.query.read" for item in body["suggested_capabilities"])


@pytest.mark.anyio
async def test_estimate_auto_select(app):
    """GET estimate without provider auto-selects best."""
    with (
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase,
        ),
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
