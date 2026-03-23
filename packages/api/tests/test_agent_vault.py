"""Tests for Agent Vault — Mode 3 ceremony + per-request token execution (R17).

Tests:
- AgentVaultTokenValidator format validation
- GET /v1/services/ceremonies
- GET /v1/services/{slug}/ceremony
- POST execute with credential_mode=agent_vault
- Security: token never in responses, never persisted
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import app as _shared_app
from services.agent_vault import AgentVaultTokenValidator

_BYPASS_KEY = "rhumb_test_bypass_key_0000"


@pytest.fixture
def app():
    # Use shared app instance so conftest autouse identity-store wiring applies.
    return _shared_app


# ── Format validation ────────────────────────────────────────────

def test_validate_format_empty_token():
    v = AgentVaultTokenValidator()
    ok, err = v.validate_format("")
    assert not ok
    assert "empty" in err.lower()


def test_validate_format_valid_prefix():
    v = AgentVaultTokenValidator()
    ok, err = v.validate_format("sk-abc123def456", token_prefix="sk-")
    assert ok
    assert err is None


def test_validate_format_wrong_prefix():
    v = AgentVaultTokenValidator()
    ok, err = v.validate_format("re_abc123", token_prefix="sk-")
    assert not ok
    assert "sk-" in err


def test_validate_format_pattern_match():
    v = AgentVaultTokenValidator()
    ok, err = v.validate_format(
        "re_AbCd1234567890abcdef",
        token_pattern=r"re_[a-zA-Z0-9_]{20,}",
    )
    assert ok


def test_validate_format_pattern_mismatch():
    v = AgentVaultTokenValidator()
    ok, err = v.validate_format("short", token_pattern=r"re_[a-zA-Z0-9_]{20,}")
    assert not ok
    assert "format" in err.lower()


def test_validate_format_bad_regex_skips():
    v = AgentVaultTokenValidator()
    ok, err = v.validate_format("anytoken", token_pattern="[invalid(")
    # Should pass — bad regex is skipped
    assert ok


# ── Ceremony routes ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_ceremonies(app):
    """GET /v1/services/ceremonies returns ceremony list."""
    async def mock_fetch(path):
        if "ceremony_skills?" in path:
            return [
                {"service_slug": "openai", "display_name": "OpenAI",
                 "description": "Get an OpenAI API key", "auth_type": "api_key",
                 "difficulty": "easy", "estimated_minutes": 3,
                 "requires_human": False, "documentation_url": "https://platform.openai.com"},
                {"service_slug": "stripe", "display_name": "Stripe",
                 "description": "Get a Stripe API key", "auth_type": "api_key",
                 "difficulty": "easy", "estimated_minutes": 3,
                 "requires_human": False, "documentation_url": "https://stripe.com"},
            ]
        return []

    with patch("services.agent_vault.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/v1/services/ceremonies")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["count"] == 2
    assert data["ceremonies"][0]["service_slug"] == "openai"


@pytest.mark.anyio
async def test_get_ceremony_for_service(app):
    """GET /v1/services/{slug}/ceremony returns ceremony details."""
    async def mock_fetch(path):
        if "ceremony_skills?" in path and "openai" in path:
            return [{
                "id": 1, "service_slug": "openai", "display_name": "OpenAI",
                "description": "Get an OpenAI API key", "auth_type": "api_key",
                "steps": [{"step": 1, "action": "Navigate to ...", "type": "navigate"}],
                "token_pattern": "sk-[a-zA-Z0-9_-]{40,}", "token_prefix": "sk-",
                "verify_endpoint": "/v1/models", "verify_method": "GET",
                "verify_expected_status": 200,
                "difficulty": "easy", "estimated_minutes": 3,
                "requires_human": False,
                "documentation_url": "https://platform.openai.com",
            }]
        return []

    with patch("services.agent_vault.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/v1/services/openai/ceremony")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["service_slug"] == "openai"
    assert len(data["steps"]) >= 1
    assert data["token_prefix"] == "sk-"


@pytest.mark.anyio
async def test_get_ceremony_not_found(app):
    """GET /v1/services/{slug}/ceremony returns error for unknown service."""
    async def mock_fetch(path):
        return []

    with patch("services.agent_vault.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/v1/services/nonexistent/ceremony")

    assert resp.status_code == 200
    assert resp.json()["data"] is None
    assert "not found" in resp.json()["error"].lower() or "no ceremony" in resp.json()["error"].lower()


# ── Execute with agent_vault mode ────────────────────────────────

@pytest.mark.anyio
async def test_execute_agent_vault_requires_token(app):
    """Agent vault mode requires X-Agent-Token header."""
    async def mock_fetch(path):
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
        return []

    with patch("routes.capability_execute.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "credential_mode": "agent_vault",
                    "provider": "resend",
                    "method": "POST",
                    "path": "/emails",
                    "body": {},
                },
                headers={"X-Rhumb-Key": _BYPASS_KEY},
            )

    assert resp.status_code == 400
    assert "X-Agent-Token" in resp.json()["detail"]


@pytest.mark.anyio
async def test_execute_agent_vault_requires_provider(app):
    """Agent vault mode requires explicit provider."""
    async def mock_fetch(path):
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
        return []

    with patch("routes.capability_execute.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "credential_mode": "agent_vault",
                    "method": "POST",
                    "path": "/emails",
                    "body": {},
                },
                headers={
                    "X-Rhumb-Key": _BYPASS_KEY,
                    "X-Agent-Token": "re_testtoken123456789012345",
                },
            )

    assert resp.status_code == 400
    assert "provider" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_execute_agent_vault_validates_token_format(app):
    """Agent vault rejects tokens with wrong format."""
    async def mock_cap_fetch(path):
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
        return []

    async def mock_vault_fetch(path):
        if "ceremony_skills?" in path:
            return [{
                "id": 1, "service_slug": "resend", "display_name": "Resend",
                "auth_type": "api_key", "token_prefix": "re_",
                "token_pattern": "re_[a-zA-Z0-9_]{20,}",
                "steps": [], "verify_endpoint": None, "verify_method": "GET",
                "verify_expected_status": 200, "difficulty": "easy",
                "estimated_minutes": 3, "requires_human": False,
                "documentation_url": None, "description": "Resend",
            }]
        return []

    with patch("routes.capability_execute.supabase_fetch", side_effect=mock_cap_fetch), \
         patch("services.agent_vault.supabase_fetch", side_effect=mock_vault_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/v1/capabilities/email.send/execute",
                json={
                    "credential_mode": "agent_vault",
                    "provider": "resend",
                    "method": "POST",
                    "path": "/emails",
                    "body": {},
                },
                headers={
                    "X-Rhumb-Key": _BYPASS_KEY,
                    "X-Agent-Token": "wrong_prefix_token",
                },
            )

    assert resp.status_code == 400
    assert "re_" in resp.json()["detail"]


@pytest.mark.anyio
async def test_execute_agent_vault_token_never_in_response(app):
    """Agent token is NEVER included in any response."""
    import httpx

    secret_token = "re_SuperSecretTokenValue1234567890123"

    async def mock_cap_fetch(path):
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
        if "services?" in path and "capability_services?" not in path:
            return [{"slug": "resend", "api_domain": "api.resend.com"}]
        return []

    async def mock_vault_fetch(path):
        if "ceremony_skills?" in path:
            return [{
                "id": 1, "service_slug": "resend", "display_name": "Resend",
                "auth_type": "api_key", "token_prefix": "re_",
                "token_pattern": "re_[a-zA-Z0-9_]{20,}",
                "steps": [], "verify_endpoint": None, "verify_method": "GET",
                "verify_expected_status": 200, "difficulty": "easy",
                "estimated_minutes": 3, "requires_human": False,
                "documentation_url": None, "description": "Resend",
            }]
        if "services?" in path and "capability_services?" not in path:
            return [{"slug": "resend", "api_domain": "api.resend.com"}]
        return []

    async def mock_insert(table, payload):
        # Verify token is not in the logged payload
        payload_str = str(payload)
        assert secret_token not in payload_str
        return {"id": payload.get("id")}

    # Instead of mocking httpx globally (which breaks the test client),
    # verify the execute route dispatches correctly by checking that
    # the route accepts the token and attempts execution.
    # We mock _get_service_domain to provide a domain, and the httpx call
    # will fail but we can verify the 502 contains no token.

    with patch("routes.capability_execute.supabase_fetch", side_effect=mock_cap_fetch), \
         patch("routes.capability_execute.supabase_insert", side_effect=mock_insert), \
         patch("routes.capability_execute._get_service_domain", return_value="api.resend.com"), \
         patch("services.agent_vault.supabase_fetch", side_effect=mock_vault_fetch):

        # Use a separate mock that only patches the context manager used in vault exec
        import httpx as httpx_mod

        class MockClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def request(self, **kwargs):
                # Verify the token went into headers, not the response
                auth_header = kwargs.get("headers", {}).get("Authorization", "")
                assert secret_token in auth_header or "Bearer" in auth_header
                return httpx_mod.Response(
                    200, json={"id": "msg_vault_test"},
                    request=httpx_mod.Request("POST", "https://api.resend.com/emails"),
                )

        with patch("routes.capability_execute.httpx.AsyncClient", return_value=MockClient()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/v1/capabilities/email.send/execute",
                    json={
                        "credential_mode": "agent_vault",
                        "provider": "resend",
                        "method": "POST",
                        "path": "/emails",
                        "body": {"from": "a@b.com", "to": "c@d.com", "subject": "Hi", "html": "hey"},
                    },
                    headers={
                        "X-Rhumb-Key": _BYPASS_KEY,
                        "X-Agent-Token": secret_token,
                    },
                )

    # Token must NEVER appear in response
    assert secret_token not in resp.text
    assert resp.status_code == 200
    assert resp.json()["data"]["credential_mode"] == "agent_vault"
