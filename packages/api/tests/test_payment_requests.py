"""Tests for x402 payment request service — services/payment_requests.py."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.payment_requests import (
    USDC_BASE_MAINNET,
    USDC_BASE_SEPOLIA,
    PaymentRequestService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_http_response(status_code: int = 201, json_data=None, headers=None):
    """Build a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or []
    resp.text = "ok"
    resp.headers = headers or {}
    return resp


def _patch_httpx(mock_resp):
    """Return a context manager that patches httpx.AsyncClient."""
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.get.return_value = mock_resp
    mock_client.patch.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return patch("services.payment_requests.httpx.AsyncClient", return_value=mock_client), mock_client


# ---------------------------------------------------------------------------
# create_payment_request
# ---------------------------------------------------------------------------


class TestCreatePaymentRequest:
    """Tests for PaymentRequestService.create_payment_request."""

    @pytest.mark.asyncio
    async def test_returns_row_on_success(self):
        """Successful insert returns the DB row."""
        svc = PaymentRequestService()
        row = {
            "id": "uuid-123",
            "org_id": "org_1",
            "capability_id": "email.send",
            "amount_usdc_atomic": "150000",
            "amount_usd_cents": 15,
            "network": "base-sepolia",
            "pay_to_address": "0xTestWallet",
            "asset_address": USDC_BASE_SEPOLIA,
            "status": "pending",
        }
        mock_resp = _mock_http_response(201, [row])
        patcher, mock_client = _patch_httpx(mock_resp)

        with (
            patcher,
            patch.dict(os.environ, {
                "RHUMB_USDC_WALLET_ADDRESS": "0xTestWallet",
                "RAILWAY_ENVIRONMENT": "",
            }),
        ):
            result = await svc.create_payment_request(
                org_id="org_1",
                capability_id="email.send",
                amount_usd_cents=15,
            )

        assert result["id"] == "uuid-123"
        assert result["amount_usdc_atomic"] == "150000"
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_usdc_amount_conversion(self):
        """Cents are converted to USDC atomic units: cents × 10000."""
        svc = PaymentRequestService()
        mock_resp = _mock_http_response(201, [{"amount_usdc_atomic": "1000000"}])
        patcher, mock_client = _patch_httpx(mock_resp)

        with (
            patcher,
            patch.dict(os.environ, {
                "RHUMB_USDC_WALLET_ADDRESS": "0xTestWallet",
                "RAILWAY_ENVIRONMENT": "",
            }),
        ):
            await svc.create_payment_request(
                org_id="org_1",
                capability_id="email.send",
                amount_usd_cents=100,  # $1.00 → 1000000 atomic
            )

        # Verify the payload sent to Supabase
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["amount_usdc_atomic"] == "1000000"

    @pytest.mark.asyncio
    async def test_returns_payload_on_http_failure(self):
        """Non-2xx response still returns the constructed payload."""
        svc = PaymentRequestService()
        mock_resp = _mock_http_response(500)
        patcher, _ = _patch_httpx(mock_resp)

        with (
            patcher,
            patch.dict(os.environ, {
                "RHUMB_USDC_WALLET_ADDRESS": "0xTestWallet",
                "RAILWAY_ENVIRONMENT": "",
            }),
        ):
            result = await svc.create_payment_request(
                org_id="org_1",
                capability_id="email.send",
                amount_usd_cents=15,
            )

        # Payload returned as fallback
        assert result["capability_id"] == "email.send"
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_execution_id_included_when_provided(self):
        """execution_id is passed through to Supabase payload."""
        svc = PaymentRequestService()
        mock_resp = _mock_http_response(201, [{"execution_id": "exec_42"}])
        patcher, mock_client = _patch_httpx(mock_resp)

        with (
            patcher,
            patch.dict(os.environ, {
                "RHUMB_USDC_WALLET_ADDRESS": "0xTestWallet",
                "RAILWAY_ENVIRONMENT": "",
            }),
        ):
            await svc.create_payment_request(
                org_id="org_1",
                capability_id="email.send",
                amount_usd_cents=15,
                execution_id="exec_42",
            )

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["execution_id"] == "exec_42"


# ---------------------------------------------------------------------------
# Wallet address
# ---------------------------------------------------------------------------


class TestWalletAddress:
    """Tests for wallet address configuration."""

    @pytest.mark.asyncio
    async def test_raises_when_wallet_not_configured(self):
        """Missing RHUMB_USDC_WALLET_ADDRESS raises ValueError."""
        svc = PaymentRequestService()
        with (
            patch.dict(os.environ, {"RHUMB_USDC_WALLET_ADDRESS": ""}, clear=False),
            pytest.raises(ValueError, match="RHUMB_USDC_WALLET_ADDRESS not configured"),
        ):
            await svc.create_payment_request(
                org_id="org_1",
                capability_id="email.send",
                amount_usd_cents=15,
            )

    @pytest.mark.asyncio
    async def test_uses_env_wallet_address(self):
        """Wallet address comes from RHUMB_USDC_WALLET_ADDRESS env var."""
        svc = PaymentRequestService()
        mock_resp = _mock_http_response(201, [{}])
        patcher, mock_client = _patch_httpx(mock_resp)

        with (
            patcher,
            patch.dict(os.environ, {
                "RHUMB_USDC_WALLET_ADDRESS": "0xMyCustomWallet",
                "RAILWAY_ENVIRONMENT": "",
            }),
        ):
            await svc.create_payment_request(
                org_id="org_1",
                capability_id="email.send",
                amount_usd_cents=15,
            )

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["pay_to_address"] == "0xMyCustomWallet"


# ---------------------------------------------------------------------------
# Network selection
# ---------------------------------------------------------------------------


class TestNetworkSelection:
    """Tests for network config based on RAILWAY_ENVIRONMENT."""

    @pytest.mark.asyncio
    async def test_testnet_by_default(self):
        """Non-production environment uses base-sepolia."""
        svc = PaymentRequestService()
        mock_resp = _mock_http_response(201, [{}])
        patcher, mock_client = _patch_httpx(mock_resp)

        with (
            patcher,
            patch.dict(os.environ, {
                "RHUMB_USDC_WALLET_ADDRESS": "0xTest",
                "RAILWAY_ENVIRONMENT": "",
            }),
        ):
            await svc.create_payment_request(
                org_id="org_1",
                capability_id="email.send",
                amount_usd_cents=15,
            )

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["network"] == "base-sepolia"
        assert payload["asset_address"] == USDC_BASE_SEPOLIA

    @pytest.mark.asyncio
    async def test_mainnet_in_production(self):
        """Production environment uses base-mainnet."""
        svc = PaymentRequestService()
        mock_resp = _mock_http_response(201, [{}])
        patcher, mock_client = _patch_httpx(mock_resp)

        with (
            patcher,
            patch.dict(os.environ, {
                "RHUMB_USDC_WALLET_ADDRESS": "0xTest",
                "RAILWAY_ENVIRONMENT": "production",
            }),
        ):
            await svc.create_payment_request(
                org_id="org_1",
                capability_id="email.send",
                amount_usd_cents=15,
            )

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["network"] == "base-mainnet"
        assert payload["asset_address"] == USDC_BASE_MAINNET


# ---------------------------------------------------------------------------
# mark_verified
# ---------------------------------------------------------------------------


class TestMarkVerified:
    """Tests for PaymentRequestService.mark_verified."""

    @pytest.mark.asyncio
    async def test_mark_verified_success(self):
        """Successful PATCH returns True."""
        svc = PaymentRequestService()
        mock_resp = _mock_http_response(200)
        patcher, mock_client = _patch_httpx(mock_resp)

        with patcher:
            result = await svc.mark_verified("uuid-123", "0xTxHash456")

        assert result is True
        call_kwargs = mock_client.patch.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["status"] == "verified"
        assert payload["payment_tx_hash"] == "0xTxHash456"
        assert "verified_at" in payload

    @pytest.mark.asyncio
    async def test_mark_verified_failure(self):
        """Non-2xx PATCH returns False."""
        svc = PaymentRequestService()
        mock_resp = _mock_http_response(500)
        patcher, _ = _patch_httpx(mock_resp)

        with patcher:
            result = await svc.mark_verified("uuid-123", "0xTxHash456")

        assert result is False

    @pytest.mark.asyncio
    async def test_mark_verified_exception(self):
        """Network exception returns False."""
        svc = PaymentRequestService()
        mock_client = AsyncMock()
        mock_client.patch.side_effect = Exception("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.payment_requests.httpx.AsyncClient", return_value=mock_client):
            result = await svc.mark_verified("uuid-123", "0xTxHash456")

        assert result is False


# ---------------------------------------------------------------------------
# expire_stale_requests
# ---------------------------------------------------------------------------


class TestExpireStaleRequests:
    """Tests for PaymentRequestService.expire_stale_requests."""

    @pytest.mark.asyncio
    async def test_expire_returns_count(self):
        """Expiry returns count from Content-Range header."""
        svc = PaymentRequestService()
        mock_resp = _mock_http_response(200, headers={"content-range": "0-2/3"})
        patcher, mock_client = _patch_httpx(mock_resp)

        with patcher:
            count = await svc.expire_stale_requests()

        assert count == 3
        # Verify the PATCH targets only pending + expired rows
        call_args = mock_client.patch.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        assert "status=eq.pending" in url
        assert "expires_at=lt." in url
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["status"] == "expired"

    @pytest.mark.asyncio
    async def test_expire_returns_zero_on_wildcard(self):
        """Content-Range with '*' total returns 0."""
        svc = PaymentRequestService()
        mock_resp = _mock_http_response(200, headers={"content-range": "*/*"})
        patcher, _ = _patch_httpx(mock_resp)

        with patcher:
            count = await svc.expire_stale_requests()

        assert count == 0

    @pytest.mark.asyncio
    async def test_expire_returns_zero_on_no_header(self):
        """Missing Content-Range header returns 0."""
        svc = PaymentRequestService()
        mock_resp = _mock_http_response(200, headers={})
        patcher, _ = _patch_httpx(mock_resp)

        with patcher:
            count = await svc.expire_stale_requests()

        assert count == 0

    @pytest.mark.asyncio
    async def test_expire_returns_zero_on_exception(self):
        """Network exception returns 0."""
        svc = PaymentRequestService()
        mock_client = AsyncMock()
        mock_client.patch.side_effect = Exception("timeout")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.payment_requests.httpx.AsyncClient", return_value=mock_client):
            count = await svc.expire_stale_requests()

        assert count == 0


# ---------------------------------------------------------------------------
# get_pending_request
# ---------------------------------------------------------------------------


class TestGetPendingRequest:
    """Tests for PaymentRequestService.get_pending_request."""

    @pytest.mark.asyncio
    async def test_returns_row_when_found(self):
        """Found pending request returns dict."""
        svc = PaymentRequestService()
        row = {"id": "uuid-123", "status": "pending"}
        mock_resp = _mock_http_response(200, [row])
        patcher, _ = _patch_httpx(mock_resp)

        with patcher:
            result = await svc.get_pending_request("uuid-123")

        assert result is not None
        assert result["id"] == "uuid-123"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Empty result returns None."""
        svc = PaymentRequestService()
        mock_resp = _mock_http_response(200, [])
        patcher, _ = _patch_httpx(mock_resp)

        with patcher:
            result = await svc.get_pending_request("uuid-nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        """Network exception returns None."""
        svc = PaymentRequestService()
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.payment_requests.httpx.AsyncClient", return_value=mock_client):
            result = await svc.get_pending_request("uuid-123")

        assert result is None
