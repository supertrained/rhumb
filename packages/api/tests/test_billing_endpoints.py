"""Tests for self-service billing endpoints (WU-0.5).

Covers: GET /billing/balance, GET /billing/ledger, PUT /billing/auto-reload.
All Supabase calls are mocked — no real DB required.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# ORG_ID must match the bypass agent's organization_id seeded in conftest.
# _auth_headers must use the bypass API key so verify_api_key_with_agent() resolves.
ORG_ID = "org-test"
_BYPASS_KEY = "rhumb_test_bypass_key_0000"


@pytest.fixture
def client() -> TestClient:
    """TestClient for the billing routes — reuses the conftest-created app so the
    autouse _inject_proxy_bypass_auth fixture wires up the identity store."""
    from app import app as _app
    return TestClient(_app)


def _auth_headers(org_id: str = ORG_ID) -> dict[str, str]:
    """Return X-Rhumb-Key header using the bypass key seeded in conftest."""
    return {"X-Rhumb-Key": _BYPASS_KEY}


# ---------------------------------------------------------------------------
# Helper mock data builders
# ---------------------------------------------------------------------------


def _credit_row(
    *,
    balance: int = 4750,
    reserved: int = 250,
    auto_reload_enabled: bool = False,
    auto_reload_threshold_cents: int | None = None,
    auto_reload_amount_cents: int | None = None,
) -> dict:
    return {
        "balance_usd_cents": balance,
        "reserved_usd_cents": reserved,
        "auto_reload_enabled": auto_reload_enabled,
        "auto_reload_threshold_cents": auto_reload_threshold_cents,
        "auto_reload_amount_cents": auto_reload_amount_cents,
    }


def _ledger_entry(
    *,
    event_type: str = "debit",
    amount_cents: int = -15,
    balance_after: int = 4750,
    execution_id: str | None = "exec_abc",
    description: str | None = "Test charge",
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "event_type": event_type,
        "amount_usd_cents": amount_cents,
        "balance_after_usd_cents": balance_after,
        "capability_execution_id": execution_id,
        "stripe_checkout_session_id": None,
        "description": description,
        "created_at": "2026-03-16T20:00:00Z",
    }


# ---------------------------------------------------------------------------
# GET /billing/balance
# ---------------------------------------------------------------------------


class TestGetBalance:
    """Tests for the enhanced balance endpoint."""

    def test_returns_all_fields(self, client: TestClient) -> None:
        mock_row = _credit_row(balance=4750, reserved=250)
        with patch("routes.billing.supabase_fetch", new_callable=AsyncMock, return_value=[mock_row]):
            resp = client.get("/v1/billing/balance", headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.json()

        assert data["org_id"] == ORG_ID
        assert data["balance_usd_cents"] == 4750
        assert data["balance_usd"] == pytest.approx(47.50)
        assert data["reserved_usd_cents"] == 250
        assert data["available_usd_cents"] == 4500
        assert data["available_usd"] == pytest.approx(45.00)
        assert data["auto_reload_enabled"] is False
        assert data["auto_reload_threshold_usd"] is None
        assert data["auto_reload_amount_usd"] is None

    def test_backward_compat_keys(self, client: TestClient) -> None:
        """Old callers that use balance_cents / reserved_cents should still work."""
        mock_row = _credit_row(balance=1000, reserved=100)
        with patch("routes.billing.supabase_fetch", new_callable=AsyncMock, return_value=[mock_row]):
            resp = client.get("/v1/billing/balance", headers=_auth_headers())

        data = resp.json()
        assert data["balance_cents"] == 1000
        assert data["reserved_cents"] == 100

    def test_auto_reload_fields_populated(self, client: TestClient) -> None:
        mock_row = _credit_row(
            auto_reload_enabled=True,
            auto_reload_threshold_cents=500,
            auto_reload_amount_cents=2000,
        )
        with patch("routes.billing.supabase_fetch", new_callable=AsyncMock, return_value=[mock_row]):
            resp = client.get("/v1/billing/balance", headers=_auth_headers())

        data = resp.json()
        assert data["auto_reload_enabled"] is True
        assert data["auto_reload_threshold_usd"] == pytest.approx(5.00)
        assert data["auto_reload_amount_usd"] == pytest.approx(20.00)

    def test_no_credits_returns_zero_defaults(self, client: TestClient) -> None:
        with patch("routes.billing.supabase_fetch", new_callable=AsyncMock, return_value=[]):
            resp = client.get("/v1/billing/balance", headers=_auth_headers())

        data = resp.json()
        assert data["org_id"] == ORG_ID
        assert data["balance_usd_cents"] == 0
        assert data["balance_usd"] == 0.0
        assert data["available_usd_cents"] == 0
        assert data["auto_reload_enabled"] is False

    def test_401_without_key(self, client: TestClient) -> None:
        resp = client.get("/v1/billing/balance")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /billing/ledger
# ---------------------------------------------------------------------------


class TestGetLedger:
    """Tests for the enhanced ledger endpoint."""

    def test_default_pagination(self, client: TestClient) -> None:
        entries = [_ledger_entry() for _ in range(3)]
        with (
            patch("routes.billing.supabase_fetch", new_callable=AsyncMock, return_value=entries),
            patch("routes.billing.supabase_count", new_callable=AsyncMock, return_value=3),
        ):
            resp = client.get("/v1/billing/ledger", headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 3
        assert data["total"] == 3
        assert data["limit"] == 50
        assert data["offset"] == 0

    def test_backward_compat_entries_key(self, client: TestClient) -> None:
        entries = [_ledger_entry()]
        with (
            patch("routes.billing.supabase_fetch", new_callable=AsyncMock, return_value=entries),
            patch("routes.billing.supabase_count", new_callable=AsyncMock, return_value=1),
        ):
            resp = client.get("/v1/billing/ledger", headers=_auth_headers())

        data = resp.json()
        # Both "events" and "entries" should exist
        assert "entries" in data
        assert data["entries"] == data["events"]

    def test_dollar_amounts_enriched(self, client: TestClient) -> None:
        entry = _ledger_entry(amount_cents=-15, balance_after=4750)
        with (
            patch("routes.billing.supabase_fetch", new_callable=AsyncMock, return_value=[entry]),
            patch("routes.billing.supabase_count", new_callable=AsyncMock, return_value=1),
        ):
            resp = client.get("/v1/billing/ledger", headers=_auth_headers())

        event = resp.json()["events"][0]
        assert event["amount_usd"] == pytest.approx(-0.15)
        assert event["balance_after_usd"] == pytest.approx(47.50)

    def test_custom_limit_and_offset(self, client: TestClient) -> None:
        """supabase_fetch is called with the requested limit and offset."""
        captured_path: list[str] = []

        async def _capture_fetch(path: str):
            captured_path.append(path)
            return []

        with (
            patch("routes.billing.supabase_fetch", side_effect=_capture_fetch),
            patch("routes.billing.supabase_count", new_callable=AsyncMock, return_value=0),
        ):
            resp = client.get(
                "/v1/billing/ledger",
                params={"limit": 10, "offset": 20},
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 20
        # Verify the Supabase query included correct limit/offset
        assert "limit=10" in captured_path[0]
        assert "offset=20" in captured_path[0]

    def test_event_type_filter(self, client: TestClient) -> None:
        """Filtering by event_type passes the filter to Supabase."""
        captured_paths: list[str] = []

        async def _capture_fetch(path: str):
            captured_paths.append(path)
            return [_ledger_entry(event_type="credit_added", amount_cents=5000, balance_after=5000)]

        with (
            patch("routes.billing.supabase_fetch", side_effect=_capture_fetch),
            patch("routes.billing.supabase_count", new_callable=AsyncMock, return_value=1),
        ):
            resp = client.get(
                "/v1/billing/ledger",
                params={"event_type": "credit_added"},
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        # Both fetch and count calls should include the event_type filter
        for path in captured_paths:
            assert "event_type=eq.credit_added" in path

    def test_event_type_filter_trims_valid_whitespace(self, client: TestClient) -> None:
        captured_paths: list[str] = []

        async def _capture_fetch(path: str):
            captured_paths.append(path)
            return [_ledger_entry(event_type="credit_added", amount_cents=5000, balance_after=5000)]

        with (
            patch("routes.billing.supabase_fetch", side_effect=_capture_fetch),
            patch("routes.billing.supabase_count", new_callable=AsyncMock, return_value=1),
        ):
            resp = client.get(
                "/v1/billing/ledger",
                params={"event_type": " credit_added "},
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        for path in captured_paths:
            assert "event_type=eq.credit_added" in path
            assert "event_type=eq.%20credit_added%20" not in path

    def test_invalid_event_type_rejected_before_supabase_reads(self, client: TestClient) -> None:
        fetch_mock = AsyncMock()
        count_mock = AsyncMock()

        with (
            patch("routes.billing.supabase_fetch", fetch_mock),
            patch("routes.billing.supabase_count", count_mock),
        ):
            resp = client.get(
                "/v1/billing/ledger",
                params={"event_type": "drop table"},
                headers=_auth_headers(),
            )

        assert resp.status_code == 400
        payload = resp.json()
        assert payload["error"] == "bad_request"
        assert payload["detail"] == (
            "Invalid event_type: use one of auto_reload_triggered, credit_added, debit, "
            "reservation_released, wallet_topup, wallet_topup_added, x402_payment"
        )
        fetch_mock.assert_not_awaited()
        count_mock.assert_not_awaited()

    def test_limit_validation_max(self, client: TestClient) -> None:
        resp = client.get(
            "/v1/billing/ledger",
            params={"limit": 999},
            headers=_auth_headers(),
        )
        assert resp.status_code == 422  # Pydantic validation

    def test_limit_validation_min(self, client: TestClient) -> None:
        resp = client.get(
            "/v1/billing/ledger",
            params={"limit": 0},
            headers=_auth_headers(),
        )
        assert resp.status_code == 422

    def test_empty_ledger(self, client: TestClient) -> None:
        with (
            patch("routes.billing.supabase_fetch", new_callable=AsyncMock, return_value=[]),
            patch("routes.billing.supabase_count", new_callable=AsyncMock, return_value=0),
        ):
            resp = client.get("/v1/billing/ledger", headers=_auth_headers())

        data = resp.json()
        assert data["events"] == []
        assert data["total"] == 0

    def test_401_without_key(self, client: TestClient) -> None:
        resp = client.get("/v1/billing/ledger")
        assert resp.status_code == 401

    def test_supabase_fetch_returns_none(self, client: TestClient) -> None:
        """supabase_fetch returning None (error) should be treated as empty list."""
        with (
            patch("routes.billing.supabase_fetch", new_callable=AsyncMock, return_value=None),
            patch("routes.billing.supabase_count", new_callable=AsyncMock, return_value=0),
        ):
            resp = client.get("/v1/billing/ledger", headers=_auth_headers())

        assert resp.status_code == 200
        assert resp.json()["events"] == []


# ---------------------------------------------------------------------------
# PUT /billing/auto-reload
# ---------------------------------------------------------------------------


class TestAutoReload:
    """Tests for the auto-reload configuration endpoint."""

    def test_enable_auto_reload(self, client: TestClient) -> None:
        returned_row = {
            "auto_reload_enabled": True,
            "auto_reload_threshold_cents": 1000,
            "auto_reload_amount_cents": 2500,
        }
        with patch("routes.billing.supabase_patch", new_callable=AsyncMock, return_value=[returned_row]):
            resp = client.put(
                "/v1/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 10.0, "amount_usd": 25.0},
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["org_id"] == ORG_ID
        assert data["auto_reload_enabled"] is True
        assert data["auto_reload_threshold_usd"] == pytest.approx(10.0)
        assert data["auto_reload_amount_usd"] == pytest.approx(25.0)

    def test_disable_auto_reload(self, client: TestClient) -> None:
        returned_row = {
            "auto_reload_enabled": False,
            "auto_reload_threshold_cents": None,
            "auto_reload_amount_cents": None,
        }
        with patch("routes.billing.supabase_patch", new_callable=AsyncMock, return_value=[returned_row]):
            resp = client.put(
                "/v1/billing/auto-reload",
                json={"enabled": False},
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["auto_reload_enabled"] is False
        assert data["auto_reload_threshold_usd"] is None
        assert data["auto_reload_amount_usd"] is None

    def test_validation_threshold_must_be_positive(self, client: TestClient) -> None:
        resp = client.put(
            "/v1/billing/auto-reload",
            json={"enabled": True, "threshold_usd": 0, "amount_usd": 10.0},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        assert "threshold_usd" in resp.json()["detail"]

    def test_validation_threshold_required_when_enabled(self, client: TestClient) -> None:
        resp = client.put(
            "/v1/billing/auto-reload",
            json={"enabled": True, "amount_usd": 10.0},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400

    def test_validation_amount_minimum(self, client: TestClient) -> None:
        resp = client.put(
            "/v1/billing/auto-reload",
            json={"enabled": True, "threshold_usd": 5.0, "amount_usd": 4.99},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        assert "amount_usd" in resp.json()["detail"]

    def test_validation_amount_required_when_enabled(self, client: TestClient) -> None:
        resp = client.put(
            "/v1/billing/auto-reload",
            json={"enabled": True, "threshold_usd": 5.0},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400

    def test_404_when_org_not_found(self, client: TestClient) -> None:
        with patch("routes.billing.supabase_patch", new_callable=AsyncMock, return_value=None):
            resp = client.put(
                "/v1/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 5.0, "amount_usd": 10.0},
                headers=_auth_headers(),
            )

        assert resp.status_code == 404

    def test_404_when_empty_list_returned(self, client: TestClient) -> None:
        with patch("routes.billing.supabase_patch", new_callable=AsyncMock, return_value=[]):
            resp = client.put(
                "/v1/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 5.0, "amount_usd": 10.0},
                headers=_auth_headers(),
            )

        assert resp.status_code == 404

    def test_patch_payload_converts_usd_to_cents(self, client: TestClient) -> None:
        """Verify the PATCH payload correctly converts dollars → cents."""
        captured_payloads: list[dict] = []

        async def _capture_patch(path: str, payload: dict):
            captured_payloads.append(payload)
            return [{"auto_reload_enabled": True, "auto_reload_threshold_cents": 750, "auto_reload_amount_cents": 5000}]

        with patch("routes.billing.supabase_patch", side_effect=_capture_patch):
            resp = client.put(
                "/v1/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 7.50, "amount_usd": 50.0},
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        assert captured_payloads[0]["auto_reload_threshold_cents"] == 750
        assert captured_payloads[0]["auto_reload_amount_cents"] == 5000
        assert captured_payloads[0]["auto_reload_enabled"] is True

    def test_401_without_key(self, client: TestClient) -> None:
        resp = client.put(
            "/v1/billing/auto-reload",
            json={"enabled": True, "threshold_usd": 5.0, "amount_usd": 10.0},
        )
        assert resp.status_code == 401
