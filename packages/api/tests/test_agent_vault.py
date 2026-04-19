"""Tests for Agent Vault — Mode 3 ceremony + per-request token execution (R17).

Tests:
- AgentVaultTokenValidator format validation
- GET /v1/services/ceremonies
- GET /v1/services/{slug}/ceremony
- POST execute with credential_mode=agent_vault
- Security: token never in responses, never persisted
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import app as _shared_app
from services.agent_vault import AgentVaultTokenValidator

_BYPASS_KEY = "rhumb_test_bypass_key_0000"


@pytest.fixture
def app():
    # Use shared app instance so conftest autouse identity-store wiring applies.
    return _shared_app


@pytest.fixture(autouse=True)
def _mock_rate_limiter():
    """Keep execute-route tests off the real durable rate-limit path."""
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
def _mock_required_execution_insert():
    """Keep focused Agent Vault tests off the durable execution insert path."""
    with patch(
        "routes.capability_execute.supabase_insert_required",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_required_execution_patch():
    """Keep focused Agent Vault tests off the durable execution patch path."""
    with patch(
        "routes.capability_execute.supabase_patch_required",
        new_callable=AsyncMock,
        return_value=[{}],
    ):
        yield


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


@pytest.mark.anyio
async def test_get_ceremony_missing_alias_input_reports_canonical_public_slug(app):
    """Missing ceremony reads should report canonical public ids for alias inputs."""

    async def mock_fetch(path):
        return []

    with patch("services.agent_vault.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/v1/services/Brave-Search/ceremony")

    assert resp.status_code == 200
    assert resp.json() == {
        "data": None,
        "error": "No ceremony available for service 'brave-search-api'",
    }


@pytest.mark.anyio
async def test_get_ceremony_resolves_alias_backed_runtime_row_to_canonical_slug(app):
    """Canonical public slugs should still resolve ceremony rows stored on runtime aliases."""
    async def mock_fetch(path):
        if "ceremony_skills?service_slug=in.(brave-search-api,brave-search)" in path:
            return [{
                "id": 1,
                "service_slug": "brave-search",
                "display_name": "Brave Search",
                "description": "Get a Brave Search API key",
                "auth_type": "api_key",
                "steps": [{"step": 1, "action": "Open the dashboard", "type": "navigate"}],
                "token_pattern": "[A-Za-z0-9_-]{20,}",
                "token_prefix": None,
                "verify_endpoint": "/res/v1/web/search",
                "verify_method": "GET",
                "verify_expected_status": 200,
                "difficulty": "easy",
                "estimated_minutes": 3,
                "requires_human": False,
                "documentation_url": "https://api.search.brave.com/app/documentation",
            }]
        return []

    with patch("services.agent_vault.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/v1/services/brave-search-api/ceremony")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["service_slug"] == "brave-search-api"
    assert data["display_name"] == "Brave Search"


@pytest.mark.anyio
async def test_get_ceremony_canonicalizes_alias_backed_copy_for_canonical_rows(app):
    """Canonical ceremony rows should rewrite alias-backed public copy."""

    async def mock_fetch(path):
        if "ceremony_skills?service_slug=in.(brave-search-api,brave-search)" in path:
            return [{
                "id": 1,
                "service_slug": "brave-search-api",
                "display_name": "Brave Search (brave-search)",
                "description": "Use brave-search before falling back to pdl.",
                "auth_type": "api_key",
                "steps": [{"step": 1, "action": "Open the dashboard", "type": "navigate"}],
                "token_pattern": "[A-Za-z0-9_-]{20,}",
                "token_prefix": None,
                "verify_endpoint": "/res/v1/web/search",
                "verify_method": "GET",
                "verify_expected_status": 200,
                "difficulty": "easy",
                "estimated_minutes": 3,
                "requires_human": False,
                "documentation_url": "https://api.search.brave.com/app/documentation",
            }]
        return []

    with patch("services.agent_vault.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/v1/services/brave-search-api/ceremony")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["service_slug"] == "brave-search-api"
    assert data["display_name"] == "Brave Search (brave-search-api)"
    assert data["description"] == "Use brave-search-api before falling back to people-data-labs."
    assert "brave-search-api-api" not in data["display_name"]
    assert "brave-search-api-api" not in data["description"]


@pytest.mark.anyio
async def test_list_ceremonies_canonicalizes_alias_backed_runtime_rows(app):
    """Ceremony listings should expose canonical public ids, not runtime aliases."""
    async def mock_fetch(path):
        if "ceremony_skills?enabled=eq.true" in path:
            return [
                {
                    "service_slug": "brave-search",
                    "display_name": "Brave Search",
                    "description": "Get a Brave Search API key",
                    "auth_type": "api_key",
                    "difficulty": "easy",
                    "estimated_minutes": 3,
                    "requires_human": False,
                    "documentation_url": "https://api.search.brave.com/app/documentation",
                },
                {
                    "service_slug": "openai",
                    "display_name": "OpenAI",
                    "description": "Get an OpenAI API key",
                    "auth_type": "api_key",
                    "difficulty": "easy",
                    "estimated_minutes": 3,
                    "requires_human": False,
                    "documentation_url": "https://platform.openai.com",
                },
            ]
        return []

    with patch("services.agent_vault.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/v1/services/ceremonies")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["count"] == 2
    assert [item["service_slug"] for item in data["ceremonies"]] == [
        "brave-search-api",
        "openai",
    ]


@pytest.mark.anyio
async def test_list_ceremonies_canonicalizes_alias_backed_copy_for_canonical_rows(app):
    """Ceremony listings should keep canonical public copy on already-canonical rows."""

    async def mock_fetch(path):
        if "ceremony_skills?enabled=eq.true" in path:
            return [
                {
                    "service_slug": "brave-search-api",
                    "display_name": "Brave Search (brave-search)",
                    "description": "Use brave-search before falling back to pdl.",
                    "auth_type": "api_key",
                    "difficulty": "easy",
                    "estimated_minutes": 3,
                    "requires_human": False,
                    "documentation_url": "https://api.search.brave.com/app/documentation",
                },
                {
                    "service_slug": "people-data-labs",
                    "display_name": "People Data Labs",
                    "description": "pdl fallback for person enrichment.",
                    "auth_type": "api_key",
                    "difficulty": "easy",
                    "estimated_minutes": 3,
                    "requires_human": False,
                    "documentation_url": "https://dashboard.peopledatalabs.com/",
                },
            ]
        return []

    with patch("services.agent_vault.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/v1/services/ceremonies")

    assert resp.status_code == 200
    ceremonies = resp.json()["data"]["ceremonies"]
    assert ceremonies == [
        {
            "service_slug": "brave-search-api",
            "display_name": "Brave Search (brave-search-api)",
            "description": "Use brave-search-api before falling back to people-data-labs.",
            "auth_type": "api_key",
            "difficulty": "easy",
            "estimated_minutes": 3,
            "requires_human": False,
            "documentation_url": "https://api.search.brave.com/app/documentation",
        },
        {
            "service_slug": "people-data-labs",
            "display_name": "People Data Labs",
            "description": "people-data-labs fallback for person enrichment.",
            "auth_type": "api_key",
            "difficulty": "easy",
            "estimated_minutes": 3,
            "requires_human": False,
            "documentation_url": "https://dashboard.peopledatalabs.com/",
        },
    ]
    assert "brave-search-api-api" not in ceremonies[0]["display_name"]
    assert "brave-search-api-api" not in ceremonies[0]["description"]


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
