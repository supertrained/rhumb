"""Tests for warehouse direct capability registry surfaces."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app

VALID_BIGQUERY_BUNDLE = json.dumps(
    {
        "provider": "bigquery",
        "auth_mode": "service_account_json",
        "service_account_json": {
            "type": "service_account",
            "project_id": "proj",
            "client_email": "rhumb@example.iam.gserviceaccount.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
        },
        "billing_project_id": "proj",
        "location": "US",
        "allowed_dataset_refs": ["proj.analytics"],
        "allowed_table_refs": ["proj.analytics.events"],
    }
)


async def _mock_supabase_empty(_path: str):
    return []


@pytest.fixture
def app():
    return create_app()


@pytest.mark.anyio
async def test_warehouse_direct_capability_surfaces_prefer_bigquery_direct(app):
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_supabase_empty,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_resp = await client.get("/v1/capabilities")
            get_resp = await client.get("/v1/capabilities/warehouse.query.read")
            resolve_resp = await client.get("/v1/capabilities/warehouse.query.read/resolve")
            modes_resp = await client.get(
                "/v1/capabilities/warehouse.query.read/credential-modes"
            )

    list_item = next(
        item for item in list_resp.json()["data"]["items"] if item["id"] == "warehouse.query.read"
    )
    assert list_item["provider_count"] == 1
    assert list_item["top_provider"]["slug"] == "bigquery"

    get_data = get_resp.json()["data"]
    assert get_data["provider_count"] == 1
    assert get_data["providers"][0]["service_slug"] == "bigquery"
    assert get_data["providers"][0]["auth_method"] == "warehouse_ref"

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["service_slug"] == "bigquery"
    assert resolve_data["providers"][0]["credential_modes"] == ["byok"]
    assert resolve_data["providers"][0]["configured"] is False
    assert resolve_data["execute_hint"]["preferred_provider"] == "bigquery"
    assert "dry-run-before-run" in resolve_data["providers"][0]["recommendation_reason"]

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "bigquery"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert mode_data["providers"][0]["modes"][0]["configured"] is False
    assert "RHUMB_WAREHOUSE_<REF>" in mode_data["providers"][0]["modes"][0]["setup_hint"]
    assert "billing_project_id" in mode_data["providers"][0]["modes"][0]["setup_hint"]
    assert "location" in mode_data["providers"][0]["modes"][0]["setup_hint"]
    assert "allowed_dataset_refs and allowed_table_refs" in mode_data["providers"][0]["modes"][0]["setup_hint"]


@pytest.mark.anyio
async def test_warehouse_direct_capability_shows_configured_when_valid_bundle_exists(app):
    with patch.dict(os.environ, {"RHUMB_WAREHOUSE_BQ_MAIN": VALID_BIGQUERY_BUNDLE}, clear=False):
        with patch(
            "routes.capabilities.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_mock_supabase_empty,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resolve_resp = await client.get("/v1/capabilities/warehouse.query.read/resolve")
                modes_resp = await client.get(
                    "/v1/capabilities/warehouse.query.read/credential-modes"
                )

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["configured"] is True

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["modes"][0]["configured"] is True
    assert mode_data["providers"][0]["any_configured"] is True
