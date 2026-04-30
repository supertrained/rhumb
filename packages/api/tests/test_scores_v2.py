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


def test_get_score_rejects_blank_provider_id_before_cache_read():
    from app import create_app

    with patch("routes.scores_v2.get_score_cache", side_effect=AssertionError("score cache read opened")):
        client = TestClient(create_app())
        resp = client.get("/v2/scores/%20%20")

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert "provider_id" in body["error"]["message"]


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


def test_get_score_history_rejects_blank_provider_id_before_reads():
    from app import create_app

    with (
        patch("routes.scores_v2.get_score_cache", side_effect=AssertionError("score cache read opened")),
        patch("routes.scores_v2.get_audit_chain", side_effect=AssertionError("audit chain read opened")),
    ):
        client = TestClient(create_app())
        resp = client.get("/v2/scores/%20%20/history")

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert "provider_id" in body["error"]["message"]


def test_get_score_history_rejects_invalid_limit_before_reads():
    from app import create_app

    with (
        patch("routes.scores_v2.get_score_cache", side_effect=AssertionError("score cache read opened")),
        patch("routes.scores_v2.get_audit_chain", side_effect=AssertionError("audit chain read opened")),
    ):
        client = TestClient(create_app())
        resp = client.get("/v2/scores/brave-search/history?limit=0")

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert "limit" in body["error"]["message"]


def test_get_score_history_rejects_non_integer_limit_with_canonical_error_before_reads():
    from app import create_app

    with (
        patch("routes.scores_v2.get_score_cache", side_effect=AssertionError("score cache read opened")),
        patch("routes.scores_v2.get_audit_chain", side_effect=AssertionError("audit chain read opened")),
    ):
        client = TestClient(create_app())
        resp = client.get("/v2/scores/brave-search/history?limit=ten")

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'limit' filter."
    assert "between 1 and 200" in body["error"]["detail"]


def test_get_score_history_trims_numeric_limit_before_audit_read():
    from app import create_app

    chain = ScoreAuditChain()
    with (
        patch("routes.scores_v2.get_score_cache") as get_score_cache,
        patch("routes.scores_v2.get_audit_chain", return_value=chain),
        patch.object(chain, "history", return_value=[]) as history,
    ):
        get_score_cache.return_value.get.return_value = CachedScore(
            service_slug="brave-search-api",
            an_score=74.2,
            execution_score=81.4,
            access_readiness_score=67.5,
            autonomy_score=72.1,
            confidence=0.93,
            tier="A2",
            refreshed_at=0.0,
        )
        client = TestClient(create_app())
        resp = client.get("/v2/scores/brave-search/history?limit=%2007%20")

    assert resp.status_code == 200
    history.assert_called_once()
    assert history.call_args.kwargs["limit"] == 7
