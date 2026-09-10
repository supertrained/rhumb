"""Index score is not callable execute. Extract rails stay on scrape.*."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from services.index_callable import CALLABLE_URL, index_callable_fields, public_callable_slugs
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


INDEX_SERVICES = [
    _service(
        "firecrawl",
        "Firecrawl",
        "browser-automation",
        "Web crawling and content extraction API.",
    ),
    _service(
        "firecrawl-v3",
        "Firecrawl (v3 catalog)",
        "web-scraping",
        "Scored catalog row that is not on the proxy registry.",
    ),
    _service("sendgrid", "SendGrid", "email", "Email delivery platform."),
    _service("exa", "Exa", "search", "AI-native web search API."),
]

INDEX_SCORES = [
    _score("firecrawl", 8.8),
    _score("firecrawl-v3", 8.8),
    _score("sendgrid", 8.5),
    _score("exa", 8.7),
]

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


def _in_filter_slugs(path: str, key: str) -> set[str] | None:
    match = re.search(rf"{re.escape(key)}=in\.\(([^)]*)\)", unquote(path))
    if not match:
        return None
    return {part.strip().strip('"') for part in match.group(1).split(",") if part.strip()}


async def _index_supabase(path: str):
    service_slugs = _in_filter_slugs(path, "slug")
    if path.startswith("services?slug=in.(") and service_slugs is not None:
        return [service for service in INDEX_SERVICES if service["slug"] in service_slugs]
    if path.startswith("services?"):
        return INDEX_SERVICES
    score_slugs = _in_filter_slugs(path, "service_slug")
    if path.startswith("scores?"):
        if score_slugs is None:
            return INDEX_SCORES
        return [row for row in INDEX_SCORES if row["service_slug"] in score_slugs]
    if path.startswith("failure_modes?"):
        return []
    raise AssertionError(f"Unexpected Supabase fetch path: {path}")


@pytest.fixture
def app():
    return create_app()


def test_public_callable_slugs_canonicalize_proxy_names() -> None:
    store = type("Store", (), {"callable_services": lambda self: ["firecrawl", "brave-search"]})()
    with patch("services.index_callable.get_credential_store", return_value=store):
        assert public_callable_slugs() == {"firecrawl", "brave-search-api"}


def test_index_callable_fields_are_distinct_from_score() -> None:
    fields = index_callable_fields("firecrawl", callable_slugs={"firecrawl"})
    assert fields == {"callable": True, "callable_url": CALLABLE_URL}
    scored_not_callable = index_callable_fields("firecrawl-v3", callable_slugs={"firecrawl"})
    assert scored_not_callable == {"callable": False, "callable_url": CALLABLE_URL}


def test_firecrawl_is_not_a_search_query_beachhead_class() -> None:
    assert search_query_provider_class("firecrawl") is SearchQueryProviderClass.OTHER
    assert search_query_provider_class("firecrawl-v3") is SearchQueryProviderClass.OTHER


@pytest.mark.anyio
async def test_service_and_score_separate_index_score_from_callable(app):
    store = type("Store", (), {"callable_services": lambda self: ["firecrawl"]})()
    with (
        patch("services.index_callable.get_credential_store", return_value=store),
        patch(
            "routes.services.supabase_fetch", new_callable=AsyncMock, side_effect=_index_supabase
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            firecrawl = await client.get("/v1/services/firecrawl")
            firecrawl_score = await client.get("/v1/services/firecrawl/score")
            ghost = await client.get("/v1/services/firecrawl-v3")
            ghost_score = await client.get("/v1/services/firecrawl-v3/score")
            sendgrid = await client.get("/v1/services/sendgrid/score")

    firecrawl_data = firecrawl.json()["data"]
    assert firecrawl.status_code == 200
    assert firecrawl_data["an_score"] == 8.8
    assert firecrawl_data["execution_score"] == 8.8
    assert firecrawl_data["callable"] is True
    assert firecrawl_data["callable_url"] == CALLABLE_URL

    assert firecrawl_score.status_code == 200
    assert firecrawl_score.json()["an_score"] == 8.8
    assert firecrawl_score.json()["execution_score"] == 8.8
    assert firecrawl_score.json()["callable"] is True
    assert firecrawl_score.json()["callable_url"] == CALLABLE_URL

    assert ghost.json()["data"]["an_score"] == 8.8
    assert ghost.json()["data"]["callable"] is False
    assert ghost.json()["data"]["callable_url"] == CALLABLE_URL
    assert ghost_score.json()["an_score"] == 8.8
    assert ghost_score.json()["callable"] is False
    assert sendgrid.json()["an_score"] == 8.5
    assert sendgrid.json()["callable"] is False


@pytest.mark.anyio
async def test_index_search_marks_callable_without_changing_hits(app):
    store = type("Store", (), {"callable_services": lambda self: ["firecrawl", "exa"]})()
    with (
        patch("services.index_callable.get_credential_store", return_value=store),
        patch("routes.search.supabase_fetch", new_callable=AsyncMock, side_effect=_index_supabase),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/search", params={"q": "firecrawl", "limit": 5})

    assert resp.status_code == 200
    results = resp.json()["data"]["results"]
    by_slug = {item["service_slug"]: item for item in results}
    assert set(by_slug) >= {"firecrawl", "firecrawl-v3"}
    assert by_slug["firecrawl"]["an_score"] == 8.8
    assert by_slug["firecrawl"]["execution_score"] == 8.8
    assert by_slug["firecrawl"]["callable"] is True
    assert by_slug["firecrawl"]["callable_url"] == CALLABLE_URL
    assert by_slug["firecrawl-v3"]["an_score"] == 8.8
    assert by_slug["firecrawl-v3"]["callable"] is False
    assert by_slug["firecrawl-v3"]["callable_url"] == CALLABLE_URL


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
