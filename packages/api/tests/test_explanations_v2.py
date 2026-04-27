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
        human_summary="brave-search selected over 1 other eligible candidate.",
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
    assert body["data"]["winner"]["provider_id"] == "brave-search-api"
    assert "brave-search-api" in body["data"]["human_summary"]
    assert "brave-search selected" not in body["data"]["human_summary"]


def test_get_explanation_canonicalizes_alternate_alias_text_when_persisted_ids_are_already_public():
    from app import create_app

    client = TestClient(create_app())
    persisted = RouteExplanation(
        explanation_id="rexp_public_ids",
        capability_id="search.query",
        winner_provider_id="brave-search-api",
        winner_composite_score=0.88,
        selection_reason="persisted lookup",
        human_summary="brave-search-api selected over pdl.",
        candidates=[],
    )

    with patch(
        "routes.explanations_v2.get_persisted_explanation",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.return_value = persisted
        resp = client.get("/v2/explanations/rexp_public_ids")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["winner"]["provider_id"] == "brave-search-api"
    assert body["data"]["human_summary"] == "brave-search-api selected over people-data-labs."
    assert "brave-search-api-api" not in body["data"]["human_summary"]


def test_get_explanation_canonicalizes_same_provider_alias_text_when_persisted_ids_are_already_public():
    from app import create_app

    client = TestClient(create_app())
    persisted = RouteExplanation(
        explanation_id="rexp_public_ids_same_alias",
        capability_id="search.query",
        winner_provider_id="brave-search-api",
        winner_composite_score=0.88,
        selection_reason="persisted lookup",
        human_summary="Brave Search (brave-search) selected over people-data-labs.",
        candidates=[],
    )

    with patch(
        "routes.explanations_v2.get_persisted_explanation",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.return_value = persisted
        resp = client.get("/v2/explanations/rexp_public_ids_same_alias")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["winner"]["provider_id"] == "brave-search-api"
    assert body["data"]["human_summary"] == (
        "Brave Search (brave-search-api) selected over people-data-labs."
    )
    assert "brave-search-api-api" not in body["data"]["human_summary"]


def test_get_explanation_not_found_uses_explanation_code():
    from app import create_app

    client = TestClient(create_app())

    with (
        patch("routes.explanations_v2.get_explanation", return_value=None),
        patch("routes.explanations_v2.get_persisted_explanation", new_callable=AsyncMock, return_value=None),
    ):
        resp = client.get("/v2/explanations/rexp_missing")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "EXPLANATION_NOT_FOUND"
    assert "rexp_missing" in body["error"]["message"]


def test_get_explanation_rejects_blank_id_before_reads():
    from app import create_app

    client = TestClient(create_app())

    with (
        patch("routes.explanations_v2.get_explanation") as mock_hot_get,
        patch("routes.explanations_v2.get_persisted_explanation", new_callable=AsyncMock) as mock_persisted_get,
    ):
        resp = client.get("/v2/explanations/%20%20")

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'explanation_id' parameter."
    assert body["error"]["detail"] == "Provide a non-empty explanation_id path value."
    mock_hot_get.assert_not_called()
    mock_persisted_get.assert_not_awaited()
