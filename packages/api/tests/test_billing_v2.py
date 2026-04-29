"""Tests for v2 Billing endpoints (routes/billing_v2.py)."""

from __future__ import annotations

import json
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

    @pytest.mark.anyio
    async def test_blank_key_is_missing_before_identity_store(self):
        from routes.billing_v2 import _require_org_or_401

        raw_request = MagicMock()
        raw_request.state.request_id = "req_test"
        raw_request.url.path = "/v2/billing/events"

        with patch("routes.billing_v2._get_identity_store") as get_store:
            response = await _require_org_or_401(raw_request, "  \t  ")

        assert response.status_code == 401
        body = json.loads(response.body)
        assert body["detail"] == "Missing X-Rhumb-Key header"
        assert body["error"] == "missing_api_key"
        get_store.assert_not_called()

    @pytest.mark.anyio
    async def test_valid_key_is_trimmed_before_verification(self):
        from routes.billing_v2 import _require_org_or_401

        raw_request = MagicMock()
        raw_request.state.request_id = "req_test"
        raw_request.url.path = "/v2/billing/events"
        agent = MagicMock(organization_id="org_test")
        mock_store = MagicMock()
        mock_store.verify_api_key_with_agent = AsyncMock(return_value=agent)

        with patch("routes.billing_v2._get_identity_store", return_value=mock_store):
            org_id = await _require_org_or_401(raw_request, "  rk_test  ")

        assert org_id == "org_test"
        mock_store.verify_api_key_with_agent.assert_awaited_once_with("rk_test")

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


def test_summary_invalid_period_uses_explicit_invalid_parameters_before_auth_or_reads():
    from app import create_app
    from fastapi.testclient import TestClient

    require_org = AsyncMock(return_value="org_test")
    with (
        patch("routes.billing_v2._require_org_or_401", new=require_org),
        patch("routes.billing_v2.get_billing_event_stream") as mock_stream,
    ):
        resp = TestClient(create_app()).get(
            "/v2/billing/summary?period=2026-99",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'period' filter."
    assert "YYYY-MM" in body["error"]["detail"]
    require_org.assert_not_awaited()
    mock_stream.assert_not_called()


def test_events_invalid_event_type_uses_explicit_invalid_parameters_before_auth_or_reads():
    from app import create_app
    from fastapi.testclient import TestClient

    require_org = AsyncMock(return_value="org_test")
    with (
        patch("routes.billing_v2._require_org_or_401", new=require_org),
        patch("routes.billing_v2.get_billing_event_stream") as mock_stream,
    ):
        resp = TestClient(create_app()).get(
            "/v2/billing/events?event_type=not-real",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'event_type' filter."
    assert "execution.charged" in body["error"]["detail"]
    require_org.assert_not_awaited()
    mock_stream.assert_not_called()


def test_events_normalizes_event_type_filter_before_query():
    from app import create_app
    from fastapi.testclient import TestClient
    from services.billing_events import BillingEventType

    mock_stream = MagicMock()
    mock_stream.query.return_value = []

    with (
        patch("routes.billing_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.billing_v2.get_billing_event_stream", return_value=mock_stream),
    ):
        resp = TestClient(create_app()).get(
            "/v2/billing/events?event_type=%20EXECUTION.CHARGED%20",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 200
    mock_stream.query.assert_called_once()
    assert mock_stream.query.call_args.kwargs["event_type"] is BillingEventType.EXECUTION_CHARGED


def test_events_invalid_since_uses_explicit_invalid_parameters_before_auth_or_reads():
    from app import create_app
    from fastapi.testclient import TestClient

    require_org = AsyncMock(return_value="org_test")
    with (
        patch("routes.billing_v2._require_org_or_401", new=require_org),
        patch("routes.billing_v2.get_billing_event_stream") as mock_stream,
    ):
        resp = TestClient(create_app()).get(
            "/v2/billing/events?since=definitely-not-iso",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'since' filter."
    assert "ISO 8601" in body["error"]["detail"]
    require_org.assert_not_awaited()
    mock_stream.assert_not_called()


def test_events_rejects_invalid_limit_before_auth_or_stream_reads():
    from app import create_app
    from fastapi.testclient import TestClient

    require_org = AsyncMock(return_value="org_test")
    with (
        patch("routes.billing_v2._require_org_or_401", new=require_org),
        patch("routes.billing_v2.get_billing_event_stream") as mock_stream,
    ):
        resp = TestClient(create_app()).get(
            "/v2/billing/events?limit=0",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'limit' filter."
    assert "between 1 and 200" in body["error"]["detail"]
    require_org.assert_not_awaited()
    mock_stream.assert_not_called()
