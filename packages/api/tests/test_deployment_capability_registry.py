"""Tests for Vercel deployment direct capability registry surfaces."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app

VALID_VERCEL_BUNDLE = json.dumps(
    {
        "provider": "vercel",
        "auth_mode": "bearer_token",
        "bearer_token": "secret-token",
        "allowed_project_ids": ["prj_123"],
        "allowed_targets": ["production"],
    }
)


async def _mock_supabase_empty(_path: str):
    return []


async def _mock_supabase_with_stale_mapping(path: str):
    if path.startswith("capability_services?"):
        return [
            {
                "capability_id": "deployment.list",
                "service_slug": "stale-deployment-proxy",
                "credential_modes": ["byo"],
                "auth_method": "api_key",
                "endpoint_pattern": "/proxy/stale-deployment",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": None,
                "notes": "stale mapping row",
                "is_primary": True,
            }
        ]
    if path.startswith("scores?"):
        return []
    if path.startswith("services?"):
        return []
    return []


@pytest.fixture
def app():
    return create_app()


@pytest.mark.anyio
async def test_deployment_direct_capability_surfaces_prefer_vercel_direct(app):
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_empty,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_resp = await client.get("/v1/capabilities")
            get_resp = await client.get("/v1/capabilities/deployment.list")
            resolve_resp = await client.get("/v1/capabilities/deployment.list/resolve")
            modes_resp = await client.get("/v1/capabilities/deployment.list/credential-modes")

    list_item = next(item for item in list_resp.json()["data"]["items"] if item["id"] == "deployment.list")
    assert list_item["provider_count"] == 1
    assert list_item["top_provider"]["slug"] == "vercel"

    get_data = get_resp.json()["data"]
    assert get_data["provider_count"] == 1
    assert get_data["providers"][0]["service_slug"] == "vercel"
    assert get_data["providers"][0]["auth_method"] == "deployment_ref"

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["service_slug"] == "vercel"
    assert resolve_data["providers"][0]["credential_modes"] == ["byok"]
    assert resolve_data["providers"][0]["configured"] is False
    assert resolve_data["execute_hint"]["preferred_provider"] == "vercel"
    assert "project scope" in resolve_data["providers"][0]["recommendation_reason"]

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "vercel"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert mode_data["providers"][0]["modes"][0]["configured"] is False
    assert mode_data["providers"][0]["any_configured"] is False
    assert "RHUMB_DEPLOYMENT_<REF>" in mode_data["providers"][0]["modes"][0]["setup_hint"]


@pytest.mark.anyio
async def test_deployment_direct_capability_ignores_catalog_mapping_rows(app):
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_with_stale_mapping,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_resp = await client.get("/v1/capabilities")
            get_resp = await client.get("/v1/capabilities/deployment.list")
            resolve_resp = await client.get("/v1/capabilities/deployment.list/resolve")
            modes_resp = await client.get("/v1/capabilities/deployment.list/credential-modes")

    list_item = next(item for item in list_resp.json()["data"]["items"] if item["id"] == "deployment.list")
    assert list_item["provider_count"] == 1
    assert list_item["top_provider"]["slug"] == "vercel"

    get_data = get_resp.json()["data"]
    assert get_data["provider_count"] == 1
    assert get_data["providers"][0]["service_slug"] == "vercel"
    assert get_data["providers"][0]["auth_method"] == "deployment_ref"

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["service_slug"] == "vercel"
    assert resolve_data["providers"][0]["credential_modes"] == ["byok"]
    assert resolve_data["providers"][0]["auth_method"] == "deployment_ref"

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "vercel"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert mode_data["providers"][0]["modes"][0]["configured"] is False


@pytest.mark.anyio
async def test_deployment_direct_capability_shows_configured_when_valid_bundle_exists(app):
    with patch.dict(os.environ, {"RHUMB_DEPLOYMENT_DEP_MAIN": VALID_VERCEL_BUNDLE}, clear=False):
        with patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_empty,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resolve_resp = await client.get("/v1/capabilities/deployment.list/resolve")
                modes_resp = await client.get("/v1/capabilities/deployment.list/credential-modes")

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["configured"] is True

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["modes"][0]["configured"] is True
    assert mode_data["providers"][0]["any_configured"] is True
