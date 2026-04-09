"""Tests for GitHub Actions direct capability registry surfaces."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app

VALID_GITHUB_ACTIONS_BUNDLE = json.dumps(
    {
        "provider": "github",
        "auth_mode": "bearer_token",
        "bearer_token": "secret-token",
        "allowed_repositories": ["openclaw/openclaw"],
    }
)


async def _mock_supabase_empty(_path: str):
    return []


@pytest.fixture
def app():
    return create_app()


@pytest.mark.anyio
async def test_actions_direct_capability_surfaces_prefer_github_direct(app):
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_empty,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_resp = await client.get("/v1/capabilities")
            get_resp = await client.get("/v1/capabilities/workflow_run.list")
            resolve_resp = await client.get("/v1/capabilities/workflow_run.list/resolve")
            modes_resp = await client.get("/v1/capabilities/workflow_run.list/credential-modes")

    list_item = next(item for item in list_resp.json()["data"]["items"] if item["id"] == "workflow_run.list")
    assert list_item["provider_count"] == 1
    assert list_item["top_provider"]["slug"] == "github"

    get_data = get_resp.json()["data"]
    assert get_data["provider_count"] == 1
    assert get_data["providers"][0]["service_slug"] == "github"
    assert get_data["providers"][0]["auth_method"] == "actions_ref"

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["service_slug"] == "github"
    assert resolve_data["providers"][0]["credential_modes"] == ["byok"]
    assert resolve_data["providers"][0]["configured"] is False
    assert resolve_data["execute_hint"]["preferred_provider"] == "github"
    assert "repository scope" in resolve_data["providers"][0]["recommendation_reason"]

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "github"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert mode_data["providers"][0]["modes"][0]["configured"] is False
    assert mode_data["providers"][0]["any_configured"] is False
    assert "RHUMB_ACTIONS_<REF>" in mode_data["providers"][0]["modes"][0]["setup_hint"]


@pytest.mark.anyio
async def test_actions_direct_capability_shows_configured_when_valid_bundle_exists(app):
    with patch.dict(os.environ, {"RHUMB_ACTIONS_GH_MAIN": VALID_GITHUB_ACTIONS_BUNDLE}, clear=False):
        with patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_empty,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resolve_resp = await client.get("/v1/capabilities/workflow_run.list/resolve")
                modes_resp = await client.get("/v1/capabilities/workflow_run.list/credential-modes")

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["configured"] is True

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["modes"][0]["configured"] is True
    assert mode_data["providers"][0]["any_configured"] is True
