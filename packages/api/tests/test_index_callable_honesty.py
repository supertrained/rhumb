from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from services.index_callable import CALLABLE_URL, index_callable_fields, public_callable_slugs


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
    assert fields == {
        "callable": True,
        "callable_url": CALLABLE_URL,
        "tenant_configured": True,
    }
    scored_not_callable = index_callable_fields("firecrawl-v3", callable_slugs={"firecrawl"})
    assert scored_not_callable == {
        "callable": False,
        "callable_url": CALLABLE_URL,
        "tenant_configured": False,
    }


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
    assert firecrawl_data["tenant_configured"] is True
    assert "schema_ready" not in firecrawl_data

    assert firecrawl_score.status_code == 200
    assert firecrawl_score.json()["an_score"] == 8.8
    assert firecrawl_score.json()["execution_score"] == 8.8
    assert firecrawl_score.json()["callable"] is True
    assert firecrawl_score.json()["callable_url"] == CALLABLE_URL
    assert firecrawl_score.json()["tenant_configured"] is True
    assert "schema_ready" not in firecrawl_score.json()

    assert ghost.json()["data"]["an_score"] == 8.8
    assert ghost.json()["data"]["callable"] is False
    assert ghost.json()["data"]["callable_url"] == CALLABLE_URL
    assert ghost.json()["data"]["tenant_configured"] is False
    assert ghost_score.json()["an_score"] == 8.8
    assert ghost_score.json()["callable"] is False
    assert sendgrid.json()["an_score"] == 8.5
    assert sendgrid.json()["callable"] is False
    assert sendgrid.json()["tenant_configured"] is False


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
    assert by_slug["firecrawl"]["tenant_configured"] is True
    assert "schema_ready" not in by_slug["firecrawl"]
    assert by_slug["firecrawl-v3"]["an_score"] == 8.8
    assert by_slug["firecrawl-v3"]["callable"] is False
    assert by_slug["firecrawl-v3"]["callable_url"] == CALLABLE_URL
    assert by_slug["firecrawl-v3"]["tenant_configured"] is False
