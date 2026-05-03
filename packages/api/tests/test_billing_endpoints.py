"""Tests for self-service billing endpoints (WU-0.5).

Covers: GET /billing/balance, GET /billing/ledger, PUT /billing/auto-reload.
All Supabase calls are mocked — no real DB required.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import create_app
from routes.billing import _require_org


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
# Shared billing auth helper
# ---------------------------------------------------------------------------


def test_require_org_rejects_blank_key_before_identity_store() -> None:
    identity_store_factory = Mock()

    with patch("routes.billing._get_identity_store", identity_store_factory):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(_require_org("   "))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing X-Rhumb-Key header"
    identity_store_factory.assert_not_called()


def test_require_org_trims_valid_key_before_identity_lookup() -> None:
    identity_store = SimpleNamespace(
        verify_api_key_with_agent=AsyncMock(return_value=SimpleNamespace(organization_id="org_trimmed"))
    )

    with patch("routes.billing._get_identity_store", return_value=identity_store):
        org_id = asyncio.run(_require_org("  rk_test  "))

    assert org_id == "org_trimmed"
    identity_store.verify_api_key_with_agent.assert_awaited_once_with("rk_test")


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
# POST /billing/checkout
# ---------------------------------------------------------------------------


class TestCheckout:
    """Tests for checkout validation before governed-key auth."""

    @pytest.mark.parametrize(
        ("payload", "detail"),
        [
            (["not", "an", "object"], "JSON body must be an object"),
            ({}, "amount_usd must be a number"),
            ({"amount_usd": True}, "amount_usd must be a number"),
            ({"amount_usd": "NaN"}, "amount_usd must be a number"),
            ({"amount_usd": 25.0, "success_url": ["bad"]}, "success_url must be a string"),
            ({"amount_usd": 25.0, "cancel_url": {"bad": True}}, "cancel_url must be a string"),
        ],
    )
    def test_malformed_payloads_rejected_before_auth(
        self,
        client: TestClient,
        payload: object,
        detail: str,
    ) -> None:
        require_org_mock = AsyncMock()
        checkout_mock = AsyncMock()

        with (
            patch("routes.billing._require_org", require_org_mock),
            patch("routes.billing.create_checkout_session", checkout_mock),
        ):
            resp = client.post(
                "/v1/billing/checkout",
                json=payload,
                headers=_auth_headers(),
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == detail
        require_org_mock.assert_not_awaited()
        checkout_mock.assert_not_awaited()

    @pytest.mark.parametrize("amount", [4.99, 5000.01])
    def test_invalid_amount_rejected_before_auth(self, client: TestClient, amount: float) -> None:
        require_org_mock = AsyncMock()
        checkout_mock = AsyncMock()

        with (
            patch("routes.billing._require_org", require_org_mock),
            patch("routes.billing.create_checkout_session", checkout_mock),
        ):
            resp = client.post(
                "/v1/billing/checkout",
                json={"amount_usd": amount},
                headers=_auth_headers(),
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "amount_usd must be between 5 and 5000"
        require_org_mock.assert_not_awaited()
        checkout_mock.assert_not_awaited()


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

    def test_event_type_filter_trims_and_canonicalizes_valid_whitespace(self, client: TestClient) -> None:
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
                params={"event_type": " Credit_Added "},
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        for path in captured_paths:
            assert "event_type=eq.credit_added" in path
            assert "event_type=eq.Credit_Added" not in path
            assert "event_type=eq.%20Credit_Added%20" not in path

    def test_invalid_event_type_rejected_before_auth_or_supabase_reads(self, client: TestClient) -> None:
        fetch_mock = AsyncMock()
        count_mock = AsyncMock()
        require_org_mock = AsyncMock()

        with (
            patch("routes.billing.supabase_fetch", fetch_mock),
            patch("routes.billing.supabase_count", count_mock),
            patch("routes.billing._require_org", require_org_mock),
        ):
            resp = client.get(
                "/v1/billing/ledger",
                params={"event_type": "drop table"},
                headers=_auth_headers(),
            )

        assert resp.status_code == 400
        payload = resp.json()
        assert payload["error"]["code"] == "INVALID_PARAMETERS"
        assert payload["error"]["message"] == "Invalid 'event_type' filter."
        assert payload["error"]["detail"] == (
            "Use one of: auto_reload_triggered, credit_added, debit, "
            "reservation_released, wallet_topup, wallet_topup_added, x402_payment."
        )
        require_org_mock.assert_not_awaited()
        fetch_mock.assert_not_awaited()
        count_mock.assert_not_awaited()

    def test_blank_event_type_rejected_before_auth_or_supabase_reads(self, client: TestClient) -> None:
        fetch_mock = AsyncMock()
        count_mock = AsyncMock()
        require_org_mock = AsyncMock()

        with (
            patch("routes.billing.supabase_fetch", fetch_mock),
            patch("routes.billing.supabase_count", count_mock),
            patch("routes.billing._require_org", require_org_mock),
        ):
            resp = client.get(
                "/v1/billing/ledger",
                params={"event_type": "   "},
                headers=_auth_headers(),
            )

        assert resp.status_code == 400
        payload = resp.json()
        assert payload["error"]["code"] == "INVALID_PARAMETERS"
        assert payload["error"]["message"] == "Invalid 'event_type' filter."
        assert payload["error"]["detail"] == "Provide a non-empty event_type or omit the filter."
        require_org_mock.assert_not_awaited()
        fetch_mock.assert_not_awaited()
        count_mock.assert_not_awaited()

    @pytest.mark.parametrize(
        ("params", "field", "detail"),
        [
            ({"limit": 999}, "limit", "Provide an integer between 1 and 200."),
            ({"limit": 0}, "limit", "Provide an integer between 1 and 200."),
            ({"limit": "ten"}, "limit", "Provide an integer between 1 and 200."),
            ({"limit": "true"}, "limit", "Provide an integer between 1 and 200."),
            ({"limit": "   "}, "limit", "Provide an integer between 1 and 200."),
            ({"offset": -1}, "offset", "Provide an integer greater than or equal to 0."),
            ({"offset": "false"}, "offset", "Provide an integer greater than or equal to 0."),
            ({"offset": "   "}, "offset", "Provide an integer greater than or equal to 0."),
        ],
    )
    def test_invalid_pagination_rejected_before_auth_or_supabase_reads(
        self,
        client: TestClient,
        params: dict[str, object],
        field: str,
        detail: str,
    ) -> None:
        fetch_mock = AsyncMock()
        count_mock = AsyncMock()
        require_org_mock = AsyncMock()

        with (
            patch("routes.billing.supabase_fetch", fetch_mock),
            patch("routes.billing.supabase_count", count_mock),
            patch("routes.billing._require_org", require_org_mock),
        ):
            resp = client.get(
                "/v1/billing/ledger",
                params=params,
                headers=_auth_headers(),
            )

        assert resp.status_code == 400
        payload = resp.json()
        assert payload["error"]["code"] == "INVALID_PARAMETERS"
        assert payload["error"]["message"] == f"Invalid '{field}' filter."
        assert payload["error"]["detail"] == detail
        require_org_mock.assert_not_awaited()
        fetch_mock.assert_not_awaited()
        count_mock.assert_not_awaited()

    def test_padded_pagination_values_are_normalized(self, client: TestClient) -> None:
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
                params={"limit": " 10 ", "offset": " 20 "},
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 20
        assert "limit=10" in captured_path[0]
        assert "offset=20" in captured_path[0]

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

    @pytest.mark.parametrize(
        ("payload", "detail"),
        [
            (["not", "an", "object"], "JSON body must be an object"),
            ({}, "enabled must be a boolean"),
            ({"enabled": "maybe"}, "enabled must be a boolean"),
            ({"enabled": True, "threshold_usd": True, "amount_usd": 10.0}, "threshold_usd must be a number"),
            ({"enabled": True, "threshold_usd": 5.0, "amount_usd": "NaN"}, "amount_usd must be a number"),
        ],
    )
    def test_malformed_payloads_rejected_before_auth(
        self,
        client: TestClient,
        payload: object,
        detail: str,
    ) -> None:
        require_org_mock = AsyncMock()
        fetch_mock = AsyncMock()
        patch_mock = AsyncMock()

        with (
            patch("routes.billing._require_org", require_org_mock),
            patch("routes.billing.supabase_fetch", fetch_mock),
            patch("routes.billing.supabase_patch", patch_mock),
        ):
            resp = client.put(
                "/v1/billing/auto-reload",
                json=payload,
                headers=_auth_headers(),
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == detail
        require_org_mock.assert_not_awaited()
        fetch_mock.assert_not_awaited()
        patch_mock.assert_not_awaited()

    def test_enable_auto_reload(self, client: TestClient) -> None:
        returned_row = {
            "auto_reload_enabled": True,
            "auto_reload_threshold_cents": 1000,
            "auto_reload_amount_cents": 2500,
        }
        with (
            patch(
                "routes.billing.supabase_fetch",
                new_callable=AsyncMock,
                return_value=[{"stripe_payment_method_id": "pm_saved"}],
            ),
            patch("routes.billing.supabase_patch", new_callable=AsyncMock, return_value=[returned_row]),
        ):
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

    @pytest.mark.parametrize(
        ("payload", "detail_fragment"),
        [
            ({"enabled": True, "threshold_usd": 0, "amount_usd": 10.0}, "threshold_usd"),
            ({"enabled": True, "amount_usd": 10.0}, "threshold_usd"),
            ({"enabled": True, "threshold_usd": 5.0, "amount_usd": 4.99}, "amount_usd"),
            ({"enabled": True, "threshold_usd": 5.0}, "amount_usd"),
        ],
    )
    def test_invalid_enabled_config_rejected_before_auth(
        self,
        client: TestClient,
        payload: dict[str, float | bool],
        detail_fragment: str,
    ) -> None:
        require_org_mock = AsyncMock()
        fetch_mock = AsyncMock()
        patch_mock = AsyncMock()

        with (
            patch("routes.billing._require_org", require_org_mock),
            patch("routes.billing.supabase_fetch", fetch_mock),
            patch("routes.billing.supabase_patch", patch_mock),
        ):
            resp = client.put(
                "/v1/billing/auto-reload",
                json=payload,
                headers=_auth_headers(),
            )

        assert resp.status_code == 400
        assert detail_fragment in resp.json()["detail"]
        require_org_mock.assert_not_awaited()
        fetch_mock.assert_not_awaited()
        patch_mock.assert_not_awaited()

    def test_enable_requires_saved_payment_method_before_patch(self, client: TestClient) -> None:
        patch_mock = AsyncMock()
        with (
            patch(
                "routes.billing.supabase_fetch",
                new_callable=AsyncMock,
                return_value=[{"stripe_payment_method_id": None}],
            ),
            patch("routes.billing.supabase_patch", patch_mock),
        ):
            resp = client.put(
                "/v1/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 5.0, "amount_usd": 10.0},
                headers=_auth_headers(),
            )

        assert resp.status_code == 400
        payload = resp.json()
        assert payload["error"]["code"] == "INVALID_PARAMETERS"
        assert payload["error"]["message"] == "Auto-reload requires a saved payment method."
        assert payload["error"]["detail"] == "Add funds once to save a card before enabling auto-reload."
        patch_mock.assert_not_awaited()

    def test_404_when_org_not_found_before_patch(self, client: TestClient) -> None:
        patch_mock = AsyncMock()
        with (
            patch("routes.billing.supabase_fetch", new_callable=AsyncMock, return_value=[]),
            patch("routes.billing.supabase_patch", patch_mock),
        ):
            resp = client.put(
                "/v1/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 5.0, "amount_usd": 10.0},
                headers=_auth_headers(),
            )

        assert resp.status_code == 404
        patch_mock.assert_not_awaited()

    def test_404_when_patch_returns_no_rows(self, client: TestClient) -> None:
        with (
            patch(
                "routes.billing.supabase_fetch",
                new_callable=AsyncMock,
                return_value=[{"stripe_payment_method_id": "pm_saved"}],
            ),
            patch("routes.billing.supabase_patch", new_callable=AsyncMock, return_value=None),
        ):
            resp = client.put(
                "/v1/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 5.0, "amount_usd": 10.0},
                headers=_auth_headers(),
            )

        assert resp.status_code == 404

    def test_404_when_empty_patch_list_returned(self, client: TestClient) -> None:
        with (
            patch(
                "routes.billing.supabase_fetch",
                new_callable=AsyncMock,
                return_value=[{"stripe_payment_method_id": "pm_saved"}],
            ),
            patch("routes.billing.supabase_patch", new_callable=AsyncMock, return_value=[]),
        ):
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

        with (
            patch(
                "routes.billing.supabase_fetch",
                new_callable=AsyncMock,
                return_value=[{"stripe_payment_method_id": "pm_saved"}],
            ),
            patch("routes.billing.supabase_patch", side_effect=_capture_patch),
        ):
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


# ---------------------------------------------------------------------------
# POST /billing/x402/topup/request
# ---------------------------------------------------------------------------


class TestLegacyWalletTopupRequest:
    """Tests for legacy billing x402 top-up request validation before wallet-session reads."""

    @pytest.mark.parametrize(
        ("payload", "detail"),
        [
            (["not", "an", "object"], "JSON body must be an object"),
            ({}, "amount_usd_cents must be between 25 and 500000"),
            ({"amount_usd_cents": True}, "amount_usd_cents must be between 25 and 500000"),
            ({"amount_usd_cents": 25.0}, "amount_usd_cents must be between 25 and 500000"),
            ({"amount_usd_cents": [25]}, "amount_usd_cents must be between 25 and 500000"),
            ({"amount_usd_cents": "24"}, "amount_usd_cents must be between 25 and 500000"),
            ({"amount_usd_cents": "500001"}, "amount_usd_cents must be between 25 and 500000"),
            ({"amount_usd_cents": "25.5"}, "amount_usd_cents must be between 25 and 500000"),
        ],
    )
    def test_rejects_invalid_request_payload_before_wallet_session(
        self,
        client: TestClient,
        payload: object,
        detail: str,
    ) -> None:
        require_session = AsyncMock()
        create_payment_request = AsyncMock()

        with (
            patch("routes.billing._require_wallet_session", require_session),
            patch("routes.billing._payment_requests.create_payment_request", create_payment_request),
        ):
            resp = client.post(
                "/v1/billing/x402/topup/request",
                json=payload,
                headers={"Authorization": "Bearer wallet-session"},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == detail
        require_session.assert_not_awaited()
        create_payment_request.assert_not_awaited()

    def test_normalizes_amount_string_before_payment_request(self, client: TestClient) -> None:
        require_session = AsyncMock(
            return_value={
                "wallet_identity_id": "wi_test",
                "org_id": "org-test",
                "wallet_address": "0xabc",
                "chain": "base",
            }
        )
        create_payment_request = AsyncMock(
            return_value={
                "id": "pr_test",
                "amount_usdc_atomic": "1000000",
                "network": "base",
                "asset_address": "0xasset",
                "pay_to_address": "0xpay",
                "expires_at": "2026-05-01T20:00:00Z",
            }
        )
        insert_topup = AsyncMock(return_value={"id": "topup_test", "status": "pending"})

        with (
            patch("routes.billing._require_wallet_session", require_session),
            patch("routes.billing._payment_requests.create_payment_request", create_payment_request),
            patch("routes.billing.supabase_insert_returning", insert_topup),
        ):
            resp = client.post(
                "/v1/billing/x402/topup/request",
                json={"amount_usd_cents": " 100 "},
                headers={"Authorization": "Bearer wallet-session"},
            )

        assert resp.status_code == 200
        create_payment_request.assert_awaited_once_with(
            org_id="org-test",
            capability_id=None,
            amount_usd_cents=100,
            purpose="prefund",
        )
        insert_topup.assert_awaited_once()
        assert insert_topup.await_args.args[1]["amount_usd_cents"] == 100
        assert resp.json()["data"]["amount_usd_cents"] == 100


# POST /billing/x402/topup/verify
# ---------------------------------------------------------------------------


class TestLegacyWalletTopupVerify:
    """Tests for legacy billing x402 top-up validation before wallet-session reads."""

    @pytest.mark.parametrize(
        ("payload", "detail"),
        [
            (["not", "an", "object"], "JSON body must be an object"),
            ({"payment_request_id": 123, "x_payment": "encoded-proof"}, "payment_request_id is required"),
            ({"payment_request_id": "   ", "x_payment": "encoded-proof"}, "payment_request_id is required"),
            ({"payment_request_id": "pr_test", "x_payment": {"payload": "encoded-proof"}}, "x_payment is required"),
            ({"payment_request_id": "pr_test", "x_payment": "   "}, "x_payment is required"),
        ],
    )
    def test_rejects_blank_verify_fields_before_wallet_session(
        self,
        client: TestClient,
        payload: dict[str, str],
        detail: str,
    ) -> None:
        require_session = AsyncMock()
        load_topup = AsyncMock()

        with (
            patch("routes.billing._require_wallet_session", require_session),
            patch("routes.billing._load_wallet_topup", load_topup),
        ):
            resp = client.post(
                "/v1/billing/x402/topup/verify",
                json=payload,
                headers={"Authorization": "Bearer wallet-session"},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == detail
        require_session.assert_not_awaited()
        load_topup.assert_not_awaited()

    def test_trims_payment_request_id_before_topup_lookup(self, client: TestClient) -> None:
        require_session = AsyncMock(
            return_value={
                "wallet_identity_id": "wi_test",
                "org_id": "org-test",
                "wallet_address": "0xabc",
            }
        )
        load_topup = AsyncMock(return_value=None)

        with (
            patch("routes.billing._require_wallet_session", require_session),
            patch("routes.billing._load_wallet_topup", load_topup),
        ):
            resp = client.post(
                "/v1/billing/x402/topup/verify",
                json={"payment_request_id": "  pr_test  ", "x_payment": "  encoded-proof  "},
                headers={"Authorization": "Bearer wallet-session"},
            )

        assert resp.status_code == 404
        load_topup.assert_awaited_once_with(
            wallet_identity_id="wi_test",
            payment_request_id="pr_test",
        )
