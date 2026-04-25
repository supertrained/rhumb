"""Tests for v2 Audit endpoints (routes/audit_v2.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from fastapi import FastAPI
    from routes.audit_v2 import router

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


class TestAuditV2Auth:
    def test_events_requires_auth_handoff(self, client):
        resp = client.get("/v2/audit/events")
        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"] == "Missing X-Rhumb-Key header"
        assert body["error"] == "missing_api_key"
        assert body["auth_handoff"]["reason"] == "missing_api_key"
        assert body["auth_handoff"]["retry_url"] == "/v2/audit/events"

    def test_invalid_key_includes_auth_handoff(self, client):
        mock_store = MagicMock()
        mock_store.verify_api_key_with_agent = AsyncMock(return_value=None)

        with patch("routes.audit_v2._get_identity_store", return_value=mock_store):
            resp = client.get(
                "/v2/audit/events",
                headers={"X-Rhumb-Key": "rk_invalid"},
            )

        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"] == "Invalid or expired API key"
        assert body["error"] == "invalid_api_key"
        assert body["auth_handoff"]["reason"] == "invalid_api_key"
        assert body["auth_handoff"]["retry_url"] == "/v2/audit/events"


def test_get_audit_event_not_found_uses_explicit_error_code():
    from app import create_app

    trail = MagicMock()
    trail.query.return_value = []

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail", return_value=trail),
    ):
        resp = TestClient(create_app()).get(
            "/v2/audit/events/aevt_missing",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "AUDIT_EVENT_NOT_FOUND"
    assert "aevt_missing" in body["error"]["message"]


def test_list_audit_events_invalid_event_type_uses_explicit_invalid_parameters():
    from app import create_app

    with patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")):
        resp = TestClient(create_app()).get(
            "/v2/audit/events?event_type=not-real",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'event_type' filter."
    assert "execution.started" in body["error"]["detail"]


def test_list_audit_events_invalid_since_uses_explicit_invalid_parameters():
    from app import create_app

    with patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")):
        resp = TestClient(create_app()).get(
            "/v2/audit/events?since=definitely-not-iso",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'since' filter."
    assert "ISO 8601" in body["error"]["detail"]


def test_list_audit_events_normalizes_event_type_and_severity_filters_before_reads():
    from app import create_app
    from services.audit_trail import AuditEventType, AuditSeverity

    trail = MagicMock()
    trail.query.return_value = []
    trail.count.return_value = 0

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail", return_value=trail),
    ):
        resp = TestClient(create_app()).get(
            "/v2/audit/events?event_type=%20EXECUTION.STARTED%20&severity=%20WARNING%20",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 200
    trail.query.assert_called_once()
    assert trail.query.call_args.kwargs["event_type"] is AuditEventType.EXECUTION_STARTED
    assert trail.query.call_args.kwargs["severity"] is AuditSeverity.WARNING


def test_list_audit_events_rejects_inverted_time_window_before_reads():
    from app import create_app

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail") as get_audit_trail,
    ):
        resp = TestClient(create_app()).get(
            "/v2/audit/events?since=2026-04-25T12:00:00%2B00:00&until=2026-04-25T11:00:00%2B00:00",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid audit time window."
    assert "since" in body["error"]["detail"]
    assert "until" in body["error"]["detail"]
    get_audit_trail.assert_not_called()


def test_list_audit_events_invalid_limit_uses_explicit_invalid_parameters_before_reads():
    from app import create_app

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail") as get_audit_trail,
    ):
        resp = TestClient(create_app()).get(
            "/v2/audit/events?limit=0",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'limit' filter."
    assert "between 1 and 500" in body["error"]["detail"]
    get_audit_trail.assert_not_called()


def test_list_audit_events_invalid_offset_uses_explicit_invalid_parameters_before_reads():
    from app import create_app

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail") as get_audit_trail,
    ):
        resp = TestClient(create_app()).get(
            "/v2/audit/events?offset=-1",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'offset' filter."
    assert "greater than or equal to 0" in body["error"]["detail"]
    get_audit_trail.assert_not_called()


def test_list_audit_events_invalid_category_uses_explicit_invalid_parameters():
    from app import create_app

    trail = MagicMock()

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail", return_value=trail),
    ):
        resp = TestClient(create_app()).get(
            "/v2/audit/events?category=totally-made-up",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'category' filter."
    assert "admin" in body["error"]["detail"]
    trail.query.assert_not_called()
    trail.count.assert_not_called()


def test_list_audit_events_rejects_blank_resource_filters_before_reads():
    from app import create_app

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail") as get_audit_trail,
    ):
        resp = TestClient(create_app()).get(
            "/v2/audit/events?resource_type=%20%20",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'resource_type' filter."
    assert "non-empty" in body["error"]["detail"]
    get_audit_trail.assert_not_called()


def test_list_audit_events_trims_resource_filters_and_counts_same_resource_id():
    from app import create_app

    trail = MagicMock()
    trail.query.return_value = []
    trail.count.return_value = 0

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail", return_value=trail),
    ):
        resp = TestClient(create_app()).get(
            "/v2/audit/events?resource_type=%20provider%20&resource_id=%20brave-search%20",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 200
    trail.query.assert_called_once()
    trail.count.assert_called_once()
    assert trail.query.call_args.kwargs["resource_type"] == "provider"
    assert trail.query.call_args.kwargs["resource_id"] == "brave-search"
    assert trail.count.call_args.kwargs["resource_type"] == "provider"
    assert trail.count.call_args.kwargs["resource_id"] == "brave-search"


def test_export_audit_valid_category_normalizes_whitespace_and_case():
    from app import create_app

    trail = MagicMock()
    trail.export.return_value = MagicMock(
        format="json",
        event_count=0,
        chain_verified=True,
        exported_at=MagicMock(isoformat=lambda: "2026-04-23T16:53:00+00:00"),
        data="[]",
    )

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail", return_value=trail),
    ):
        resp = TestClient(create_app()).post(
            "/v2/audit/export?category=%20Auth%20",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 200
    trail.export.assert_called_once()
    assert trail.export.call_args.kwargs["category"] == "auth"


def test_export_audit_rejects_blank_category_before_reads():
    from app import create_app

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail") as get_audit_trail,
    ):
        resp = TestClient(create_app()).post(
            "/v2/audit/export?category=%20%20",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'category' filter."
    get_audit_trail.assert_not_called()


def test_export_audit_trims_resource_filters_before_export():
    from app import create_app

    trail = MagicMock()
    trail.export.return_value = MagicMock(
        format="json",
        event_count=0,
        chain_verified=True,
        exported_at=MagicMock(isoformat=lambda: "2026-04-25T23:52:00+00:00"),
        data="[]",
    )

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail", return_value=trail),
    ):
        resp = TestClient(create_app()).post(
            "/v2/audit/export?resource_type=%20provider%20&resource_id=%20pdl%20",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 200
    trail.export.assert_called_once()
    assert trail.export.call_args.kwargs["resource_type"] == "provider"
    assert trail.export.call_args.kwargs["resource_id"] == "pdl"


def test_export_audit_normalizes_event_type_and_severity_filters():
    from app import create_app
    from services.audit_trail import AuditEventType, AuditSeverity

    trail = MagicMock()
    trail.export.return_value = MagicMock(
        format="json",
        event_count=0,
        chain_verified=True,
        exported_at=MagicMock(isoformat=lambda: "2026-04-25T19:20:00+00:00"),
        data="[]",
    )

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail", return_value=trail),
    ):
        resp = TestClient(create_app()).post(
            "/v2/audit/export?event_type=%20EXECUTION.STARTED%20&severity=%20WARNING%20",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 200
    trail.export.assert_called_once()
    assert trail.export.call_args.kwargs["event_type"] is AuditEventType.EXECUTION_STARTED
    assert trail.export.call_args.kwargs["severity"] is AuditSeverity.WARNING


def test_export_audit_rejects_inverted_time_window_before_reads():
    from app import create_app

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail") as get_audit_trail,
    ):
        resp = TestClient(create_app()).post(
            "/v2/audit/export?since=2026-04-25T12:00:00%2B00:00&until=2026-04-25T11:00:00%2B00:00",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid audit time window."
    get_audit_trail.assert_not_called()


def test_export_audit_invalid_format_uses_explicit_invalid_parameters():
    from app import create_app

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail") as get_audit_trail,
    ):
        resp = TestClient(create_app()).post(
            "/v2/audit/export?format=xml",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'format' filter."
    assert "json, csv" in body["error"]["detail"]
    get_audit_trail.assert_not_called()


def test_export_audit_format_normalizes_whitespace_and_case():
    from app import create_app

    trail = MagicMock()
    trail.export.return_value = MagicMock(
        format="csv",
        event_count=0,
        chain_verified=True,
        data="event_id,event_type\n",
    )

    with (
        patch("routes.audit_v2._require_org_or_401", new=AsyncMock(return_value="org_test")),
        patch("routes.audit_v2.get_audit_trail", return_value=trail),
    ):
        resp = TestClient(create_app()).post(
            "/v2/audit/export?format=%20CSV%20",
            headers={"X-Rhumb-Key": "rk_test"},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    trail.export.assert_called_once()
    assert trail.export.call_args.kwargs["format"] == "csv"
