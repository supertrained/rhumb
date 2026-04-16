"""Tests for Trust Dashboard API v2 endpoints (WU-41.6)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.billing_events import BillingEventType, BillingEventStream, get_billing_event_stream
from services.score_cache import ScoreReadCache, get_score_cache
from tests.test_score_cache import _make_score


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def app():
    from fastapi import FastAPI
    from routes.trust_v2 import router
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


# ── Auth checks ──────────────────────────────────────────────────────


class TestTrustV2Auth:
    def test_summary_requires_auth(self, client):
        resp = client.get("/v2/trust/summary")
        assert resp.status_code == 401

    def test_providers_requires_auth(self, client):
        resp = client.get("/v2/trust/providers")
        assert resp.status_code == 401

    def test_costs_requires_auth(self, client):
        resp = client.get("/v2/trust/costs")
        assert resp.status_code == 401

    def test_reliability_requires_auth(self, client):
        resp = client.get("/v2/trust/reliability")
        assert resp.status_code == 401


# ── Trust posture computation ────────────────────────────────────────


class TestTrustPosture:
    def test_new_posture(self):
        from routes.trust_v2 import _compute_trust_posture
        posture = _compute_trust_posture(0, 0.0, 0)
        assert posture["level"] == "new"

    def test_excellent_posture(self):
        from routes.trust_v2 import _compute_trust_posture
        posture = _compute_trust_posture(100, 99.5, 5)
        assert posture["level"] == "excellent"

    def test_good_posture(self):
        from routes.trust_v2 import _compute_trust_posture
        posture = _compute_trust_posture(50, 96.0, 2)
        assert posture["level"] == "good"

    def test_fair_posture(self):
        from routes.trust_v2 import _compute_trust_posture
        posture = _compute_trust_posture(50, 90.0, 3)
        assert posture["level"] == "fair"

    def test_needs_attention_posture(self):
        from routes.trust_v2 import _compute_trust_posture
        posture = _compute_trust_posture(100, 70.0, 5)
        assert posture["level"] == "needs_attention"


# ── Provider health labels ───────────────────────────────────────────


class TestProviderHealth:
    def test_insufficient_data(self):
        from routes.trust_v2 import _provider_health_label
        assert _provider_health_label(100.0, 2) == "insufficient_data"

    def test_healthy(self):
        from routes.trust_v2 import _provider_health_label
        assert _provider_health_label(99.5, 100) == "healthy"

    def test_degraded(self):
        from routes.trust_v2 import _provider_health_label
        assert _provider_health_label(97.0, 50) == "degraded"

    def test_unstable(self):
        from routes.trust_v2 import _provider_health_label
        assert _provider_health_label(85.0, 20) == "unstable"

    def test_unhealthy(self):
        from routes.trust_v2 import _provider_health_label
        assert _provider_health_label(50.0, 10) == "unhealthy"


# ── Billing event integration ────────────────────────────────────────


class TestTrustBillingIntegration:
    def test_summary_aggregation(self):
        """Verify trust summary correctly aggregates billing events."""
        stream = BillingEventStream()
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_t1", 150, provider_slug="stripe", capability_id="payments.create")
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_t1", 200, provider_slug="openai", capability_id="ai.generate_text")
        stream.emit(BillingEventType.EXECUTION_FAILED_NO_CHARGE, "org_t1", 0, provider_slug="stripe", capability_id="payments.create")

        summary = stream.summarize("org_t1")
        assert summary.execution_count == 2  # Only charged events
        assert summary.total_charged_usd_cents == 350
        assert len(summary.by_provider) == 2

    def test_provider_distribution(self):
        """Verify provider stats are computed correctly from events."""
        stream = BillingEventStream()
        for _ in range(5):
            stream.emit(BillingEventType.EXECUTION_CHARGED, "org_t2", 100, provider_slug="stripe")
        for _ in range(3):
            stream.emit(BillingEventType.EXECUTION_CHARGED, "org_t2", 200, provider_slug="openai")
        stream.emit(BillingEventType.EXECUTION_FAILED_NO_CHARGE, "org_t2", 0, provider_slug="openai")

        events = stream.query(org_id="org_t2")
        assert len(events) == 9

        # Check provider event counts
        stripe_events = [e for e in events if e.provider_slug == "stripe"]
        openai_events = [e for e in events if e.provider_slug == "openai"]
        assert len(stripe_events) == 5
        assert len(openai_events) == 4

    def test_cost_breakdown(self):
        """Verify cost breakdowns are correct."""
        stream = BillingEventStream()
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_t3", 100, provider_slug="a", capability_id="cap1")
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_t3", 200, provider_slug="b", capability_id="cap2")
        stream.emit(BillingEventType.EXECUTION_CHARGED, "org_t3", 300, provider_slug="a", capability_id="cap1")

        summary = stream.summarize("org_t3")
        assert summary.by_provider == {"a": 400, "b": 200}
        assert summary.by_capability == {"cap1": 400, "cap2": 200}

    def test_score_cache_enrichment(self):
        """Verify score cache provides AN scores for provider enrichment."""
        cache = get_score_cache()
        cache._populate([
            _make_score("stripe", 8.5, tier="L4"),
            _make_score("openai", 9.1, tier="L4"),
        ])

        # Score cache should be accessible for enrichment
        stripe_score = cache.get("stripe")
        assert stripe_score is not None
        assert stripe_score.an_score == 8.5

        openai_score = cache.get("openai")
        assert openai_score is not None
        assert openai_score.an_score == 9.1


class TestTrustV2Endpoints:
    def test_summary_counts_alias_and_public_provider_as_one_provider(self, client):
        stream = BillingEventStream()
        stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            "org_alias",
            100,
            provider_slug="brave-search",
            capability_id="search.query",
        )
        stream.emit(
            BillingEventType.EXECUTION_FAILED_NO_CHARGE,
            "org_alias",
            0,
            provider_slug="brave-search-api",
            capability_id="search.query",
        )

        with (
            patch("routes.trust_v2._require_org", new=AsyncMock(return_value="org_alias")),
            patch("routes.trust_v2.get_billing_event_stream", return_value=stream),
        ):
            resp = client.get("/v2/trust/summary", headers={"X-Rhumb-Key": "test_key"})

        assert resp.status_code == 200
        assert resp.json()["data"]["unique_providers_used"] == 1

    def test_providers_canonicalize_alias_backed_provider_slug_and_keep_scores(self, client):
        stream = BillingEventStream()
        stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            "org_alias",
            100,
            provider_slug="brave-search",
            capability_id="search.query",
        )
        stream.emit(
            BillingEventType.EXECUTION_FAILED_NO_CHARGE,
            "org_alias",
            0,
            provider_slug="brave-search-api",
            capability_id="search.query",
        )
        cache = ScoreReadCache(ttl_seconds=300.0, max_entries=100)
        cache._populate([_make_score("brave-search", 8.8, tier="L4")])

        with (
            patch("routes.trust_v2._require_org", new=AsyncMock(return_value="org_alias")),
            patch("routes.trust_v2.get_billing_event_stream", return_value=stream),
            patch("routes.trust_v2.get_score_cache", return_value=cache),
        ):
            resp = client.get("/v2/trust/providers", headers={"X-Rhumb-Key": "test_key"})

        assert resp.status_code == 200
        providers = resp.json()["data"]["providers"]
        assert providers == [{
            "provider_slug": "brave-search-api",
            "execution_count": 2,
            "success_count": 1,
            "failure_count": 1,
            "total_charged_usd_cents": 100,
            "success_rate_pct": 50.0,
            "total_charged_usd": 1.0,
            "an_score": 8.8,
            "tier": "L4",
        }]

    def test_costs_and_reliability_merge_alias_backed_provider_truth(self, client):
        stream = BillingEventStream()
        stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            "org_alias",
            100,
            provider_slug="pdl",
            capability_id="people.enrich",
        )
        stream.emit(
            BillingEventType.EXECUTION_FAILED_NO_CHARGE,
            "org_alias",
            0,
            provider_slug="people-data-labs",
            capability_id="people.enrich",
        )
        stream.emit(
            BillingEventType.EXECUTION_CHARGED,
            "org_alias",
            200,
            provider_slug="people-data-labs",
            capability_id="people.enrich",
        )

        with (
            patch("routes.trust_v2._require_org", new=AsyncMock(return_value="org_alias")),
            patch("routes.trust_v2.get_billing_event_stream", return_value=stream),
        ):
            costs_resp = client.get("/v2/trust/costs", headers={"X-Rhumb-Key": "test_key"})
            reliability_resp = client.get("/v2/trust/reliability", headers={"X-Rhumb-Key": "test_key"})

        assert costs_resp.status_code == 200
        assert costs_resp.json()["data"]["by_provider"] == {
            "people-data-labs": {
                "charged_usd_cents": 300,
                "charged_usd": 3.0,
                "pct_of_total": 100.0,
            }
        }

        assert reliability_resp.status_code == 200
        assert reliability_resp.json()["data"]["by_provider"] == [{
            "provider_slug": "people-data-labs",
            "total_executions": 3,
            "successes": 2,
            "failures": 1,
            "success_rate_pct": 66.7,
            "health": "unhealthy",
        }]
