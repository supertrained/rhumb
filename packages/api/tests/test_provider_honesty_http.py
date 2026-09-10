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
async def test_search_query_resolve_splits_schema_ready_from_callable(app):
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
    slugs = [provider["service_slug"] for provider in data["providers"]]
    assert slugs[:3] == ["exa", "tavily", "brave-search-api"]
    assert slugs[3:] == ["algolia", "elasticsearch", "meilisearch", "typesense"]
    assert data["execute_hint"]["preferred_provider"] == "exa"
    assert data["execute_hint"]["schema_ready"] is True
    assert data["execute_hint"]["tenant_configured"] is True
    assert data["execute_hint"]["callable"] is True
    assert data["execute_hint"]["configured"] is True

    by_slug = {provider["service_slug"]: provider for provider in data["providers"]}
    for slug in INDEX_ENGINES:
        provider = by_slug[slug]
        assert provider["available_for_execute"] is True
        assert provider["configured"] is False
        assert provider["schema_ready"] is True
        assert provider["tenant_configured"] is False
        assert provider["callable"] is False

    exa = by_slug["exa"]
    assert exa["available_for_execute"] is True
    assert exa["configured"] is True
    assert exa["schema_ready"] is True
    assert exa["tenant_configured"] is True
    assert exa["callable"] is True


@pytest.mark.anyio
async def test_search_query_estimate_labels_unconfigured_index_engine(app):
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
            meili_resp = await client.get(
                "/v1/capabilities/search.query/execute/estimate",
                params={"provider": "meilisearch"},
            )
            typesense_resp = await client.get(
                "/v1/capabilities/search.query/execute/estimate",
                params={"provider": "typesense"},
            )

    default_data = default_resp.json()["data"]
    assert default_resp.status_code == 200
    assert default_data["provider"] == "exa"
    assert default_data["schema_ready"] is True
    assert default_data["tenant_configured"] is True
    assert default_data["callable"] is True

    for resp, slug in (
        (elastic_resp, "elasticsearch"),
        (meili_resp, "meilisearch"),
        (typesense_resp, "typesense"),
    ):
        data = resp.json()["data"]
        assert resp.status_code == 200
        assert data["provider"] == slug
        assert data["circuit_state"] == "closed"
        assert bool(data["endpoint_pattern"]) is True
        assert data["schema_ready"] is True
        assert data["tenant_configured"] is False
        assert data["callable"] is False
