from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from tests.test_search_query_estimate_resolve_alignment import _alignment_fetch


INDEX_ENGINES = ("elasticsearch", "meilisearch", "typesense")


@pytest.fixture
def app():
    return create_app()


def _closed_breaker_registry():
    breaker = SimpleNamespace(
        state=SimpleNamespace(value="closed"),
        allow_request=lambda: True,
    )
    return SimpleNamespace(get=lambda *_args, **_kwargs: breaker)


@pytest.mark.anyio
async def test_search_query_resolve_stamps_catalog_mode_map(app):
    mock_fetch = _alignment_fetch()
    with (
        patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
        patch(
            "routes.capabilities.get_breaker_registry",
            create=True,
            return_value=_closed_breaker_registry(),
        ),
        patch(
            "routes.proxy.get_breaker_registry",
            return_value=_closed_breaker_registry(),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/search.query/resolve")

    assert resp.status_code == 200
    data = resp.json()["data"]
    by_slug = {provider["service_slug"]: provider for provider in data["providers"]}

    exa = by_slug["exa"]
    assert exa["credential_modes"] == ["byok", "rhumb_managed"]
    assert exa["configured_by_mode"] == {"byok": False, "rhumb_managed": True}
    assert exa["configured_credential_modes"] == ["rhumb_managed"]
    assert exa["schema_ready"] is True
    assert exa["tenant_configured"] is True
    assert exa["callable"] is True

    hint = data["execute_hint"]
    assert hint["preferred_provider"] == "exa"
    assert hint["credential_modes"] == ["byok", "rhumb_managed"]
    assert hint["preferred_credential_mode"] == "rhumb_managed"
    assert hint["credential_modes_url"] == "/v1/capabilities/search.query/credential-modes"
    assert "configured_by_mode" not in hint
    assert hint["schema_ready"] is True
    assert hint["tenant_configured"] is True
    assert hint["callable"] is True

    for slug in INDEX_ENGINES:
        provider = by_slug[slug]
        assert provider["credential_modes"] == ["byok"]
        assert provider["configured_by_mode"] == {"byok": False}
        assert provider["configured_credential_modes"] == []
        assert provider["schema_ready"] is True
        assert provider["tenant_configured"] is False
        assert provider["callable"] is False


@pytest.mark.anyio
async def test_search_query_estimate_surfaces_mode_map_and_modes_url(app):
    mock_fetch = _alignment_fetch()
    with (
        patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
        patch(
            "services.rhumb_managed.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ),
        patch(
            "routes.capability_execute.get_breaker_registry",
            return_value=_closed_breaker_registry(),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            default_resp = await client.get("/v1/capabilities/search.query/execute/estimate")
            elastic_resp = await client.get(
                "/v1/capabilities/search.query/execute/estimate",
                params={"provider": "elasticsearch"},
            )

    default_data = default_resp.json()["data"]
    assert default_resp.status_code == 200
    assert default_data["provider"] == "exa"
    assert default_data["credential_mode"] == "rhumb_managed"
    assert default_data["credential_modes"] == ["byok", "rhumb_managed"]
    assert default_data["configured_by_mode"] == {"byok": False, "rhumb_managed": True}
    assert default_data["configured_credential_modes"] == ["rhumb_managed"]
    assert default_data["credential_modes_url"] == (
        "/v1/capabilities/search.query/credential-modes"
    )
    assert default_data["schema_ready"] is True
    assert default_data["tenant_configured"] is True
    assert default_data["callable"] is True

    elastic = elastic_resp.json()["data"]
    assert elastic_resp.status_code == 200
    assert elastic["provider"] == "elasticsearch"
    assert elastic["credential_mode"] == "byok"
    assert elastic["credential_modes"] == ["byok"]
    assert elastic["configured_by_mode"] == {"byok": False}
    assert elastic["configured_credential_modes"] == []
    assert elastic["credential_modes_url"] == (
        "/v1/capabilities/search.query/credential-modes"
    )
    assert elastic["schema_ready"] is True
    assert elastic["tenant_configured"] is False
    assert elastic["callable"] is False


@pytest.mark.anyio
async def test_direct_ticket_search_estimate_keeps_existing_mode_map(app):
    with (
        patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "routes.capabilities.has_any_support_bundle_configured",
            return_value=False,
        ),
        patch(
            "routes.capability_execute.get_breaker_registry",
            return_value=_closed_breaker_registry(),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resolve_resp = await client.get("/v1/capabilities/ticket.search/resolve")
            estimate_resp = await client.get(
                "/v1/capabilities/ticket.search/execute/estimate"
            )

    resolve_provider = resolve_resp.json()["data"]["providers"][0]
    assert resolve_resp.status_code == 200
    assert resolve_provider["service_slug"] == "zendesk"
    assert resolve_provider["configured_by_mode"] == {"byok": False}
    assert resolve_provider["configured_credential_modes"] == []
    assert resolve_provider["schema_ready"] is True
    assert resolve_provider["tenant_configured"] is False
    assert resolve_provider["callable"] is False

    estimate = estimate_resp.json()["data"]
    assert estimate_resp.status_code == 200
    assert estimate["provider"] == "zendesk"
    assert estimate["credential_mode"] == "byok"
    assert estimate["credential_modes"] == ["byok"]
    assert estimate["configured_by_mode"] == {"byok": False}
    assert estimate["configured_credential_modes"] == []
    assert estimate["credential_modes_url"] == (
        "/v1/capabilities/ticket.search/credential-modes"
    )
    assert estimate["schema_ready"] is True
    assert estimate["tenant_configured"] is False
    assert estimate["callable"] is False
    assert estimate["execute_readiness"]["credential_modes_url"] == (
        "/v1/capabilities/ticket.search/credential-modes"
    )


@pytest.mark.anyio
async def test_db_direct_estimate_copies_dual_mode_map(app):
    with (
        patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "routes.capability_execute.supabase_fetch",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "routes.capabilities.has_any_db_bundle_configured",
            return_value=False,
        ),
        patch(
            "routes.capability_execute.get_breaker_registry",
            return_value=_closed_breaker_registry(),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resolve_resp = await client.get("/v1/capabilities/db.query.read/resolve")
            estimate_resp = await client.get(
                "/v1/capabilities/db.query.read/execute/estimate"
            )

    resolve_provider = resolve_resp.json()["data"]["providers"][0]
    assert resolve_resp.status_code == 200
    assert resolve_provider["configured_by_mode"] == {
        "byok": False,
        "agent_vault": False,
    }
    assert resolve_provider["configured_credential_modes"] == []

    estimate = estimate_resp.json()["data"]
    assert estimate_resp.status_code == 200
    assert estimate["provider"] == "postgresql"
    assert estimate["credential_modes"] == ["byok", "agent_vault"]
    assert estimate["configured_by_mode"] == {
        "byok": False,
        "agent_vault": False,
    }
    assert estimate["configured_credential_modes"] == []
    assert estimate["credential_modes_url"] == (
        "/v1/capabilities/db.query.read/credential-modes"
    )
    assert estimate["schema_ready"] is True
    assert estimate["tenant_configured"] is False
    assert estimate["callable"] is False
