"""Tests for USDC payment verification — services/usdc_verifier.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.usdc_verifier import (
    BASE_MAINNET_RPC,
    BASE_SEPOLIA_RPC,
    TRANSFER_EVENT_TOPIC,
    USDC_BASE_MAINNET,
    USDC_BASE_SEPOLIA,
    verify_usdc_payment,
)

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

WALLET = "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623"
SENDER = "0x1234567890abcdef1234567890abcdef12345678"
TX_HASH = "0xabc123def456abc123def456abc123def456abc123def456abc123def456abc1"
AMOUNT_ATOMIC = "150000"  # $0.15 in USDC atomic units (6 decimals)

# Properly zero-padded 32-byte hex topics
SENDER_TOPIC = "0x000000000000000000000000" + SENDER[2:]
WALLET_TOPIC = "0x000000000000000000000000" + WALLET[2:].lower()
# Amount as 32-byte hex data (150000 = 0x249F0)
AMOUNT_HEX = "0x00000000000000000000000000000000000000000000000000000000000249f0"


def _make_receipt(
    status: str = "0x1",
    logs: list | None = None,
    block_number: str = "0x1a4",
) -> dict:
    """Build a minimal transaction receipt dict."""
    if logs is None:
        logs = [
            {
                "address": USDC_BASE_SEPOLIA,
                "topics": [TRANSFER_EVENT_TOPIC, SENDER_TOPIC, WALLET_TOPIC],
                "data": AMOUNT_HEX,
            }
        ]
    return {
        "status": status,
        "blockNumber": block_number,
        "logs": logs,
    }


def _make_rpc_response(receipt: dict | None) -> dict:
    """Wrap a receipt in a JSON-RPC response envelope."""
    return {"jsonrpc": "2.0", "id": 1, "result": receipt}


def _mock_httpx_client(rpc_response: dict):
    """Create a mock httpx.AsyncClient that returns the given RPC response."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = rpc_response

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# Tests: successful verification
# ---------------------------------------------------------------------------


class TestSuccessfulVerification:
    """Tests for successful on-chain USDC transfer verification."""

    @pytest.mark.asyncio
    async def test_valid_transfer(self):
        """Matching USDC transfer returns valid=True with details."""
        receipt = _make_receipt()
        mock_client = _mock_httpx_client(_make_rpc_response(receipt))

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_amount_atomic=AMOUNT_ATOMIC,
                network="base-sepolia",
            )

        assert result["valid"] is True
        assert result["from_address"].lower() == SENDER.lower()
        assert result["to_address"].lower() == WALLET.lower()
        assert result["amount_atomic"] == AMOUNT_ATOMIC
        assert result["block_number"] == 0x1A4
        assert result["tx_hash"] == TX_HASH

    @pytest.mark.asyncio
    async def test_mainnet_network(self):
        """base-mainnet uses mainnet RPC and USDC contract address."""
        logs = [
            {
                "address": USDC_BASE_MAINNET,
                "topics": [TRANSFER_EVENT_TOPIC, SENDER_TOPIC, WALLET_TOPIC],
                "data": AMOUNT_HEX,
            }
        ]
        receipt = _make_receipt(logs=logs)
        mock_client = _mock_httpx_client(_make_rpc_response(receipt))

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_amount_atomic=AMOUNT_ATOMIC,
                network="base-mainnet",
            )

        assert result["valid"] is True
        # Verify it called the mainnet RPC
        call_args = mock_client.post.call_args
        assert call_args[0][0] == BASE_MAINNET_RPC

    @pytest.mark.asyncio
    async def test_multiple_logs_finds_match(self):
        """Transaction with multiple logs finds the matching USDC Transfer."""
        logs = [
            {
                "address": "0xOtherContract",
                "topics": ["0xother_topic"],
                "data": "0x0",
            },
            {
                "address": USDC_BASE_SEPOLIA,
                "topics": [TRANSFER_EVENT_TOPIC, SENDER_TOPIC, WALLET_TOPIC],
                "data": AMOUNT_HEX,
            },
        ]
        receipt = _make_receipt(logs=logs)
        mock_client = _mock_httpx_client(_make_rpc_response(receipt))

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is True


# ---------------------------------------------------------------------------
# Tests: failed verification
# ---------------------------------------------------------------------------


class TestFailedVerification:
    """Tests for on-chain verification failures."""

    @pytest.mark.asyncio
    async def test_tx_not_found(self):
        """Transaction not found (null receipt) returns valid=False."""
        mock_client = _mock_httpx_client(_make_rpc_response(None))

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_reverted_transaction(self):
        """Reverted transaction (status != 0x1) returns valid=False."""
        receipt = _make_receipt(status="0x0")
        mock_client = _mock_httpx_client(_make_rpc_response(receipt))

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "reverted" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_wrong_recipient(self):
        """Transfer to wrong address returns valid=False."""
        wrong_wallet_topic = "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        logs = [
            {
                "address": USDC_BASE_SEPOLIA,
                "topics": [TRANSFER_EVENT_TOPIC, SENDER_TOPIC, wrong_wallet_topic],
                "data": AMOUNT_HEX,
            }
        ]
        receipt = _make_receipt(logs=logs)
        mock_client = _mock_httpx_client(_make_rpc_response(receipt))

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "no matching" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_wrong_amount(self):
        """Transfer with wrong amount returns valid=False."""
        # 200000 instead of 150000 → 0x30D40
        wrong_amount_hex = "0x0000000000000000000000000000000000000000000000000000000000030d40"
        logs = [
            {
                "address": USDC_BASE_SEPOLIA,
                "topics": [TRANSFER_EVENT_TOPIC, SENDER_TOPIC, WALLET_TOPIC],
                "data": wrong_amount_hex,
            }
        ]
        receipt = _make_receipt(logs=logs)
        mock_client = _mock_httpx_client(_make_rpc_response(receipt))

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "no matching" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_no_transfer_events(self):
        """Transaction with no Transfer events returns valid=False."""
        receipt = _make_receipt(logs=[])
        mock_client = _mock_httpx_client(_make_rpc_response(receipt))

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "no matching" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_wrong_contract(self):
        """Transfer from non-USDC contract is ignored."""
        logs = [
            {
                "address": "0xNotUSDC1234567890123456789012345678901234",
                "topics": [TRANSFER_EVENT_TOPIC, SENDER_TOPIC, WALLET_TOPIC],
                "data": AMOUNT_HEX,
            }
        ]
        receipt = _make_receipt(logs=logs)
        mock_client = _mock_httpx_client(_make_rpc_response(receipt))

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for RPC errors and timeouts."""

    @pytest.mark.asyncio
    async def test_rpc_timeout(self):
        """RPC timeout returns valid=False with timeout error."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_rpc_connection_error(self):
        """RPC connection error returns valid=False."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "verification failed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_case_insensitive_address_matching(self):
        """Address matching is case-insensitive (checksummed vs lowercase)."""
        # Use mixed-case wallet address
        wallet_mixed = "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623"
        wallet_topic = "0x000000000000000000000000ea63ef9b4fac31db058977065c8fe12fdca02623"
        logs = [
            {
                "address": USDC_BASE_SEPOLIA,
                "topics": [TRANSFER_EVENT_TOPIC, SENDER_TOPIC, wallet_topic],
                "data": AMOUNT_HEX,
            }
        ]
        receipt = _make_receipt(logs=logs)
        mock_client = _mock_httpx_client(_make_rpc_response(receipt))

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=wallet_mixed,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is True
