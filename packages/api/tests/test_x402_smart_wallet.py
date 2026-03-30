"""Smart wallet verification tests for x402 local settlement."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data

import services.x402_local_settlement as settlement
from services.x402_local_settlement import (
    LocalX402Settlement,
    abi_encode_transfer_with_authorization_bytes,
    verify_authorization_signature,
)


TEST_PRIVATE_KEY = "0x" + "ab" * 32
SMART_WALLET_ADDRESS = "0x1111111111111111111111111111111111111111"


def _make_eoa_authorization_and_signature() -> tuple[dict[str, str], str, str]:
    account = Account.from_key(TEST_PRIVATE_KEY)
    now = int(time.time())

    authorization = {
        "from": account.address,
        "to": "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623",
        "value": "100000",  # 0.10 USDC
        "validAfter": "0",
        "validBefore": str(now + 3600),
        "nonce": "0x" + "de" * 32,
    }

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

    return authorization, "0x" + signed.signature.hex(), account.address


def _make_smart_wallet_authorization(value: str = "100000") -> dict[str, str]:
    now = int(time.time())
    return {
        "from": SMART_WALLET_ADDRESS,
        "to": "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623",
        "value": value,
        "validAfter": "0",
        "validBefore": str(now + 3600),
        "nonce": "0x" + "ab" * 32,
    }


@pytest.fixture(autouse=True)
def _clear_contract_code_cache():
    settlement._CONTRACT_CODE_CACHE.clear()


@pytest.mark.anyio
async def test_eoa_65_byte_signature_passes_regression():
    auth, sig, addr = _make_eoa_authorization_and_signature()

    with patch("services.x402_local_settlement._rpc_call", new=AsyncMock()) as rpc_mock:
        result = await verify_authorization_signature(auth, sig)

    assert result["valid"] is True
    assert result["recovered_signer"].lower() == addr.lower()
    rpc_mock.assert_not_called()


@pytest.mark.anyio
async def test_eoa_64_byte_signature_passes_regression():
    auth, sig, addr = _make_eoa_authorization_and_signature()
    sig_bytes = bytes.fromhex(sig.replace("0x", ""))
    compact_sig = "0x" + sig_bytes[:64].hex()  # r || s, no v

    with patch("services.x402_local_settlement._rpc_call", new=AsyncMock()) as rpc_mock:
        result = await verify_authorization_signature(auth, compact_sig)

    assert result["valid"] is True
    assert result["recovered_signer"].lower() == addr.lower()
    rpc_mock.assert_not_called()


@pytest.mark.anyio
async def test_smart_wallet_signature_passes_when_contract_and_balance_ok():
    auth = _make_smart_wallet_authorization(value="100000")
    smart_wallet_sig = "0x" + "cd" * 640

    async def rpc_side_effect(method, params, rpc_url=settlement.BASE_MAINNET_RPC, **kwargs):
        if method == "eth_getCode":
            return "0x6001600155"
        if method == "eth_call":
            to_addr = params[0]["to"].lower()
            if to_addr == SMART_WALLET_ADDRESS.lower():
                return "0x1626ba7e"
            if to_addr == settlement.USDC_BASE_MAINNET.lower():
                return hex(1_000_000)
        raise AssertionError(f"Unexpected RPC call: method={method}, params={params}")

    with patch("services.x402_local_settlement._rpc_call", new=AsyncMock(side_effect=rpc_side_effect)):
        result = await verify_authorization_signature(auth, smart_wallet_sig)

    assert result["valid"] is True
    assert result["recovered_signer"].lower() == SMART_WALLET_ADDRESS.lower()


@pytest.mark.anyio
async def test_65_byte_owner_signature_falls_through_to_erc1271_for_contract_wallet():
    owner_auth, owner_sig, owner_addr = _make_eoa_authorization_and_signature()
    auth = {**owner_auth, "from": SMART_WALLET_ADDRESS}

    async def rpc_side_effect(method, params, rpc_url=settlement.BASE_MAINNET_RPC, **kwargs):
        if method == "eth_getCode":
            return "0x6001600155"
        if method == "eth_call":
            to_addr = params[0]["to"].lower()
            if to_addr == SMART_WALLET_ADDRESS.lower():
                return "0x1626ba7e"
            if to_addr == settlement.USDC_BASE_MAINNET.lower():
                return hex(1_000_000)
        raise AssertionError(f"Unexpected RPC call: method={method}, params={params}")

    with patch("services.x402_local_settlement._rpc_call", new=AsyncMock(side_effect=rpc_side_effect)):
        result = await verify_authorization_signature(auth, owner_sig)

    assert result["valid"] is True
    assert result["recovered_signer"].lower() == SMART_WALLET_ADDRESS.lower()
    assert owner_addr.lower() != SMART_WALLET_ADDRESS.lower()


@pytest.mark.anyio
async def test_smart_wallet_signature_fails_when_address_has_no_code():
    auth = _make_smart_wallet_authorization()
    smart_wallet_sig = "0x" + "cd" * 640

    async def rpc_side_effect(method, params, rpc_url=settlement.BASE_MAINNET_RPC, **kwargs):
        if method == "eth_getCode":
            return "0x"
        raise AssertionError(f"Unexpected RPC call: method={method}, params={params}")

    with patch("services.x402_local_settlement._rpc_call", new=AsyncMock(side_effect=rpc_side_effect)):
        result = await verify_authorization_signature(auth, smart_wallet_sig)

    assert result["valid"] is False
    assert result["error_code"] == "smart_wallet_not_contract"


@pytest.mark.anyio
async def test_smart_wallet_signature_fails_on_wrong_magic_value():
    auth = _make_smart_wallet_authorization()
    smart_wallet_sig = "0x" + "cd" * 640

    async def rpc_side_effect(method, params, rpc_url=settlement.BASE_MAINNET_RPC, **kwargs):
        if method == "eth_getCode":
            return "0x6001600155"
        if method == "eth_call":
            to_addr = params[0]["to"].lower()
            if to_addr == SMART_WALLET_ADDRESS.lower():
                return "0x00000000"
            raise AssertionError(f"Unexpected eth_call target: {to_addr}")
        raise AssertionError(f"Unexpected RPC call: method={method}, params={params}")

    with patch("services.x402_local_settlement._rpc_call", new=AsyncMock(side_effect=rpc_side_effect)):
        result = await verify_authorization_signature(auth, smart_wallet_sig)

    assert result["valid"] is False
    assert result["error_code"] == "smart_wallet_signature_invalid"


@pytest.mark.anyio
async def test_smart_wallet_signature_fails_on_insufficient_balance():
    auth = _make_smart_wallet_authorization(value="100000")
    smart_wallet_sig = "0x" + "cd" * 640

    async def rpc_side_effect(method, params, rpc_url=settlement.BASE_MAINNET_RPC, **kwargs):
        if method == "eth_getCode":
            return "0x6001600155"
        if method == "eth_call":
            to_addr = params[0]["to"].lower()
            if to_addr == SMART_WALLET_ADDRESS.lower():
                return "0x1626ba7e"
            if to_addr == settlement.USDC_BASE_MAINNET.lower():
                return "0x0"
            raise AssertionError(f"Unexpected eth_call target: {to_addr}")
        raise AssertionError(f"Unexpected RPC call: method={method}, params={params}")

    with patch("services.x402_local_settlement._rpc_call", new=AsyncMock(side_effect=rpc_side_effect)):
        result = await verify_authorization_signature(auth, smart_wallet_sig)

    assert result["valid"] is False
    assert result["error_code"] == "smart_wallet_insufficient_balance"


@pytest.mark.anyio
async def test_signature_over_2048_bytes_fails_with_size_guard():
    auth = _make_smart_wallet_authorization()
    oversized_sig = "0x" + "ab" * 2049

    with patch("services.x402_local_settlement._rpc_call", new=AsyncMock()) as rpc_mock:
        result = await verify_authorization_signature(auth, oversized_sig)

    assert result["valid"] is False
    assert result["error_code"] == "signature_too_large"
    rpc_mock.assert_not_called()


@pytest.mark.anyio
async def test_smart_wallet_signature_timeout_on_is_valid_signature():
    auth = _make_smart_wallet_authorization()
    smart_wallet_sig = "0x" + "cd" * 640

    async def rpc_side_effect(method, params, rpc_url=settlement.BASE_MAINNET_RPC, **kwargs):
        if method == "eth_getCode":
            return "0x6001600155"
        if method == "eth_call":
            to_addr = params[0]["to"].lower()
            if to_addr == SMART_WALLET_ADDRESS.lower():
                raise httpx.TimeoutException("isValidSignature timeout")
            raise AssertionError(f"Unexpected eth_call target: {to_addr}")
        raise AssertionError(f"Unexpected RPC call: method={method}, params={params}")

    with patch("services.x402_local_settlement._rpc_call", new=AsyncMock(side_effect=rpc_side_effect)):
        result = await verify_authorization_signature(auth, smart_wallet_sig)

    assert result["valid"] is False
    assert result["error_code"] == "smart_wallet_signature_timeout"
    assert result["retryable_with_facilitator"] is True


def test_abi_encode_transfer_with_authorization_bytes_structure():
    signature_bytes = bytes.fromhex("ab" * 640)
    call_data = abi_encode_transfer_with_authorization_bytes(
        from_addr=SMART_WALLET_ADDRESS,
        to_addr="0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623",
        value="100000",
        valid_after="0",
        valid_before="1700000000",
        nonce="0x" + "11" * 32,
        signature_bytes=signature_bytes,
    )

    encoded = call_data[2:]
    assert encoded[:8] == settlement.TRANSFER_WITH_AUTH_BYTES_SELECTOR

    # Slot 6 (offset for bytes arg) is after 6 static params.
    # Layout: selector (8 hex chars) + 6 slots * 64 chars -> offset slot starts there.
    offset_slot_start = 8 + (6 * 64)
    offset_slot = encoded[offset_slot_start : offset_slot_start + 64]
    assert int(offset_slot, 16) == 7 * 32


@pytest.mark.anyio
async def test_verify_and_settle_uses_bytes_variant_for_long_signature():
    service = LocalX402Settlement(rpc_url="https://rpc.example")

    long_sig = "0x" + "cd" * 640
    payment_payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "base",
        "payload": {
            "authorization": {
                "from": SMART_WALLET_ADDRESS,
                "to": "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623",
                "value": "100000",
                "validAfter": "0",
                "validBefore": str(int(time.time()) + 3600),
                "nonce": "0x" + "ab" * 32,
            },
            "signature": long_sig,
        },
    }
    payment_requirements = {"maxAmountRequired": "100000"}

    observed_call_data: dict[str, str] = {}

    async def rpc_side_effect(method, params, rpc_url=settlement.BASE_MAINNET_RPC, **kwargs):
        if method == "eth_getTransactionCount":
            return "0x1"
        if method == "eth_estimateGas":
            observed_call_data["data"] = params[0]["data"]
            return hex(65000)
        if method == "eth_gasPrice":
            return hex(100000000)
        if method == "eth_sendRawTransaction":
            return "0x" + "ab" * 32
        if method == "eth_getTransactionReceipt":
            return {"status": "0x1", "blockNumber": "0x100"}
        raise AssertionError(f"Unexpected RPC call: method={method}")

    with (
        patch("services.x402_local_settlement.verify_authorization_signature", new=AsyncMock(return_value={"valid": True, "recovered_signer": SMART_WALLET_ADDRESS})),
        patch("services.x402_local_settlement._rpc_call", new=AsyncMock(side_effect=rpc_side_effect)),
        patch("services.x402_local_settlement._async_sleep", new_callable=AsyncMock),
        patch.dict("os.environ", {"RHUMB_SETTLEMENT_PRIVATE_KEY": TEST_PRIVATE_KEY}, clear=False),
    ):
        result = await service.verify_and_settle(payment_payload, payment_requirements)

    assert result["transaction"].startswith("0x")
    assert observed_call_data["data"][2:10] == settlement.TRANSFER_WITH_AUTH_BYTES_SELECTOR
