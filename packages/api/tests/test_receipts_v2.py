"""Tests for the v2 receipts API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


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
