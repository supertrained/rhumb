"""Tests for Zendesk support direct capability registry surfaces."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app

SUPPORT_DIRECT_CAPABILITIES = [
    {
        "id": "ticket.search",
        "domain": "support",
        "action": "search",
        "description": "Search support tickets",
        "input_hint": "support_ref, query",
        "outcome": "Ticket summaries",
    },
    {
        "id": "ticket.get",
        "domain": "support",
        "action": "get",
        "description": "Fetch one support ticket",
        "input_hint": "support_ref, ticket_id",
        "outcome": "Ticket detail",
    },
    {
        "id": "ticket.list_comments",
        "domain": "support",
        "action": "list_comments",
        "description": "List support ticket comments",
        "input_hint": "support_ref, ticket_id",
        "outcome": "Ticket comments",
    },
]

VALID_SUPPORT_BUNDLE = json.dumps(
    {
        "provider": "zendesk",
        "subdomain": "acme",
        "auth_mode": "api_token",
        "email": "ops@example.com",
        "api_token": "secret-token",
        "allowed_group_ids": [12345],
        "allowed_brand_ids": [67890],
        "allow_internal_comments": False,
    }
)


def _mock_support_direct_supabase(path: str):
    if path.startswith("capabilities?"):
        if "id=eq.ticket.search" in path:
            return [SUPPORT_DIRECT_CAPABILITIES[0]]
        if "id=eq.ticket.get" in path:
            return [SUPPORT_DIRECT_CAPABILITIES[1]]
        if "id=eq.ticket.list_comments" in path:
            return [SUPPORT_DIRECT_CAPABILITIES[2]]
        return list(SUPPORT_DIRECT_CAPABILITIES)
    if path.startswith("capability_services?"):
        return [
            {
                "capability_id": "ticket.search",
                "service_slug": "intercom",
                "credential_modes": ["byo"],
                "auth_method": "oauth",
                "endpoint_pattern": "/proxy/intercom",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": None,
                "notes": "generic",
                "is_primary": False,
            },
            {
                "capability_id": "ticket.search",
                "service_slug": "zendesk",
                "credential_modes": ["byo"],
                "auth_method": "api_token",
                "endpoint_pattern": "/proxy/zendesk",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": None,
                "notes": "generic",
                "is_primary": True,
            },
        ]
    if path.startswith("scores?"):
        return []
    if path.startswith("services?"):
        return []
    if path.startswith("bundle_capabilities?"):
        return []
    return []


@pytest.fixture
def app():
    return create_app()


@pytest.mark.anyio
async def test_support_direct_capability_surfaces_prefer_zendesk_direct(app):
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_support_direct_supabase,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_resp = await client.get("/v1/capabilities")
            get_resp = await client.get("/v1/capabilities/ticket.search")
            resolve_resp = await client.get("/v1/capabilities/ticket.search/resolve")
            modes_resp = await client.get("/v1/capabilities/ticket.search/credential-modes")

    list_item = next(item for item in list_resp.json()["data"]["items"] if item["id"] == "ticket.search")
    assert list_item["provider_count"] == 1
    assert list_item["top_provider"]["slug"] == "zendesk"

    get_data = get_resp.json()["data"]
    assert get_data["provider_count"] == 1
    assert get_data["providers"][0]["service_slug"] == "zendesk"
    assert get_data["providers"][0]["auth_method"] == "support_ref"

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["service_slug"] == "zendesk"
    assert resolve_data["providers"][0]["credential_modes"] == ["byok"]
    assert resolve_data["providers"][0]["configured"] is False
    assert resolve_data["execute_hint"]["preferred_provider"] == "zendesk"
    assert "support_ref" in resolve_data["providers"][0]["recommendation_reason"]

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "zendesk"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert mode_data["providers"][0]["modes"][0]["configured"] is False
    assert mode_data["providers"][0]["any_configured"] is False
    assert "RHUMB_SUPPORT_<REF>" in mode_data["providers"][0]["modes"][0]["setup_hint"]


@pytest.mark.anyio
async def test_support_direct_capability_surfaces_show_configured_when_valid_bundle_exists(app):
    with patch.dict(os.environ, {"RHUMB_SUPPORT_ST_ZD": VALID_SUPPORT_BUNDLE}, clear=False):
        with patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_support_direct_supabase,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resolve_resp = await client.get("/v1/capabilities/ticket.search/resolve")
                modes_resp = await client.get("/v1/capabilities/ticket.search/credential-modes")

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["configured"] is True

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["modes"][0]["configured"] is True
    assert mode_data["providers"][0]["any_configured"] is True
