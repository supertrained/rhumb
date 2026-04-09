"""Tests for HubSpot CRM direct capability registry surfaces."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app

VALID_HUBSPOT_BUNDLE = json.dumps(
    {
        "provider": "hubspot",
        "auth_mode": "private_app_token",
        "private_app_token": "secret-token",
        "portal_id": "12345678",
        "allowed_object_types": ["contacts"],
        "allowed_properties_by_object": {
            "contacts": ["email", "firstname", "lastname"],
        },
    }
)


async def _mock_supabase_empty(_path: str):
    return []


@pytest.fixture
def app():
    return create_app()


@pytest.mark.anyio
async def test_crm_direct_capability_surfaces_prefer_hubspot_direct(app):
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_empty,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_resp = await client.get("/v1/capabilities")
            get_resp = await client.get("/v1/capabilities/crm.record.search")
            resolve_resp = await client.get("/v1/capabilities/crm.record.search/resolve")
            modes_resp = await client.get("/v1/capabilities/crm.record.search/credential-modes")

    list_item = next(item for item in list_resp.json()["data"]["items"] if item["id"] == "crm.record.search")
    assert list_item["provider_count"] == 1
    assert list_item["top_provider"]["slug"] == "hubspot"

    get_data = get_resp.json()["data"]
    assert get_data["provider_count"] == 1
    assert get_data["providers"][0]["service_slug"] == "hubspot"
    assert get_data["providers"][0]["auth_method"] == "crm_ref"

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["service_slug"] == "hubspot"
    assert resolve_data["providers"][0]["credential_modes"] == ["byok"]
    assert resolve_data["providers"][0]["configured"] is False
    assert resolve_data["execute_hint"]["preferred_provider"] == "hubspot"
    assert "crm_ref" in resolve_data["providers"][0]["recommendation_reason"]

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "hubspot"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert mode_data["providers"][0]["modes"][0]["configured"] is False
    assert mode_data["providers"][0]["any_configured"] is False
    assert "RHUMB_CRM_<REF>" in mode_data["providers"][0]["modes"][0]["setup_hint"]


@pytest.mark.anyio
async def test_crm_direct_capability_shows_configured_when_valid_bundle_exists(app):
    with patch.dict(os.environ, {"RHUMB_CRM_HS_MAIN": VALID_HUBSPOT_BUNDLE}, clear=False):
        with patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_empty,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resolve_resp = await client.get("/v1/capabilities/crm.record.search/resolve")
                modes_resp = await client.get("/v1/capabilities/crm.record.search/credential-modes")

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["configured"] is True

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["modes"][0]["configured"] is True
    assert mode_data["providers"][0]["any_configured"] is True
