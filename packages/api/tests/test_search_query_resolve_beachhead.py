"""search.query resolve ranks beachhead web search above index engines."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from services.search_query_resolve_rank import (
    SearchQueryProviderClass,
    search_query_provider_class,
)

SEARCH_QUERY = {
    "id": "search.query",
    "domain": "search",
    "action": "query",
    "description": "Search the web",
}

SEARCH_WEB_SEARCH = {
    "id": "search.web_search",
    "domain": "search",
    "action": "web_search",
    "description": "Search the web",
}

EMAIL_SEND = {
    "id": "email.send",
    "domain": "email",
    "action": "send",
    "description": "Send transactional or marketing email",
}

BEACHHEAD_FIRST = ["exa", "tavily", "brave-search-api"]
INDEX_ENGINES = ["algolia", "elasticsearch", "meilisearch", "typesense"]


def _mapping(service_slug: str, *, endpoint: str = "GET /search") -> dict[str, object]:
    return {
        "service_slug": service_slug,
        "credential_modes": ["byo"],
        "auth_method": "api_key",
        "endpoint_pattern": endpoint,
        "cost_per_call": None,
        "cost_currency": "USD",
        "free_tier_calls": None,
        "notes": None,
    }


def _score(service_slug: str, an_score: float) -> dict[str, object]:
    return {
        "service_slug": service_slug,
        "aggregate_recommendation_score": an_score,
        "execution_score": an_score,
        "access_readiness_score": an_score,
        "tier": "L3",
        "tier_label": "Ready",
        "confidence": 0.9,
    }


def _service(slug: str, name: str) -> dict[str, str]:
    return {"slug": slug, "name": name}


LIVE_LIKE_MAPPINGS = [
    _mapping("algolia"),
    _mapping("elasticsearch"),
    _mapping("meilisearch"),
    _mapping("exa"),
    _mapping("typesense"),
    _mapping("tavily"),
    _mapping("brave-search"),
]

LIVE_LIKE_SCORES = [
    _score("algolia", 9.0),
    _score("elasticsearch", 8.9),
    _score("meilisearch", 8.7),
    _score("exa", 8.7),
    _score("typesense", 8.6),
    _score("tavily", 8.6),
    _score("brave-search-api", 7.1),
]

LIVE_LIKE_SERVICES = [
    _service("algolia", "Algolia"),
    _service("elasticsearch", "Elasticsearch"),
    _service("meilisearch", "Meilisearch"),
    _service("exa", "Exa"),
    _service("typesense", "Typesense"),
    _service("tavily", "Tavily"),
    _service("brave-search-api", "Brave Search API"),
]


def _catalog_fetch(
    *,
    capability: dict[str, str],
    mappings: list[dict[str, object]],
    scores: list[dict[str, object]],
    services: list[dict[str, str]],
):
    capability_id = capability["id"]

    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            if f"id=eq.{capability_id}" in path:
                return [capability]
            return []
        if path.startswith("capability_services?"):
            if f"capability_id=eq.{capability_id}" in path:
                return mappings
            return []
        if path.startswith("scores?"):
            return scores
        if path.startswith("services?"):
            return services
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    return mock_fetch


@pytest.fixture
def app():
    return create_app()


def test_brave_search_alias_is_beachhead_class() -> None:
    assert (
        search_query_provider_class("brave-search") is SearchQueryProviderClass.BEACHHEAD_WEB_SEARCH
    )
    assert (
        search_query_provider_class("brave-search-api")
        is SearchQueryProviderClass.BEACHHEAD_WEB_SEARCH
    )
    assert search_query_provider_class("algolia") is SearchQueryProviderClass.INDEX_ENGINE
    assert search_query_provider_class("people-data-labs") is SearchQueryProviderClass.OTHER
    assert search_query_provider_class("firecrawl") is SearchQueryProviderClass.OTHER


@pytest.mark.anyio
async def test_search_query_resolve_prefers_beachhead_web_over_index_engines(app):
    mock_fetch = _catalog_fetch(
        capability=SEARCH_QUERY,
        mappings=LIVE_LIKE_MAPPINGS,
        scores=LIVE_LIKE_SCORES,
        services=LIVE_LIKE_SERVICES,
    )
    with patch(
        "routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/search.query/resolve")

    assert resp.status_code == 200
    data = resp.json()["data"]
    slugs = [provider["service_slug"] for provider in data["providers"]]
    assert slugs[:3] == BEACHHEAD_FIRST
    assert slugs[3:] == INDEX_ENGINES
    assert "brave-search" not in slugs
    assert "firecrawl" not in slugs
    assert data["capability"] == "search.query"
    assert data["fallback_chain"] == BEACHHEAD_FIRST
    assert data["execute_hint"]["preferred_provider"] == "exa"
    assert data["execute_hint"]["selection_reason"] == "highest_ranked_provider"
    assert data["execute_hint"]["fallback_providers"] == [
        "tavily",
        "brave-search-api",
        "algolia",
    ]
    by_slug = {provider["service_slug"]: provider for provider in data["providers"]}
    assert by_slug["algolia"]["an_score"] == 9.0
    assert by_slug["algolia"]["recommendation"] == "preferred"
    assert by_slug["brave-search-api"]["an_score"] == 7.1
    assert by_slug["brave-search-api"]["recommendation"] == "available"


@pytest.mark.anyio
async def test_search_query_resolve_ranks_other_providers_above_index_engines(app):
    mock_fetch = _catalog_fetch(
        capability=SEARCH_QUERY,
        mappings=[
            _mapping("algolia"),
            _mapping("people-data-labs", endpoint="POST /person/enrich"),
            _mapping("exa"),
        ],
        scores=[
            _score("algolia", 9.0),
            _score("people-data-labs", 6.4),
            _score("exa", 8.7),
        ],
        services=[
            _service("algolia", "Algolia"),
            _service("people-data-labs", "People Data Labs"),
            _service("exa", "Exa"),
        ],
    )
    with patch(
        "routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/search.query/resolve")

    slugs = [provider["service_slug"] for provider in resp.json()["data"]["providers"]]
    assert slugs == ["exa", "people-data-labs", "algolia"]


@pytest.mark.anyio
async def test_search_query_resolve_index_only_catalog_keeps_an_order(app):
    mock_fetch = _catalog_fetch(
        capability=SEARCH_QUERY,
        mappings=[_mapping(slug) for slug in INDEX_ENGINES],
        scores=[
            _score("algolia", 9.0),
            _score("elasticsearch", 8.9),
            _score("meilisearch", 8.7),
            _score("typesense", 8.6),
        ],
        services=[_service(slug, slug) for slug in INDEX_ENGINES],
    )
    with patch(
        "routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/search.query/resolve")

    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == INDEX_ENGINES
    assert data["execute_hint"]["preferred_provider"] == "algolia"
    assert data["fallback_chain"] == INDEX_ENGINES[:3]


@pytest.mark.anyio
async def test_search_web_search_resolve_stays_an_ranked(app):
    mock_fetch = _catalog_fetch(
        capability=SEARCH_WEB_SEARCH,
        mappings=LIVE_LIKE_MAPPINGS,
        scores=LIVE_LIKE_SCORES,
        services=LIVE_LIKE_SERVICES,
    )
    with patch(
        "routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/search.web_search/resolve")

    data = resp.json()["data"]
    slugs = [provider["service_slug"] for provider in data["providers"]]
    assert slugs[0] == "algolia"
    assert data["execute_hint"]["preferred_provider"] == "algolia"
    assert data["fallback_chain"][0] == "algolia"


@pytest.mark.anyio
async def test_email_send_resolve_stays_an_ranked(app):
    mock_fetch = _catalog_fetch(
        capability=EMAIL_SEND,
        mappings=[
            _mapping("sendgrid", endpoint="POST /v3/mail/send"),
            _mapping("resend", endpoint="POST /emails"),
        ],
        scores=[
            _score("resend", 7.79),
            _score("sendgrid", 6.35),
        ],
        services=[
            _service("sendgrid", "SendGrid"),
            _service("resend", "Resend"),
        ],
    )
    with patch(
        "routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")

    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == ["resend", "sendgrid"]
    assert data["execute_hint"]["preferred_provider"] == "resend"
    assert data["execute_hint"]["selection_reason"] == "highest_ranked_provider"
