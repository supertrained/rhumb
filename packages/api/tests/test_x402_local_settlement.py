"""Tests for local EIP-3009 x402 settlement.

Covers:
- Off-chain signature verification (valid, invalid signer, expired, not-yet-valid)
- ABI encoding correctness
- Signature splitting (v, r, s)
- Settlement success path (mock RPC)
- Settlement failure paths (gas, timeout, revert)
- Wallet ETH balance health check
"""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.x402_local_settlement import (
    LocalX402Settlement,
    SettlementOnChainFailed,
    SettlementVerificationFailed,
    abi_encode_transfer_with_authorization,
    get_wallet_eth_balance,
    verify_authorization_signature,
    _split_signature,
    _to_address,
    _to_bytes32,
    _to_uint256,
    _to_uint8,
    TRANSFER_WITH_AUTH_SELECTOR,
)


# ── Test fixtures ─────────────────────────────────────────────────────────

# A deterministic test private key (DO NOT use on mainnet!)
TEST_PRIVATE_KEY = "0x" + "ab" * 32  # 32 bytes of 0xab

# Generate a real signature for testing using eth_account
def _make_test_authorization_and_signature():
    """Create a valid EIP-3009 authorization + signature for tests."""
    from eth_account import Account
    from eth_account.messages import encode_typed_data

    account = Account.from_key(TEST_PRIVATE_KEY)
    now = int(time.time())

    authorization = {
        "from": account.address,
        "to": "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623",
        "value": "100000",  # 0.10 USDC
        "validAfter": "0",
        "validBefore": str(now + 3600),  # 1 hour from now
        "nonce": "0x" + "de" * 32,
    }

    # Build EIP-712 typed data
    domain = {
        "name": "USD Coin",
        "version": "2",
        "chainId": 8453,
        "verifyingContract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    }
    types = {
        "TransferWithAuthorization": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ],
    }

    nonce_bytes = bytes.fromhex(authorization["nonce"].replace("0x", "").ljust(64, "0"))
    message_data = {
        "from": authorization["from"],
        "to": authorization["to"],
        "value": int(authorization["value"]),
        "validAfter": int(authorization["validAfter"]),
        "validBefore": int(authorization["validBefore"]),
        "nonce": nonce_bytes,
    }

    signable = encode_typed_data(
        domain_data=domain,
        message_types=types,
        message_data=message_data,
    )
    signed = account.sign_message(signable)
    signature = signed.signature.hex()

    return authorization, "0x" + signature, account.address


# ── Signature splitting ───────────────────────────────────────────────────


class TestSignatureSplit:
    def test_split_65_byte_signature(self):
        """65-byte signature: r(32) + s(32) + v(1)."""
        r_bytes = b"\x01" * 32
        s_bytes = b"\x02" * 32
        sig = "0x" + r_bytes.hex() + s_bytes.hex() + "1b"  # v=27
        v, r, s = _split_signature(sig)
        assert v == 27
        assert r == r_bytes
        assert s == s_bytes

    def test_split_65_byte_with_low_v(self):
        """v=0 should be normalized to v=27."""
        r_bytes = b"\x01" * 32
        s_bytes = b"\x02" * 32
        sig = "0x" + r_bytes.hex() + s_bytes.hex() + "00"  # v=0
        v, r, s = _split_signature(sig)
        assert v == 27

    def test_split_65_byte_with_v_1(self):
        """v=1 should be normalized to v=28."""
        r_bytes = b"\x01" * 32
        s_bytes = b"\x02" * 32
        sig = "0x" + r_bytes.hex() + s_bytes.hex() + "01"  # v=1
        v, r, s = _split_signature(sig)
        assert v == 28

    def test_split_invalid_length(self):
        """Signatures with wrong length should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid signature length"):
            _split_signature("0x" + "ab" * 33)  # 33 bytes


# ── ABI encoding ──────────────────────────────────────────────────────────


class TestAbiEncoding:
    def test_encode_transfer_with_authorization(self):
        """Verify ABI encoding produces correct structure."""
        result = abi_encode_transfer_with_authorization(
            from_addr="0x43Ab546B202033e4680aEB0923140Bc4105Edfed",
            to_addr="0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623",
            value="100000",
            valid_after="0",
            valid_before="1700000000",
            nonce="0x" + "de" * 32,
            v=27,
            r=b"\x01" * 32,
            s=b"\x02" * 32,
        )

        assert result.startswith("0x")
        assert result[2:10] == TRANSFER_WITH_AUTH_SELECTOR
        # 4 bytes selector + 9 * 32 bytes parameters = 4 + 288 = 292 bytes = 584 hex chars
        assert len(result) == 2 + 8 + 9 * 64  # 0x + selector + 9 params

    def test_encode_addresses_are_left_padded(self):
        """Addresses should be left-padded to 32 bytes."""
        result = abi_encode_transfer_with_authorization(
            from_addr="0x0000000000000000000000000000000000000001",
            to_addr="0x0000000000000000000000000000000000000002",
            value="0",
            valid_after="0",
            valid_before="0",
            nonce="0x" + "00" * 32,
            v=27,
            r=b"\x00" * 32,
            s=b"\x00" * 32,
        )

        # from address should be at offset 8 (after selector), padded to 64 chars
        from_slot = result[10 : 10 + 64]
        assert from_slot.endswith("0000000000000000000000000000000000000001")


# ── Off-chain signature verification ─────────────────────────────────────


class TestVerifyAuthorizationSignature:
    def test_valid_signature(self):
        """A correctly signed authorization should pass verification."""
        auth, sig, addr = _make_test_authorization_and_signature()
        result = verify_authorization_signature(auth, sig)
        assert result["valid"] is True
        assert result["recovered_signer"].lower() == addr.lower()

    def test_invalid_signer(self):
        """Signature from a different address should fail."""
        auth, sig, _ = _make_test_authorization_and_signature()
        # Change the 'from' to a different address
        auth["from"] = "0x0000000000000000000000000000000000000001"
        result = verify_authorization_signature(auth, sig)
        assert result["valid"] is False
        assert "mismatch" in result["error"].lower()

    def test_expired_authorization(self):
        """Authorization with validBefore in the past should fail."""
        auth, sig, _ = _make_test_authorization_and_signature()
        auth["validBefore"] = "1000"  # Way in the past (Unix timestamp)
        result = verify_authorization_signature(auth, sig)
        assert result["valid"] is False
        assert "expired" in result["error"].lower()

    def test_not_yet_valid_authorization(self):
        """Authorization with validAfter far in the future should fail."""
        auth, sig, _ = _make_test_authorization_and_signature()
        auth["validAfter"] = str(int(time.time()) + 999999)
        result = verify_authorization_signature(auth, sig)
        assert result["valid"] is False
        assert "not yet valid" in result["error"].lower()


# ── Settlement success path (mock RPC) ────────────────────────────────────


@pytest.mark.anyio
async def test_settle_success():
    """Full settlement path with mocked RPC calls."""
    auth, sig, payer_addr = _make_test_authorization_and_signature()

    payment_payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "base",
        "payload": {
            "authorization": auth,
            "signature": sig,
        },
    }
    payment_requirements = {
        "scheme": "exact",
        "network": "base",
        "maxAmountRequired": "100000",
        "payTo": "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623",
        "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    }

    # Mock RPC responses
    mock_rpc_responses = [
        # eth_getTransactionCount
        {"jsonrpc": "2.0", "result": "0x5", "id": 1},
        # eth_estimateGas
        {"jsonrpc": "2.0", "result": hex(65000), "id": 1},
        # eth_gasPrice
        {"jsonrpc": "2.0", "result": hex(100000000), "id": 1},  # 0.1 Gwei
        # eth_sendRawTransaction
        {"jsonrpc": "2.0", "result": "0x" + "ab" * 32, "id": 1},
        # eth_getTransactionReceipt (first poll)
        {"jsonrpc": "2.0", "result": {"status": "0x1", "blockNumber": "0x100"}, "id": 1},
    ]

    call_idx = 0

    async def mock_post(url, json=None, **kwargs):
        nonlocal call_idx
        resp = MagicMock()
        resp.json.return_value = mock_rpc_responses[call_idx]
        call_idx += 1
        return resp

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.dict(os.environ, {"RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY}, clear=False),
        patch("services.x402_local_settlement.httpx.AsyncClient", return_value=mock_client),
        patch("services.x402_local_settlement._async_sleep", new_callable=AsyncMock),
    ):
        service = LocalX402Settlement()
        result = await service.verify_and_settle(payment_payload, payment_requirements)

    assert result["transaction"] == "0x" + "ab" * 32
    assert result["network"] == "base"
    assert result["payer"].lower() == payer_addr.lower()
    assert "payment_response_header" in result
    assert result["verify"]["isValid"] is True
    assert result["settle"]["success"] is True


# ── Settlement failure: gas/revert ────────────────────────────────────────


@pytest.mark.anyio
async def test_settle_revert():
    """Settlement should fail when the on-chain transaction reverts."""
    auth, sig, _ = _make_test_authorization_and_signature()

    payment_payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "base",
        "payload": {"authorization": auth, "signature": sig},
    }
    payment_requirements = {"maxAmountRequired": "100000"}

    mock_rpc_responses = [
        {"jsonrpc": "2.0", "result": "0x5", "id": 1},           # nonce
        {"jsonrpc": "2.0", "result": hex(65000), "id": 1},      # gas estimate
        {"jsonrpc": "2.0", "result": hex(100000000), "id": 1},  # gas price
        {"jsonrpc": "2.0", "result": "0x" + "ab" * 32, "id": 1},  # sendRawTx
        # Receipt: reverted
        {"jsonrpc": "2.0", "result": {"status": "0x0", "blockNumber": "0x100"}, "id": 1},
    ]

    call_idx = 0

    async def mock_post(url, json=None, **kwargs):
        nonlocal call_idx
        resp = MagicMock()
        resp.json.return_value = mock_rpc_responses[call_idx]
        call_idx += 1
        return resp

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.dict(os.environ, {"RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY}, clear=False),
        patch("services.x402_local_settlement.httpx.AsyncClient", return_value=mock_client),
        patch("services.x402_local_settlement._async_sleep", new_callable=AsyncMock),
        pytest.raises(SettlementOnChainFailed, match="reverted"),
    ):
        service = LocalX402Settlement()
        await service.verify_and_settle(payment_payload, payment_requirements)


@pytest.mark.anyio
async def test_settle_send_failure():
    """Settlement should fail when eth_sendRawTransaction returns an RPC error."""
    auth, sig, _ = _make_test_authorization_and_signature()

    payment_payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "base",
        "payload": {"authorization": auth, "signature": sig},
    }
    payment_requirements = {"maxAmountRequired": "100000"}

    mock_rpc_responses = [
        {"jsonrpc": "2.0", "result": "0x5", "id": 1},
        {"jsonrpc": "2.0", "result": hex(65000), "id": 1},
        {"jsonrpc": "2.0", "result": hex(100000000), "id": 1},
        # sendRawTransaction error
        {"jsonrpc": "2.0", "error": {"code": -32000, "message": "insufficient funds"}, "id": 1},
    ]

    call_idx = 0

    async def mock_post(url, json=None, **kwargs):
        nonlocal call_idx
        resp = MagicMock()
        resp.json.return_value = mock_rpc_responses[call_idx]
        call_idx += 1
        return resp

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.dict(os.environ, {"RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY}, clear=False),
        patch("services.x402_local_settlement.httpx.AsyncClient", return_value=mock_client),
        patch("services.x402_local_settlement._async_sleep", new_callable=AsyncMock),
        pytest.raises(SettlementOnChainFailed, match="submission failed"),
    ):
        service = LocalX402Settlement()
        await service.verify_and_settle(payment_payload, payment_requirements)


# ── Settlement failure: timeout ───────────────────────────────────────────


@pytest.mark.anyio
async def test_settle_timeout():
    """Settlement should handle receipt timeout gracefully.

    When the receipt never arrives within the poll window, the tx is still
    submitted — the service logs a warning but doesn't raise (tx will
    eventually confirm on-chain).
    """
    auth, sig, payer_addr = _make_test_authorization_and_signature()

    payment_payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "base",
        "payload": {"authorization": auth, "signature": sig},
    }
    payment_requirements = {"maxAmountRequired": "100000"}

    mock_rpc_responses = [
        {"jsonrpc": "2.0", "result": "0x5", "id": 1},
        {"jsonrpc": "2.0", "result": hex(65000), "id": 1},
        {"jsonrpc": "2.0", "result": hex(100000000), "id": 1},
        {"jsonrpc": "2.0", "result": "0x" + "ab" * 32, "id": 1},
    ]

    call_idx = 0

    async def mock_post(url, json=None, **kwargs):
        nonlocal call_idx
        if call_idx < len(mock_rpc_responses):
            resp = MagicMock()
            resp.json.return_value = mock_rpc_responses[call_idx]
            call_idx += 1
            return resp
        # Receipt polls always return null
        resp = MagicMock()
        resp.json.return_value = {"jsonrpc": "2.0", "result": None, "id": 1}
        return resp

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # Patch RECEIPT_POLL_TIMEOUT to 0 so it exits immediately
    with (
        patch.dict(os.environ, {"RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY}, clear=False),
        patch("services.x402_local_settlement.httpx.AsyncClient", return_value=mock_client),
        patch("services.x402_local_settlement._async_sleep", new_callable=AsyncMock),
        patch("services.x402_local_settlement.RECEIPT_POLL_TIMEOUT", 0),
    ):
        service = LocalX402Settlement()
        result = await service.verify_and_settle(payment_payload, payment_requirements)

    # Should still return the tx_hash even without receipt
    assert result["transaction"] == "0x" + "ab" * 32


# ── Nonce management ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_nonce_fetched_from_rpc():
    """Settlement should use the nonce from eth_getTransactionCount."""
    auth, sig, _ = _make_test_authorization_and_signature()

    payment_payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "base",
        "payload": {"authorization": auth, "signature": sig},
    }
    payment_requirements = {"maxAmountRequired": "100000"}

    rpc_calls = []

    async def mock_post(url, json=None, **kwargs):
        rpc_calls.append(json)
        resp = MagicMock()
        method = json.get("method") if json else ""
        if method == "eth_getTransactionCount":
            resp.json.return_value = {"jsonrpc": "2.0", "result": "0xa", "id": 1}  # nonce=10
        elif method == "eth_estimateGas":
            resp.json.return_value = {"jsonrpc": "2.0", "result": hex(65000), "id": 1}
        elif method == "eth_gasPrice":
            resp.json.return_value = {"jsonrpc": "2.0", "result": hex(100000000), "id": 1}
        elif method == "eth_sendRawTransaction":
            resp.json.return_value = {"jsonrpc": "2.0", "result": "0x" + "ab" * 32, "id": 1}
        elif method == "eth_getTransactionReceipt":
            resp.json.return_value = {"jsonrpc": "2.0", "result": {"status": "0x1"}, "id": 1}
        else:
            resp.json.return_value = {"jsonrpc": "2.0", "result": None, "id": 1}
        return resp

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.dict(os.environ, {"RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY}, clear=False),
        patch("services.x402_local_settlement.httpx.AsyncClient", return_value=mock_client),
        patch("services.x402_local_settlement._async_sleep", new_callable=AsyncMock),
    ):
        service = LocalX402Settlement()
        await service.verify_and_settle(payment_payload, payment_requirements)

    # Verify eth_getTransactionCount was called
    nonce_calls = [c for c in rpc_calls if c and c.get("method") == "eth_getTransactionCount"]
    assert len(nonce_calls) == 1


# ── Wallet ETH balance ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_wallet_eth_balance_success():
    """Balance check should return correct ETH conversion."""
    async def mock_post(url, json=None, **kwargs):
        resp = MagicMock()
        # 0.005 ETH in wei = 5000000000000000
        resp.json.return_value = {"jsonrpc": "2.0", "result": hex(5000000000000000), "id": 1}
        return resp

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.dict(os.environ, {"RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY}, clear=False),
        patch("services.x402_local_settlement.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await get_wallet_eth_balance()

    assert result["balance_eth"] == pytest.approx(0.005, rel=1e-6)
    assert result["low"] is False  # 0.005 > 0.001 threshold
    assert result["critical"] is False


@pytest.mark.anyio
async def test_get_wallet_eth_balance_low():
    """Balance below threshold should report low/critical."""
    async def mock_post(url, json=None, **kwargs):
        resp = MagicMock()
        # 0.0003 ETH = 300000000000000 wei
        resp.json.return_value = {"jsonrpc": "2.0", "result": hex(300000000000000), "id": 1}
        return resp

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.dict(os.environ, {"RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY}, clear=False),
        patch("services.x402_local_settlement.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await get_wallet_eth_balance()

    assert result["balance_eth"] == pytest.approx(0.0003, rel=1e-6)
    assert result["low"] is True
    assert result["critical"] is True


@pytest.mark.anyio
async def test_get_wallet_eth_balance_not_configured():
    """Should return error when no private key is set."""
    with patch.dict(os.environ, {"RHUMB_SETTLEMENT_PRIVATE_KEY": ""}, clear=False):
        result = await get_wallet_eth_balance()
    assert result.get("error") == "not_configured"
