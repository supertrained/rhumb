"""Tests for Intercom support direct capability registry surfaces."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app

VALID_INTERCOM_BUNDLE = json.dumps(
    {
        "provider": "intercom",
        "region": "us",
        "auth_mode": "bearer_token",
        "bearer_token": "secret-token",
        "allowed_team_ids": [12345],
        "allow_internal_notes": False,
    }
)


async def _mock_supabase_empty(_path: str):
    return []


@pytest.fixture
def app():
    return create_app()


@pytest.mark.anyio
async def test_intercom_direct_capability_surfaces_prefer_intercom_direct(app):
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_empty,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_resp = await client.get("/v1/capabilities")
            get_resp = await client.get("/v1/capabilities/conversation.list")
            resolve_resp = await client.get("/v1/capabilities/conversation.list/resolve")
            modes_resp = await client.get("/v1/capabilities/conversation.list/credential-modes")

    list_item = next(item for item in list_resp.json()["data"]["items"] if item["id"] == "conversation.list")
    assert list_item["provider_count"] == 1
    assert list_item["top_provider"]["slug"] == "intercom"

    get_data = get_resp.json()["data"]
    assert get_data["provider_count"] == 1
    assert get_data["providers"][0]["service_slug"] == "intercom"
    assert get_data["providers"][0]["auth_method"] == "support_ref"

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["service_slug"] == "intercom"
    assert resolve_data["providers"][0]["credential_modes"] == ["byok"]
    assert resolve_data["providers"][0]["configured"] is False
    assert resolve_data["execute_hint"]["preferred_provider"] == "intercom"
    assert "allowed_team_ids" in resolve_data["providers"][0]["recommendation_reason"] or "team/admin scope" in resolve_data["providers"][0]["recommendation_reason"]

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "intercom"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert mode_data["providers"][0]["modes"][0]["configured"] is False
    assert mode_data["providers"][0]["any_configured"] is False
    assert "provider=intercom" in mode_data["providers"][0]["modes"][0]["setup_hint"]


@pytest.mark.anyio
async def test_intercom_direct_capability_surfaces_show_configured_when_valid_bundle_exists(app):
    with patch.dict(os.environ, {"RHUMB_SUPPORT_SUP_CHAT": VALID_INTERCOM_BUNDLE}, clear=False):
        with patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_empty,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resolve_resp = await client.get("/v1/capabilities/conversation.list/resolve")
                modes_resp = await client.get("/v1/capabilities/conversation.list/credential-modes")

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["configured"] is True

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["modes"][0]["configured"] is True
    assert mode_data["providers"][0]["any_configured"] is True
