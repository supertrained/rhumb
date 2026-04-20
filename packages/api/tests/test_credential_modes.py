"""Tests for credential mode awareness endpoints (R15).

Tests:
- GET /v1/capabilities/{id}/credential-modes
- GET /v1/agent/credentials
- configured field in resolve response
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app


@pytest.fixture
def app():
    return create_app()


# ── credential-modes endpoint ──────────────────────────────────

@pytest.mark.anyio
async def test_credential_modes_returns_modes_per_provider(app):
    """credential-modes endpoint returns mode details per provider."""
    async def mock_fetch(path):
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send email"}]
        if "capability_services?" in path:
            return [
                {"service_slug": "resend", "credential_modes": ["byo", "agent_vault"], "auth_method": "api_key"},
                {"service_slug": "sendgrid", "credential_modes": ["byo"], "auth_method": "api_key"},
            ]
        return []

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/capabilities/email.send/credential-modes",
                headers={"X-Rhumb-Key": "test-agent"},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["capability_id"] == "email.send"
    assert len(data["providers"]) == 2

    resend = data["providers"][0]
    assert resend["service_slug"] == "resend"
    assert len(resend["modes"]) == 2
    assert resend["modes"][0]["mode"] == "byok"
    assert resend["modes"][1]["mode"] == "agent_vault"
    assert "setup_hint" in resend["modes"][0]


@pytest.mark.anyio
async def test_credential_modes_unknown_capability(app):
    """credential-modes for unknown capability returns error."""
    async def mock_fetch(path):
        return []

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/capabilities/nonexistent.action/credential-modes",
                headers={"X-Rhumb-Key": "test"},
            )

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "capability_not_found"
    assert "nonexistent.action" in body["message"]
    assert body["search_url"] == "/v1/capabilities?search=nonexistent.action"


@pytest.mark.anyio
async def test_credential_modes_shows_configured_for_byo(app, monkeypatch):
    """BYO mode shows configured=True when env var credential exists."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_RESEND_API_KEY", "re_test123")

    # Reset credential store singleton to pick up new env var
    import services.proxy_credentials as pc
    pc._credential_store = None

    async def mock_fetch(path):
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
        if "capability_services?" in path:
            return [{"service_slug": "resend", "credential_modes": ["byo"], "auth_method": "api_key"}]
        return []

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/capabilities/email.send/credential-modes",
                headers={"X-Rhumb-Key": "test"},
            )

    data = resp.json()["data"]
    resend = data["providers"][0]
    byo_mode = resend["modes"][0]
    assert byo_mode["mode"] == "byok"
    assert byo_mode["configured"] is True
    assert resend["any_configured"] is True

    pc._credential_store = None


@pytest.mark.anyio
async def test_credential_modes_prefers_hardcoded_twilio_basic_auth(app, monkeypatch):
    """Twilio should report BASIC_AUTH config even if capability metadata says api_key."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_TWILIO_BASIC_AUTH", "AC123:auth_token")

    import services.proxy_credentials as pc
    pc._credential_store = None

    async def mock_fetch(path):
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "phone.lookup", "domain": "phone", "action": "lookup", "description": "Lookup"}]
        if "capability_services?" in path:
            return [{"service_slug": "twilio", "credential_modes": ["byo"], "auth_method": "api_key"}]
        return []

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/capabilities/phone.lookup/credential-modes",
                headers={"X-Rhumb-Key": "test"},
            )

    assert resp.status_code == 200
    twilio = resp.json()["data"]["providers"][0]
    byo_mode = twilio["modes"][0]
    assert twilio["auth_method"] == "basic_auth"
    assert byo_mode["mode"] == "byok"
    assert byo_mode["configured"] is True
    assert "TWILIO_BASIC_AUTH" in byo_mode["setup_hint"]

    pc._credential_store = None


@pytest.mark.anyio
async def test_credential_modes_no_providers(app):
    """credential-modes with no providers returns empty list."""
    async def mock_fetch(path):
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
        return []

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/capabilities/email.send/credential-modes",
                headers={"X-Rhumb-Key": "test"},
            )

    assert resp.status_code == 200
    assert resp.json()["data"]["providers"] == []


# ── agent/credentials endpoint ──────────────────────────────────

@pytest.mark.anyio
async def test_agent_credentials_requires_auth(app):
    """Agent credentials endpoint requires X-Rhumb-Key."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/v1/agent/credentials")

    assert resp.status_code == 401
    assert resp.json()["detail"] == "X-Rhumb-Key header required"


@pytest.mark.anyio
async def test_agent_credentials_invalid_key_uses_governed_language(app):
    """Agent credentials invalid-key auth should use governed-key wording."""

    class MockIdentityStore:
        async def verify_api_key_with_agent(self, api_key: str):
            assert api_key == "bogus-agent"
            return None

    with patch("schemas.agent_identity.get_agent_identity_store", return_value=MockIdentityStore()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/agent/credentials",
                headers={"X-Rhumb-Key": "bogus-agent"},
            )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired governed API key"


@pytest.mark.anyio
async def test_agent_credentials_returns_status(app, monkeypatch):
    """Agent credentials returns configured services and capability counts."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_RESEND_API_KEY", "re_test123")

    import services.proxy_credentials as pc
    pc._credential_store = None

    async def mock_fetch(path):
        if "capability_services?" in path:
            return [
                {"capability_id": "email.send", "service_slug": "resend", "credential_modes": ["byo"], "auth_method": "api_key"},
                {"capability_id": "email.send", "service_slug": "sendgrid", "credential_modes": ["byo"], "auth_method": "api_key"},
                {"capability_id": "payment.charge", "service_slug": "stripe", "credential_modes": ["byo"], "auth_method": "api_key"},
            ]
        return []

    class MockIdentityStore:
        async def verify_api_key_with_agent(self, api_key: str):
            assert api_key == "test-agent"
            return SimpleNamespace(agent_id="test-agent")

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch), patch(
        "schemas.agent_identity.get_agent_identity_store",
        return_value=MockIdentityStore(),
    ), patch("routes.capabilities.has_any_db_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_storage_bundle_configured", return_value=False
    ), patch("routes.capabilities.has_any_deployment_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_warehouse_bundle_configured", return_value=False
    ), patch("routes.capabilities.has_any_actions_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_crm_bundle_configured",
        side_effect=lambda provider_slug: False,
    ), patch(
        "routes.capabilities.has_any_support_bundle_configured",
        side_effect=lambda provider_slug: False,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/agent/credentials",
                headers={"X-Rhumb-Key": "test-agent"},
            )

    data = resp.json()["data"]
    assert data["agent_id"] == "test-agent"
    assert "resend" in data["configured_services"]
    assert "email.send" in data["unlocked_capabilities"]
    assert data["unlocked_count"] >= 1
    # payment.charge should be locked (no stripe credential)
    assert "payment.charge" in data["locked_capabilities"]

    pc._credential_store = None


@pytest.mark.anyio
async def test_agent_credentials_counts_rhumb_managed_modes_as_unlocked(app):
    """Rhumb-managed modes should unlock capabilities without agent BYOK setup."""
    async def mock_fetch(path):
        if "capability_services?" in path:
            return [
                {
                    "capability_id": "search.query",
                    "service_slug": "brave-search",
                    "credential_modes": ["rhumb_managed"],
                    "auth_method": "api_key",
                }
            ]
        return []

    class MockIdentityStore:
        async def verify_api_key_with_agent(self, api_key: str):
            assert api_key == "test-agent"
            return SimpleNamespace(agent_id="test-agent")

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch), patch(
        "schemas.agent_identity.get_agent_identity_store",
        return_value=MockIdentityStore(),
    ), patch("routes.capabilities.has_any_db_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_storage_bundle_configured", return_value=False
    ), patch("routes.capabilities.has_any_deployment_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_warehouse_bundle_configured", return_value=False
    ), patch("routes.capabilities.has_any_actions_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_crm_bundle_configured",
        side_effect=lambda provider_slug: False,
    ), patch(
        "routes.capabilities.has_any_support_bundle_configured",
        side_effect=lambda provider_slug: False,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/agent/credentials",
                headers={"X-Rhumb-Key": "test-agent"},
            )

    data = resp.json()["data"]
    assert data["configured_services"] == []
    assert "search.query" in data["unlocked_capabilities"]
    assert "search.query" not in data["locked_capabilities"]


@pytest.mark.anyio
async def test_agent_credentials_canonicalize_alias_backed_configured_services(app, monkeypatch):
    monkeypatch.setenv("RHUMB_CREDENTIAL_BRAVE_SEARCH_API_KEY", "brave_test_secret")

    import services.proxy_credentials as pc
    pc._credential_store = None

    async def mock_fetch(path):
        if "capability_services?" in path:
            return [
                {
                    "capability_id": "search.query",
                    "service_slug": "brave-search",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                }
            ]
        return []

    class MockIdentityStore:
        async def verify_api_key_with_agent(self, api_key: str):
            assert api_key == "test-agent"
            return SimpleNamespace(agent_id="test-agent")

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch), patch(
        "schemas.agent_identity.get_agent_identity_store",
        return_value=MockIdentityStore(),
    ), patch("routes.capabilities.has_any_db_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_storage_bundle_configured", return_value=False
    ), patch("routes.capabilities.has_any_deployment_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_warehouse_bundle_configured", return_value=False
    ), patch("routes.capabilities.has_any_actions_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_crm_bundle_configured",
        side_effect=lambda provider_slug: False,
    ), patch(
        "routes.capabilities.has_any_support_bundle_configured",
        side_effect=lambda provider_slug: False,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/agent/credentials",
                headers={"X-Rhumb-Key": "test-agent"},
            )

    data = resp.json()["data"]
    assert data["configured_services"] == ["brave-search-api"]
    assert "search.query" in data["unlocked_capabilities"]

    pc._credential_store = None


@pytest.mark.anyio
async def test_agent_credentials_includes_direct_bundle_capabilities_when_catalog_is_empty(app):
    """Direct bundle-backed rails should still appear when the catalog table is empty."""
    async def mock_fetch(path):
        if "capability_services?" in path:
            return []
        return []

    class MockIdentityStore:
        async def verify_api_key_with_agent(self, api_key: str):
            assert api_key == "test-agent"
            return SimpleNamespace(agent_id="test-agent")

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch), patch(
        "schemas.agent_identity.get_agent_identity_store",
        return_value=MockIdentityStore(),
    ), patch("routes.capabilities.has_any_deployment_bundle_configured", return_value=True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/agent/credentials",
                headers={"X-Rhumb-Key": "test-agent"},
            )

    data = resp.json()["data"]
    assert "vercel" in data["configured_services"]
    assert "deployment.list" in data["unlocked_capabilities"]
    assert "deployment.get" in data["unlocked_capabilities"]
    assert "workflow_run.list" in data["locked_capabilities"]


@pytest.mark.anyio
async def test_agent_credentials_includes_db_and_storage_direct_bundles_when_catalog_is_empty(app):
    """DB and object-storage direct rails should remain discoverable during catalog outages."""
    async def mock_fetch(path):
        if "capability_services?" in path:
            return []
        return []

    class MockIdentityStore:
        async def verify_api_key_with_agent(self, api_key: str):
            assert api_key == "test-agent"
            return SimpleNamespace(agent_id="test-agent")

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch), patch(
        "schemas.agent_identity.get_agent_identity_store",
        return_value=MockIdentityStore(),
    ), patch("routes.capabilities.has_any_db_bundle_configured", return_value=True), patch(
        "routes.capabilities.has_any_storage_bundle_configured", return_value=True
    ), patch("routes.capabilities.has_any_deployment_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_warehouse_bundle_configured", return_value=False
    ), patch("routes.capabilities.has_any_actions_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_crm_bundle_configured", return_value=False
    ), patch("routes.capabilities.has_any_support_bundle_configured", return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/agent/credentials",
                headers={"X-Rhumb-Key": "test-agent"},
            )

    data = resp.json()["data"]
    assert "postgresql" in data["configured_services"]
    assert "aws-s3" in data["configured_services"]
    assert "db.query.read" in data["unlocked_capabilities"]
    assert "db.schema.describe" in data["unlocked_capabilities"]
    assert "db.row.get" in data["unlocked_capabilities"]
    assert "object.list" in data["unlocked_capabilities"]
    assert "object.head" in data["unlocked_capabilities"]
    assert "object.get" in data["unlocked_capabilities"]
    assert "deployment.list" in data["locked_capabilities"]


@pytest.mark.anyio
async def test_agent_credentials_includes_remaining_direct_bundles_when_catalog_is_empty(app):
    """Warehouse, actions, CRM, and support direct rails should stay discoverable during catalog outages."""
    async def mock_fetch(path):
        if "capability_services?" in path:
            return []
        return []

    class MockIdentityStore:
        async def verify_api_key_with_agent(self, api_key: str):
            assert api_key == "test-agent"
            return SimpleNamespace(agent_id="test-agent")

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch), patch(
        "schemas.agent_identity.get_agent_identity_store",
        return_value=MockIdentityStore(),
    ), patch("routes.capabilities.has_any_db_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_storage_bundle_configured", return_value=False
    ), patch("routes.capabilities.has_any_deployment_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_warehouse_bundle_configured", return_value=True
    ), patch("routes.capabilities.has_any_actions_bundle_configured", return_value=True), patch(
        "routes.capabilities.has_any_crm_bundle_configured",
        side_effect=lambda provider_slug: provider_slug == "hubspot",
    ), patch(
        "routes.capabilities.has_any_support_bundle_configured",
        side_effect=lambda provider_slug: provider_slug == "zendesk",
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/agent/credentials",
                headers={"X-Rhumb-Key": "test-agent"},
            )

    data = resp.json()["data"]
    assert "bigquery" in data["configured_services"]
    assert "github" in data["configured_services"]
    assert "hubspot" in data["configured_services"]
    assert "zendesk" in data["configured_services"]
    assert "warehouse.query.read" in data["unlocked_capabilities"]
    assert "workflow_run.list" in data["unlocked_capabilities"]
    assert "crm.record.search" in data["unlocked_capabilities"]
    assert "ticket.search" in data["unlocked_capabilities"]
    assert "deployment.list" in data["locked_capabilities"]
    assert "conversation.list" in data["locked_capabilities"]


@pytest.mark.anyio
async def test_agent_credentials_ignores_stale_catalog_mapping_rows_for_direct_capabilities(app, monkeypatch):
    """Direct rails should not unlock from stale catalog mappings that point at proxy providers."""
    monkeypatch.setenv("RHUMB_CREDENTIAL_RESEND_API_KEY", "re_test123")

    import services.proxy_credentials as pc
    pc._credential_store = None

    async def mock_fetch(path):
        if "capability_services?" in path:
            return [
                {
                    "capability_id": "db.query.read",
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                }
            ]
        return []

    class MockIdentityStore:
        async def verify_api_key_with_agent(self, api_key: str):
            assert api_key == "test-agent"
            return SimpleNamespace(agent_id="test-agent")

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch), patch(
        "schemas.agent_identity.get_agent_identity_store",
        return_value=MockIdentityStore(),
    ), patch("routes.capabilities.has_any_db_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_storage_bundle_configured", return_value=False
    ), patch("routes.capabilities.has_any_deployment_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_warehouse_bundle_configured", return_value=False
    ), patch("routes.capabilities.has_any_actions_bundle_configured", return_value=False), patch(
        "routes.capabilities.has_any_crm_bundle_configured",
        side_effect=lambda provider_slug: False,
    ), patch(
        "routes.capabilities.has_any_support_bundle_configured",
        side_effect=lambda provider_slug: False,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/agent/credentials",
                headers={"X-Rhumb-Key": "test-agent"},
            )

    data = resp.json()["data"]
    assert data["configured_services"] == []
    assert "db.query.read" in data["locked_capabilities"]
    assert "db.query.read" not in data["unlocked_capabilities"]

    pc._credential_store = None


# ── resolve with configured field ──────────────────────────────

@pytest.mark.anyio
async def test_resolve_includes_configured_field(app):
    """Resolve endpoint includes configured: bool per provider."""
    async def mock_fetch(path):
        if "bundle_capabilities?" in path:
            return []
        if "capabilities?" in path and "id=eq." in path:
            return [{"id": "email.send", "domain": "email", "action": "send", "description": "Send"}]
        if "capability_services?" in path:
            return [{
                "service_slug": "resend",
                "credential_modes": ["byo"],
                "auth_method": "api_key",
                "endpoint_pattern": "POST /emails",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": 3000,
                "notes": None,
            }]
        if "scores?" in path:
            return [{"service_slug": "resend", "aggregate_recommendation_score": 7.79,
                      "execution_score": 8.5, "access_readiness_score": 7.0,
                      "tier": "L4", "tier_label": "Native", "confidence": 0.85}]
        if "services?" in path:
            return [{"slug": "resend", "name": "Resend"}]
        return []

    with patch("routes.capabilities.supabase_fetch", side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/v1/capabilities/email.send/resolve",
                headers={"X-Rhumb-Key": "test"},
            )

    data = resp.json()["data"]
    assert len(data["providers"]) == 1
    assert "configured" in data["providers"][0]
    assert isinstance(data["providers"][0]["configured"], bool)
