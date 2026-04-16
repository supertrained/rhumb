"""Tests for direct /resolve provider mode-configuration shape."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app

SINGLE_PROVIDER_DIRECT_CASES = [
    (
        "warehouse.query.read",
        "bigquery",
        "routes.capabilities.has_any_warehouse_bundle_configured",
    ),
    (
        "object.get",
        "aws-s3",
        "routes.capabilities.has_any_storage_bundle_configured",
    ),
    (
        "deployment.list",
        "vercel",
        "routes.capabilities.has_any_deployment_bundle_configured",
    ),
    (
        "workflow_run.list",
        "github",
        "routes.capabilities.has_any_actions_bundle_configured",
    ),
    (
        "ticket.search",
        "zendesk",
        "routes.capabilities.has_any_support_bundle_configured",
    ),
    (
        "conversation.list",
        "intercom",
        "routes.capabilities.has_any_support_bundle_configured",
    ),
]


async def _mock_supabase_empty(_path: str):
    return []


@pytest.fixture
def app():
    return create_app()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("capability_id", "service_slug", "patch_target"),
    SINGLE_PROVIDER_DIRECT_CASES,
)
async def test_single_provider_direct_resolve_exposes_unconfigured_mode_shape(
    app,
    capability_id: str,
    service_slug: str,
    patch_target: str,
):
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_empty,
    ), patch(patch_target, return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/v1/capabilities/{capability_id}/resolve")

    data = response.json()["data"]
    provider = data["providers"][0]
    assert provider["service_slug"] == service_slug
    assert provider["configured"] is False
    assert provider["configured_by_mode"] == {"byok": False}
    assert provider["configured_credential_modes"] == []
    assert data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert data["execute_hint"]["configured"] is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("capability_id", "service_slug", "patch_target"),
    SINGLE_PROVIDER_DIRECT_CASES,
)
async def test_single_provider_direct_resolve_exposes_configured_mode_shape(
    app,
    capability_id: str,
    service_slug: str,
    patch_target: str,
):
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_empty,
    ), patch(patch_target, return_value=True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/v1/capabilities/{capability_id}/resolve")

    data = response.json()["data"]
    provider = data["providers"][0]
    assert provider["service_slug"] == service_slug
    assert provider["configured"] is True
    assert provider["configured_by_mode"] == {"byok": True}
    assert provider["configured_credential_modes"] == ["byok"]
    assert data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert data["execute_hint"]["configured"] is True


@pytest.mark.anyio
async def test_crm_direct_resolve_exposes_configured_mode_shape_per_provider(app):
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_empty,
    ), patch(
        "routes.capabilities.has_any_crm_bundle_configured",
        side_effect=lambda provider_slug: provider_slug == "salesforce",
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/v1/capabilities/crm.record.search/resolve")

    data = response.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == [
        "salesforce",
        "hubspot",
    ]

    salesforce_provider = data["providers"][0]
    assert salesforce_provider["configured"] is True
    assert salesforce_provider["configured_by_mode"] == {"byok": True}
    assert salesforce_provider["configured_credential_modes"] == ["byok"]

    hubspot_provider = data["providers"][1]
    assert hubspot_provider["configured"] is False
    assert hubspot_provider["configured_by_mode"] == {"byok": False}
    assert hubspot_provider["configured_credential_modes"] == []

    assert data["execute_hint"]["preferred_provider"] == "salesforce"
    assert data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert data["execute_hint"]["configured"] is True
