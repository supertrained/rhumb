"""Tests for Rhumb-managed execution (Mode 2, R16).

Tests:
- RhumbManagedExecutor service
- GET /v1/capabilities/rhumb-managed catalog
- POST execute with credential_mode=rhumb_managed
- Security: no credential leakage in responses
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app

# Bypass key must match conftest.BYPASS_KEY so the autouse identity-store
# fixture resolves it to the pre-seeded bypass agent.
_BYPASS_KEY = "rhumb_test_bypass_key_0000"


@pytest.fixture
def app():
    return create_app()


@pytest.fixture(autouse=True)
def _mock_required_execution_insert():
    with patch(
        "routes.capability_execute.supabase_insert_required",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_required_execution_patch():
    with patch(
        "routes.capability_execute.supabase_patch_required",
        new_callable=AsyncMock,
        return_value=[{}],
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_rate_limiter():
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
    with patch(
        "routes.capability_execute.check_billing_health",
        new_callable=AsyncMock,
        return_value=(True, "ok"),
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_managed_provider_budget():
    with patch(
        "services.upstream_budget.claim_provider_budget",
        new_callable=AsyncMock,
        return_value=(True, None),
    ):
        yield


# ── RhumbManagedExecutor unit tests ────────────────────────────


@pytest.mark.anyio
async def test_managed_executor_is_managed(monkeypatch):
    """is_managed returns True when a managed config exists."""

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [{"id": 1}]
        return []

    with patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        assert await executor.is_managed("email.send") is True


@pytest.mark.anyio
async def test_managed_executor_not_managed(monkeypatch):
    """is_managed returns False when no managed config exists."""

    async def mock_fetch(path):
        return []

    with patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        assert await executor.is_managed("nonexistent.action") is False


@pytest.mark.anyio
async def test_managed_executor_list(monkeypatch):
    """list_managed returns enabled managed capabilities."""

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "capability_id": "email.send",
                    "service_slug": "resend",
                    "description": "Send email via Resend",
                    "daily_limit_per_agent": 100,
                },
            ]
        return []

    with patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        managed = await executor.list_managed()
        assert len(managed) == 1
        assert managed[0]["capability_id"] == "email.send"


@pytest.mark.anyio
async def test_managed_executor_prelogged_execution_uses_required_patch(monkeypatch):
    """Precreated execution rows should be updated in place, not silently fall back to insert."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_RESEND_API_KEY", "re_test_managed")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1,
                    "capability_id": "email.send",
                    "service_slug": "resend",
                    "description": "Managed email send",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_RESEND_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/emails",
                    "default_headers": {},
                    "daily_limit_per_agent": 100,
                }
            ]
        if "services?slug=eq.resend" in path:
            return [{"api_domain": "api.resend.com"}]
        return []

    required_patch_calls: list[tuple[str, dict]] = []
    insert_calls: list[tuple[str, dict]] = []

    async def mock_patch_required(path, payload):
        required_patch_calls.append((path, payload))
        return [payload]

    async def mock_insert(table, payload):
        insert_calls.append((table, payload))
        return {"id": payload.get("id")}

    async def mock_patch(path, payload):
        raise AssertionError("prelogged managed execution should not use best-effort patch")

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"id": "msg_prelogged", "object": "email"}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            self.base_url = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_patch_required", side_effect=mock_patch_required),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="email.send",
            agent_id="agent_prelogged",
            body={"to": "user@example.com"},
            service_slug="resend",
            execution_id="exec_prelogged_123",
        )

    assert result["execution_id"] == "exec_prelogged_123"
    assert len(required_patch_calls) == 1
    assert required_patch_calls[0][0] == "capability_executions?id=eq.exec_prelogged_123"
    assert insert_calls == []


# ── Catalog endpoint ──────────────────────────────────────────


@pytest.mark.anyio
async def test_managed_catalog_endpoint(app):
    """GET /v1/capabilities/rhumb-managed returns managed capabilities."""

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "capability_id": "email.send",
                    "service_slug": "resend",
                    "description": "Send email via Resend",
                    "daily_limit_per_agent": 100,
                },
            ]
        if "capabilities?" in path and "id=in." in path:
            return [
                {
                    "id": "email.send",
                    "domain": "email",
                    "action": "send",
                    "description": "Send transactional email",
                }
            ]
        return []

    with (
        patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/v1/capabilities/rhumb-managed")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["count"] == 1
    assert data["managed_capabilities"][0]["capability_id"] == "email.send"
    assert data["managed_capabilities"][0]["domain"] == "email"


@pytest.mark.anyio
async def test_managed_catalog_empty(app):
    """Managed catalog returns empty list when no managed capabilities."""

    async def mock_fetch(path):
        return []

    with (
        patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/v1/capabilities/rhumb-managed")

    assert resp.status_code == 200
    assert resp.json()["data"]["count"] == 0


# ── Execute with rhumb_managed mode ──────────────────────────


@pytest.mark.anyio
async def test_execute_rhumb_managed_mode(app, monkeypatch):
    """Execute with credential_mode=rhumb_managed delegates to RhumbManagedExecutor."""
    import httpx

    monkeypatch.setenv("RHUMB_CREDENTIAL_RESEND_API_KEY", "re_test_managed")

    call_log = []

    async def mock_fetch(path):
        call_log.append(("fetch", path))
        if path.startswith("capabilities?") and "id=eq." in path:
            return [
                {"id": "email.send", "domain": "email", "action": "send", "description": "Send"}
            ]
        if "capability_services?" in path:
            return [{
                "service_slug": "resend",
                "credential_modes": ["rhumb_managed"],
                "auth_method": "api_key",
                "endpoint_pattern": "POST /emails",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": None,
            }]
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1,
                    "capability_id": "email.send",
                    "service_slug": "resend",
                    "description": "Managed email send",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_RESEND_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/emails",
                    "default_headers": {},
                    "daily_limit_per_agent": 100,
                }
            ]
        if "services?" in path and "capability_services?" not in path:
            return [{"slug": "resend", "api_domain": "api.resend.com"}]
        return []

    async def mock_insert(table, payload):
        call_log.append(("insert", table, payload))
        return {"id": payload.get("id")}

    # Mock at the executor's execute method to avoid httpx.AsyncClient global patch
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
            "upstream_response": {"id": "msg_123", "object": "email"},
            "latency_ms": 42.0,
            "execution_id": "exec_test123",
        }

    with (
        patch("routes.capability_execute.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.RhumbManagedExecutor.execute", mock_execute),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "credential_mode": "rhumb_managed",
                    "body": {
                        "from": "test@rhumb.dev",
                        "to": "user@example.com",
                        "subject": "Test",
                        "html": "<p>Hello</p>",
                    },
                },
                headers={"X-Rhumb-Key": _BYPASS_KEY},
            )

    assert resp.status_code == 200
    result = resp.json()["data"]
    assert result["credential_mode"] == "rhumb_managed"
    assert result["provider_used"] == "resend"
    assert result["upstream_status"] == 200
    assert "execution_id" in result


@pytest.mark.anyio
async def test_execute_rhumb_managed_no_credential_leakage(app, monkeypatch):
    """Managed execution response never contains credential values."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_RESEND_API_KEY", "re_SECRET_VALUE_12345")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1,
                    "capability_id": "email.send",
                    "service_slug": "resend",
                    "description": "Managed email send",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_RESEND_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/emails",
                    "default_headers": {},
                    "daily_limit_per_agent": 100,
                }
            ]
        if path.startswith("capabilities?") and "id=eq." in path:
            return [
                {"id": "email.send", "domain": "email", "action": "send", "description": "Send"}
            ]
        if "capability_services?" in path:
            return [{
                "service_slug": "resend",
                "credential_modes": ["rhumb_managed"],
                "auth_method": "api_key",
                "endpoint_pattern": "POST /emails",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": None,
            }]
        return []

    # Mock executor to return a result that we can inspect for leakage
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
            "upstream_response": {"id": "msg_456"},
            "latency_ms": 35.0,
            "execution_id": "exec_leak_test",
        }

    with (
        patch("routes.capability_execute.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.RhumbManagedExecutor.execute", mock_execute),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/v1/capabilities/email.send/execute",
                json={"credential_mode": "rhumb_managed", "body": {}},
                headers={"X-Rhumb-Key": _BYPASS_KEY},
            )

    assert resp.status_code == 200
    response_text = resp.text
    assert "re_SECRET_VALUE_12345" not in response_text
    assert "RHUMB_CREDENTIAL_RESEND_API_KEY" not in response_text


@pytest.mark.anyio
async def test_execute_rhumb_managed_missing_env_var(app, monkeypatch):
    """Managed execution fails gracefully when env var is missing."""
    monkeypatch.delenv("RHUMB_CREDENTIAL_RESEND_API_KEY", raising=False)

    async def mock_cap_fetch(path):
        if path.startswith("capabilities?") and "id=eq." in path:
            return [
                {"id": "email.send", "domain": "email", "action": "send", "description": "Send"}
            ]
        if "capability_services?" in path:
            return [{
                "service_slug": "resend",
                "credential_modes": ["rhumb_managed"],
                "auth_method": "api_key",
                "endpoint_pattern": "POST /emails",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": None,
            }]
        return []

    async def mock_managed_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1,
                    "capability_id": "email.send",
                    "service_slug": "resend",
                    "description": "Managed",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_RESEND_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/emails",
                    "default_headers": {},
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?" in path and "capability_services?" not in path:
            return [{"slug": "resend", "api_domain": "api.resend.com"}]
        return []

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_managed_fetch),
        patch("routes.capability_execute.supabase_fetch", side_effect=mock_cap_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/v1/capabilities/email.send/execute",
                json={"credential_mode": "rhumb_managed", "body": {}},
                headers={"X-Rhumb-Key": _BYPASS_KEY},
            )

    assert resp.status_code == 503
    assert "credential" in resp.json()["detail"].lower()
    assert "RHUMB_CREDENTIAL_RESEND_API_KEY" not in resp.json()["detail"]


@pytest.mark.anyio
async def test_execute_byo_still_requires_method_path(app):
    """BYO mode execution still requires method and path."""

    async def mock_fetch(path):
        if path.startswith("capabilities?") and "id=eq." in path:
            return [
                {"id": "email.send", "domain": "email", "action": "send", "description": "Send"}
            ]
        return []

    with patch("routes.capability_execute.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/v1/capabilities/email.send/execute",
                json={"credential_mode": "byo", "body": {}},
                headers={"X-Rhumb-Key": _BYPASS_KEY},
            )

    assert resp.status_code == 400
    assert "method and path" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_execute_managed_omits_method_path(app, monkeypatch):
    """Managed mode does not require method/path — uses defaults from config."""

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1,
                    "capability_id": "email.send",
                    "service_slug": "resend",
                    "description": "Managed email send",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_RESEND_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/emails",
                    "default_headers": {},
                    "daily_limit_per_agent": 100,
                }
            ]
        if path.startswith("capabilities?") and "id=eq." in path:
            return [
                {"id": "email.send", "domain": "email", "action": "send", "description": "Send"}
            ]
        if "capability_services?" in path:
            return [{
                "service_slug": "resend",
                "credential_modes": ["rhumb_managed"],
                "auth_method": "api_key",
                "endpoint_pattern": "POST /emails",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": None,
            }]
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
            "provider_used": "resend",
            "credential_mode": "rhumb_managed",
            "upstream_status": 200,
            "upstream_response": {"id": "msg_789"},
            "latency_ms": 28.0,
            "execution_id": "exec_omit_test",
        }

    with (
        patch("routes.capability_execute.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.RhumbManagedExecutor.execute", mock_execute),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # No method or path — managed mode uses defaults
            resp = await c.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "credential_mode": "rhumb_managed",
                    "body": {"from": "a@b.com", "to": "c@d.com", "subject": "Hi", "html": "hey"},
                },
                headers={"X-Rhumb-Key": _BYPASS_KEY},
            )

    assert resp.status_code == 200
    assert resp.json()["data"]["credential_mode"] == "rhumb_managed"


@pytest.mark.anyio
async def test_get_managed_config_normalizes_canonical_alias():
    """Canonical/public aliases should resolve to proxy slugs in managed config lookup."""
    seen_paths: list[str] = []

    async def mock_fetch(path):
        seen_paths.append(path)
        if "service_slug=eq.brave-search-api" in path:
            return []
        if "service_slug=eq.brave-search" in path:
            return [{"id": 1, "capability_id": "search.query", "service_slug": "brave-search"}]
        return []

    with patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.get_managed_config("search.query", "brave-search-api")

    assert result["service_slug"] == "brave-search"
    assert any("service_slug=eq.brave-search-api" in path for path in seen_paths)
    assert any("service_slug=eq.brave-search" in path for path in seen_paths)


@pytest.mark.anyio
async def test_get_managed_config_accepts_proxy_alias_for_canonical_row():
    """Proxy aliases like ``pdl`` should find canonical managed-config rows."""
    seen_paths: list[str] = []

    async def mock_fetch(path):
        seen_paths.append(path)
        if "service_slug=eq.pdl" in path:
            return []
        if "service_slug=eq.people-data-labs" in path:
            return [
                {
                    "id": 144,
                    "capability_id": "data.enrich_person",
                    "service_slug": "people-data-labs",
                }
            ]
        return []

    with patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.get_managed_config("data.enrich_person", "pdl")

    assert result["service_slug"] == "people-data-labs"
    assert any("service_slug=eq.pdl" in path for path in seen_paths)
    assert any("service_slug=eq.people-data-labs" in path for path in seen_paths)


@pytest.mark.anyio
async def test_managed_executor_post_merges_params_into_body_and_marks_4xx_failure(monkeypatch):
    """POST managed executions should merge params into body and treat 4xx as failure."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_TAVILY_API_KEY", "tvly_test_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 321,
                    "capability_id": "search.query",
                    "service_slug": "tavily",
                    "description": "Managed Tavily search",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_TAVILY_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/search",
                    "default_headers": {},
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?slug=eq.tavily" in path:
            return [{"api_domain": "api.tavily.com"}]
        return []

    async def mock_insert(table, payload):
        return {"id": payload.get("id")}

    patched_payloads: list[dict] = []

    async def mock_patch(path, payload):
        patched_payloads.append(payload)
        return [payload]

    captured: dict = {}

    class DummyResponse:
        status_code = 422

        def json(self):
            return {"detail": [{"msg": "Field required", "loc": ["body", "query"]}]}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["base_url"] = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="search.query",
            agent_id="agent_tavily_test",
            params={
                "query": "best AI agent observability tools",
                "search_depth": "basic",
                "max_results": 5,
            },
            service_slug="tavily",
        )

    assert result["provider_used"] == "tavily"
    assert result["upstream_status"] == 422
    assert captured["base_url"] == "https://api.tavily.com"
    assert captured["method"] == "POST"
    assert captured["url"] == "/search"
    assert not captured["params"]
    assert captured["json"]["api_key"] == "tvly_test_secret"
    assert captured["json"]["query"] == "best AI agent observability tools"
    assert captured["json"]["search_depth"] == "basic"
    assert captured["json"]["max_results"] == 5
    assert patched_payloads[-1]["success"] is False
    assert patched_payloads[-1]["upstream_status"] == 422


@pytest.mark.anyio
async def test_managed_executor_brave_search_maps_query_to_q(monkeypatch):
    """Brave managed executions should translate logical query fields to Brave's q/count params."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_BRAVE_SEARCH_API_KEY", "brave_test_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 654,
                    "capability_id": "search.query",
                    "service_slug": "brave-search",
                    "description": "Managed Brave search",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_BRAVE_SEARCH_API_KEY"],
                    "default_method": "GET",
                    "default_path": "/res/v1/web/search",
                    "default_headers": {"Accept": "application/json"},
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?slug=eq.brave-search" in path:
            return [{"api_domain": "api.search.brave.com"}]
        return []

    async def mock_insert(table, payload):
        return {"id": payload.get("id")}

    async def mock_patch(path, payload):
        return [payload]

    captured: dict = {}

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"type": "search", "web": {"results": []}}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["base_url"] = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="search.query",
            agent_id="agent_brave_test",
            params={
                "query": "best AI agent observability tools",
                "numResults": 3,
            },
            service_slug="brave-search-api",
        )

    assert result["provider_used"] == "brave-search"
    assert captured["base_url"] == "https://api.search.brave.com"
    assert captured["method"] == "GET"
    assert captured["url"] == "/res/v1/web/search"
    assert captured["json"] is None
    assert captured["params"]["q"] == "best AI agent observability tools"
    assert captured["params"]["count"] == 3
    assert "query" not in captured["params"]
    assert "numResults" not in captured["params"]
    assert captured["headers"]["X-Subscription-Token"] == "brave_test_secret"


@pytest.mark.anyio
async def test_managed_executor_google_ai_uses_x_goog_api_key(monkeypatch):
    """Google AI managed execution should use x-goog-api-key, not Bearer auth."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY", "gemini_test_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 999,
                    "capability_id": "ai.generate_text",
                    "service_slug": "google-ai",
                    "description": "Managed Google AI text generation",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/v1beta/models/{model}:generateContent",
                    "default_headers": {"Content-Type": "application/json"},
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?slug=eq.google-ai" in path:
            return [{"api_domain": "generativelanguage.googleapis.com"}]
        return []

    async def mock_insert(table, payload):
        return {"id": payload.get("id")}

    async def mock_patch(path, payload):
        return [payload]

    captured: dict = {}

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["base_url"] = kwargs.get("base_url")
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="ai.generate_text",
            agent_id="agent_google_test",
            body={
                "model": "gemini-3-flash-preview",
                "contents": [{"parts": [{"text": "Say hi"}]}],
            },
            service_slug="google-ai",
        )

    assert result["provider_used"] == "google-ai"
    assert captured["base_url"] == "https://generativelanguage.googleapis.com"
    assert captured["method"] == "POST"
    assert captured["url"] == "/v1beta/models/gemini-3-flash-preview:generateContent"
    assert captured["headers"]["x-goog-api-key"] == "gemini_test_secret"
    assert "Authorization" not in captured["headers"]
    assert captured["headers"]["Content-Type"] == "application/json"


@pytest.mark.anyio
async def test_managed_executor_algolia_accepts_index_alias_and_strips_path_param_from_body(
    monkeypatch,
):
    """Algolia managed execution should accept index aliases and keep them out of the POST body."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_ALGOLIA_API_KEY", "algolia_test_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1701,
                    "capability_id": "search.autocomplete",
                    "service_slug": "algolia",
                    "description": "Managed Algolia autocomplete",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_ALGOLIA_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/1/indexes/{indexName}/query",
                    "default_headers": {"X-Algolia-Application-Id": "80LYFTF37Y"},
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?slug=eq.algolia" in path:
            return [{"api_domain": "80LYFTF37Y-dsn.algolia.net"}]
        return []

    async def mock_insert(table, payload):
        return {"id": payload.get("id")}

    async def mock_patch(path, payload):
        return [payload]

    captured: dict = {}

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"hits": [{"objectID": "1", "name": "Rhumb Runtime Test"}], "nbHits": 1}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["base_url"] = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="search.autocomplete",
            agent_id="agent_algolia_test",
            body={
                "index": "rhumb_test",
                "query": "rhumb",
            },
            service_slug="algolia",
        )

    assert result["provider_used"] == "algolia"
    assert captured["base_url"] == "https://80LYFTF37Y-dsn.algolia.net"
    assert captured["method"] == "POST"
    assert captured["url"] == "/1/indexes/rhumb_test/query"
    assert captured["json"] == {"query": "rhumb"}
    assert captured["params"] == {}
    assert captured["headers"]["X-Algolia-Application-Id"] == "80LYFTF37Y"
    assert captured["headers"]["X-Algolia-API-Key"] == "algolia_test_secret"


@pytest.mark.anyio
async def test_managed_executor_missing_path_template_param_returns_clear_400(monkeypatch):
    """Managed execution should fail clearly when a templated path input is missing."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_ALGOLIA_API_KEY", "algolia_test_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1702,
                    "capability_id": "search.autocomplete",
                    "service_slug": "algolia",
                    "description": "Managed Algolia autocomplete",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_ALGOLIA_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/1/indexes/{indexName}/query",
                    "default_headers": {"X-Algolia-Application-Id": "80LYFTF37Y"},
                    "daily_limit_per_agent": None,
                }
            ]
        return []

    with patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        with pytest.raises(Exception) as exc_info:
            await executor.execute(
                capability_id="search.autocomplete",
                agent_id="agent_algolia_missing_index",
                body={"query": "rhumb"},
                service_slug="algolia",
            )

    assert "Missing required managed path parameter(s): indexName" in str(exc_info.value)


@pytest.mark.anyio
async def test_managed_executor_emailable_verify_normalizes_email_and_uses_bearer_auth(monkeypatch):
    """Emailable single verify should normalize email aliases and use bearer auth."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_EMAILABLE_API_KEY", "ema_test_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1301,
                    "capability_id": "email.verify",
                    "service_slug": "emailable",
                    "description": "Managed Emailable verify",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_EMAILABLE_API_KEY"],
                    "default_method": "GET",
                    "default_path": "/v1/verify",
                    "default_headers": {},
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?slug=eq.emailable" in path:
            return [{"api_domain": "api.emailable.com"}]
        return []

    async def mock_insert(table, payload):
        return {"id": payload.get("id")}

    async def mock_patch(path, payload):
        return [payload]

    captured: dict = {}

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"email": "john@example.com", "state": "deliverable", "score": 95}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["base_url"] = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="email.verify",
            agent_id="agent_emailable_verify_test",
            params={
                "email_address": "john@example.com",
                "smtp_check": False,
                "accept_all_check": True,
                "max_wait_seconds": 7,
            },
            service_slug="emailable",
        )

    assert result["provider_used"] == "emailable"
    assert captured["base_url"] == "https://api.emailable.com"
    assert captured["method"] == "GET"
    assert captured["url"] == "/v1/verify"
    assert captured["json"] is None
    assert captured["params"] == {
        "email": "john@example.com",
        "smtp": False,
        "accept_all": True,
        "timeout": 7,
    }
    assert captured["headers"]["Authorization"] == "Bearer ema_test_secret"


@pytest.mark.anyio
async def test_managed_executor_emailable_batch_verify_joins_inputs(monkeypatch):
    """Emailable batch verify should join list inputs and honor callback aliases."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_EMAILABLE_API_KEY", "ema_batch_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1302,
                    "capability_id": "email.batch_verify",
                    "service_slug": "emailable",
                    "description": "Managed Emailable batch verify",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_EMAILABLE_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/v1/batch",
                    "default_headers": {"Content-Type": "application/json"},
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?slug=eq.emailable" in path:
            return [{"api_domain": "api.emailable.com"}]
        return []

    async def mock_insert(table, payload):
        return {"id": payload.get("id")}

    async def mock_patch(path, payload):
        return [payload]

    captured: dict = {}

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"message": "Batch successfully created.", "id": "batch_123"}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["base_url"] = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="email.batch_verify",
            agent_id="agent_emailable_batch_test",
            body={
                "emails": ["tim@example.com", "john@example.com"],
                "callback_url": "https://rhumb.dev/hooks/emailable",
                "response_fields": ["email", "state", "score"],
                "retries": False,
            },
            service_slug="emailable",
        )

    assert result["provider_used"] == "emailable"
    assert captured["base_url"] == "https://api.emailable.com"
    assert captured["method"] == "POST"
    assert captured["url"] == "/v1/batch"
    assert captured["params"] == {}
    assert captured["json"] == {
        "emails": "tim@example.com,john@example.com",
        "url": "https://rhumb.dev/hooks/emailable",
        "response_fields": "email,state,score",
        "retries": False,
    }
    assert captured["headers"]["Authorization"] == "Bearer ema_batch_secret"
    assert captured["headers"]["Content-Type"] == "application/json"


@pytest.mark.anyio
async def test_managed_executor_airship_send_to_user_normalizes_and_uses_validate_path(monkeypatch):
    """Airship send_to_user should normalize named users and switch to validate path."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_AIRSHIP_BASIC_AUTH", "app_key:master_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1201,
                    "capability_id": "push_notification.send_to_user",
                    "service_slug": "airship",
                    "description": "Managed Airship named-user push",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_AIRSHIP_BASIC_AUTH"],
                    "default_method": "POST",
                    "default_path": "/api/push",
                    "default_headers": {
                        "Accept": "application/vnd.urbanairship+json; version=3",
                        "Content-Type": "application/json",
                    },
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?slug=eq.airship" in path:
            return [{"api_domain": "go.urbanairship.com"}]
        return []

    async def mock_insert(table, payload):
        return {"id": payload.get("id")}

    async def mock_patch(path, payload):
        return [payload]

    captured: dict = {}

    class DummyResponse:
        status_code = 202

        def json(self):
            return {"ok": True, "operation_id": "airship_validate_123"}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["base_url"] = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="push_notification.send_to_user",
            agent_id="agent_airship_user_test",
            body={
                "message": "Hello from Rhumb",
                "named_user_id": "user_123",
                "device_types": ["ios"],
                "validate_only": True,
            },
            service_slug="airship",
        )

    assert result["provider_used"] == "airship"
    assert captured["base_url"] == "https://go.urbanairship.com"
    assert captured["method"] == "POST"
    assert captured["url"] == "/api/push/validate"
    assert captured["params"] == {}
    assert captured["json"] == {
        "audience": {"named_user": "user_123"},
        "notification": {"alert": "Hello from Rhumb"},
        "device_types": ["ios"],
    }
    assert "validate_only" not in captured["json"]


@pytest.mark.anyio
async def test_managed_executor_airship_topic_publish_normalizes_tag_group(monkeypatch):
    """Airship topic publish should map logical topic inputs to tag/group audience."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_AIRSHIP_BASIC_AUTH", "app_key:master_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1202,
                    "capability_id": "push_topic.publish",
                    "service_slug": "airship",
                    "description": "Managed Airship tag-group push",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_AIRSHIP_BASIC_AUTH"],
                    "default_method": "POST",
                    "default_path": "/api/push",
                    "default_headers": {
                        "Accept": "application/vnd.urbanairship+json; version=3",
                        "Content-Type": "application/json",
                    },
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?slug=eq.airship" in path:
            return [{"api_domain": "go.urbanairship.com"}]
        return []

    async def mock_insert(table, payload):
        return {"id": payload.get("id")}

    async def mock_patch(path, payload):
        return [payload]

    captured: dict = {}

    class DummyResponse:
        status_code = 202

        def json(self):
            return {"ok": True, "operation_id": "airship_push_456"}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["base_url"] = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="push_topic.publish",
            agent_id="agent_airship_topic_test",
            params={
                "topic": "trial-expiring",
                "topic_group": "lifecycle",
                "alert": "Your trial ends soon",
                "device_types": ["ios", "android"],
            },
            service_slug="airship",
        )

    assert result["provider_used"] == "airship"
    assert captured["base_url"] == "https://go.urbanairship.com"
    assert captured["url"] == "/api/push"
    assert captured["params"] == {}
    assert captured["json"] == {
        "audience": {"tag": "trial-expiring", "group": "lifecycle"},
        "notification": {"alert": "Your trial ends soon"},
        "device_types": ["ios", "android"],
    }


@pytest.mark.anyio
async def test_managed_executor_airship_uses_basic_auth_and_preserves_accept_header(monkeypatch):
    """Airship managed execution should use basic auth and keep Airship's Accept header."""
    raw_basic = "app_key:master_secret"
    monkeypatch.setenv("RHUMB_CREDENTIAL_AIRSHIP_BASIC_AUTH", raw_basic)

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1203,
                    "capability_id": "push_notification.send",
                    "service_slug": "airship",
                    "description": "Managed Airship push",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_AIRSHIP_BASIC_AUTH"],
                    "default_method": "POST",
                    "default_path": "/api/push",
                    "default_headers": {
                        "Accept": "application/vnd.urbanairship+json; version=3",
                        "Content-Type": "application/json",
                    },
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?slug=eq.airship" in path:
            return [{"api_domain": "go.urbanairship.com"}]
        return []

    async def mock_insert(table, payload):
        return {"id": payload.get("id")}

    async def mock_patch(path, payload):
        return [payload]

    captured: dict = {}

    class DummyResponse:
        status_code = 202

        def json(self):
            return {"ok": True, "operation_id": "airship_push_789"}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["base_url"] = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="push_notification.send",
            agent_id="agent_airship_auth_test",
            body={
                "audience": {"named_user": "existing_user"},
                "notification": {"alert": "Already normalized"},
                "device_types": ["ios"],
            },
            service_slug="airship",
        )

    assert result["provider_used"] == "airship"
    assert captured["base_url"] == "https://go.urbanairship.com"
    assert captured["url"] == "/api/push"
    assert captured["headers"]["Accept"] == "application/vnd.urbanairship+json; version=3"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["headers"]["Authorization"] == (
        f"Basic {base64.b64encode(raw_basic.encode()).decode()}"
    )
    assert captured["json"]["audience"] == {"named_user": "existing_user"}
    assert captured["json"]["notification"] == {"alert": "Already normalized"}


@pytest.mark.anyio
async def test_managed_executor_mindee_uses_token_auth_and_document_multipart(monkeypatch):
    """Mindee managed execution should use Token auth and `document` multipart uploads."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_MINDEE_API_KEY", "mindee_test_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1401,
                    "capability_id": "invoice.extract",
                    "service_slug": "mindee",
                    "description": "Managed Mindee invoice extraction",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_MINDEE_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/v1/products/mindee/financial_document/v1/predict",
                    "default_headers": {},
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?slug=eq.mindee" in path:
            return [{"api_domain": "api.mindee.net"}]
        return []

    async def mock_insert(table, payload):
        return {"id": payload.get("id")}

    async def mock_patch(path, payload):
        return [payload]

    captured: dict = {}

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"api_request": {"status": "success"}, "document": {"inference": {}}}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["base_url"] = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(
            self, method, url, headers=None, json=None, params=None, data=None, files=None
        ):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            captured["data"] = data
            captured["files"] = files
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="invoice.extract",
            agent_id="agent_mindee_invoice_test",
            body={
                "file": {
                    "filename": "invoice.pdf",
                    "content_base64": base64.b64encode(b"%PDF-invoice").decode(),
                    "content_type": "application/pdf",
                },
                "include_mvision": True,
            },
            service_slug="mindee",
        )

    assert result["provider_used"] == "mindee"
    assert captured["base_url"] == "https://api.mindee.net"
    assert captured["method"] == "POST"
    assert captured["url"] == "/v1/products/mindee/financial_document/v1/predict"
    assert captured["json"] is None
    assert not captured["params"]
    assert captured["headers"]["Authorization"] == "Token mindee_test_secret"
    assert "Content-Type" not in captured["headers"]

    assert captured["data"] is None
    all_files = captured["files"]
    form_entries = [(name, tup[1].decode("utf-8")) for name, tup in all_files if tup[0] is None]
    assert ("include_mvision", "true") in form_entries

    file_entries = [(name, tup) for name, tup in all_files if tup[0] is not None]
    assert len(file_entries) == 1
    field_name, file_tuple = file_entries[0]
    assert field_name == "document"
    assert file_tuple[0] == "invoice.pdf"
    assert file_tuple[1] == b"%PDF-invoice"
    assert file_tuple[2] == "application/pdf"


@pytest.mark.anyio
async def test_managed_executor_mindee_accepts_files_alias_for_document_extract(monkeypatch):
    """Mindee document.extract_fields should accept `files` and normalize it to `document`."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_MINDEE_API_KEY", "mindee_alias_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1402,
                    "capability_id": "document.extract_fields",
                    "service_slug": "mindee",
                    "description": "Managed Mindee document extraction",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_MINDEE_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/v1/products/mindee/financial_document/v1/predict",
                    "default_headers": {},
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?slug=eq.mindee" in path:
            return [{"api_domain": "api.mindee.net"}]
        return []

    async def mock_insert(table, payload):
        return {"id": payload.get("id")}

    async def mock_patch(path, payload):
        return [payload]

    captured: dict = {}

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"api_request": {"status": "success"}, "document": {"inference": {}}}

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["base_url"] = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(
            self, method, url, headers=None, json=None, params=None, data=None, files=None
        ):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            captured["data"] = data
            captured["files"] = files
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="document.extract_fields",
            agent_id="agent_mindee_document_test",
            body={
                "files": {
                    "filename": "financial.txt",
                    "text": "gross amount: 12.00",
                },
                "raw_text": True,
            },
            service_slug="mindee",
        )

    assert result["provider_used"] == "mindee"
    assert captured["base_url"] == "https://api.mindee.net"
    assert captured["headers"]["Authorization"] == "Token mindee_alias_secret"
    assert captured["json"] is None

    assert captured["data"] is None
    all_files = captured["files"]
    form_entries = [(name, tup[1].decode("utf-8")) for name, tup in all_files if tup[0] is None]
    assert ("raw_text", "true") in form_entries

    file_entries = [(name, tup) for name, tup in all_files if tup[0] is not None]
    assert len(file_entries) == 1
    field_name, file_tuple = file_entries[0]
    assert field_name == "document"
    assert file_tuple[0] == "financial.txt"
    assert file_tuple[1] == b"gross amount: 12.00"
    assert file_tuple[2] == "text/plain"


@pytest.mark.anyio
async def test_managed_executor_unstructured_translates_json_body_to_multipart(monkeypatch):
    """Unstructured managed execution should translate JSON-native file descriptors to multipart."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY", "unstructured_test_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {
                    "id": 1111,
                    "capability_id": "documents.partition",
                    "service_slug": "unstructured",
                    "description": "Managed Unstructured partition",
                    "credential_env_keys": ["RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY"],
                    "default_method": "POST",
                    "default_path": "/general/v0/general",
                    "default_headers": {"Content-Type": "application/json"},
                    "daily_limit_per_agent": None,
                }
            ]
        if "services?slug=eq.unstructured" in path:
            return [{"api_domain": "api.unstructuredapp.io"}]
        return []

    async def mock_insert(table, payload):
        return {"id": payload.get("id")}

    async def mock_patch(path, payload):
        return [payload]

    captured: dict = {}

    class DummyResponse:
        status_code = 200

        def json(self):
            return [{"type": "Title", "text": "Hello"}]

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["base_url"] = kwargs.get("base_url")
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(
            self, method, url, headers=None, json=None, params=None, data=None, files=None
        ):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            captured["data"] = data
            captured["files"] = files
            return DummyResponse()

    with (
        patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch),
        patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert),
        patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch),
        patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient),
    ):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.execute(
            capability_id="documents.partition",
            agent_id="agent_unstructured_test",
            body={
                "files": {
                    "filename": "sample.txt",
                    "content_base64": base64.b64encode(b"hello world").decode(),
                    "content_type": "text/plain",
                },
                "strategy": "hi_res",
                "languages": ["eng", "deu"],
                "coordinates": True,
            },
            service_slug="unstructured",
        )

    assert result["provider_used"] == "unstructured"
    assert captured["base_url"] == "https://api.unstructuredapp.io"
    assert captured["method"] == "POST"
    assert captured["url"] == "/general/v0/general"
    assert captured["json"] is None
    assert not captured["params"]
    assert captured["headers"]["unstructured-api-key"] == "unstructured_test_secret"
    assert "Content-Type" not in captured["headers"]

    # Form fields are now merged into the files list as (field, (None, value_bytes, mime))
    # to avoid httpx AsyncClient sync/async multipart encoding conflict.
    assert captured["data"] is None

    all_files = captured["files"]
    # Extract form-data entries (None filename = form field)
    form_entries = [(name, tup[1].decode("utf-8")) for name, tup in all_files if tup[0] is None]
    assert ("strategy", "hi_res") in form_entries
    assert ("coordinates", "true") in form_entries
    assert ("languages", "eng") in form_entries
    assert ("languages", "deu") in form_entries

    # Extract actual file entries (non-None filename)
    file_entries = [(name, tup) for name, tup in all_files if tup[0] is not None]
    assert len(file_entries) == 1
    field_name, file_tuple = file_entries[0]
    assert field_name == "files"
    assert file_tuple[0] == "sample.txt"
    assert file_tuple[1] == b"hello world"
    assert file_tuple[2] == "text/plain"
