"""Tests for USDC payment verification — services/usdc_verifier.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.usdc_verifier import (
    BASE_MAINNET_RPC,
    TRANSFER_EVENT_TOPIC,
    USDC_BASE_MAINNET,
    USDC_BASE_SEPOLIA,
    verify_usdc_payment,
)

WALLET = "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623"
SENDER = "0x1234567890abcdef1234567890abcdef12345678"
OTHER_SENDER = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
TX_HASH = "0xabc123def456abc123def456abc123def456abc123def456abc123def456abc1"
AMOUNT_ATOMIC = "150000"  # $0.15 in USDC atomic units (6 decimals)
LOW_AMOUNT_ATOMIC = "100000"  # $0.10 in USDC atomic units

SENDER_TOPIC = "0x000000000000000000000000" + SENDER[2:]
OTHER_SENDER_TOPIC = "0x000000000000000000000000" + OTHER_SENDER[2:]
WALLET_TOPIC = "0x000000000000000000000000" + WALLET[2:].lower()
WRONG_WALLET_TOPIC = "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
AMOUNT_HEX = "0x00000000000000000000000000000000000000000000000000000000000249f0"
LOW_AMOUNT_HEX = "0x00000000000000000000000000000000000000000000000000000000000186a0"


def _make_transfer_log(
    *,
    address: str = USDC_BASE_SEPOLIA,
    from_topic: str = SENDER_TOPIC,
    to_topic: str = WALLET_TOPIC,
    amount_hex: str = AMOUNT_HEX,
) -> dict:
    return {
        "address": address,
        "topics": [TRANSFER_EVENT_TOPIC, from_topic, to_topic],
        "data": amount_hex,
    }


def _make_receipt(
    *,
    status: str = "0x1",
    logs: list[dict] | None = None,
    block_number: str = "0x1a4",
) -> dict:
    if logs is None:
        logs = [_make_transfer_log()]
    return {
        "status": status,
        "blockNumber": block_number,
        "logs": logs,
    }


def _make_rpc_result(result: dict | None, rpc_id: int) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _mock_httpx_client(receipt: dict | None, latest_block: str = "0x1a5"):
    receipt_resp = MagicMock()
    receipt_resp.json.return_value = _make_rpc_result(receipt, 1)

    latest_block_resp = MagicMock()
    latest_block_resp.json.return_value = _make_rpc_result(latest_block, 2)

    mock_client = AsyncMock()
    mock_client.post.side_effect = [receipt_resp, latest_block_resp]
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestSuccessfulVerification:
    """Tests for successful on-chain USDC transfer verification."""

    @pytest.mark.asyncio
    async def test_valid_transfer(self):
        receipt = _make_receipt()
        mock_client = _mock_httpx_client(receipt)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
                network="base-sepolia",
            )

        assert result["valid"] is True
        assert result["from_address"].lower() == SENDER.lower()
        assert result["to_address"].lower() == WALLET.lower()
        assert result["amount_atomic"] == AMOUNT_ATOMIC
        assert result["block_number"] == 0x1A4
        assert result["confirmations"] == 2
        assert result["token_address"] == USDC_BASE_SEPOLIA
        assert result["tx_hash"] == TX_HASH

    @pytest.mark.asyncio
    async def test_mainnet_network_uses_canonical_contract(self):
        receipt = _make_receipt(logs=[_make_transfer_log(address=USDC_BASE_MAINNET)])
        mock_client = _mock_httpx_client(receipt)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
                network="base-mainnet",
            )

        assert result["valid"] is True
        assert result["token_address"] == USDC_BASE_MAINNET
        assert mock_client.post.call_args_list[0][0][0] == BASE_MAINNET_RPC

    @pytest.mark.asyncio
    async def test_case_insensitive_address_matching(self):
        receipt = _make_receipt(
            logs=[
                _make_transfer_log(
                    to_topic="0x000000000000000000000000ea63ef9b4fac31db058977065c8fe12fdca02623",
                )
            ]
        )
        mock_client = _mock_httpx_client(receipt)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is True


class TestFailedVerification:
    """Tests for on-chain verification failures."""

    @pytest.mark.asyncio
    async def test_tx_not_found(self):
        mock_client = _mock_httpx_client(None)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_reverted_transaction(self):
        receipt = _make_receipt(status="0x0")
        mock_client = _mock_httpx_client(receipt)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "reverted" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_multiple_transfers_to_rhumb_rejected(self):
        receipt = _make_receipt(
            logs=[
                _make_transfer_log(),
                _make_transfer_log(from_topic=OTHER_SENDER_TOPIC),
            ]
        )
        mock_client = _mock_httpx_client(receipt)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "ambiguous transaction" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_wrong_amount_rejected(self):
        receipt = _make_receipt(logs=[_make_transfer_log(amount_hex=LOW_AMOUNT_HEX)])
        mock_client = _mock_httpx_client(receipt)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "underpayment" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_wrong_sender_rejected(self):
        receipt = _make_receipt(logs=[_make_transfer_log(from_topic=OTHER_SENDER_TOPIC)])
        mock_client = _mock_httpx_client(receipt)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "sender does not match" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_wrong_contract_rejected(self):
        receipt = _make_receipt(
            logs=[
                _make_transfer_log(
                    address="0x1111111111111111111111111111111111111111",
                )
            ]
        )
        mock_client = _mock_httpx_client(receipt)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "no payment found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_no_transfers_to_rhumb_rejected(self):
        receipt = _make_receipt(logs=[_make_transfer_log(to_topic=WRONG_WALLET_TOPIC)])
        mock_client = _mock_httpx_client(receipt)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "no payment found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unfinalized_transaction_rejected(self):
        receipt = _make_receipt(block_number="0x1a4")
        mock_client = _mock_httpx_client(receipt, latest_block="0x1a3")

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "not yet finalized" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unsupported_network_rejected(self):
        result = await verify_usdc_payment(
            tx_hash=TX_HASH,
            expected_to=WALLET,
            expected_from=SENDER,
            expected_amount_atomic=AMOUNT_ATOMIC,
            network="base-unknown",
        )

        assert result["valid"] is False
        assert "unsupported network" in result["error"].lower()


class TestErrorHandling:
    """Tests for RPC errors and timeouts."""

    @pytest.mark.asyncio
    async def test_rpc_timeout(self):
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_rpc_connection_error(self):
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.usdc_verifier.httpx.AsyncClient", return_value=mock_client):
            result = await verify_usdc_payment(
                tx_hash=TX_HASH,
                expected_to=WALLET,
                expected_from=SENDER,
                expected_amount_atomic=AMOUNT_ATOMIC,
            )

        assert result["valid"] is False
        assert "verification failed" in result["error"].lower()
