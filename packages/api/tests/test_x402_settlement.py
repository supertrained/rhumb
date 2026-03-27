"""Tests for the unified x402 settlement service (local + facilitator).

Covers:
- is_configured() with various env combinations
- verify_and_settle() prefers local settlement when available
- verify_and_settle() falls back to facilitator on local on-chain failure
- verify_and_settle() uses facilitator when only facilitator is configured
- verify_and_settle() raises when neither path is configured
- Facilitator-only paths (existing behavior preserved)
"""

from __future__ import annotations

import base64
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.x402_settlement import (
    X402FacilitatorNotConfigured,
    X402SettlementFailed,
    X402SettlementService,
    X402VerificationFailed,
)


PAYMENT_PAYLOAD = {
    "x402Version": 2,
    "accepted": {
        "scheme": "exact",
        "network": "base-sepolia",
        "amount": "100000",
        "payTo": "0xReceiver",
        "asset": "0xAsset",
        "maxTimeoutSeconds": 300,
        "resource": "https://api.rhumb.dev/v1/capabilities/email.send/execute",
        "description": "Rhumb capability execution: email.send",
        "mimeType": "application/json",
        "extra": {"name": "USD Coin", "version": "2", "assetTransferMethod": "eip3009"},
    },
    "payload": {
        "authorization": {
            "from": "0xPayer",
            "to": "0xReceiver",
            "value": "100000",
            "validAfter": "1",
            "validBefore": "2",
            "nonce": "0xdeadbeef",
        },
        "signature": "0xsigned",
    },
}

PAYMENT_REQUIREMENTS = PAYMENT_PAYLOAD["accepted"]

# Deterministic test key for local settlement tests
TEST_PRIVATE_KEY = "0x" + "ab" * 32


# ── Configuration tests ───────────────────────────────────────────────────


class TestIsConfigured:
    def test_with_private_key_only(self):
        """is_configured() should return True when RHUMB_SETTLEMENT_PRIVATE_KEY is set."""
        with patch.dict(os.environ, {
            "RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY,
            "X402_FACILITATOR_URL": "",
        }, clear=False):
            service = X402SettlementService()
            assert service.is_configured() is True
            assert service.local_configured() is True
            assert service.facilitator_configured() is False

    def test_with_facilitator_url_only(self):
        """is_configured() should return True when X402_FACILITATOR_URL is set."""
        with patch.dict(os.environ, {
            "RHUMB_SETTLEMENT_PRIVATE_KEY": "",
            "X402_FACILITATOR_URL": "https://facilitator.example",
        }, clear=False):
            service = X402SettlementService()
            assert service.is_configured() is True
            assert service.local_configured() is False
            assert service.facilitator_configured() is True

    def test_with_both(self):
        """is_configured() should return True when both are set."""
        with patch.dict(os.environ, {
            "RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY,
            "X402_FACILITATOR_URL": "https://facilitator.example",
        }, clear=False):
            service = X402SettlementService()
            assert service.is_configured() is True
            assert service.local_configured() is True
            assert service.facilitator_configured() is True

    def test_with_neither(self):
        """is_configured() should return False when neither is set."""
        with patch.dict(os.environ, {
            "RHUMB_SETTLEMENT_PRIVATE_KEY": "",
            "X402_FACILITATOR_URL": "",
        }, clear=False):
            service = X402SettlementService()
            assert service.is_configured() is False


# ── Routing tests ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_prefers_local_settlement():
    """When both paths are configured, local settlement should be tried first."""
    mock_local_result = {
        "verify": {"isValid": True, "payer": "0xPayer"},
        "settle": {"success": True, "transaction": "0xlocal", "network": "base"},
        "payer": "0xPayer",
        "transaction": "0xlocal",
        "network": "base",
        "payment_response_header": "base64header",
    }

    with patch.dict(os.environ, {
        "RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY,
        "X402_FACILITATOR_URL": "https://facilitator.example",
    }, clear=False):
        service = X402SettlementService()
        service._local = MagicMock()
        service._local.is_configured.return_value = True
        service._local.verify_and_settle = AsyncMock(return_value=mock_local_result)

        result = await service.verify_and_settle(PAYMENT_PAYLOAD, PAYMENT_REQUIREMENTS)

    assert result["transaction"] == "0xlocal"
    service._local.verify_and_settle.assert_called_once()


@pytest.mark.anyio
async def test_falls_back_to_facilitator_on_local_chain_failure():
    """When local on-chain settlement fails and facilitator is configured, try facilitator."""
    from services.x402_local_settlement import SettlementOnChainFailed

    verify_response = MagicMock()
    verify_response.status_code = 200
    verify_response.json.return_value = {"isValid": True, "payer": "0xPayer"}

    settle_payload = {
        "success": True,
        "transaction": "0xfacilitator",
        "network": "base-sepolia",
        "payer": "0xPayer",
    }
    settle_response = MagicMock()
    settle_response.status_code = 200
    settle_response.json.return_value = settle_payload

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[verify_response, settle_response])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.dict(os.environ, {
            "RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY,
            "X402_FACILITATOR_URL": "https://facilitator.example",
        }, clear=False),
        patch("services.x402_settlement.httpx.AsyncClient", return_value=mock_client),
    ):
        service = X402SettlementService()
        service._local = MagicMock()
        service._local.is_configured.return_value = True
        service._local.verify_and_settle = AsyncMock(
            side_effect=SettlementOnChainFailed("gas exhausted")
        )

        result = await service.verify_and_settle(PAYMENT_PAYLOAD, PAYMENT_REQUIREMENTS)

    assert result["transaction"] == "0xfacilitator"


@pytest.mark.anyio
async def test_verification_failure_does_not_fallback():
    """Verification failures should NOT try the facilitator — they're definitive."""
    from services.x402_local_settlement import SettlementVerificationFailed

    with (
        patch.dict(os.environ, {
            "RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY,
            "X402_FACILITATOR_URL": "https://facilitator.example",
        }, clear=False),
    ):
        service = X402SettlementService()
        service._local = MagicMock()
        service._local.is_configured.return_value = True
        service._local.verify_and_settle = AsyncMock(
            side_effect=SettlementVerificationFailed("bad signature")
        )

        with pytest.raises(X402VerificationFailed, match="bad signature"):
            await service.verify_and_settle(PAYMENT_PAYLOAD, PAYMENT_REQUIREMENTS)


@pytest.mark.anyio
async def test_raises_when_neither_configured():
    """Should raise X402FacilitatorNotConfigured when no path is available."""
    with patch.dict(os.environ, {
        "RHUMB_SETTLEMENT_PRIVATE_KEY": "",
        "X402_FACILITATOR_URL": "",
    }, clear=False):
        service = X402SettlementService()
        with pytest.raises(X402FacilitatorNotConfigured):
            await service.verify_and_settle(PAYMENT_PAYLOAD, PAYMENT_REQUIREMENTS)


# ── Facilitator-only tests (preserved from original) ─────────────────────


@pytest.mark.anyio
async def test_facilitator_verify_and_settle_success():
    service = X402SettlementService()

    verify_response = MagicMock()
    verify_response.status_code = 200
    verify_response.json.return_value = {"isValid": True, "payer": "0xPayer"}

    settle_payload = {
        "success": True,
        "transaction": "0xabc123",
        "network": "base-sepolia",
        "payer": "0xPayer",
    }
    settle_response = MagicMock()
    settle_response.status_code = 200
    settle_response.json.return_value = settle_payload

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[verify_response, settle_response])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.dict(os.environ, {
            "RHUMB_SETTLEMENT_PRIVATE_KEY": "",
            "X402_FACILITATOR_URL": "https://facilitator.example",
        }, clear=False),
        patch("services.x402_settlement.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await service.verify_and_settle(PAYMENT_PAYLOAD, PAYMENT_REQUIREMENTS)

    assert result["transaction"] == "0xabc123"
    assert result["network"] == "base-sepolia"
    assert result["payer"] == "0xPayer"
    decoded_header = json.loads(base64.b64decode(result["payment_response_header"]).decode())
    assert decoded_header == settle_payload


@pytest.mark.anyio
async def test_facilitator_verify_failure():
    service = X402SettlementService()

    verify_response = MagicMock()
    verify_response.status_code = 200
    verify_response.json.return_value = {
        "isValid": False,
        "invalidMessage": "signature mismatch",
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=verify_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.dict(os.environ, {
            "RHUMB_SETTLEMENT_PRIVATE_KEY": "",
            "X402_FACILITATOR_URL": "https://facilitator.example",
        }, clear=False),
        patch("services.x402_settlement.httpx.AsyncClient", return_value=mock_client),
        pytest.raises(X402VerificationFailed, match="signature mismatch"),
    ):
        await service.verify_and_settle(PAYMENT_PAYLOAD, PAYMENT_REQUIREMENTS)


@pytest.mark.anyio
async def test_facilitator_settle_failure():
    service = X402SettlementService()

    verify_response = MagicMock()
    verify_response.status_code = 200
    verify_response.json.return_value = {"isValid": True, "payer": "0xPayer"}

    settle_response = MagicMock()
    settle_response.status_code = 200
    settle_response.json.return_value = {
        "success": False,
        "errorMessage": "nonce already used",
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[verify_response, settle_response])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.dict(os.environ, {
            "RHUMB_SETTLEMENT_PRIVATE_KEY": "",
            "X402_FACILITATOR_URL": "https://facilitator.example",
        }, clear=False),
        patch("services.x402_settlement.httpx.AsyncClient", return_value=mock_client),
        pytest.raises(X402SettlementFailed, match="nonce already used"),
    ):
        await service.verify_and_settle(PAYMENT_PAYLOAD, PAYMENT_REQUIREMENTS)
