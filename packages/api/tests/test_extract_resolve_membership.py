from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from services.search_query_resolve_rank import SearchQueryProviderClass, search_query_provider_class


def _mapping(service_slug: str, endpoint: str) -> dict[str, object]:
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
        "tier": "L4",
        "tier_label": "Native",
        "confidence": 0.6,
        "calculated_at": "2026-09-10T00:00:00Z",
        "probe_metadata": {"freshness": "1 hour ago"},
    }


def _service(slug: str, name: str, category: str, description: str) -> dict[str, str]:
    return {
        "slug": slug,
        "name": name,
        "category": category,
        "description": description,
        "official_docs": f"https://docs.example/{slug}",
    }


SCRAPE_EXTRACT = {
    "id": "scrape.extract",
    "domain": "scrape",
    "action": "extract",
    "description": "Extract structured data from a web page URL",
}

SCRAPE_CRAWL = {
    "id": "scrape.crawl",
    "domain": "scrape",
    "action": "crawl",
    "description": "Crawl a website starting from a URL",
}

SCRAPE_SCREENSHOT = {
    "id": "scrape.screenshot",
    "domain": "scrape",
    "action": "screenshot",
    "description": "Capture a screenshot of a web page",
}

DOCUMENT_EXTRACT = {
    "id": "document.extract",
    "domain": "document",
    "action": "extract",
    "description": "Extract structured data from a document",
}

SEARCH_QUERY = {
    "id": "search.query",
    "domain": "search",
    "action": "query",
    "description": "Search the web",
}

SCRAPE_EXTRACT_MAPPINGS = [
    _mapping("firecrawl", "POST /v1/scrape"),
    _mapping("apify", "POST /v2/acts/{actorId}/runs"),
    _mapping("bright-data", "POST /datasets/trigger"),
]

SCRAPE_CRAWL_MAPPINGS = [
    _mapping("firecrawl", "POST /v1/crawl"),
    _mapping("apify", "POST /v2/acts/apify~web-scraper/runs"),
]

SCRAPE_SCREENSHOT_MAPPINGS = [
    _mapping("firecrawl", "POST /v1/scrape (screenshot option)"),
    _mapping("apify", "POST /v2/acts/apify~screenshot-url/runs"),
]

DOCUMENT_EXTRACT_MAPPINGS = [
    _mapping("google-document-ai", "POST /v1/projects/{project}/processors/{processor}:process"),
    _mapping("unstructured", "POST /general/v0/general"),
]

SEARCH_QUERY_MAPPINGS = [
    _mapping("algolia", "POST /1/indexes/{index}/query"),
    _mapping("exa", "POST /search"),
    _mapping("tavily", "POST /search"),
    _mapping("brave-search-api", "GET /res/v1/web/search"),
]


def _resolve_fetch(
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


def test_firecrawl_is_not_a_search_query_beachhead_class() -> None:
    assert search_query_provider_class("firecrawl") is SearchQueryProviderClass.OTHER
    assert search_query_provider_class("firecrawl-v3") is SearchQueryProviderClass.OTHER


@pytest.mark.anyio
async def test_scrape_extract_family_resolve_includes_firecrawl(app):
    cases = (
        (SCRAPE_EXTRACT, SCRAPE_EXTRACT_MAPPINGS, "POST /v1/scrape"),
        (SCRAPE_CRAWL, SCRAPE_CRAWL_MAPPINGS, "POST /v1/crawl"),
        (SCRAPE_SCREENSHOT, SCRAPE_SCREENSHOT_MAPPINGS, "POST /v1/scrape (screenshot option)"),
    )
    for capability, mappings, endpoint in cases:
        mock_fetch = _resolve_fetch(
            capability=capability,
            mappings=mappings,
            scores=[
                _score("firecrawl", 8.8),
                _score("apify", 8.6),
                _score("bright-data", 8.5),
            ],
            services=[
                _service("firecrawl", "Firecrawl", "browser-automation", "extract"),
                _service("apify", "Apify", "browser-automation", "actors"),
                _service("bright-data", "Bright Data", "web-scraping", "scrape"),
            ],
        )
        with patch(
            "routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/v1/capabilities/{capability['id']}/resolve")

        assert resp.status_code == 200
        data = resp.json()["data"]
        slugs = [provider["service_slug"] for provider in data["providers"]]
        assert slugs[0] == "firecrawl"
        assert "firecrawl" in slugs
        assert data["execute_hint"]["preferred_provider"] == "firecrawl"
        by_slug = {provider["service_slug"]: provider for provider in data["providers"]}
        assert by_slug["firecrawl"]["endpoint_pattern"] == endpoint
        assert "firecrawl-v3" not in slugs


@pytest.mark.anyio
async def test_search_query_resolve_does_not_invent_firecrawl(app):
    mock_fetch = _resolve_fetch(
        capability=SEARCH_QUERY,
        mappings=SEARCH_QUERY_MAPPINGS,
        scores=[
            _score("algolia", 9.0),
            _score("exa", 8.7),
            _score("tavily", 8.6),
            _score("brave-search-api", 7.1),
            _score("firecrawl", 8.8),
        ],
        services=[
            _service("algolia", "Algolia", "search", "index"),
            _service("exa", "Exa", "search", "web"),
            _service("tavily", "Tavily", "search", "web"),
            _service("brave-search-api", "Brave Search API", "search", "web"),
            _service("firecrawl", "Firecrawl", "browser-automation", "extract"),
        ],
    )
    with patch(
        "routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/search.query/resolve")

    data = resp.json()["data"]
    slugs = [provider["service_slug"] for provider in data["providers"]]
    assert "firecrawl" not in slugs
    assert "firecrawl-v3" not in slugs
    assert slugs[:3] == ["exa", "tavily", "brave-search-api"]
    assert data["execute_hint"]["preferred_provider"] == "exa"


@pytest.mark.anyio
async def test_document_extract_resolve_stays_off_firecrawl(app):
    mock_fetch = _resolve_fetch(
        capability=DOCUMENT_EXTRACT,
        mappings=DOCUMENT_EXTRACT_MAPPINGS,
        scores=[
            _score("google-document-ai", 7.4),
            _score("unstructured", 7.0),
            _score("firecrawl", 8.8),
        ],
        services=[
            _service("google-document-ai", "Google Document AI", "document", "ocr"),
            _service("unstructured", "Unstructured", "document", "parse"),
            _service("firecrawl", "Firecrawl", "browser-automation", "extract"),
        ],
    )
    with patch(
        "routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/document.extract/resolve")

    slugs = [provider["service_slug"] for provider in resp.json()["data"]["providers"]]
    assert slugs == ["google-document-ai", "unstructured"]
    assert "firecrawl" not in slugs
