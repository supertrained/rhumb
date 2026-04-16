"""Tests for the provider attribution service (WU-41.2).

Verifies the canonical ``_rhumb`` block, response headers, and error context
are correctly built from provider detail data.
"""

from __future__ import annotations

import pytest

from services.provider_attribution import (
    ProviderAttribution,
    build_attribution,
    build_attribution_sync,
    clear_provider_cache,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the provider cache before each test."""
    clear_provider_cache()
    yield
    clear_provider_cache()


def _make_attribution(**overrides) -> ProviderAttribution:
    defaults = {
        "provider_slug": "stripe",
        "provider_name": "Stripe",
        "provider_category": "payments",
        "provider_docs_url": "https://stripe.com/docs/api",
        "an_score": 8.1,
        "tier": "L4",
        "layer": 2,
        "receipt_id": "rcpt_test_001",
        "cost_provider_usd": 0.0100,
        "cost_rhumb_fee_usd": 0.0020,
        "cost_total_usd": 0.0120,
        "latency_total_ms": 250.0,
        "latency_provider_ms": 200.0,
        "latency_overhead_ms": 50.0,
        "credential_mode": "rhumb_managed",
    }
    defaults.update(overrides)
    return build_attribution_sync(**defaults)


# ---------------------------------------------------------------------------
# _rhumb block tests
# ---------------------------------------------------------------------------

class TestRhumbBlock:
    """Test the canonical _rhumb response body block."""

    def test_full_block_structure(self):
        attr = _make_attribution()
        block = attr.to_rhumb_block()

        assert block["provider"]["id"] == "stripe"
        assert block["provider"]["name"] == "Stripe"
        assert block["provider"]["category"] == "payments"
        assert block["provider"]["docs_url"] == "https://stripe.com/docs/api"
        assert block["provider"]["an_score"] == 8.1
        assert block["provider"]["tier"] == "L4"
        assert block["layer"] == 2
        assert block["receipt_id"] == "rcpt_test_001"
        assert block["cost"]["provider_usd"] == 0.0100
        assert block["cost"]["rhumb_fee_usd"] == 0.0020
        assert block["cost"]["total_usd"] == 0.0120
        assert block["latency"]["total_ms"] == 250.0
        assert block["latency"]["provider_ms"] == 200.0
        assert block["latency"]["overhead_ms"] == 50.0
        assert block["credential_mode"] == "rhumb_managed"

    def test_minimal_block(self):
        attr = build_attribution_sync(provider_slug="unknown-api")
        block = attr.to_rhumb_block()

        assert block["provider"]["id"] == "unknown-api"
        assert block["provider"]["name"] == "unknown-api"
        assert block["layer"] == 2
        assert "cost" not in block
        assert "latency" not in block
        assert "credential_mode" not in block
        assert "region" not in block

    def test_layer1_block(self):
        attr = _make_attribution(layer=1)
        block = attr.to_rhumb_block()
        assert block["layer"] == 1

    def test_region_included_when_set(self):
        attr = _make_attribution(region="us-east-1")
        block = attr.to_rhumb_block()
        assert block["region"] == "us-east-1"

    def test_name_falls_back_to_slug(self):
        attr = build_attribution_sync(provider_slug="my-api", provider_name=None)
        block = attr.to_rhumb_block()
        assert block["provider"]["name"] == "my-api"


# ---------------------------------------------------------------------------
# Response header tests
# ---------------------------------------------------------------------------

class TestResponseHeaders:
    """Test the spec-required response headers."""

    def test_full_headers(self):
        attr = _make_attribution()
        headers = attr.to_response_headers()

        assert headers["X-Rhumb-Provider"] == "stripe"
        assert headers["X-Rhumb-Layer"] == "2"
        assert headers["X-Rhumb-Receipt-Id"] == "rcpt_test_001"
        assert headers["X-Rhumb-Cost-Usd"] == "0.012000"

    def test_minimal_headers(self):
        attr = build_attribution_sync(provider_slug="test-api")
        headers = attr.to_response_headers()

        assert headers["X-Rhumb-Provider"] == "test-api"
        assert headers["X-Rhumb-Layer"] == "2"
        assert "X-Rhumb-Receipt-Id" not in headers
        assert "X-Rhumb-Cost-Usd" not in headers
        assert "X-Rhumb-Provider-Region" not in headers

    def test_region_header(self):
        attr = _make_attribution(region="eu-west-1")
        headers = attr.to_response_headers()
        assert headers["X-Rhumb-Provider-Region"] == "eu-west-1"

    def test_layer1_header(self):
        attr = _make_attribution(layer=1)
        headers = attr.to_response_headers()
        assert headers["X-Rhumb-Layer"] == "1"

    def test_cost_precision(self):
        attr = _make_attribution(cost_total_usd=0.000200)
        headers = attr.to_response_headers()
        assert headers["X-Rhumb-Cost-Usd"] == "0.000200"


# ---------------------------------------------------------------------------
# Error context tests
# ---------------------------------------------------------------------------

class TestErrorContext:
    """Test attribution context for error envelopes."""

    def test_error_context_structure(self):
        attr = _make_attribution()
        ctx = attr.to_error_context()

        assert ctx["provider_id"] == "stripe"
        assert ctx["provider_name"] == "Stripe"
        assert ctx["layer"] == 2
        assert ctx["receipt_id"] == "rcpt_test_001"

    def test_error_context_minimal(self):
        attr = build_attribution_sync(provider_slug="test")
        ctx = attr.to_error_context()

        assert ctx["provider_id"] == "test"
        assert ctx["provider_name"] == "test"
        assert ctx["layer"] == 2
        assert ctx["receipt_id"] is None


# ---------------------------------------------------------------------------
# Builder tests
# ---------------------------------------------------------------------------

class TestSyncBuilder:
    """Test the synchronous builder with pre-fetched data."""

    def test_all_fields_propagate(self):
        attr = build_attribution_sync(
            provider_slug="openai",
            provider_name="OpenAI",
            provider_category="ai",
            provider_docs_url="https://platform.openai.com/docs",
            an_score=8.5,
            tier="L4",
            layer=2,
            receipt_id="rcpt_123",
            cost_provider_usd=0.05,
            cost_rhumb_fee_usd=0.004,
            cost_total_usd=0.054,
            latency_total_ms=800.0,
            latency_provider_ms=750.0,
            latency_overhead_ms=50.0,
            credential_mode="byo",
            region="us-west-2",
        )
        block = attr.to_rhumb_block()
        headers = attr.to_response_headers()

        assert block["provider"]["id"] == "openai"
        assert block["cost"]["total_usd"] == 0.054
        assert block["region"] == "us-west-2"
        assert headers["X-Rhumb-Provider"] == "openai"
        assert headers["X-Rhumb-Provider-Region"] == "us-west-2"

    def test_sync_builder_canonicalizes_runtime_alias_for_public_identity(self):
        attr = build_attribution_sync(
            provider_slug="pdl",
            provider_name="People Data Labs",
        )

        block = attr.to_rhumb_block()
        headers = attr.to_response_headers()

        assert attr.provider_id == "people-data-labs"
        assert block["provider"]["id"] == "people-data-labs"
        assert block["provider"]["name"] == "People Data Labs"
        assert headers["X-Rhumb-Provider"] == "people-data-labs"


class TestAsyncBuilder:
    """Test the async builder that fetches from the database."""

    @pytest.mark.asyncio
    async def test_build_attribution_canonicalizes_runtime_alias_for_public_identity(self, monkeypatch):
        seen_queries: list[str] = []

        async def _mock_fetch(query):
            seen_queries.append(query)
            return [{
                "slug": "brave-search-api",
                "name": "Brave Search",
                "category": "search",
                "api_domain": "api.search.brave.com",
                "aggregate_recommendation_score": 7.8,
                "tier_label": "L3",
                "official_docs": "https://api.search.brave.com/docs",
            }]

        monkeypatch.setattr(
            "services.provider_attribution.supabase_fetch",
            _mock_fetch,
        )

        attr = await build_attribution(
            provider_slug="brave-search",
            layer=2,
            receipt_id="rcpt_brave_alias",
        )

        block = attr.to_rhumb_block()
        headers = attr.to_response_headers()

        assert seen_queries == [
            "services?slug=eq.brave-search-api&select=slug,name,description,category,api_domain,aggregate_recommendation_score,tier_label,official_docs&limit=1"
        ]
        assert attr.provider_id == "brave-search-api"
        assert block["provider"]["id"] == "brave-search-api"
        assert block["provider"]["name"] == "Brave Search"
        assert headers["X-Rhumb-Provider"] == "brave-search-api"

    @pytest.mark.asyncio
    async def test_build_attribution_with_mock(self, monkeypatch):
        """Mock the supabase fetch to test async builder."""
        async def _mock_fetch(query):
            return [{
                "slug": "brave-search-api",
                "name": "Brave Search",
                "category": "search",
                "api_domain": "api.search.brave.com",
                "aggregate_recommendation_score": 7.8,
                "tier_label": "L3",
                "official_docs": "https://api.search.brave.com/docs",
            }]

        monkeypatch.setattr(
            "services.provider_attribution.supabase_fetch",
            _mock_fetch,
        )

        attr = await build_attribution(
            provider_slug="brave-search-api",
            layer=2,
            receipt_id="rcpt_brave_001",
            cost_total_usd=0.005,
        )

        assert attr.provider_id == "brave-search-api"
        assert attr.provider_name == "Brave Search"
        assert attr.provider_category == "search"
        assert attr.provider_docs_url == "https://api.search.brave.com/docs"
        assert attr.an_score == 7.8

        block = attr.to_rhumb_block()
        assert block["provider"]["name"] == "Brave Search"
        assert block["cost"]["total_usd"] == 0.005

    @pytest.mark.asyncio
    async def test_build_attribution_provider_not_found(self, monkeypatch):
        """When provider is not in DB, attribution still works with slug as name."""
        async def _mock_fetch(query):
            return []

        monkeypatch.setattr(
            "services.provider_attribution.supabase_fetch",
            _mock_fetch,
        )

        attr = await build_attribution(
            provider_slug="nonexistent-api",
            layer=1,
        )

        assert attr.provider_id == "nonexistent-api"
        assert attr.provider_name is None

        block = attr.to_rhumb_block()
        assert block["provider"]["name"] == "nonexistent-api"

    @pytest.mark.asyncio
    async def test_cache_hit(self, monkeypatch):
        """Second call for same provider should use the cache."""
        call_count = 0

        async def _mock_fetch(query):
            nonlocal call_count
            call_count += 1
            return [{"slug": "stripe", "name": "Stripe", "category": "payments"}]

        monkeypatch.setattr(
            "services.provider_attribution.supabase_fetch",
            _mock_fetch,
        )

        attr1 = await build_attribution(provider_slug="stripe")
        attr2 = await build_attribution(provider_slug="stripe")

        assert call_count == 1  # Only one DB call
        assert attr1.provider_name == "Stripe"
        assert attr2.provider_name == "Stripe"


# ---------------------------------------------------------------------------
# Integration pattern tests
# ---------------------------------------------------------------------------

class TestIntegrationPatterns:
    """Test common integration patterns callers will use."""

    def test_merge_into_existing_response_headers(self):
        """Callers merge attribution headers with other response headers."""
        existing_headers = {
            "X-Rhumb-Version": "2026-03-30",
            "X-Request-ID": "req_abc",
        }
        attr = _make_attribution()
        existing_headers.update(attr.to_response_headers())

        assert existing_headers["X-Rhumb-Provider"] == "stripe"
        assert existing_headers["X-Rhumb-Version"] == "2026-03-30"

    def test_inject_rhumb_block_into_response_data(self):
        """Callers inject the _rhumb block into execution response data."""
        execution_data = {
            "execution_id": "exec_123",
            "result": {"status": "ok"},
        }
        attr = _make_attribution()
        execution_data["_rhumb"] = attr.to_rhumb_block()

        assert execution_data["_rhumb"]["provider"]["id"] == "stripe"
        assert execution_data["execution_id"] == "exec_123"
