"""Tests for AN Score structural separation — score cache + audit chain (WU-41.4)."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
import httpx

from services.score_cache import (
    CachedScore,
    ScoreAuditChain,
    ScoreAuditEntry,
    ScoreReadCache,
    fetch_scores_from_db,
    get_audit_chain,
    get_score_cache,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_score(
    slug: str = "stripe",
    an_score: float = 8.5,
    execution_score: float = 8.2,
    access_readiness_score: float | None = 7.9,
    autonomy_score: float | None = 6.0,
    confidence: float = 0.85,
    tier: str = "L4",
    refreshed_at: float = 0.0,
) -> CachedScore:
    return CachedScore(
        service_slug=slug,
        an_score=an_score,
        execution_score=execution_score,
        access_readiness_score=access_readiness_score,
        autonomy_score=autonomy_score,
        confidence=confidence,
        tier=tier,
        refreshed_at=refreshed_at,
    )


# ── CachedScore immutability ────────────────────────────────────────


class TestCachedScoreImmutability:
    def test_frozen_dataclass(self):
        """CachedScore is frozen — consumers cannot mutate it."""
        score = _make_score()
        with pytest.raises(AttributeError):
            score.an_score = 9.9  # type: ignore[misc]

    def test_fields_present(self):
        score = _make_score(slug="openai", an_score=9.1, tier="L4")
        assert score.service_slug == "openai"
        assert score.an_score == 9.1
        assert score.tier == "L4"


# ── ScoreReadCache ───────────────────────────────────────────────────


class TestScoreReadCache:
    def test_empty_cache_returns_none(self):
        cache = ScoreReadCache(ttl_seconds=60.0)
        assert cache.get("nonexistent") is None

    def test_populate_and_get(self):
        cache = ScoreReadCache(ttl_seconds=60.0)
        entries = [
            _make_score("stripe", 8.5),
            _make_score("openai", 9.1),
        ]
        count = cache._populate(entries)
        assert count == 2

        stripe = cache.get("stripe")
        assert stripe is not None
        assert stripe.an_score == 8.5

        openai = cache.get("openai")
        assert openai is not None
        assert openai.an_score == 9.1

    def test_get_many(self):
        cache = ScoreReadCache(ttl_seconds=60.0)
        cache._populate([
            _make_score("stripe", 8.5),
            _make_score("openai", 9.1),
            _make_score("twilio", 7.0),
        ])
        result = cache.get_many(["stripe", "openai", "nonexistent"])
        assert "stripe" in result
        assert "openai" in result
        assert "nonexistent" not in result

    def test_scores_by_slug(self):
        cache = ScoreReadCache(ttl_seconds=60.0)
        cache._populate([
            _make_score("stripe", 8.5),
            _make_score("openai", 9.1),
        ])
        scores = cache.scores_by_slug(["stripe", "openai", "missing"])
        assert scores == {"stripe": 8.5, "openai": 9.1}

    def test_ttl_expiry(self):
        """Entries expire after TTL."""
        clock_time = [0.0]
        cache = ScoreReadCache(ttl_seconds=10.0)
        cache._clock = lambda: clock_time[0]

        cache._populate([_make_score("stripe", 8.5)])
        assert cache.get("stripe") is not None

        # Advance past TTL
        clock_time[0] = 15.0
        assert cache.get("stripe") is None

    def test_all_scores(self):
        cache = ScoreReadCache(ttl_seconds=60.0)
        cache._populate([
            _make_score("stripe", 8.5),
            _make_score("openai", 9.1),
        ])
        all_scores = cache.all_scores()
        assert len(all_scores) == 2
        assert "stripe" in all_scores
        assert "openai" in all_scores

    def test_upsert(self):
        cache = ScoreReadCache(ttl_seconds=60.0)
        cache._populate([_make_score("stripe", 8.5)])

        # Update stripe's score
        cache._upsert(_make_score("stripe", 9.0))
        entry = cache.get("stripe")
        assert entry is not None
        assert entry.an_score == 9.0

    def test_size_property(self):
        cache = ScoreReadCache(ttl_seconds=60.0)
        assert cache.size == 0
        cache._populate([_make_score("stripe"), _make_score("openai")])
        assert cache.size == 2

    def test_last_refresh_age(self):
        clock_time = [100.0]
        cache = ScoreReadCache(ttl_seconds=60.0)
        cache._clock = lambda: clock_time[0]

        # Never refreshed
        assert cache.last_refresh_age_seconds == float("inf")

        cache._populate([_make_score("stripe")])
        assert cache.last_refresh_age_seconds == 0.0

        clock_time[0] = 130.0
        assert cache.last_refresh_age_seconds == 30.0

    def test_eviction_on_max_entries(self):
        cache = ScoreReadCache(ttl_seconds=60.0, max_entries=2)
        cache._populate([_make_score("a"), _make_score("b")])
        assert cache.size == 2

        cache._upsert(_make_score("c"))
        assert cache.size == 2
        # One of the originals should have been evicted
        remaining = cache.all_scores()
        assert "c" in remaining


# ── ScoreAuditChain ──────────────────────────────────────────────────


class TestScoreAuditChain:
    def test_empty_chain_verifies(self):
        chain = ScoreAuditChain()
        assert chain.verify_chain() is True
        assert chain.length == 0
        assert chain.latest_hash == ScoreAuditChain.GENESIS_HASH

    def test_append_and_verify(self):
        chain = ScoreAuditChain()
        entry = chain.append("stripe", None, 8.5, "initial")
        assert entry.service_slug == "stripe"
        assert entry.old_score is None
        assert entry.new_score == 8.5
        assert entry.change_reason == "initial"
        assert entry.prev_hash == ScoreAuditChain.GENESIS_HASH
        assert chain.length == 1
        assert chain.verify_chain() is True

    def test_chain_hash_links(self):
        chain = ScoreAuditChain()
        e1 = chain.append("stripe", None, 8.5, "initial")
        e2 = chain.append("stripe", 8.5, 8.7, "recalculation")
        assert e2.prev_hash == e1.chain_hash
        assert chain.verify_chain() is True

    def test_multi_service_chain(self):
        chain = ScoreAuditChain()
        chain.append("stripe", None, 8.5, "initial")
        chain.append("openai", None, 9.1, "initial")
        chain.append("stripe", 8.5, 8.7, "evidence_update")
        assert chain.length == 3
        assert chain.verify_chain() is True

    def test_history_filtered(self):
        chain = ScoreAuditChain()
        chain.append("stripe", None, 8.5, "initial")
        chain.append("openai", None, 9.1, "initial")
        chain.append("stripe", 8.5, 8.7, "recalculation")

        stripe_hist = chain.history(service_slug="stripe")
        assert len(stripe_hist) == 2
        assert all(e.service_slug == "stripe" for e in stripe_hist)

        openai_hist = chain.history(service_slug="openai")
        assert len(openai_hist) == 1

    def test_history_limit(self):
        chain = ScoreAuditChain()
        for i in range(10):
            chain.append("stripe", float(i), float(i + 1), "recalculation")

        hist = chain.history(service_slug="stripe", limit=3)
        assert len(hist) == 3
        # Should be the 3 most recent
        assert hist[-1].new_score == 10.0

    def test_tamper_detection(self):
        chain = ScoreAuditChain()
        chain.append("stripe", None, 8.5, "initial")
        chain.append("stripe", 8.5, 8.7, "recalculation")
        assert chain.verify_chain() is True

        # Tamper with an entry (simulated by modifying internal list)
        with chain._lock:
            original = chain._entries[0]
            tampered = ScoreAuditEntry(
                entry_id=original.entry_id,
                service_slug=original.service_slug,
                old_score=original.old_score,
                new_score=99.9,  # Tampered score
                change_reason=original.change_reason,
                timestamp=original.timestamp,
                chain_hash=original.chain_hash,  # Hash won't match
                prev_hash=original.prev_hash,
            )
            chain._entries[0] = tampered

        assert chain.verify_chain() is False


# ── Module singleton ─────────────────────────────────────────────────


class TestModuleSingletons:
    def test_get_score_cache_returns_instance(self):
        cache = get_score_cache()
        assert isinstance(cache, ScoreReadCache)
        # Same instance on repeat call
        assert get_score_cache() is cache

    def test_get_audit_chain_returns_instance(self):
        chain = get_audit_chain()
        assert isinstance(chain, ScoreAuditChain)
        assert get_audit_chain() is chain


# ── v2 Score endpoints ───────────────────────────────────────────────


@pytest.fixture
def app():
    """Build a minimal FastAPI app with the v2 scores router."""
    from fastapi import FastAPI
    from routes.scores_v2 import router
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Sync test client."""
    from fastapi.testclient import TestClient
    return TestClient(app)


class TestScoresV2Endpoints:
    def test_get_score_not_found(self, client):
        resp = client.get("/v2/scores/nonexistent")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["error"] == "SCORE_NOT_FOUND"

    def test_get_score_from_cache(self, client):
        # Populate cache
        cache = get_score_cache()
        cache._populate([_make_score("stripe", 8.5, tier="L4")])

        resp = client.get("/v2/scores/stripe")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["service_slug"] == "stripe"
        assert body["data"]["an_score"] == 8.5
        assert body["data"]["source"] == "score_cache"
        assert body["error"] is None

    def test_get_score_history_empty(self, client):
        resp = client.get("/v2/scores/stripe/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["service_slug"] == "stripe"
        assert body["data"]["chain_verified"] is True

    def test_get_score_history_with_entries(self, client):
        chain = get_audit_chain()
        chain.append("test-svc", None, 7.0, "initial")
        chain.append("test-svc", 7.0, 7.5, "evidence_update")

        resp = client.get("/v2/scores/test-svc/history?limit=10")
        assert resp.status_code == 200
        body = resp.json()
        entries = body["data"]["entries"]
        assert len(entries) >= 2
        # Check chain-hash fields are present
        assert "chain_hash" in entries[0]
        assert "prev_hash" in entries[0]

    def test_cache_status(self, client):
        resp = client.get("/v2/scores/cache/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "cache_size" in body["data"]
        assert "last_refresh_status" in body["data"]
        assert "last_refresh_error" in body["data"]
        assert "structural_guarantees" in body["data"]
        assert isinstance(body["data"]["structural_guarantees"], list)


# ── Auto-refresh background task ─────────────────────────────────────


class TestScoreCacheAutoRefresh:
    @pytest.mark.asyncio
    async def test_refresh_loop_populates_cache(self):
        """The refresh loop should populate the cache from DB results."""
        from services.score_cache import _refresh_loop, ScoreReadCache

        cache = ScoreReadCache(ttl_seconds=60.0)
        mock_entries = [
            _make_score("stripe", 8.5),
            _make_score("openai", 9.1),
        ]

        stop = asyncio.Event()

        with patch(
            "services.score_cache.fetch_scores_from_db",
            new_callable=AsyncMock,
            return_value=mock_entries,
        ):
            # Start the loop, let it run once, then stop
            task = asyncio.create_task(_refresh_loop(cache, interval=0.1, stop_event=stop))
            await asyncio.sleep(0.3)
            stop.set()
            await task

        assert cache.size == 2
        assert cache.get("stripe") is not None
        assert cache.get("stripe").an_score == 8.5

    @pytest.mark.asyncio
    async def test_refresh_loop_handles_empty_db(self):
        """Empty DB result should not crash the loop."""
        from services.score_cache import _refresh_loop, ScoreReadCache

        cache = ScoreReadCache(ttl_seconds=60.0)
        stop = asyncio.Event()

        with patch(
            "services.score_cache.fetch_scores_from_db",
            new_callable=AsyncMock,
            return_value=[],
        ):
            task = asyncio.create_task(_refresh_loop(cache, interval=0.1, stop_event=stop))
            await asyncio.sleep(0.2)
            stop.set()
            await task

        assert cache.size == 0
        assert cache.last_refresh_status == "empty"
        assert cache.last_refresh_error is None

    @pytest.mark.asyncio
    async def test_refresh_loop_handles_exception(self):
        """Exceptions during refresh should not kill the loop."""
        from services.score_cache import _refresh_loop, ScoreReadCache

        cache = ScoreReadCache(ttl_seconds=60.0)
        stop = asyncio.Event()

        call_count = [0]
        async def flaky_fetch():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Simulated DB failure")
            return [_make_score("stripe", 8.5)]

        with patch(
            "services.score_cache.fetch_scores_from_db",
            side_effect=flaky_fetch,
        ):
            task = asyncio.create_task(_refresh_loop(cache, interval=0.1, stop_event=stop))
            await asyncio.sleep(0.4)
            stop.set()
            await task

        # Should have recovered after the first failure
        assert call_count[0] >= 2
        assert cache.size >= 1
        assert cache.last_refresh_status == "success"

    @pytest.mark.asyncio
    async def test_refresh_loop_records_error_state(self):
        """Refresh errors should be reflected in cache diagnostics."""
        from services.score_cache import _refresh_loop, ScoreReadCache

        cache = ScoreReadCache(ttl_seconds=60.0)
        stop = asyncio.Event()

        async def always_fail():
            raise RuntimeError("db unavailable")

        with patch("services.score_cache.fetch_scores_from_db", side_effect=always_fail):
            task = asyncio.create_task(_refresh_loop(cache, interval=0.1, stop_event=stop))
            await asyncio.sleep(0.15)
            stop.set()
            await task

        assert cache.last_refresh_status == "error"
        assert cache.last_refresh_error is not None
        assert "db unavailable" in cache.last_refresh_error

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self):
        """start/stop should work without errors."""
        from services.score_cache import (
            start_score_cache_refresh,
            stop_score_cache_refresh,
        )

        with patch(
            "services.score_cache.fetch_scores_from_db",
            new_callable=AsyncMock,
            return_value=[_make_score("test", 7.0)],
        ):
            await start_score_cache_refresh()
            # Give it a moment to warm up
            await asyncio.sleep(0.1)
            await stop_score_cache_refresh()

        # Cache should have been warmed
        cache = get_score_cache()
        assert cache.get("test") is not None


class TestFetchScoresFromDb:
    @pytest.mark.asyncio
    async def test_fetch_scores_from_db_does_not_select_nonexistent_score_column(self):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = []

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("services.score_cache.httpx.AsyncClient", return_value=mock_client):
            await fetch_scores_from_db()

        called_url = mock_client.get.call_args.args[0]
        assert "aggregate_recommendation_score" in called_url
        assert ",score," not in called_url
        assert "dimension_snapshot" not in called_url
        assert "?select=service_slug,score," not in called_url

    @pytest.mark.asyncio
    async def test_fetch_scores_from_db_raises_instead_of_masking_query_errors(self):
        request = httpx.Request("GET", "https://example.test/rest/v1/scores")
        response = httpx.Response(400, request=request, text='{"code":"42703"}')

        mock_client = AsyncMock()
        mock_client.get.return_value = response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("services.score_cache.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                await fetch_scores_from_db()

    @pytest.mark.asyncio
    async def test_fetch_scores_from_db_parses_live_scores_shape(self):
        row = {
            "service_slug": "stripe",
            "aggregate_recommendation_score": 8.9,
            "execution_score": 9.1,
            "access_readiness_score": 8.4,
            "autonomy_score": 7.2,
            "confidence": 0.98,
            "tier": "L4",
            "dimension_snapshot": {"score_breakdown": {"execution": 9.1}},
            "calculated_at": "2026-04-01T22:00:00Z",
        }

        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [row]

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("services.score_cache.httpx.AsyncClient", return_value=mock_client):
            entries = await fetch_scores_from_db()

        assert len(entries) == 1
        entry = entries[0]
        assert entry.service_slug == "stripe"
        assert entry.an_score == 8.9
        assert entry.execution_score == 9.1
        assert entry.access_readiness_score == 8.4
        assert entry.autonomy_score == 7.2
        assert entry.confidence == 0.98
        assert entry.tier == "L4"

    @pytest.mark.asyncio
    async def test_fetch_scores_from_db_falls_back_to_legacy_score_field(self):
        row = {
            "service_slug": "legacy-svc",
            "score": 7.5,
            "dimension_snapshot": {
                "score_breakdown": {
                    "execution": 7.0,
                    "access_readiness": 6.8,
                    "autonomy": 5.9,
                }
            },
        }

        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [row]

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("services.score_cache.httpx.AsyncClient", return_value=mock_client):
            entries = await fetch_scores_from_db()

        assert len(entries) == 1
        entry = entries[0]
        assert entry.service_slug == "legacy-svc"
        assert entry.an_score == 7.5
        assert entry.execution_score == 7.0
        assert entry.access_readiness_score == 6.8
        assert entry.autonomy_score == 5.9
