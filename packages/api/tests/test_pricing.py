"""Tests for the public pricing contract endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import create_app


def test_api_pricing_fallback_catalog_matches_shared_catalog() -> None:
    """Keep API-only pricing fallback aligned with canonical shared pricing truth.

    The API prefers packages/shared/pricing.json in the monorepo, but API-only Docker
    builds fall back to packages/api/pricing.json.
    """

    import json
    from pathlib import Path

    packages_root = Path(__file__).resolve().parents[2]
    shared_pricing = packages_root / "shared" / "pricing.json"
    api_fallback_pricing = Path(__file__).resolve().parents[1] / "pricing.json"

    assert shared_pricing.exists()
    assert api_fallback_pricing.exists()

    shared = json.loads(shared_pricing.read_text("utf-8"))
    fallback = json.loads(api_fallback_pricing.read_text("utf-8"))

    assert fallback == shared


def test_get_pricing_returns_public_contract() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/pricing")

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None

    data = body["data"]
    assert data["canonical_api_base_url"] == "https://api.rhumb.dev/v1"
    assert data["free_tier"] is None
    assert data["modes"]["rhumb_managed"]["margin_percent"] == 20
    assert data["modes"]["x402"]["margin_percent"] == 15
    assert data["modes"]["x402"]["network"] == "Base"
    assert data["modes"]["x402"]["token"] == "USDC"
    assert data["modes"]["byok"]["label"] == "BYOK or Agent Vault"
    assert data["modes"]["byok"]["upstream_passthrough"] is True
    assert data["modes"]["byok"]["margin_percent"] == 0
    assert "Agent Vault" in data["modes"]["byok"]["passthrough_note"]


def test_get_pricing_omits_finalized_volume_discount_tiers() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/pricing")

    assert response.status_code == 200
    data = response.json()["data"]
    assert "volume_discounts" not in data
    assert any("Volume discount tiers are not final" in note for note in data["notes"])
