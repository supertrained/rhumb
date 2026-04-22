"""Tests for v2 Billing endpoints (routes/billing_v2.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def app():
    from fastapi import FastAPI
    from routes.billing_v2 import router

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


class TestBillingV2Auth:
    def test_summary_requires_auth_handoff(self, client):
        resp = client.get("/v2/billing/summary")
        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"] == "Missing X-Rhumb-Key header"
        assert body["error"] == "missing_api_key"
        assert body["auth_handoff"]["reason"] == "missing_api_key"
        assert body["auth_handoff"]["retry_url"] == "/v2/billing/summary"

    def test_events_invalid_key_includes_auth_handoff(self, client):
        mock_store = MagicMock()
        mock_store.verify_api_key_with_agent = AsyncMock(return_value=None)

        with patch("routes.billing_v2._get_identity_store", return_value=mock_store):
            resp = client.get(
                "/v2/billing/events",
                headers={"X-Rhumb-Key": "rk_invalid"},
            )

        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"] == "Invalid or expired API key"
        assert body["error"] == "invalid_api_key"
        assert body["auth_handoff"]["reason"] == "invalid_api_key"
        assert body["auth_handoff"]["retry_url"] == "/v2/billing/events"


def test_summary_invalid_period_uses_explicit_invalid_parameters():
    from app import create_app
    from fastapi.testclient import TestClient

    with patch("routes.billing_v2._require_org_or_401", new=AsyncMock(return_value="org_test")):
        resp = TestClient(create_app()).get(
            "/v2/billing/summary?period=2026-99",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'period' filter."
    assert "YYYY-MM" in body["error"]["detail"]


def test_events_invalid_event_type_uses_explicit_invalid_parameters():
    from app import create_app
    from fastapi.testclient import TestClient

    with patch("routes.billing_v2._require_org_or_401", new=AsyncMock(return_value="org_test")):
        resp = TestClient(create_app()).get(
            "/v2/billing/events?event_type=not-real",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'event_type' filter."
    assert "execution.charged" in body["error"]["detail"]


def test_events_invalid_since_uses_explicit_invalid_parameters():
    from app import create_app
    from fastapi.testclient import TestClient

    with patch("routes.billing_v2._require_org_or_401", new=AsyncMock(return_value="org_test")):
        resp = TestClient(create_app()).get(
            "/v2/billing/events?since=definitely-not-iso",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'since' filter."
    assert "ISO 8601" in body["error"]["detail"]
