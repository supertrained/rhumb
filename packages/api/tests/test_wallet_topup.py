"""Tests for wallet x402 top-up flow (DF-18 / WU-W4).

Covers:
- Top-up request: minimum enforcement, payment request creation
- Top-up verify: settlement, receipt recording, balance crediting, anti-fraud
- Balance endpoint: current balance and top-up history
- Error paths: below minimum, wallet mismatch, settlement failure
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app as _shared_app
from middleware.rate_limit import _buckets as _rate_limit_buckets
from routes.auth_wallet import _issue_wallet_jwt
from services.wallet_auth import reset_challenge_throttle


# ── Helpers ──────────────────────────────────────────────────────────

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _reset_all_rate_limits():
    reset_challenge_throttle()
    _rate_limit_buckets.clear()


TEST_WALLET_ADDRESS = "0xabcdef1234567890abcdef1234567890abcdef12"
TEST_ORG_ID = "org_topup_test"
TEST_WALLET_IDENTITY_ID = "wi_topup_test_001"
TEST_AGENT_ID = "agent_topup_test"
TEST_PAYMENT_REQUEST_ID = "pr_topup_001"
TEST_RECEIPT_ID = "rc_topup_001"
TEST_TX_HASH = "0x" + "ab" * 32


def _make_wallet_token(**overrides) -> str:
    """Issue a test wallet session token."""
    claims = {
        "wallet_identity_id": TEST_WALLET_IDENTITY_ID,
        "wallet_address": TEST_WALLET_ADDRESS,
        "chain": "base",
        "org_id": TEST_ORG_ID,
        "agent_id": TEST_AGENT_ID,
        "purpose": "wallet_access",
    }
    claims.update(overrides)
    return _issue_wallet_jwt(claims)


# ── Top-up Request Tests ─────────────────────────────────────────────


class TestTopupRequest:
    """Test POST /v1/auth/wallet/topup/request."""

    def setup_method(self):
        _reset_all_rate_limits()

    @patch("routes.wallet_topup.supabase_insert_returning", new_callable=AsyncMock)
    @patch("routes.wallet_topup._payment_requests")
    def test_creates_payment_request_and_topup(self, mock_pr_service, mock_insert):
        """Valid request creates payment_request + wallet_balance_topups row."""
        mock_pr_service.create_payment_request = AsyncMock(return_value={
            "id": TEST_PAYMENT_REQUEST_ID,
            "org_id": TEST_ORG_ID,
            "amount_usd_cents": 50,
            "amount_usdc_atomic": "500000",
            "network": "base",
            "pay_to_address": "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623",
            "asset_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "purpose": "prefund",
        })
        mock_insert.return_value = {
            "id": "topup_001",
            "wallet_identity_id": TEST_WALLET_IDENTITY_ID,
            "status": "pending",
        }

        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/request",
            json={"amount_usd_cents": 50},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["payment_request_id"] == TEST_PAYMENT_REQUEST_ID
        assert data["amount_usd_cents"] == 50
        assert data["amount_usd"] == 0.50
        assert "x402" in data
        # x402 body should include at least one payment option
        assert len(data["x402"]["accepts"]) >= 1
        schemes = [a["scheme"] for a in data["x402"]["accepts"]]
        assert "stripe_checkout" in schemes  # always present

        # Verify payment request was created with purpose=prefund
        call_kwargs = mock_pr_service.create_payment_request.call_args
        assert call_kwargs.kwargs.get("purpose") == "prefund"
        assert call_kwargs.kwargs.get("capability_id") is None

    @patch("routes.wallet_topup.supabase_insert_returning", new_callable=AsyncMock)
    @patch("routes.wallet_topup._payment_requests")
    def test_minimum_topup_enforced(self, mock_pr, mock_insert):
        """Amounts below $0.25 should be rejected."""
        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/request",
            json={"amount_usd_cents": 10},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 400
        assert "$0.25" in resp.json()["detail"]

    @patch("routes.wallet_topup.supabase_insert_returning", new_callable=AsyncMock)
    @patch("routes.wallet_topup._payment_requests")
    def test_maximum_topup_enforced(self, mock_pr, mock_insert):
        """Amounts above $100 should be rejected."""
        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/request",
            json={"amount_usd_cents": 15000},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 400
        assert "Maximum" in resp.json()["detail"]

    def test_unauthenticated_rejected(self):
        """No wallet session should get 401."""
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/request",
            json={"amount_usd_cents": 25},
        )
        assert resp.status_code == 401

    @patch("routes.wallet_topup.supabase_insert_returning", new_callable=AsyncMock)
    @patch("routes.wallet_topup._payment_requests")
    def test_exact_minimum_accepted(self, mock_pr_service, mock_insert):
        """Exactly $0.25 should be accepted."""
        mock_pr_service.create_payment_request = AsyncMock(return_value={
            "id": TEST_PAYMENT_REQUEST_ID,
            "org_id": TEST_ORG_ID,
            "amount_usd_cents": 25,
            "amount_usdc_atomic": "250000",
            "network": "base",
            "pay_to_address": "0xEA63...",
            "asset_address": "0x8335...",
            "purpose": "prefund",
        })
        mock_insert.return_value = {"id": "topup_min", "status": "pending"}

        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/request",
            json={"amount_usd_cents": 25},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["amount_usd_cents"] == 25


# ── Top-up Verify Tests ──────────────────────────────────────────────


class TestTopupVerify:
    """Test POST /v1/auth/wallet/topup/verify."""

    def setup_method(self):
        _reset_all_rate_limits()

    @patch("routes.wallet_topup.supabase_insert", new_callable=AsyncMock)
    @patch("routes.wallet_topup.supabase_patch", new_callable=AsyncMock)
    @patch("routes.wallet_topup.supabase_insert_returning", new_callable=AsyncMock)
    @patch("routes.wallet_topup.supabase_fetch")
    @patch("routes.wallet_topup._settlement")
    @patch("routes.wallet_topup._payment_requests")
    def test_successful_topup_credits_balance(
        self, mock_pr, mock_settlement, mock_fetch, mock_insert_ret, mock_patch, mock_insert
    ):
        """Successful settlement should credit org balance and write ledger."""
        # Setup payment request lookup
        mock_pr.get_pending_request = AsyncMock(return_value={
            "id": TEST_PAYMENT_REQUEST_ID,
            "org_id": TEST_ORG_ID,
            "amount_usd_cents": 50,
            "amount_usdc_atomic": "500000",
            "network": "base",
            "pay_to_address": "0xEA63...",
            "asset_address": "0x8335...",
            "purpose": "prefund",
        })
        mock_pr.mark_verified = AsyncMock(return_value=True)

        # Settlement succeeds
        mock_settlement.verify_and_settle = AsyncMock(return_value={
            "verify": {"isValid": True, "payer": TEST_WALLET_ADDRESS},
            "settle": {"success": True, "transaction": TEST_TX_HASH},
            "payer": TEST_WALLET_ADDRESS,
            "transaction": TEST_TX_HASH,
            "network": "base",
        })

        # Receipt insert
        mock_insert_ret.return_value = {"id": TEST_RECEIPT_ID}

        # org_credits fetch for crediting
        _fetch_count = {"n": 0}
        async def _mock_fetch(path: str):
            idx = _fetch_count["n"]
            _fetch_count["n"] += 1
            if "org_credits" in path:
                return [{"balance_usd_cents": 100}]  # existing $1.00 balance
            return []

        mock_fetch.side_effect = _mock_fetch
        mock_patch.return_value = [{}]
        mock_insert.return_value = True

        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/verify",
            json={
                "payment_request_id": TEST_PAYMENT_REQUEST_ID,
                "x_payment": {
                    "payload": {
                        "authorization": {
                            "from": TEST_WALLET_ADDRESS,
                            "to": "0xEA63...",
                            "value": "500000",
                        },
                        "signature": "0x" + "ab" * 65,
                    },
                },
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "credited"
        assert data["amount_usd_cents"] == 50
        assert data["balance_usd_cents"] == 150  # 100 + 50
        assert data["transaction"] == TEST_TX_HASH

    @patch("routes.wallet_topup._payment_requests")
    def test_wallet_mismatch_rejected(self, mock_pr):
        """Payment from a different wallet should be rejected."""
        mock_pr.get_pending_request = AsyncMock(return_value={
            "id": TEST_PAYMENT_REQUEST_ID,
            "org_id": TEST_ORG_ID,
            "amount_usd_cents": 25,
            "amount_usdc_atomic": "250000",
            "purpose": "prefund",
        })

        different_wallet = "0x1111111111111111111111111111111111111111"
        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/verify",
            json={
                "payment_request_id": TEST_PAYMENT_REQUEST_ID,
                "x_payment": {
                    "payload": {
                        "authorization": {
                            "from": different_wallet,
                            "to": "0xEA63...",
                            "value": "250000",
                        },
                        "signature": "0x" + "ab" * 65,
                    },
                },
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403
        assert "does not match" in resp.json()["detail"]

    @patch("routes.wallet_topup._payment_requests")
    def test_wrong_org_rejected(self, mock_pr):
        """Payment request for a different org should be rejected."""
        mock_pr.get_pending_request = AsyncMock(return_value={
            "id": TEST_PAYMENT_REQUEST_ID,
            "org_id": "org_different",
            "amount_usd_cents": 25,
            "purpose": "prefund",
        })

        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/verify",
            json={
                "payment_request_id": TEST_PAYMENT_REQUEST_ID,
                "x_payment": {
                    "payload": {
                        "authorization": {"from": TEST_WALLET_ADDRESS},
                        "signature": "0xabc",
                    },
                },
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403
        assert "does not belong" in resp.json()["detail"]

    @patch("routes.wallet_topup._payment_requests")
    def test_non_prefund_request_rejected(self, mock_pr):
        """Payment request with purpose != 'prefund' should be rejected."""
        mock_pr.get_pending_request = AsyncMock(return_value={
            "id": TEST_PAYMENT_REQUEST_ID,
            "org_id": TEST_ORG_ID,
            "amount_usd_cents": 25,
            "purpose": "execution",  # wrong purpose
        })

        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/verify",
            json={
                "payment_request_id": TEST_PAYMENT_REQUEST_ID,
                "x_payment": {
                    "payload": {
                        "authorization": {"from": TEST_WALLET_ADDRESS},
                        "signature": "0xabc",
                    },
                },
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 400
        assert "not a prefund" in resp.json()["detail"]

    @patch("routes.wallet_topup.supabase_patch", new_callable=AsyncMock)
    @patch("routes.wallet_topup._settlement")
    @patch("routes.wallet_topup._payment_requests")
    def test_settlement_failure_marks_topup_failed(
        self, mock_pr, mock_settlement, mock_patch
    ):
        """Failed settlement should mark topup as failed and return error."""
        mock_pr.get_pending_request = AsyncMock(return_value={
            "id": TEST_PAYMENT_REQUEST_ID,
            "org_id": TEST_ORG_ID,
            "amount_usd_cents": 25,
            "amount_usdc_atomic": "250000",
            "purpose": "prefund",
            "network": "base",
            "asset_address": "0x8335...",
            "pay_to_address": "0xEA63...",
        })

        from services.x402_settlement import X402SettlementFailed
        mock_settlement.verify_and_settle = AsyncMock(
            side_effect=X402SettlementFailed("tx reverted")
        )

        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/verify",
            json={
                "payment_request_id": TEST_PAYMENT_REQUEST_ID,
                "x_payment": {
                    "payload": {
                        "authorization": {"from": TEST_WALLET_ADDRESS},
                        "signature": "0xabc",
                    },
                },
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 502
        assert "Settlement failed" in resp.json()["detail"]

        # Verify topup was marked as failed
        mock_patch.assert_called()

    @patch("routes.wallet_topup._payment_requests")
    def test_missing_payment_request_rejected(self, mock_pr):
        """Nonexistent payment request ID should return 400."""
        mock_pr.get_pending_request = AsyncMock(return_value=None)

        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/verify",
            json={
                "payment_request_id": "nonexistent",
                "x_payment": {"payload": {"authorization": {}, "signature": "0x"}},
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    def test_unauthenticated_rejected(self):
        """No wallet session should get 401."""
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/verify",
            json={"payment_request_id": "x", "x_payment": {}},
        )
        assert resp.status_code == 401

    def test_missing_fields_rejected(self):
        """Missing required fields should return 400."""
        token = _make_wallet_token()
        client = TestClient(_shared_app)

        resp = client.post(
            "/v1/auth/wallet/topup/verify",
            json={"x_payment": {"payload": {}}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400


# ── Balance Endpoint Tests ───────────────────────────────────────────


class TestWalletBalance:
    """Test GET /v1/auth/wallet/balance."""

    def setup_method(self):
        _reset_all_rate_limits()

    @patch("routes.wallet_topup.supabase_fetch")
    def test_returns_balance_and_history(self, mock_fetch):
        """Should return current balance and recent top-up history."""
        _fetch_count = {"n": 0}
        async def _mock_fetch(path: str):
            idx = _fetch_count["n"]
            _fetch_count["n"] += 1
            if idx == 0:
                # org_credits
                return [{"balance_usd_cents": 275}]
            elif idx == 1:
                # wallet_balance_topups
                return [
                    {
                        "id": "topup_1",
                        "amount_usd_cents": 100,
                        "status": "credited",
                        "credited_at": "2026-03-27T14:00:00+00:00",
                        "created_at": "2026-03-27T13:59:00+00:00",
                    },
                    {
                        "id": "topup_2",
                        "amount_usd_cents": 200,
                        "status": "credited",
                        "credited_at": "2026-03-27T15:00:00+00:00",
                        "created_at": "2026-03-27T14:59:00+00:00",
                    },
                    {
                        "id": "topup_3",
                        "amount_usd_cents": 25,
                        "status": "pending",
                        "credited_at": None,
                        "created_at": "2026-03-27T16:00:00+00:00",
                    },
                ]
            return []

        mock_fetch.side_effect = _mock_fetch

        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.get(
            "/v1/auth/wallet/balance",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["balance_usd_cents"] == 275
        assert data["balance_usd"] == 2.75
        assert data["total_topped_up_usd_cents"] == 300  # 100 + 200 (not pending 25)
        assert len(data["recent_topups"]) == 3

    @patch("routes.wallet_topup.supabase_fetch")
    def test_zero_balance(self, mock_fetch):
        """New wallet with no top-ups should show zero balance."""
        _fetch_count = {"n": 0}
        async def _mock_fetch(path: str):
            idx = _fetch_count["n"]
            _fetch_count["n"] += 1
            if idx == 0:
                return [{"balance_usd_cents": 0}]
            return []

        mock_fetch.side_effect = _mock_fetch

        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.get(
            "/v1/auth/wallet/balance",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["balance_usd_cents"] == 0
        assert data["total_topped_up_usd_cents"] == 0

    def test_unauthenticated_rejected(self):
        """No wallet session should get 401."""
        client = TestClient(_shared_app)
        resp = client.get("/v1/auth/wallet/balance")
        assert resp.status_code == 401


# ── Credit Ledger Event Shape Tests ──────────────────────────────────


class TestCreditLedgerEvent:
    """Verify the shape of credit_ledger entries written during top-up."""

    @patch("routes.wallet_topup.supabase_insert", new_callable=AsyncMock)
    @patch("routes.wallet_topup.supabase_fetch")
    @patch("routes.wallet_topup.supabase_patch", new_callable=AsyncMock)
    def test_ledger_event_shape(self, mock_patch, mock_fetch, mock_insert):
        """Credit ledger event should have the correct event_type and metadata."""
        from routes.wallet_topup import _credit_org_balance

        async def _mock_fetch(path: str):
            return [{"balance_usd_cents": 100}]

        mock_fetch.side_effect = _mock_fetch
        mock_patch.return_value = [{}]
        mock_insert.return_value = True

        new_balance = _run(_credit_org_balance(
            org_id=TEST_ORG_ID,
            amount_cents=50,
            wallet_identity_id=TEST_WALLET_IDENTITY_ID,
            wallet_address=TEST_WALLET_ADDRESS,
            payment_request_id=TEST_PAYMENT_REQUEST_ID,
            receipt_id=TEST_RECEIPT_ID,
            tx_hash=TEST_TX_HASH,
            network="base",
        ))

        assert new_balance == 150

        # Find the credit_ledger insert call
        ledger_call = None
        for call in mock_insert.call_args_list:
            if call.args[0] == "credit_ledger":
                ledger_call = call
                break

        assert ledger_call is not None
        ledger_payload = ledger_call.args[1]
        assert ledger_payload["event_type"] == "wallet_topup_added"
        assert ledger_payload["amount_usd_cents"] == 50
        assert ledger_payload["balance_after_usd_cents"] == 150
        assert ledger_payload["metadata"]["source"] == "wallet_x402_topup"
        assert ledger_payload["metadata"]["wallet_identity_id"] == TEST_WALLET_IDENTITY_ID
        assert ledger_payload["metadata"]["topup_type"] == "prefund"
        assert ledger_payload["metadata"]["tx_hash"] == TEST_TX_HASH


# ── Idempotency Tests ────────────────────────────────────────────────


class TestTopupIdempotency:
    """Verify idempotency boundaries."""

    def setup_method(self):
        _reset_all_rate_limits()

    @patch("routes.wallet_topup._payment_requests")
    def test_already_processed_request_rejected(self, mock_pr):
        """An already-verified payment request should be rejected on retry."""
        mock_pr.get_pending_request = AsyncMock(return_value=None)

        token = _make_wallet_token()
        client = TestClient(_shared_app)
        resp = client.post(
            "/v1/auth/wallet/topup/verify",
            json={
                "payment_request_id": "already-processed",
                "x_payment": {"payload": {"authorization": {}, "signature": "0x"}},
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 400
        assert "not found or already processed" in resp.json()["detail"]
