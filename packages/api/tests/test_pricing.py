"""Tests for the public pricing contract endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import create_app


def test_get_pricing_returns_public_contract() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/pricing")

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None

    data = body["data"]
    assert data["canonical_api_base_url"] == "https://api.rhumb.dev/v1"
    assert data["free_tier"]["included_executions_per_month"] == 1000
    assert data["modes"]["rhumb_managed"]["margin_percent"] == 20
    assert data["modes"]["x402"]["margin_percent"] == 15
    assert data["modes"]["x402"]["network"] == "Base"
    assert data["modes"]["x402"]["token"] == "USDC"
    assert data["modes"]["byok"]["upstream_passthrough"] is True
    assert data["modes"]["byok"]["margin_percent"] == 0


def test_get_pricing_omits_finalized_volume_discount_tiers() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/pricing")

    assert response.status_code == 200
    data = response.json()["data"]
    assert "volume_discounts" not in data
    assert any("Volume discount tiers are not final" in note for note in data["notes"])
