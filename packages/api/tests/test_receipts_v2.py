"""Tests for the v2 receipts API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from services.route_explanation import RouteExplanation


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from app import create_app
    app = create_app()
    return TestClient(app)


def test_get_receipt_not_found(client):
    """GET /v2/receipts/{id} returns 404 for unknown receipt."""
    with patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        resp = client.get("/v2/receipts/rcpt_nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        # FastAPI serializes HTTPException detail — check for the error message
        assert "rcpt_nonexistent" in str(body)


def test_get_receipt_found(client):
    """GET /v2/receipts/{id} returns receipt when found."""
    receipt_data = {
        "receipt_id": "rcpt_test123",
        "execution_id": "exec_001",
        "status": "success",
        "chain_sequence": 1,
        "receipt_hash": "sha256:abc",
    }
    with patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [receipt_data]
        resp = client.get("/v2/receipts/rcpt_test123")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["receipt_id"] == "rcpt_test123"
        assert body["error"] is None


def test_get_receipt_canonicalizes_legacy_provider_text(client):
    receipt_data = {
        "receipt_id": "rcpt_test123",
        "execution_id": "exec_001",
        "status": "failure",
        "provider_id": "brave-search-api",
        "provider_name": "brave-search",
        "error_message": "brave-search upstream exploded",
        "winner_reason": "brave-search won on freshness",
        "error_provider_raw": "brave-search",
        "chain_sequence": 1,
        "receipt_hash": "sha256:abc",
    }
    with patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [receipt_data]
        resp = client.get("/v2/receipts/rcpt_test123")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["provider_id"] == "brave-search-api"
        assert body["data"]["provider_name"] == "brave-search-api"
        assert body["data"]["error_message"] == "brave-search-api upstream exploded"
        assert body["data"]["winner_reason"] == "brave-search-api won on freshness"
        assert "error_provider_raw" not in body["data"]


def test_get_receipt_canonicalizes_alternate_provider_alias_text(client):
    receipt_data = {
        "receipt_id": "rcpt_test124",
        "execution_id": "exec_002",
        "status": "failure",
        "provider_id": "brave-search-api",
        "error_message": "brave-search failed after pdl credential lookup",
        "winner_reason": "brave-search fell back to pdl on contact coverage",
        "error_provider_raw": "pdl",
        "chain_sequence": 2,
        "receipt_hash": "sha256:def",
    }
    with patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [receipt_data]
        resp = client.get("/v2/receipts/rcpt_test124")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["provider_id"] == "brave-search-api"
        assert body["data"]["error_message"] == "brave-search-api failed after people-data-labs credential lookup"
        assert body["data"]["winner_reason"] == "brave-search-api fell back to people-data-labs on contact coverage"
        assert "error_provider_raw" not in body["data"]


def test_query_receipts_empty(client):
    """GET /v2/receipts returns empty list when no receipts match."""
    with patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        resp = client.get("/v2/receipts?agent_id=agent_test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["receipts"] == []
        assert body["data"]["count"] == 0


def test_query_receipts_with_results(client):
    """GET /v2/receipts returns results when receipts exist."""
    receipts = [
        {"receipt_id": "rcpt_1", "agent_id": "agent_test"},
        {"receipt_id": "rcpt_2", "agent_id": "agent_test"},
    ]
    with patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = receipts
        resp = client.get("/v2/receipts?agent_id=agent_test&limit=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["count"] == 2


def test_query_receipts_canonicalizes_alias_backed_provider_ids(client):
    receipts = [{"receipt_id": "rcpt_1", "provider_id": "brave-search"}]
    with patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = receipts
        resp = client.get("/v2/receipts?provider_id=brave-search-api")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["receipts"][0]["provider_id"] == "brave-search-api"
        query = mock_fetch.await_args.args[0]
        assert "provider_id=in.(brave-search-api,brave-search)" in query


def test_query_receipts_canonicalizes_alias_backed_provider_text(client):
    receipts = [
        {
            "receipt_id": "rcpt_1",
            "provider_id": "people-data-labs",
            "provider_name": "PDL",
            "error_message": "PDL credential unavailable",
            "winner_reason": "PDL won on contact coverage",
        }
    ]
    with patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = receipts
        resp = client.get("/v2/receipts?provider_id=people-data-labs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["receipts"][0]["provider_id"] == "people-data-labs"
        assert body["data"]["receipts"][0]["provider_name"] == "people-data-labs"
        assert body["data"]["receipts"][0]["error_message"] == "people-data-labs credential unavailable"
        assert body["data"]["receipts"][0]["winner_reason"] == "people-data-labs won on contact coverage"


def test_get_receipt_explanation_uses_persisted_receipt_link(client):
    """GET /v2/receipts/{id}/explanation falls back to persisted route_explanations by receipt_id."""
    receipt_data = {
        "receipt_id": "rcpt_test123",
        "execution_id": "exec_001",
        "status": "success",
        "chain_sequence": 1,
        "layer": 2,
        "receipt_hash": "sha256:abc",
    }
    persisted = RouteExplanation(
        explanation_id="rexp_test123",
        capability_id="search.query",
        winner_provider_id="brave-search",
        winner_composite_score=0.91,
        selection_reason="best composite score",
        human_summary="brave-search won on quality and price.",
    )
    with (
        patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock) as mock_fetch,
        patch("routes.receipts_v2.get_persisted_explanation_by_receipt", new_callable=AsyncMock) as mock_get,
    ):
        mock_fetch.return_value = [receipt_data]
        mock_get.return_value = persisted
        resp = client.get("/v2/receipts/rcpt_test123/explanation")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["explanation_id"] == "rexp_test123"
        assert body["data"]["winner"]["provider_id"] == "brave-search-api"
        assert "brave-search-api" in body["data"]["human_summary"]


def test_verify_chain_endpoint(client):
    """GET /v2/receipts/chain/verify returns verification results."""
    chain_data = [
        {
            "receipt_id": "rcpt_1",
            "receipt_hash": "sha256:aaa",
            "previous_receipt_hash": None,
            "chain_sequence": 1,
        },
        {
            "receipt_id": "rcpt_2",
            "receipt_hash": "sha256:bbb",
            "previous_receipt_hash": "sha256:aaa",
            "chain_sequence": 2,
        },
    ]
    with patch("services.receipt_service.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = chain_data
        resp = client.get("/v2/receipts/chain/verify?limit=100")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["chain_intact"] is True
        assert body["data"]["verified"] == 2
