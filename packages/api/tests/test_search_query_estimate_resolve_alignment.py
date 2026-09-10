from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from tests.test_search_query_resolve_beachhead import (
    LIVE_LIKE_SCORES,
    LIVE_LIKE_SERVICES,
    SEARCH_QUERY,
    _catalog_fetch,
    _mapping,
)

BEACHHEAD_MANAGED_MODES = ["byo", "rhumb_managed"]


def _alignment_mapping(service_slug: str, *, endpoint: str, cost: str | None) -> dict[str, object]:
    row = _mapping(service_slug, endpoint=endpoint)
    if service_slug in {"exa", "tavily", "brave-search"}:
        row["credential_modes"] = list(BEACHHEAD_MANAGED_MODES)
        row["cost_per_call"] = cost
    return row


ALIGNMENT_MAPPINGS = [
    _alignment_mapping("algolia", endpoint="POST /1/indexes/{index}/query", cost="0.001"),
    _alignment_mapping("elasticsearch", endpoint="POST /{index}/_search", cost="0.0001"),
    _alignment_mapping("meilisearch", endpoint="POST /indexes/{uid}/search", cost="0.0001"),
    _alignment_mapping("exa", endpoint="POST /search", cost="0.001"),
    _alignment_mapping(
        "typesense", endpoint="GET /collections/{col}/documents/search", cost="0.0001"
    ),
    _alignment_mapping("tavily", endpoint="POST /search", cost="0.001"),
    _alignment_mapping("brave-search", endpoint="GET /res/v1/web/search", cost="0.003"),
]


def _managed_row(service_slug: str, *, method: str, path: str) -> dict[str, object]:
    return {
        "id": f"managed-{service_slug}",
        "capability_id": "search.query",
        "service_slug": service_slug,
        "description": service_slug,
        "credential_env_keys": ["RHUMB_TEST_KEY"],
        "default_method": method,
        "default_path": path,
        "default_headers": None,
        "daily_limit_per_agent": 100,
    }


MANAGED_BY_SLUG = {
    "brave-search-api": _managed_row("brave-search-api", method="GET", path="/res/v1/web/search"),
    "brave-search": _managed_row("brave-search", method="GET", path="/res/v1/web/search"),
    "exa": _managed_row("exa", method="POST", path="/search"),
    "tavily": _managed_row("tavily", method="POST", path="/search"),
}


def _alignment_fetch():
    catalog = _catalog_fetch(
        capability=SEARCH_QUERY,
        mappings=ALIGNMENT_MAPPINGS,
        scores=LIVE_LIKE_SCORES,
        services=LIVE_LIKE_SERVICES,
    )

    async def mock_fetch(path: str):
        if path.startswith("rhumb_managed_capabilities?"):
            if "service_slug=eq." in path:
                for slug, row in MANAGED_BY_SLUG.items():
                    if f"service_slug=eq.{slug}" in path:
                        return [row]
                return []
            return [MANAGED_BY_SLUG["brave-search-api"]]
        if path.startswith("capability_executions?"):
            return []
        return await catalog(path)

    return mock_fetch


@pytest.fixture
def app():
    return create_app()


@pytest.mark.anyio
async def test_search_query_estimate_default_provider_matches_resolve_preferred(app):
    mock_fetch = _alignment_fetch()
    breaker = SimpleNamespace(
        state=SimpleNamespace(value="closed"),
        allow_request=lambda: True,
    )
    breaker_registry = SimpleNamespace(get=lambda *_args, **_kwargs: breaker)

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
            return_value=breaker_registry,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resolve_resp = await client.get("/v1/capabilities/search.query/resolve")
            estimate_resp = await client.get("/v1/capabilities/search.query/execute/estimate")

    assert resolve_resp.status_code == 200
    assert estimate_resp.status_code == 200
    resolve_data = resolve_resp.json()["data"]
    estimate_data = estimate_resp.json()["data"]
    assert resolve_data["execute_hint"]["preferred_provider"] == "exa"
    assert estimate_data["provider"] == "exa"
    assert estimate_data["provider"] == resolve_data["execute_hint"]["preferred_provider"]
    assert estimate_data["credential_mode"] == "rhumb_managed"
    assert estimate_data["cost_estimate_usd"] == 0.001
    assert estimate_resp.json()["error"] is None
