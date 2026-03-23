"""Tests for Rhumb-managed execution (Mode 2, R16).

Tests:
- RhumbManagedExecutor service
- GET /v1/capabilities/rhumb-managed catalog
- POST execute with credential_mode=rhumb_managed
- Security: no credential leakage in responses
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
                           service_slug=None, interface="rest"):
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
                           service_slug=None, interface="rest"):
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
                           service_slug=None, interface="rest"):
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
