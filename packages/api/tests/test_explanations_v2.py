"""Tests for the v2 explanations API endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from services.route_explanation import RouteExplanation


def test_get_explanation_falls_back_to_persisted_store():
    from app import create_app

    client = TestClient(create_app())
    persisted = RouteExplanation(
        explanation_id="rexp_persisted",
        capability_id="search.query",
        winner_provider_id="brave-search",
        winner_composite_score=0.88,
        selection_reason="persisted lookup",
        human_summary="Persisted explanation was returned.",
    )

    with patch(
        "routes.explanations_v2.get_persisted_explanation",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.return_value = persisted
        resp = client.get("/v2/explanations/rexp_persisted")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["explanation_id"] == "rexp_persisted"
    assert body["data"]["winner"]["provider_id"] == "brave-search"
