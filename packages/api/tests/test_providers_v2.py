"""Tests for Layer 1 — Raw Provider Access (routes/providers_v2.py)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import create_app
from routes.providers_v2 import _canonicalize_service_rows

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEST_PROVIDER_SLUG = "openai"
_TEST_CAPABILITY = "ai.generate_text"
_DIRECT_PROVIDER_SLUG = "postgresql"
_DIRECT_CAPABILITY = "db.query.read"

_MOCK_SERVICE_DETAIL = {
    "slug": _TEST_PROVIDER_SLUG,
    "name": "OpenAI",
    "description": "OpenAI API platform",
    "category": "ai",
    "api_domain": "api.openai.com",
    "aggregate_recommendation_score": 8.5,
    "tier_label": "L4",
}

_MOCK_CAPABILITY_MAPPING = {
    "capability_id": _TEST_CAPABILITY,
    "service_slug": _TEST_PROVIDER_SLUG,
    "credential_modes": "byo,rhumb_managed",
    "auth_method": "bearer_token",
    "endpoint_pattern": "POST /v1/chat/completions",
    "cost_per_call": 0.005,
    "cost_currency": "USD",
    "free_tier_calls": 0,
}

_MOCK_SERVICES_LIST = [
    _MOCK_SERVICE_DETAIL,
    {
        "slug": "anthropic",
        "name": "Anthropic",
        "description": "Claude API",
        "category": "ai",
        "api_domain": "api.anthropic.com",
        "aggregate_recommendation_score": 8.3,
        "tier_label": "L4",
    },
]


@pytest.fixture()
def client():
    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_supabase_fetch(query: str):
    """Route supabase_fetch calls to appropriate mock data."""
    # Check capability_services BEFORE services (since "services?" matches both)
    if query.startswith("capability_services?"):
        # Match on capability_id first (list providers by capability)
        if "capability_id=eq." in query:
            if _TEST_CAPABILITY in query:
                return [{"service_slug": _TEST_PROVIDER_SLUG}]
            return []
        # Match on service_slug (get provider capabilities)
        if f"service_slug=eq.{_TEST_PROVIDER_SLUG}" in query:
            return [_MOCK_CAPABILITY_MAPPING]
        # General all-slugs query (used by list_providers to build initial set)
        if "select=service_slug" in query and "capability_id" not in query and "service_slug=eq." not in query:
            return [{"service_slug": _TEST_PROVIDER_SLUG}, {"service_slug": "anthropic"}]
        return []
    if query.startswith("scores?"):
        # scores lookup by slug set
        results = []
        for svc in _MOCK_SERVICES_LIST:
            if svc["slug"] in query:
                results.append({
                    "service_slug": svc["slug"],
                    "aggregate_recommendation_score": svc.get("aggregate_recommendation_score"),
                    "tier": svc.get("tier_label"),
                    "tier_label": svc.get("tier_label"),
                    "calculated_at": "2026-03-31T00:00:00Z",
                })
        return results
    if query.startswith("services?"):
        if f"slug=eq.{_TEST_PROVIDER_SLUG}" in query:
            return [_MOCK_SERVICE_DETAIL]
        if "slug=eq.nonexistent" in query:
            return []
        # slug=in.(...) filter for list providers
        if "slug=in." in query:
            return [s for s in _MOCK_SERVICES_LIST if s["slug"] in query]
        # list query
        return _MOCK_SERVICES_LIST
    return []


_DEFUNCT_DIRECT_MAPPING_PROVIDER = {
    "slug": "resend",
    "name": "Resend",
    "description": "Transactional email API",
    "category": "email",
    "official_docs": "https://resend.com/docs",
    "aggregate_recommendation_score": 7.2,
    "tier_label": "L3",
}

_BRAVE_ALIAS_SERVICE_DETAIL = {
    "slug": "brave-search",
    "name": "Brave Search",
    "description": "Independent web search API with web, news, image, and video results. Privacy-focused with no tracking.",
    "category": "search",
    "official_docs": "https://brave.com/search/api",
}

_BRAVE_CANONICAL_SERVICE_DETAIL = {
    "slug": "brave-search-api",
    "name": "Brave Search API",
    "description": "Canonical public provider record for Brave Search API.",
    "category": "search",
    "official_docs": "https://api.search.brave.com/docs",
}

_BRAVE_ALIAS_TEXTY_SERVICE_DETAIL = {
    "slug": "brave-search",
    "name": "Brave Search (brave-search)",
    "description": "Use brave-search for search.",
    "category": "search",
    "official_docs": "https://brave.com/search/api",
}

_BRAVE_ALTERNATE_ALIAS_TEXTY_SERVICE_DETAIL = {
    "slug": "brave-search",
    "name": "brave-search won after pdl comparison",
    "description": "Use brave-search after pdl comparison.",
    "category": "search",
    "official_docs": "https://brave.com/search/api",
}


def _mock_supabase_fetch_with_alias_backed_callable_provider(query: str):
    """Store Brave metadata on the runtime alias while v2 exposes the canonical provider id."""
    if query.startswith("capability_services?"):
        if "capability_id=eq.search.query" in query:
            return [{"service_slug": "brave-search"}]
        if "service_slug=eq.brave-search" in query:
            return [{
                "capability_id": "search.query",
                "service_slug": "brave-search",
                "credential_modes": "byo,rhumb_managed",
                "auth_method": "api_key",
                "endpoint_pattern": "GET /res/v1/web/search",
                "cost_per_call": 0.003,
                "cost_currency": "USD",
                "free_tier_calls": 2000,
            }]
        if "select=service_slug" in query and "capability_id" not in query and "service_slug=eq." not in query:
            return [{"service_slug": "brave-search"}]
        return []
    if query.startswith("services?"):
        if "slug=eq.brave-search-api" in query:
            return []
        if "slug=eq.brave-search" in query:
            return [_BRAVE_ALIAS_SERVICE_DETAIL]
        if "slug=in." in query and "brave-search" in query:
            return [_BRAVE_ALIAS_SERVICE_DETAIL]
        return []
    if query.startswith("scores?"):
        if "brave-search" in query:
            return [{
                "service_slug": "brave-search",
                "aggregate_recommendation_score": 8.6,
                "tier": "native",
                "tier_label": "Native",
                "calculated_at": "2026-03-31T00:00:00Z",
            }]
        return []
    return []


def _mock_supabase_fetch_with_alias_backed_texty_callable_provider(query: str):
    if query.startswith("capability_services?"):
        if "capability_id=eq.search.query" in query:
            return [{"service_slug": "brave-search"}]
        if "service_slug=eq.brave-search" in query:
            return [{
                "capability_id": "search.query",
                "service_slug": "brave-search",
                "credential_modes": "byo,rhumb_managed",
                "auth_method": "api_key",
                "endpoint_pattern": "GET /res/v1/web/search",
                "cost_per_call": 0.003,
                "cost_currency": "USD",
                "free_tier_calls": 2000,
            }]
        if "select=service_slug" in query and "capability_id" not in query and "service_slug=eq." not in query:
            return [{"service_slug": "brave-search"}]
        return []
    if query.startswith("services?"):
        if "slug=eq.brave-search-api" in query:
            return []
        if "slug=eq.brave-search" in query:
            return [_BRAVE_ALIAS_TEXTY_SERVICE_DETAIL]
        if "slug=in." in query and "brave-search" in query:
            return [_BRAVE_ALIAS_TEXTY_SERVICE_DETAIL]
        return []
    if query.startswith("scores?"):
        if "brave-search" in query:
            return [{
                "service_slug": "brave-search",
                "aggregate_recommendation_score": 8.6,
                "tier": "native",
                "tier_label": "Native",
                "calculated_at": "2026-03-31T00:00:00Z",
            }]
        return []
    return []


def _mock_supabase_fetch_with_alias_backed_alternate_alias_texty_callable_provider(query: str):
    if query.startswith("capability_services?"):
        if "capability_id=eq.search.query" in query:
            return [{"service_slug": "brave-search"}]
        if "service_slug=eq.brave-search" in query:
            return [{
                "capability_id": "search.query",
                "service_slug": "brave-search",
                "credential_modes": "byo,rhumb_managed",
                "auth_method": "api_key",
                "endpoint_pattern": "GET /res/v1/web/search",
                "cost_per_call": 0.003,
                "cost_currency": "USD",
                "free_tier_calls": 2000,
            }]
        if "select=service_slug" in query and "capability_id" not in query and "service_slug=eq." not in query:
            return [{"service_slug": "brave-search"}]
        return []
    if query.startswith("services?"):
        if "slug=eq.brave-search-api" in query:
            return []
        if "slug=eq.brave-search" in query:
            return [_BRAVE_ALTERNATE_ALIAS_TEXTY_SERVICE_DETAIL]
        if "slug=in." in query and "brave-search" in query:
            return [_BRAVE_ALTERNATE_ALIAS_TEXTY_SERVICE_DETAIL]
        return []
    if query.startswith("scores?"):
        if "brave-search" in query:
            return [{
                "service_slug": "brave-search",
                "aggregate_recommendation_score": 8.6,
                "tier": "native",
                "tier_label": "Native",
                "calculated_at": "2026-03-31T00:00:00Z",
            }]
        return []
    return []


def _mock_supabase_fetch_with_duplicate_canonical_and_alias_rows(query: str):
    """Return both canonical and runtime rows, with the alias row ordered last."""
    if query.startswith("capability_services?"):
        if "capability_id=eq.search.query" in query:
            return [{"service_slug": "brave-search"}]
        if "select=service_slug" in query and "capability_id" not in query and "service_slug=eq." not in query:
            return [{"service_slug": "brave-search"}]
        return []
    if query.startswith("services?"):
        if "slug=in." in query and "brave-search" in query:
            return [_BRAVE_CANONICAL_SERVICE_DETAIL, _BRAVE_ALIAS_SERVICE_DETAIL]
        if "slug=eq.brave-search-api" in query:
            return [_BRAVE_CANONICAL_SERVICE_DETAIL]
        if "slug=eq.brave-search" in query:
            return [_BRAVE_ALIAS_SERVICE_DETAIL]
        return []
    if query.startswith("scores?"):
        if "brave-search" in query:
            return [{
                "service_slug": "brave-search",
                "aggregate_recommendation_score": 8.6,
                "tier": "native",
                "tier_label": "Native",
                "calculated_at": "2026-03-31T00:00:00Z",
            }]
        return []
    return []


def _mock_supabase_fetch_with_partial_canonical_and_alias_rows(query: str):
    """Return a sparse canonical row plus a richer alias row for detail backfill."""
    if query.startswith("capability_services?"):
        if "service_slug=eq.brave-search" in query:
            return [{
                "capability_id": "search.query",
                "service_slug": "brave-search",
                "credential_modes": "byo,rhumb_managed",
                "auth_method": "api_key",
                "endpoint_pattern": "GET /res/v1/web/search",
                "cost_per_call": 0.003,
                "cost_currency": "USD",
                "free_tier_calls": 2000,
            }]
        return []
    if query.startswith("services?"):
        if "slug=eq.brave-search-api" in query:
            return [{
                "slug": "brave-search-api",
                "name": None,
                "description": None,
                "category": None,
                "official_docs": None,
            }]
        if "slug=eq.brave-search" in query:
            return [_BRAVE_ALIAS_SERVICE_DETAIL]
        return []
    if query.startswith("scores?"):
        if "brave-search" in query:
            return [{
                "service_slug": "brave-search",
                "aggregate_recommendation_score": 8.6,
                "tier": "native",
                "tier_label": "Native",
                "calculated_at": "2026-03-31T00:00:00Z",
            }]
        return []
    return []


def _mock_supabase_fetch_with_stale_direct_db_mapping(query: str):
    """Inject a stale db.query.read -> resend row and no real postgresql catalog rows."""
    if query.startswith("capability_services?"):
        if f"capability_id=eq.{_DIRECT_CAPABILITY}" in query:
            return [{"service_slug": "resend"}]
        if "select=service_slug" in query and "capability_id" not in query and "service_slug=eq." not in query:
            return [{"service_slug": "resend"}]
        if "service_slug=eq.resend" in query:
            return [{
                "capability_id": _DIRECT_CAPABILITY,
                "service_slug": "resend",
                "credential_modes": "byok",
                "auth_method": "api_key",
                "endpoint_pattern": "POST /emails",
                "cost_per_call": 0.001,
                "cost_currency": "USD",
                "free_tier_calls": 100,
            }]
        return []
    if query.startswith("services?"):
        if "slug=eq.resend" in query:
            return [_DEFUNCT_DIRECT_MAPPING_PROVIDER]
        if "slug=in." in query and "resend" in query:
            return [_DEFUNCT_DIRECT_MAPPING_PROVIDER]
        return []
    if query.startswith("scores?"):
        if "resend" in query:
            return [{
                "service_slug": "resend",
                "aggregate_recommendation_score": _DEFUNCT_DIRECT_MAPPING_PROVIDER["aggregate_recommendation_score"],
                "tier": _DEFUNCT_DIRECT_MAPPING_PROVIDER["tier_label"],
                "tier_label": _DEFUNCT_DIRECT_MAPPING_PROVIDER["tier_label"],
                "calculated_at": "2026-03-31T00:00:00Z",
            }]
        return []
    return []


# ---------------------------------------------------------------------------
# GET /v2/providers
# ---------------------------------------------------------------------------


def test_canonicalize_service_rows_preserves_human_shorthand_for_canonical_rows():
    rows = _canonicalize_service_rows([
        {
            "slug": "people-data-labs",
            "name": "People Data Labs",
            "description": "PDL contact data API for enrichment.",
            "category": "enrichment",
            "official_docs": "https://docs.peopledatalabs.com/docs",
        }
    ])

    assert rows["people-data-labs"]["name"] == "People Data Labs"
    assert rows["people-data-labs"]["description"] == "PDL contact data API for enrichment."


class TestListProviders:
    def test_list_returns_providers(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch):
            resp = client.get("/v2/providers")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["_rhumb_v2"]["layer"] == 1
        assert len(data["providers"]) >= 1
        provider = data["providers"][0]
        assert "id" in provider
        assert "name" in provider
        assert "callable" in provider

    def test_list_with_capability_filter_and_status_listed(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch):
            resp = client.get(f"/v2/providers?capability={_TEST_CAPABILITY}&status=listed")
        assert resp.status_code == 200
        data = resp.json()["data"]
        slugs = [p["id"] for p in data["providers"]]
        assert _TEST_PROVIDER_SLUG in slugs

    def test_list_hides_noncallable_stale_catalog_rows_by_default(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_stale_direct_db_mapping):
            resp = client.get("/v2/providers")

        assert resp.status_code == 200
        data = resp.json()["data"]
        slugs = [p["id"] for p in data["providers"]]
        assert _DIRECT_PROVIDER_SLUG in slugs
        assert "resend" not in slugs

    def test_list_with_status_listed_keeps_noncallable_catalog_rows(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_stale_direct_db_mapping):
            resp = client.get("/v2/providers?status=listed")

        assert resp.status_code == 200
        data = resp.json()["data"]
        providers_by_id = {provider["id"]: provider for provider in data["providers"]}
        assert _DIRECT_PROVIDER_SLUG in providers_by_id
        assert providers_by_id["resend"]["callable"] is False

    def test_list_with_direct_capability_filter_ignores_stale_catalog_mapping_rows(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_stale_direct_db_mapping):
            resp = client.get(f"/v2/providers?capability={_DIRECT_CAPABILITY}")

        assert resp.status_code == 200
        data = resp.json()["data"]
        slugs = [p["id"] for p in data["providers"]]
        assert _DIRECT_PROVIDER_SLUG in slugs
        assert "resend" not in slugs

    def test_list_with_direct_capability_filter_and_status_listed_ignores_stale_catalog_mapping_rows(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_stale_direct_db_mapping):
            resp = client.get(f"/v2/providers?capability={_DIRECT_CAPABILITY}&status=listed")

        assert resp.status_code == 200
        data = resp.json()["data"]
        slugs = [p["id"] for p in data["providers"]]
        assert _DIRECT_PROVIDER_SLUG in slugs
        assert "resend" not in slugs

    def test_list_with_direct_capability_filter_and_status_scored_ignores_stale_catalog_mapping_rows(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_stale_direct_db_mapping):
            resp = client.get(f"/v2/providers?capability={_DIRECT_CAPABILITY}&status=scored")

        assert resp.status_code == 200
        data = resp.json()["data"]
        slugs = [p["id"] for p in data["providers"]]
        assert _DIRECT_PROVIDER_SLUG not in slugs
        assert "resend" not in slugs
        assert data["total"] == 0

    def test_list_with_direct_capability_filter_and_status_callable_ignores_stale_catalog_mapping_rows(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_stale_direct_db_mapping):
            resp = client.get(f"/v2/providers?capability={_DIRECT_CAPABILITY}&status=callable")

        assert resp.status_code == 200
        data = resp.json()["data"]
        providers_by_id = {provider["id"]: provider for provider in data["providers"]}
        assert _DIRECT_PROVIDER_SLUG in providers_by_id
        assert providers_by_id[_DIRECT_PROVIDER_SLUG]["callable"] is True
        assert "resend" not in providers_by_id
        assert data["total"] == 1

    def test_list_uses_alias_backed_metadata_for_callable_provider(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider):
            resp = client.get("/v2/providers?capability=search.query")

        assert resp.status_code == 200
        data = resp.json()["data"]
        providers_by_id = {provider["id"]: provider for provider in data["providers"]}
        brave = providers_by_id["brave-search-api"]
        assert brave["name"] == "Brave Search"
        assert brave["description"] == _BRAVE_ALIAS_SERVICE_DETAIL["description"]
        assert brave["category"] == "search"
        assert brave["an_score"] == 8.6
        assert brave["tier"] == "Native"
        assert brave["callable"] is True

    def test_list_with_status_scored_keeps_alias_backed_callable_provider(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider):
            resp = client.get("/v2/providers?status=scored")

        assert resp.status_code == 200
        data = resp.json()["data"]
        providers_by_id = {provider["id"]: provider for provider in data["providers"]}
        assert "brave-search" not in providers_by_id
        brave = providers_by_id["brave-search-api"]
        assert brave["name"] == "Brave Search"
        assert brave["an_score"] == 8.6
        assert brave["tier"] == "Native"
        assert brave["callable"] is True

    def test_list_with_status_listed_keeps_alias_backed_callable_provider(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider):
            resp = client.get("/v2/providers?status=listed")

        assert resp.status_code == 200
        data = resp.json()["data"]
        providers_by_id = {provider["id"]: provider for provider in data["providers"]}
        assert "brave-search" not in providers_by_id
        brave = providers_by_id["brave-search-api"]
        assert brave["name"] == "Brave Search"
        assert brave["description"] == _BRAVE_ALIAS_SERVICE_DETAIL["description"]
        assert brave["category"] == "search"
        assert brave["callable"] is True

    def test_list_with_status_callable_keeps_alias_backed_callable_provider(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider):
            resp = client.get("/v2/providers?status=callable")

        assert resp.status_code == 200
        data = resp.json()["data"]
        providers_by_id = {provider["id"]: provider for provider in data["providers"]}
        assert "brave-search" not in providers_by_id
        brave = providers_by_id["brave-search-api"]
        assert brave["name"] == "Brave Search"
        assert brave["description"] == _BRAVE_ALIAS_SERVICE_DETAIL["description"]
        assert brave["category"] == "search"
        assert brave["callable"] is True

    def test_list_with_capability_filter_and_status_callable_keeps_alias_backed_provider(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider):
            resp = client.get("/v2/providers?capability=search.query&status=callable")

        assert resp.status_code == 200
        data = resp.json()["data"]
        providers_by_id = {provider["id"]: provider for provider in data["providers"]}
        assert "brave-search" not in providers_by_id
        brave = providers_by_id["brave-search-api"]
        assert brave["name"] == "Brave Search"
        assert brave["description"] == _BRAVE_ALIAS_SERVICE_DETAIL["description"]
        assert brave["category"] == "search"
        assert brave["callable"] is True

    def test_list_with_capability_filter_and_status_listed_keeps_alias_backed_provider(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider):
            resp = client.get("/v2/providers?capability=search.query&status=listed")

        assert resp.status_code == 200
        data = resp.json()["data"]
        providers_by_id = {provider["id"]: provider for provider in data["providers"]}
        assert "brave-search" not in providers_by_id
        brave = providers_by_id["brave-search-api"]
        assert brave["name"] == "Brave Search"
        assert brave["description"] == _BRAVE_ALIAS_SERVICE_DETAIL["description"]
        assert brave["category"] == "search"
        assert brave["callable"] is True

    def test_list_with_capability_filter_and_status_scored_keeps_alias_backed_provider(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider):
            resp = client.get("/v2/providers?capability=search.query&status=scored")

        assert resp.status_code == 200
        data = resp.json()["data"]
        providers_by_id = {provider["id"]: provider for provider in data["providers"]}
        assert "brave-search" not in providers_by_id
        brave = providers_by_id["brave-search-api"]
        assert brave["name"] == "Brave Search"
        assert brave["description"] == _BRAVE_ALIAS_SERVICE_DETAIL["description"]
        assert brave["category"] == "search"
        assert brave["an_score"] == 8.6
        assert brave["tier"] == "Native"
        assert brave["callable"] is True

    def test_list_prefers_canonical_service_metadata_when_alias_row_is_also_present(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_duplicate_canonical_and_alias_rows):
            resp = client.get("/v2/providers?capability=search.query")

        assert resp.status_code == 200
        data = resp.json()["data"]
        providers_by_id = {provider["id"]: provider for provider in data["providers"]}
        brave = providers_by_id["brave-search-api"]
        assert brave["name"] == _BRAVE_CANONICAL_SERVICE_DETAIL["name"]
        assert brave["description"] == _BRAVE_CANONICAL_SERVICE_DETAIL["description"]
        assert brave["category"] == _BRAVE_CANONICAL_SERVICE_DETAIL["category"]
        assert brave["an_score"] == 8.6
        assert brave["tier"] == "Native"
        assert brave["callable"] is True

    def test_list_canonicalizes_alias_backed_provider_metadata_text(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_texty_callable_provider):
            resp = client.get("/v2/providers?capability=search.query")

        assert resp.status_code == 200
        data = resp.json()["data"]
        providers_by_id = {provider["id"]: provider for provider in data["providers"]}
        brave = providers_by_id["brave-search-api"]
        assert brave["name"] == "Brave Search (brave-search-api)"
        assert brave["description"] == "Use brave-search-api for search."
        assert brave["category"] == "search"
        assert brave["callable"] is True

    def test_list_canonicalizes_alternate_alias_mentions_in_provider_metadata_text(self, client):
        with patch(
            "routes.providers_v2.supabase_fetch",
            side_effect=_mock_supabase_fetch_with_alias_backed_alternate_alias_texty_callable_provider,
        ):
            resp = client.get("/v2/providers?capability=search.query")

        assert resp.status_code == 200
        data = resp.json()["data"]
        providers_by_id = {provider["id"]: provider for provider in data["providers"]}
        brave = providers_by_id["brave-search-api"]
        assert brave["name"] == "brave-search-api won after people-data-labs comparison"
        assert brave["description"] == "Use brave-search-api after people-data-labs comparison."
        assert brave["category"] == "search"
        assert brave["callable"] is True


# ---------------------------------------------------------------------------
# GET /v2/providers/{provider_id}
# ---------------------------------------------------------------------------

class TestGetProvider:
    def test_get_existing_provider(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch):
            resp = client.get(f"/v2/providers/{_TEST_PROVIDER_SLUG}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == _TEST_PROVIDER_SLUG
        assert data["_rhumb_v2"]["layer"] == 1
        assert "capabilities" in data
        assert len(data["capabilities"]) >= 1
        assert data["pricing"]["markup_rate"] == 0.08
        assert data["pricing"]["markup_floor_usd"] == 0.0002

    def test_get_direct_provider_uses_synthetic_capabilities_when_catalog_rows_stale(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_stale_direct_db_mapping):
            resp = client.get(f"/v2/providers/{_DIRECT_PROVIDER_SLUG}")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == _DIRECT_PROVIDER_SLUG
        assert data["name"] == "PostgreSQL"
        assert data["category"] == "database"
        assert data["callable"] is True
        capabilities_by_id = {capability["capability_id"]: capability for capability in data["capabilities"]}
        assert {"db.query.read", "db.schema.describe", "db.row.get"}.issubset(capabilities_by_id)
        direct_capability = capabilities_by_id[_DIRECT_CAPABILITY]
        assert direct_capability["credential_modes"] == ["byok", "agent_vault"]
        assert direct_capability["cost_per_call"] is None
        assert direct_capability["cost_currency"] == "USD"
        assert direct_capability["free_tier_calls"] is None

    def test_get_provider_accepts_alias_backed_service_and_score_rows(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider):
            resp = client.get("/v2/providers/brave-search-api")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "brave-search-api"
        assert data["name"] == "Brave Search"
        assert data["an_score"] == 8.6
        assert data["tier"] == "Native"
        assert data["capabilities"][0]["capability_id"] == "search.query"

    def test_get_provider_accepts_mixed_case_alias_inputs(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider):
            resp = client.get("/v2/providers/Brave-Search-Api")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "brave-search-api"
        assert data["name"] == "Brave Search"
        assert data["an_score"] == 8.6
        assert data["tier"] == "Native"
        assert data["capabilities"][0]["capability_id"] == "search.query"

    def test_get_provider_backfills_sparse_canonical_metadata_from_alias_row(self, client):
        with patch(
            "routes.providers_v2.supabase_fetch",
            side_effect=_mock_supabase_fetch_with_partial_canonical_and_alias_rows,
        ):
            resp = client.get("/v2/providers/brave-search-api")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "brave-search-api"
        assert data["name"] == _BRAVE_ALIAS_SERVICE_DETAIL["name"]
        assert data["description"] == _BRAVE_ALIAS_SERVICE_DETAIL["description"]
        assert data["category"] == _BRAVE_ALIAS_SERVICE_DETAIL["category"]
        assert data["an_score"] == 8.6
        assert data["tier"] == "Native"

    def test_get_provider_canonicalizes_alias_backed_metadata_text(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_texty_callable_provider):
            resp = client.get("/v2/providers/brave-search-api")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "brave-search-api"
        assert data["name"] == "Brave Search (brave-search-api)"
        assert data["description"] == "Use brave-search-api for search."
        assert data["an_score"] == 8.6
        assert data["tier"] == "Native"

    def test_get_provider_canonicalizes_alternate_alias_mentions_in_metadata_text(self, client):
        with patch(
            "routes.providers_v2.supabase_fetch",
            side_effect=_mock_supabase_fetch_with_alias_backed_alternate_alias_texty_callable_provider,
        ):
            resp = client.get("/v2/providers/brave-search-api")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "brave-search-api"
        assert data["name"] == "brave-search-api won after people-data-labs comparison"
        assert data["description"] == "Use brave-search-api after people-data-labs comparison."
        assert data["an_score"] == 8.6
        assert data["tier"] == "Native"

    def test_get_nonexistent_provider(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch):
            resp = client.get("/v2/providers/nonexistent")
        assert resp.status_code == 503  # PROVIDER_UNAVAILABLE

    def test_get_nonexistent_provider_error_normalizes_public_provider_id(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch):
            resp = client.get("/v2/providers/NonExistent")

        assert resp.status_code == 503
        error = resp.json()["error"]
        assert error["message"] == "Provider 'nonexistent' not found."


# ---------------------------------------------------------------------------
# POST /v2/providers/{provider_id}/execute
# ---------------------------------------------------------------------------

class TestExecuteOnProvider:
    def _mock_v1_estimate(self, query: str):
        """Mock for the supabase calls during estimation."""
        return _mock_supabase_fetch(query)

    @patch("routes.providers_v2._resolve_agent_for_budget", new_callable=AsyncMock, return_value=None)
    @patch("routes.providers_v2.get_receipt_service")
    @patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch)
    def test_execute_success(self, mock_fetch, mock_receipt_svc, mock_budget, client):
        # Mock receipt service
        mock_receipt = MagicMock()
        mock_receipt.receipt_id = "rcpt_test_123"
        mock_receipt_svc.return_value.create_receipt = AsyncMock(return_value=mock_receipt)

        # The v1 internal forward will be handled by the actual app,
        # so we mock the internal forward instead
        mock_execute_response = {
            "data": {
                "execution_id": "exec_test_123",
                "result": {"text": "Hello"},
                "provider_latency_ms": 100,
                "agent_id": "test_agent",
                "org_id": "test_org",
            },
            "error": None,
        }

        with patch("routes.providers_v2._forward_internal") as mock_forward:
            # First call: estimate; second call: execute
            estimate_resp = MagicMock()
            estimate_resp.status_code = 200
            estimate_resp.json.return_value = {
                "data": {
                    "provider": _TEST_PROVIDER_SLUG,
                    "cost_estimate_usd": 0.005,
                    "endpoint_pattern": "POST /v1/chat/completions",
                },
            }
            estimate_resp.headers = {}

            execute_resp = MagicMock()
            execute_resp.status_code = 200
            execute_resp.json.return_value = mock_execute_response
            execute_resp.headers = {}

            mock_forward.side_effect = [estimate_resp, execute_resp]

            resp = client.post(
                f"/v2/providers/{_TEST_PROVIDER_SLUG}/execute",
                json={
                    "capability": _TEST_CAPABILITY,
                    "parameters": {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert data["_rhumb_v2"]["layer"] == 1
        assert data["_rhumb_v2"]["provider"]["id"] == _TEST_PROVIDER_SLUG
        assert data["_rhumb_v2"]["cost"]["provider_cost_usd"] == 0.005
        assert data["_rhumb_v2"]["cost"]["rhumb_fee_usd"] == 0.0004  # max(0.0002, 0.005*0.08)
        assert data["_rhumb_v2"]["cost"]["total_usd"] == 0.0054
        assert data["receipt_id"] == "rcpt_test_123"
        assert data["_rhumb_v2"]["receipt_id"] == "rcpt_test_123"
        assert resp.headers.get("X-Rhumb-Provider") == _TEST_PROVIDER_SLUG
        assert resp.headers.get("X-Rhumb-Layer") == "1"
        assert resp.headers.get("X-Rhumb-Receipt-Id") == "rcpt_test_123"

        execute_call = mock_forward.call_args_list[1]
        assert execute_call.kwargs["extra_headers"] == {"X-Rhumb-Skip-Receipt": "true"}

    @patch("routes.providers_v2._resolve_agent_for_budget", new_callable=AsyncMock, return_value=None)
    @patch("routes.providers_v2.get_receipt_service")
    @patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_stale_direct_db_mapping)
    def test_execute_direct_provider_ignores_stale_catalog_mapping_rows(self, mock_fetch, mock_receipt_svc, mock_budget, client):
        mock_receipt = MagicMock()
        mock_receipt.receipt_id = "rcpt_direct_123"
        mock_receipt_svc.return_value.create_receipt = AsyncMock(return_value=mock_receipt)

        mock_execute_response = {
            "data": {
                "execution_id": "exec_direct_123",
                "result": {"rows": [{"value": 1}]},
                "provider_latency_ms": 12,
                "agent_id": "test_agent",
                "org_id": "test_org",
            },
            "error": None,
        }

        with patch("routes.providers_v2._forward_internal") as mock_forward:
            estimate_resp = MagicMock()
            estimate_resp.status_code = 200
            estimate_resp.json.return_value = {
                "data": {
                    "provider": _DIRECT_PROVIDER_SLUG,
                    "cost_estimate_usd": 0,
                    "endpoint_pattern": f"POST /v1/capabilities/{_DIRECT_CAPABILITY}/execute",
                },
            }
            estimate_resp.headers = {}

            execute_resp = MagicMock()
            execute_resp.status_code = 200
            execute_resp.json.return_value = mock_execute_response
            execute_resp.headers = {}

            mock_forward.side_effect = [estimate_resp, execute_resp]

            resp = client.post(
                f"/v2/providers/{_DIRECT_PROVIDER_SLUG}/execute",
                json={
                    "capability": _DIRECT_CAPABILITY,
                    "parameters": {"sql": "select 1"},
                    "credential_mode": "byok",
                },
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["_rhumb_v2"]["provider"]["id"] == _DIRECT_PROVIDER_SLUG
        estimate_call = mock_forward.call_args_list[0]
        assert estimate_call.kwargs["params"]["provider"] == _DIRECT_PROVIDER_SLUG
        execute_call = mock_forward.call_args_list[1]
        assert execute_call.kwargs["json_body"]["provider"] == _DIRECT_PROVIDER_SLUG

    @patch("routes.providers_v2._resolve_agent_for_budget", new_callable=AsyncMock, return_value=None)
    @patch("routes.providers_v2.get_receipt_service")
    @patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider)
    def test_execute_alias_backed_provider_uses_runtime_slug(self, mock_fetch, mock_receipt_svc, mock_budget, client):
        mock_receipt = MagicMock()
        mock_receipt.receipt_id = "rcpt_alias_123"
        mock_receipt_svc.return_value.create_receipt = AsyncMock(return_value=mock_receipt)

        mock_execute_response = {
            "data": {
                "execution_id": "exec_alias_123",
                "result": {"items": [{"title": "Result"}]},
                "provider_latency_ms": 45,
                "agent_id": "test_agent",
                "org_id": "test_org",
            },
            "error": None,
        }

        with patch("routes.providers_v2._forward_internal") as mock_forward:
            estimate_resp = MagicMock()
            estimate_resp.status_code = 200
            estimate_resp.json.return_value = {
                "data": {
                    "provider": "brave-search",
                    "cost_estimate_usd": 0.003,
                    "endpoint_pattern": "GET /res/v1/web/search",
                },
            }
            estimate_resp.headers = {}

            execute_resp = MagicMock()
            execute_resp.status_code = 200
            execute_resp.json.return_value = mock_execute_response
            execute_resp.headers = {}

            mock_forward.side_effect = [estimate_resp, execute_resp]

            resp = client.post(
                "/v2/providers/brave-search-api/execute",
                json={
                    "capability": "search.query",
                    "parameters": {"q": "rhumb"},
                    "credential_mode": "byok",
                },
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["_rhumb_v2"]["provider"]["id"] == "brave-search-api"
        estimate_call = mock_forward.call_args_list[0]
        assert estimate_call.kwargs["params"]["provider"] == "brave-search"
        execute_call = mock_forward.call_args_list[1]
        assert execute_call.kwargs["json_body"]["provider"] == "brave-search"

    @patch("routes.providers_v2._resolve_agent_for_budget", new_callable=AsyncMock, return_value=None)
    @patch("routes.providers_v2.get_receipt_service")
    @patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider)
    def test_execute_accepts_mixed_case_alias_inputs(self, mock_fetch, mock_receipt_svc, mock_budget, client):
        mock_receipt = MagicMock()
        mock_receipt.receipt_id = "rcpt_alias_mixed_123"
        mock_receipt_svc.return_value.create_receipt = AsyncMock(return_value=mock_receipt)

        mock_execute_response = {
            "data": {
                "execution_id": "exec_alias_mixed_123",
                "result": {"items": [{"title": "Result"}]},
                "provider_latency_ms": 45,
                "agent_id": "test_agent",
                "org_id": "test_org",
            },
            "error": None,
        }

        with patch("routes.providers_v2._forward_internal") as mock_forward:
            estimate_resp = MagicMock()
            estimate_resp.status_code = 200
            estimate_resp.json.return_value = {
                "data": {
                    "provider": "brave-search",
                    "cost_estimate_usd": 0.003,
                    "endpoint_pattern": "GET /res/v1/web/search",
                },
            }
            estimate_resp.headers = {}

            execute_resp = MagicMock()
            execute_resp.status_code = 200
            execute_resp.json.return_value = mock_execute_response
            execute_resp.headers = {}

            mock_forward.side_effect = [estimate_resp, execute_resp]

            resp = client.post(
                "/v2/providers/Brave-Search/execute",
                json={
                    "capability": "search.query",
                    "parameters": {"q": "rhumb"},
                    "credential_mode": "byok",
                },
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["_rhumb_v2"]["provider"]["id"] == "brave-search-api"
        estimate_call = mock_forward.call_args_list[0]
        assert estimate_call.kwargs["params"]["provider"] == "brave-search"
        execute_call = mock_forward.call_args_list[1]
        assert execute_call.kwargs["json_body"]["provider"] == "brave-search"

    @patch("routes.providers_v2._resolve_agent_for_budget", new_callable=AsyncMock, return_value=None)
    @patch("routes.providers_v2.get_receipt_service")
    @patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider)
    def test_execute_canonicalizes_alias_backed_provider_fields_in_success_payload(self, mock_fetch, mock_receipt_svc, mock_budget, client):
        mock_receipt = MagicMock()
        mock_receipt.receipt_id = "rcpt_alias_success_123"
        mock_receipt_svc.return_value.create_receipt = AsyncMock(return_value=mock_receipt)

        mock_execute_response = {
            "data": {
                "execution_id": "exec_alias_success_123",
                "provider_used": "brave-search",
                "selected_provider": "brave-search",
                "result": {
                    "provider_slug": "brave-search",
                    "fallback_providers": ["brave-search"],
                },
                "provider_latency_ms": 45,
                "agent_id": "test_agent",
                "org_id": "test_org",
            },
            "error": None,
        }

        with patch("routes.providers_v2._forward_internal") as mock_forward:
            estimate_resp = MagicMock()
            estimate_resp.status_code = 200
            estimate_resp.json.return_value = {
                "data": {
                    "provider": "brave-search",
                    "cost_estimate_usd": 0.003,
                    "endpoint_pattern": "GET /res/v1/web/search",
                },
            }
            estimate_resp.headers = {}

            execute_resp = MagicMock()
            execute_resp.status_code = 200
            execute_resp.json.return_value = mock_execute_response
            execute_resp.headers = {}

            mock_forward.side_effect = [estimate_resp, execute_resp]

            resp = client.post(
                "/v2/providers/brave-search-api/execute",
                json={
                    "capability": "search.query",
                    "parameters": {"q": "rhumb"},
                    "credential_mode": "byok",
                },
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["provider_used"] == "brave-search-api"
        assert data["selected_provider"] == "brave-search-api"
        assert data["result"]["provider_slug"] == "brave-search-api"
        assert data["result"]["fallback_providers"] == ["brave-search-api"]

    @patch("routes.providers_v2._resolve_agent_for_budget", new_callable=AsyncMock, return_value=None)
    @patch("routes.providers_v2.get_receipt_service")
    @patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider)
    def test_execute_canonicalizes_alias_backed_provider_text_in_failure_payload(self, mock_fetch, mock_receipt_svc, mock_budget, client):
        mock_receipt = MagicMock()
        mock_receipt.receipt_id = "rcpt_alias_failure_123"
        mock_receipt_svc.return_value.create_receipt = AsyncMock(return_value=mock_receipt)

        with patch("routes.providers_v2._forward_internal") as mock_forward:
            estimate_resp = MagicMock()
            estimate_resp.status_code = 200
            estimate_resp.json.return_value = {
                "data": {
                    "provider": "brave-search",
                    "cost_estimate_usd": 0.003,
                    "endpoint_pattern": "GET /res/v1/web/search",
                },
            }
            estimate_resp.headers = {}

            execute_resp = MagicMock()
            execute_resp.status_code = 502
            execute_resp.json.return_value = {
                "data": {
                    "provider_used": "brave-search",
                    "fallback_provider": "brave-search",
                },
                "error": {
                    "code": "UPSTREAM_FAILURE",
                    "message": "brave-search upstream exploded",
                    "detail": "Retry brave-search or choose pdl after the outage clears.",
                    "available_providers": ["brave-search", "pdl"],
                },
            }
            execute_resp.headers = {}

            mock_forward.side_effect = [estimate_resp, execute_resp]

            resp = client.post(
                "/v2/providers/brave-search-api/execute",
                json={
                    "capability": "search.query",
                    "parameters": {"q": "rhumb"},
                    "credential_mode": "byok",
                },
            )

        assert resp.status_code == 502
        body = resp.json()
        assert body["data"]["provider_used"] == "brave-search-api"
        assert body["data"]["fallback_provider"] == "brave-search-api"
        assert body["error"]["message"] == "brave-search-api upstream exploded"
        assert body["error"]["detail"] == "Retry brave-search-api or choose people-data-labs after the outage clears."
        assert body["error"]["available_providers"] == ["brave-search-api", "people-data-labs"]

        receipt_input = mock_receipt_svc.return_value.create_receipt.await_args.args[0]
        assert receipt_input.provider_id == "brave-search-api"
        assert receipt_input.error_message == "brave-search-api upstream exploded"

    def test_execute_canonicalizes_alias_backed_provider_text_in_estimate_failure(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider):
            with patch("routes.providers_v2._forward_internal") as mock_forward:
                estimate_resp = MagicMock()
                estimate_resp.status_code = 502
                estimate_resp.json.return_value = {
                    "data": {
                        "provider_used": "brave-search",
                        "fallback_providers": ["brave-search"],
                    },
                    "error": {
                        "code": "UPSTREAM_FAILURE",
                        "message": "brave-search estimate failed",
                        "detail": "Check brave-search or pdl before retrying.",
                        "available_providers": ["brave-search", "pdl"],
                    },
                }
                estimate_resp.headers = {}
                mock_forward.return_value = estimate_resp

                resp = client.post(
                    "/v2/providers/brave-search-api/execute",
                    json={
                        "capability": "search.query",
                        "parameters": {"q": "rhumb"},
                        "credential_mode": "byok",
                    },
                )

        assert resp.status_code == 502
        body = resp.json()
        assert body["data"]["provider_used"] == "brave-search-api"
        assert body["data"]["fallback_providers"] == ["brave-search-api"]
        assert body["error"]["message"] == "brave-search-api estimate failed"
        assert body["error"]["detail"] == "Check brave-search-api or people-data-labs before retrying."
        assert body["error"]["available_providers"] == ["brave-search-api", "people-data-labs"]

    def test_execute_nonexistent_provider(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch):
            resp = client.post(
                "/v2/providers/nonexistent/execute",
                json={"capability": _TEST_CAPABILITY, "parameters": {}},
            )
        assert resp.status_code == 503  # PROVIDER_UNAVAILABLE

    def test_execute_unsupported_capability(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch):
            resp = client.post(
                f"/v2/providers/{_TEST_PROVIDER_SLUG}/execute",
                json={"capability": "nonexistent.capability", "parameters": {}},
            )
        assert resp.status_code == 404  # CAPABILITY_NOT_FOUND

    def test_execute_unsupported_capability_error_uses_canonical_public_provider_id(self, client):
        with patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch_with_alias_backed_callable_provider):
            resp = client.post(
                "/v2/providers/Brave-Search/execute",
                json={"capability": "nonexistent.capability", "parameters": {}},
            )

        assert resp.status_code == 404
        error = resp.json()["error"]
        assert error["message"] == "Provider 'brave-search-api' does not support capability 'nonexistent.capability'."
        assert error["detail"] == "Check supported capabilities at GET /v2/providers/brave-search-api."

    @patch("routes.providers_v2._resolve_agent_for_budget", new_callable=AsyncMock, return_value=None)
    @patch("routes.providers_v2.get_receipt_service")
    @patch("routes.providers_v2.supabase_fetch", side_effect=_mock_supabase_fetch)
    def test_execute_max_cost_exceeded(self, mock_fetch, mock_receipt_svc, mock_budget, client):
        with patch("routes.providers_v2._forward_internal") as mock_forward:
            estimate_resp = MagicMock()
            estimate_resp.status_code = 200
            estimate_resp.json.return_value = {
                "data": {
                    "provider": _TEST_PROVIDER_SLUG,
                    "cost_estimate_usd": 0.10,
                    "endpoint_pattern": "POST /v1/chat/completions",
                },
            }
            estimate_resp.headers = {}
            mock_forward.return_value = estimate_resp

            resp = client.post(
                f"/v2/providers/{_TEST_PROVIDER_SLUG}/execute",
                json={
                    "capability": _TEST_CAPABILITY,
                    "parameters": {},
                    "policy": {"max_cost_usd": 0.001},
                },
            )

        assert resp.status_code == 402  # BUDGET_EXCEEDED


# ---------------------------------------------------------------------------
# Layer 1 cost calculation
# ---------------------------------------------------------------------------

class TestLayer1Cost:
    def test_cost_above_floor(self):
        from routes.providers_v2 import _layer1_cost

        cost = _layer1_cost(0.10)
        assert cost["provider_cost_usd"] == 0.1
        assert cost["rhumb_fee_usd"] == 0.008  # 10% of 0.10 = 0.01, but 8% = 0.008
        assert cost["total_usd"] == 0.108

    def test_cost_below_floor(self):
        from routes.providers_v2 import _layer1_cost

        cost = _layer1_cost(0.001)
        # 0.001 * 0.08 = 0.00008, which is below floor of 0.0002
        assert cost["rhumb_fee_usd"] == 0.0002
        assert cost["total_usd"] == 0.0012

    def test_zero_cost(self):
        from routes.providers_v2 import _layer1_cost

        cost = _layer1_cost(0.0)
        assert cost["rhumb_fee_usd"] == 0.0002  # floor applies
        assert cost["total_usd"] == 0.0002
