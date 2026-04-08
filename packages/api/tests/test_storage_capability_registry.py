"""Tests for synthetic AWS S3 capability registry surfaces."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_capabilities_list_includes_synthetic_object_storage_capabilities(app) -> None:
    async def fake_fetch(path: str):
        if path.startswith("capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new=AsyncMock(side_effect=fake_fetch)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/v1/capabilities?search=s3")

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    ids = {item["id"] for item in items}
    assert "object.list" in ids
    assert "object.head" in ids
    assert "object.get" in ids


@pytest.mark.asyncio
async def test_get_object_storage_capability_returns_synthetic_provider_details(app) -> None:
    async def fake_fetch(path: str):
        if path.startswith("capabilities?id=eq.object.list"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new=AsyncMock(side_effect=fake_fetch)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/v1/capabilities/object.list")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["id"] == "object.list"
    assert body["providers"][0]["service_slug"] == "aws-s3"


@pytest.mark.asyncio
async def test_resolve_and_credential_modes_work_for_synthetic_object_storage_capability(app) -> None:
    async def fake_fetch(path: str):
        if path.startswith("capabilities?id=eq.object.get"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new=AsyncMock(side_effect=fake_fetch)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resolve_response = await client.get("/v1/capabilities/object.get/resolve")
            modes_response = await client.get("/v1/capabilities/object.get/credential-modes")

    assert resolve_response.status_code == 200
    resolve_body = resolve_response.json()["data"]
    assert resolve_body["providers"][0]["service_slug"] == "aws-s3"
    assert resolve_body["providers"][0]["auth_method"] == "storage_ref"

    assert modes_response.status_code == 200
    providers = modes_response.json()["data"]["providers"]
    assert providers[0]["service_slug"] == "aws-s3"
    assert providers[0]["modes"][0]["mode"] == "byok"
