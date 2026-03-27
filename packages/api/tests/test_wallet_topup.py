"""Tests for wallet-linked x402 top-up routes (DF-18)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import app as _shared_app


TEST_WALLET_ID = "wa11e700-0000-0000-0000-000000000001"
TEST_ORG_ID = "org_wallet_test"
TEST_PAYMENT_REQUEST_ID = "pr_123"
TEST_TOPUP_ID = "topup_123"
TEST_RECEIPT_ID = "receipt_123"
TEST_WALLET_ADDRESS = "0x43ab546b202033e4680aeb0923140bc4105edfed"


def _wallet_claims() -> dict[str, str]:
    return {
        "wallet_identity_id": TEST_WALLET_ID,
        "wallet_address": TEST_WALLET_ADDRESS,
        "chain": "base",
        "org_id": TEST_ORG_ID,
        "agent_id": "agent_wallet_test",
        "purpose": "wallet_access",
    }


@patch("routes.billing.supabase_insert_returning", new_callable=AsyncMock)
@patch("routes.billing._payment_requests.create_payment_request", new_callable=AsyncMock)
@patch("routes.billing._require_wallet_session", new_callable=AsyncMock)
def test_wallet_topup_request_returns_x402_envelope(
    mock_require_wallet: AsyncMock,
    mock_create_payment_request: AsyncMock,
    mock_insert_returning: AsyncMock,
) -> None:
    mock_require_wallet.return_value = _wallet_claims()
    mock_create_payment_request.return_value = {
        "id": TEST_PAYMENT_REQUEST_ID,
        "org_id": TEST_ORG_ID,
        "capability_id": None,
        "purpose": "prefund",
        "amount_usd_cents": 25,
        "amount_usdc_atomic": "250000",
        "network": "base",
        "pay_to_address": "0xRhumbReceive",
        "asset_address": "0xUSDC",
        "status": "pending",
        "expires_at": "2026-03-27T23:30:00Z",
    }
    mock_insert_returning.return_value = {
        "id": TEST_TOPUP_ID,
        "status": "pending",
    }

    client = TestClient(_shared_app)
    resp = client.post(
        "/v1/billing/x402/topup/request",
        headers={"Authorization": "Bearer test-wallet-token"},
        json={"amount_usd_cents": 25},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["topup_id"] == TEST_TOPUP_ID
    assert data["payment_request_id"] == TEST_PAYMENT_REQUEST_ID
    assert data["amount_usd_cents"] == 25
    assert data["x402"]["paymentRequestId"] == TEST_PAYMENT_REQUEST_ID
    assert len(data["x402"]["accepts"]) == 1
    assert data["x402"]["accepts"][0]["scheme"] == "exact"
    assert data["x402"]["accepts"][0]["extra"]["paymentRequestId"] == TEST_PAYMENT_REQUEST_ID

    mock_create_payment_request.assert_awaited_once()
    create_kwargs = mock_create_payment_request.await_args.kwargs
    assert create_kwargs["org_id"] == TEST_ORG_ID
    assert create_kwargs["capability_id"] is None
    assert create_kwargs["amount_usd_cents"] == 25
    assert create_kwargs["purpose"] == "prefund"

    insert_args = mock_insert_returning.await_args.args
    insert_payload = mock_insert_returning.await_args.args[1]
    assert insert_args[0] == "wallet_balance_topups"
    assert insert_payload["wallet_identity_id"] == TEST_WALLET_ID
    assert insert_payload["org_id"] == TEST_ORG_ID
    assert insert_payload["payment_request_id"] == TEST_PAYMENT_REQUEST_ID
    assert insert_payload["status"] == "pending"


@patch("routes.billing.supabase_patch", new_callable=AsyncMock)
@patch("routes.billing.supabase_insert", new_callable=AsyncMock)
@patch("routes.billing.supabase_insert_returning", new_callable=AsyncMock)
@patch("routes.billing.verify_usdc_payment", new_callable=AsyncMock)
@patch("routes.billing.inspect_x_payment_header")
@patch("routes.billing.supabase_fetch")
@patch("routes.billing._payment_requests.mark_verified", new_callable=AsyncMock)
@patch("routes.billing._require_wallet_session", new_callable=AsyncMock)
def test_wallet_topup_verify_credits_balance_from_tx_hash(
    mock_require_wallet: AsyncMock,
    mock_mark_verified: AsyncMock,
    mock_fetch,
    mock_inspect_x_payment_header,
    mock_verify_usdc_payment: AsyncMock,
    mock_insert_returning: AsyncMock,
    mock_insert: AsyncMock,
    mock_patch: AsyncMock,
) -> None:
    mock_require_wallet.return_value = _wallet_claims()
    mock_fetch.side_effect = [
        [{
            "id": TEST_TOPUP_ID,
            "wallet_identity_id": TEST_WALLET_ID,
            "org_id": TEST_ORG_ID,
            "payment_request_id": TEST_PAYMENT_REQUEST_ID,
            "amount_usd_cents": 250,
            "amount_usdc_atomic": "2500000",
            "status": "pending",
        }],
        [{
            "id": TEST_PAYMENT_REQUEST_ID,
            "org_id": TEST_ORG_ID,
            "purpose": "prefund",
            "amount_usd_cents": 250,
            "amount_usdc_atomic": "2500000",
            "network": "base",
            "pay_to_address": "0xRhumbReceive",
            "asset_address": "0xUSDC",
            "status": "pending",
        }],
        [],
        [{"balance_usd_cents": 500}],
    ]
    mock_inspect_x_payment_header.return_value = {
        "proof_format": "legacy_tx_hash",
        "payment_data": {
            "tx_hash": "0xabc123",
            "network": "base",
            "wallet_address": TEST_WALLET_ADDRESS,
        },
    }
    mock_verify_usdc_payment.return_value = {
        "valid": True,
        "from_address": TEST_WALLET_ADDRESS,
        "to_address": "0xRhumbReceive",
        "amount_atomic": "2500000",
        "block_number": 12345,
    }
    mock_insert_returning.return_value = {
        "id": TEST_RECEIPT_ID,
        "tx_hash": "0xabc123",
        "from_address": TEST_WALLET_ADDRESS,
        "network": "base",
    }
    mock_insert.return_value = True
    mock_patch.return_value = [{}]
    mock_mark_verified.return_value = True

    client = TestClient(_shared_app)
    resp = client.post(
        "/v1/billing/x402/topup/verify",
        headers={"Authorization": "Bearer test-wallet-token"},
        json={
            "payment_request_id": TEST_PAYMENT_REQUEST_ID,
            "x_payment": "opaque-x-payment-proof",
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["receipt_id"] == TEST_RECEIPT_ID
    assert data["status"] == "credited"
    assert data["amount_usd_cents"] == 250
    assert data["balance_usd_cents"] == 750
    assert data["balance_usd"] == 7.5

    mock_mark_verified.assert_awaited_once_with(TEST_PAYMENT_REQUEST_ID, "0xabc123")
    mock_verify_usdc_payment.assert_awaited_once()

    receipt_insert = mock_insert_returning.await_args
    assert receipt_insert.args[0] == "usdc_receipts"
    assert receipt_insert.args[1]["payment_request_id"] == TEST_PAYMENT_REQUEST_ID
    assert receipt_insert.args[1]["amount_usd_cents"] == 250

    ledger_call = mock_insert.await_args_list[0]
    assert ledger_call.args[0] == "credit_ledger"
    assert ledger_call.args[1]["event_type"] == "wallet_topup"
    assert ledger_call.args[1]["balance_after_usd_cents"] == 750

    patch_paths = [call.args[0] for call in mock_patch.await_args_list]
    assert any(path.startswith("org_credits?") for path in patch_paths)
    assert any(path.startswith("wallet_balance_topups?") for path in patch_paths)
