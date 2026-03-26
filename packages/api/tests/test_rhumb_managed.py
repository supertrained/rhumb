"""Tests for Rhumb-managed execution (Mode 2, R16).

Tests:
- RhumbManagedExecutor service
- GET /v1/capabilities/rhumb-managed catalog
- POST execute with credential_mode=rhumb_managed
- Security: no credential leakage in responses
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app

# Bypass key must match conftest.BYPASS_KEY so the autouse identity-store
# fixture resolves it to the pre-seeded bypass agent.
_BYPASS_KEY = "rhumb_test_bypass_key_0000"


@pytest.fixture
def app():
    return create_app()


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
                {"capability_id": "email.send", "service_slug": "resend",
                 "description": "Send email via Resend", "daily_limit_per_agent": 100},
            ]
        return []

    with patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch):
        from services.rhumb_managed import RhumbManagedExecutor
        executor = RhumbManagedExecutor()
        managed = await executor.list_managed()
        assert len(managed) == 1
        assert managed[0]["capability_id"] == "email.send"


# ── Catalog endpoint ──────────────────────────────────────────

@pytest.mark.anyio
async def test_managed_catalog_endpoint(app):
    """GET /v1/capabilities/rhumb-managed returns managed capabilities."""
    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [
                {"capability_id": "email.send", "service_slug": "resend",
                 "description": "Send email via Resend", "daily_limit_per_agent": 100},
            ]
        if "capabilities?" in path and "id=in." in path:
            return [{"id": "email.send", "domain": "email", "action": "send",
                      "description": "Send transactional email"}]
        return []

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch), \
         patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch):
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

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch), \
         patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch):
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
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
        if "rhumb_managed_capabilities?" in path:
            return [{
                "id": 1,
                "capability_id": "email.send",
                "service_slug": "resend",
                "description": "Managed email send",
                "credential_env_keys": ["RHUMB_CREDENTIAL_RESEND_API_KEY"],
                "default_method": "POST",
                "default_path": "/emails",
                "default_headers": {},
                "daily_limit_per_agent": 100,
            }]
        if "services?" in path and "capability_services?" not in path:
            return [{"slug": "resend", "api_domain": "api.resend.com"}]
        return []

    async def mock_insert(table, payload):
        call_log.append(("insert", table, payload))
        return {"id": payload.get("id")}

    # Mock at the executor's execute method to avoid httpx.AsyncClient global patch
    async def mock_execute(self, capability_id, agent_id, body=None, params=None,
                           service_slug=None, interface="rest", execution_id=None):
        return {
            "capability_id": capability_id,
            "provider_used": "resend",
            "credential_mode": "rhumb_managed",
            "upstream_status": 200,
            "upstream_response": {"id": "msg_123", "object": "email"},
            "latency_ms": 42.0,
            "execution_id": "exec_test123",
        }

    with patch("routes.capability_execute.supabase_fetch", side_effect=mock_fetch), \
         patch("services.rhumb_managed.RhumbManagedExecutor.execute", mock_execute):

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "credential_mode": "rhumb_managed",
                    "body": {"from": "test@rhumb.dev", "to": "user@example.com",
                             "subject": "Test", "html": "<p>Hello</p>"},
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
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
        return []

    # Mock executor to return a result that we can inspect for leakage
    async def mock_execute(self, capability_id, agent_id, body=None, params=None,
                           service_slug=None, interface="rest", execution_id=None):
        return {
            "capability_id": capability_id,
            "provider_used": "resend",
            "credential_mode": "rhumb_managed",
            "upstream_status": 200,
            "upstream_response": {"id": "msg_456"},
            "latency_ms": 35.0,
            "execution_id": "exec_leak_test",
        }

    with patch("routes.capability_execute.supabase_fetch", side_effect=mock_fetch), \
         patch("services.rhumb_managed.RhumbManagedExecutor.execute", mock_execute):

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
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
        return []

    async def mock_managed_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [{
                "id": 1,
                "capability_id": "email.send",
                "service_slug": "resend",
                "description": "Managed",
                "credential_env_keys": ["RHUMB_CREDENTIAL_RESEND_API_KEY"],
                "default_method": "POST",
                "default_path": "/emails",
                "default_headers": {},
                "daily_limit_per_agent": None,
            }]
        if "services?" in path and "capability_services?" not in path:
            return [{"slug": "resend", "api_domain": "api.resend.com"}]
        return []

    with patch("services.rhumb_managed.supabase_fetch", side_effect=mock_managed_fetch), \
         patch("routes.capability_execute.supabase_fetch", side_effect=mock_cap_fetch):

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
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
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
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
        return []

    async def mock_execute(self, capability_id, agent_id, body=None, params=None,
                           service_slug=None, interface="rest", execution_id=None):
        return {
            "capability_id": capability_id,
            "provider_used": "resend",
            "credential_mode": "rhumb_managed",
            "upstream_status": 200,
            "upstream_response": {"id": "msg_789"},
            "latency_ms": 28.0,
            "execution_id": "exec_omit_test",
        }

    with patch("routes.capability_execute.supabase_fetch", side_effect=mock_fetch), \
         patch("services.rhumb_managed.RhumbManagedExecutor.execute", mock_execute):

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
        return [{"id": 1, "capability_id": "search.query", "service_slug": "brave-search"}]

    with patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch):
        from services.rhumb_managed import RhumbManagedExecutor

        executor = RhumbManagedExecutor()
        result = await executor.get_managed_config("search.query", "brave-search-api")

    assert result["service_slug"] == "brave-search"
    assert any("service_slug=eq.brave-search" in path for path in seen_paths)


@pytest.mark.anyio
async def test_managed_executor_post_merges_params_into_body_and_marks_4xx_failure(monkeypatch):
    """POST managed executions should merge params into body and treat 4xx as failure."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_TAVILY_API_KEY", "tvly_test_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [{
                "id": 321,
                "capability_id": "search.query",
                "service_slug": "tavily",
                "description": "Managed Tavily search",
                "credential_env_keys": ["RHUMB_CREDENTIAL_TAVILY_API_KEY"],
                "default_method": "POST",
                "default_path": "/search",
                "default_headers": {},
                "daily_limit_per_agent": None,
            }]
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

    with patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch), \
         patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert), \
         patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch), \
         patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient):
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
async def test_managed_executor_google_ai_uses_x_goog_api_key(monkeypatch):
    """Google AI managed execution should use x-goog-api-key, not Bearer auth."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY", "gemini_test_secret")

    async def mock_fetch(path):
        if "rhumb_managed_capabilities?" in path:
            return [{
                "id": 999,
                "capability_id": "ai.generate_text",
                "service_slug": "google-ai",
                "description": "Managed Google AI text generation",
                "credential_env_keys": ["RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY"],
                "default_method": "POST",
                "default_path": "/v1beta/models/{model}:generateContent",
                "default_headers": {"Content-Type": "application/json"},
                "daily_limit_per_agent": None,
            }]
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

    with patch("services.rhumb_managed.supabase_fetch", side_effect=mock_fetch), \
         patch("services.rhumb_managed.supabase_insert", side_effect=mock_insert), \
         patch("services.rhumb_managed.supabase_patch", side_effect=mock_patch), \
         patch("services.rhumb_managed.httpx.AsyncClient", DummyAsyncClient):
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
