"""Tests for the v2 scores API endpoints."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from services.score_cache import CachedScore, ScoreAuditChain, ScoreReadCache


def test_get_score_not_found_uses_explicit_score_code():
    from app import create_app

    client = TestClient(create_app())
    resp = client.get("/v2/scores/missing-provider")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "SCORE_NOT_FOUND"
    assert "missing-provider" in body["error"]["message"]
    assert "cache" in body["error"]["detail"].lower()


def test_get_score_found_returns_cached_score():
    from app import create_app

    cache = ScoreReadCache(ttl_seconds=60.0)
    cache._populate([
        CachedScore(
            service_slug="brave-search-api",
            an_score=74.2,
            execution_score=81.4,
            access_readiness_score=67.5,
            autonomy_score=72.1,
            confidence=0.93,
            tier="A2",
            refreshed_at=0.0,
        )
    ])

    with patch("routes.scores_v2.get_score_cache", return_value=cache):
        client = TestClient(create_app())
        resp = client.get("/v2/scores/brave-search")

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["service_slug"] == "brave-search-api"
    assert body["data"]["an_score"] == 74.2


def test_get_score_history_not_found_uses_explicit_score_code():
    from app import create_app

    client = TestClient(create_app())
    resp = client.get("/v2/scores/missing-provider/history")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "SCORE_NOT_FOUND"
    assert "missing-provider" in body["error"]["message"]
    assert "cache" in body["error"]["detail"].lower()


def test_get_score_history_found_returns_empty_entries_for_cached_provider():
    from app import create_app

    cache = ScoreReadCache(ttl_seconds=60.0)
    cache._populate([
        CachedScore(
            service_slug="brave-search-api",
            an_score=74.2,
            execution_score=81.4,
            access_readiness_score=67.5,
            autonomy_score=72.1,
            confidence=0.93,
            tier="A2",
            refreshed_at=0.0,
        )
    ])
    chain = ScoreAuditChain()

    with (
        patch("routes.scores_v2.get_score_cache", return_value=cache),
        patch("routes.scores_v2.get_audit_chain", return_value=chain),
    ):
        client = TestClient(create_app())
        resp = client.get("/v2/scores/brave-search/history")

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["service_slug"] == "brave-search-api"
    assert body["data"]["entries"] == []
    assert body["data"]["chain_verified"] is True
