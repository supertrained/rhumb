"""Local EIP-3009 settlement for standard x402 authorization payloads.

Settles USDC payments on Base mainnet by calling ``transferWithAuthorization``
on the USDC contract.  This avoids dependency on an external facilitator and
works on mainnet immediately.

The buyer signs an EIP-3009 authorization off-chain.  Rhumb's settlement
wallet submits the pre-signed authorization on-chain, paying only gas (ETH).
The USDC moves directly from the buyer to Rhumb's ``payTo`` address.

Requires:
    - ``RHUMB_SETTLEMENT_PRIVATE_KEY`` env var (hex-encoded private key)
    - A small ETH balance in the settlement wallet for gas on Base
    - ``eth-account`` package for transaction signing and signature recovery
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

BASE_MAINNET_RPC = "https://mainnet.base.org"
BASE_CHAIN_ID = 8453

# USDC on Base mainnet
USDC_BASE_MAINNET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# EIP-712 domain for USDC on Base mainnet (used for signature verification)
USDC_EIP712_DOMAIN = {
    "name": "USD Coin",
    "version": "2",
    "chainId": BASE_CHAIN_ID,
    "verifyingContract": USDC_BASE_MAINNET,
}

# EIP-712 type definition for TransferWithAuthorization
TRANSFER_WITH_AUTHORIZATION_TYPES = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ],
}

# transferWithAuthorization(address,address,uint256,uint256,uint256,bytes32,uint8,bytes32,bytes32)
# Function selector: keccak256 of the above signature, first 4 bytes
# Pre-computed: 0xe3ee160e
TRANSFER_WITH_AUTH_SELECTOR = "e3ee160e"

# Gas safety margin (20%)
GAS_SAFETY_MARGIN = 1.2

# Default gas limit if estimation fails (transferWithAuthorization is ~65k gas)
DEFAULT_GAS_LIMIT = 100_000

# Receipt polling
RECEIPT_POLL_INTERVAL = 2.0  # seconds
RECEIPT_POLL_TIMEOUT = 30.0  # seconds

# Health thresholds (ETH)
ETH_LOW_THRESHOLD = 0.001
ETH_CRITICAL_THRESHOLD = 0.0005


# ── ABI Encoding Helpers ──────────────────────────────────────────────────


def _to_uint256(value: str | int) -> str:
    """Encode a value as a 256-bit hex string (64 chars, no 0x prefix)."""
    if isinstance(value, str):
        value = int(value, 16) if value.startswith("0x") else int(value)
    return format(value, "064x")


def _to_address(addr: str) -> str:
    """Encode an address as a 256-bit hex string (left-padded, no 0x prefix)."""
    return addr.lower().replace("0x", "").rjust(64, "0")


def _to_bytes32(value: str | bytes) -> str:
    """Encode a bytes32 value as a 64-char hex string (no 0x prefix)."""
    if isinstance(value, bytes):
        return value.hex().ljust(64, "0")
    hex_str = value.replace("0x", "")
    return hex_str.ljust(64, "0")


def _to_uint8(value: int) -> str:
    """Encode a uint8 as a 256-bit hex string (left-padded, no 0x prefix)."""
    return format(value, "064x")


def _split_signature(signature: str) -> tuple[int, bytes, bytes]:
    """Split a hex signature into (v, r, s).

    Handles both 65-byte (r + s + v) and 64-byte (r + s) formats.
    For 65-byte signatures, the last byte is v.
    """
    sig_bytes = bytes.fromhex(signature.replace("0x", ""))
    if len(sig_bytes) == 65:
        r = sig_bytes[:32]
        s = sig_bytes[32:64]
        v = sig_bytes[64]
        # Normalize v: some signers use 0/1 instead of 27/28
        if v < 27:
            v += 27
        return v, r, s
    elif len(sig_bytes) == 64:
        r = sig_bytes[:32]
        s = sig_bytes[32:64]
        # Default v=27; caller should try both if recovery fails
        return 27, r, s
    else:
        raise ValueError(f"Invalid signature length: {len(sig_bytes)} bytes (expected 64 or 65)")


def abi_encode_transfer_with_authorization(
    from_addr: str,
    to_addr: str,
    value: str | int,
    valid_after: str | int,
    valid_before: str | int,
    nonce: str | bytes,
    v: int,
    r: bytes,
    s: bytes,
) -> str:
    """ABI-encode a ``transferWithAuthorization`` call.

    Returns the full call data as a hex string with ``0x`` prefix.
    """
    return (
        "0x"
        + TRANSFER_WITH_AUTH_SELECTOR
        + _to_address(from_addr)
        + _to_address(to_addr)
        + _to_uint256(value)
        + _to_uint256(valid_after)
        + _to_uint256(valid_before)
        + _to_bytes32(nonce)
        + _to_uint8(v)
        + _to_bytes32(r.hex() if isinstance(r, bytes) else r)
        + _to_bytes32(s.hex() if isinstance(s, bytes) else s)
    )


# ── Signature Verification ────────────────────────────────────────────────


def verify_authorization_signature(
    authorization: dict[str, Any],
    signature: str,
) -> dict[str, Any]:
    """Verify an EIP-3009 TransferWithAuthorization signature off-chain.

    Recovers the signer from the EIP-712 typed data signature and checks:
    1. The recovered address matches ``authorization["from"]``
    2. ``validBefore`` is in the future (not expired)
    3. ``validAfter`` is in the past or now (already valid)

    Returns ``{"valid": True, "recovered_signer": "0x..."}`` on success,
    or ``{"valid": False, "error": "reason"}`` on failure.
    """
    from_addr = authorization.get("from", "")
    to_addr = authorization.get("to", "")
    value = authorization.get("value", "0")
    valid_after = authorization.get("validAfter", "0")
    valid_before = authorization.get("validBefore", "0")
    nonce = authorization.get("nonce", "0x" + "00" * 32)

    # Convert to integers for time checks
    valid_after_int = int(valid_after, 16) if isinstance(valid_after, str) and valid_after.startswith("0x") else int(valid_after)
    valid_before_int = int(valid_before, 16) if isinstance(valid_before, str) and valid_before.startswith("0x") else int(valid_before)
    now = int(time.time())

    if valid_before_int != 0 and now >= valid_before_int:
        return {"valid": False, "error": f"Authorization expired: validBefore={valid_before_int}, now={now}"}

    if valid_after_int != 0 and now < valid_after_int:
        return {"valid": False, "error": f"Authorization not yet valid: validAfter={valid_after_int}, now={now}"}

    # Convert value for EIP-712
    value_int = int(value, 16) if isinstance(value, str) and value.startswith("0x") else int(value)

    # Ensure nonce is bytes32
    if isinstance(nonce, str):
        nonce_hex = nonce.replace("0x", "").ljust(64, "0")
        nonce_bytes = bytes.fromhex(nonce_hex)
    else:
        nonce_bytes = nonce

    # Build EIP-712 typed data for signature recovery
    message_data = {
        "from": from_addr,
        "to": to_addr,
        "value": value_int,
        "validAfter": valid_after_int,
        "validBefore": valid_before_int,
        "nonce": nonce_bytes,
    }

    try:
        signable = encode_typed_data(
            domain_data=USDC_EIP712_DOMAIN,
            message_types=TRANSFER_WITH_AUTHORIZATION_TYPES,
            message_data=message_data,
        )
        recovered = Account.recover_message(signable, signature=bytes.fromhex(signature.replace("0x", "")))
    except Exception as e:
        return {"valid": False, "error": f"Signature recovery failed: {e}"}

    if recovered.lower() != from_addr.lower():
        return {
            "valid": False,
            "error": f"Signer mismatch: recovered {recovered}, expected {from_addr}",
        }

    return {"valid": True, "recovered_signer": recovered}


# ── On-Chain Settlement ───────────────────────────────────────────────────


async def _rpc_call(method: str, params: list, rpc_url: str = BASE_MAINNET_RPC) -> Any:
    """Make a JSON-RPC call to the Base node."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            rpc_url,
            json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
        )
        result = resp.json()
        if "error" in result and result["error"]:
            raise RuntimeError(f"RPC error: {result['error']}")
        return result.get("result")


async def get_wallet_eth_balance(wallet_address: str | None = None) -> dict[str, Any]:
    """Get ETH balance for the settlement wallet.

    Returns ``{"balance_wei": int, "balance_eth": float, "low": bool, "critical": bool}``.
    """
    if wallet_address is None:
        private_key = os.environ.get("RHUMB_SETTLEMENT_PRIVATE_KEY", "").strip()
        if not private_key:
            return {"balance_wei": 0, "balance_eth": 0.0, "low": True, "critical": True, "error": "not_configured"}
        account = Account.from_key(private_key)
        wallet_address = account.address

    try:
        balance_hex = await _rpc_call("eth_getBalance", [wallet_address, "latest"])
        balance_wei = int(balance_hex, 16)
        balance_eth = balance_wei / 1e18
        return {
            "balance_wei": balance_wei,
            "balance_eth": balance_eth,
            "low": balance_eth < ETH_LOW_THRESHOLD,
            "critical": balance_eth < ETH_CRITICAL_THRESHOLD,
        }
    except Exception as e:
        logger.warning("Failed to fetch settlement wallet ETH balance: %s", e)
        return {"balance_wei": 0, "balance_eth": 0.0, "low": True, "critical": True, "error": str(e)}


class LocalX402Settlement:
    """Settle standard x402 authorization payloads on Base mainnet.

    Submits ``transferWithAuthorization`` on-chain using Rhumb's settlement
    wallet for gas.
    """

    def __init__(self, rpc_url: str = BASE_MAINNET_RPC):
        self._rpc_url = rpc_url

    def is_configured(self) -> bool:
        """Return True if the settlement private key is available."""
        return bool(os.environ.get("RHUMB_SETTLEMENT_PRIVATE_KEY", "").strip())

    def _get_account(self) -> Account:
        """Load the settlement wallet from env."""
        private_key = os.environ.get("RHUMB_SETTLEMENT_PRIVATE_KEY", "").strip()
        if not private_key:
            raise RuntimeError("RHUMB_SETTLEMENT_PRIVATE_KEY not configured")
        return Account.from_key(private_key)

    async def verify_and_settle(
        self,
        payment_payload: dict[str, Any],
        payment_requirements: dict[str, Any],
    ) -> dict[str, Any]:
        """Verify off-chain, then settle on-chain.

        Returns the same shape as the facilitator path::

            {
                "verify": {"isValid": True, "payer": "0x..."},
                "settle": {"success": True, "transaction": "0x...", "network": "base"},
                "payer": "0x...",
                "transaction": "0x...",
                "network": "base",
                "payment_response_header": "<base64>",
            }
        """
        import base64
        import json

        # Extract authorization + signature from payload
        payload_inner = payment_payload.get("payload", {})
        authorization = payload_inner.get("authorization", {})
        signature = payload_inner.get("signature", "")

        if not authorization or not signature:
            raise SettlementVerificationFailed("Missing authorization or signature in payment payload")

        # ── Step 1: Off-chain verification (no gas spent) ─────────────
        verification = verify_authorization_signature(authorization, signature)
        if not verification.get("valid"):
            raise SettlementVerificationFailed(verification.get("error", "Signature verification failed"))

        payer = authorization["from"]

        # Validate amount matches requirements
        required_amount = payment_requirements.get("maxAmountRequired") or payment_requirements.get("amount")
        if required_amount:
            auth_value = int(authorization.get("value", "0"))
            req_value = int(required_amount)
            if auth_value < req_value:
                raise SettlementVerificationFailed(
                    f"Underpayment: authorized {auth_value} atomic, required {req_value}"
                )

        verify_result = {"isValid": True, "payer": payer}

        # ── Step 2: Submit on-chain ───────────────────────────────────
        v, r, s = _split_signature(signature)

        call_data = abi_encode_transfer_with_authorization(
            from_addr=authorization["from"],
            to_addr=authorization["to"],
            value=authorization.get("value", "0"),
            valid_after=authorization.get("validAfter", "0"),
            valid_before=authorization.get("validBefore", "0"),
            nonce=authorization.get("nonce", "0x" + "00" * 32),
            v=v,
            r=r,
            s=s,
        )

        account = self._get_account()

        # Get nonce for the settlement wallet
        nonce_hex = await _rpc_call(
            "eth_getTransactionCount",
            [account.address, "latest"],
            self._rpc_url,
        )
        tx_nonce = int(nonce_hex, 16)

        # Estimate gas
        try:
            gas_estimate_hex = await _rpc_call(
                "eth_estimateGas",
                [{"from": account.address, "to": USDC_BASE_MAINNET, "data": call_data}],
                self._rpc_url,
            )
            gas_limit = int(int(gas_estimate_hex, 16) * GAS_SAFETY_MARGIN)
        except Exception as e:
            logger.warning("Gas estimation failed, using default: %s", e)
            gas_limit = DEFAULT_GAS_LIMIT

        # Get current gas price (Base uses EIP-1559 but legacy gasPrice works)
        gas_price_hex = await _rpc_call("eth_gasPrice", [], self._rpc_url)
        gas_price = int(gas_price_hex, 16)

        # Build and sign the transaction
        tx = {
            "nonce": tx_nonce,
            "gasPrice": gas_price,
            "gas": gas_limit,
            "to": USDC_BASE_MAINNET,
            "value": 0,
            "data": bytes.fromhex(call_data[2:]),  # strip 0x prefix
            "chainId": BASE_CHAIN_ID,
        }

        signed_tx = account.sign_transaction(tx)
        raw_tx_hex = "0x" + signed_tx.raw_transaction.hex()

        # Submit
        try:
            tx_hash = await _rpc_call(
                "eth_sendRawTransaction",
                [raw_tx_hex],
                self._rpc_url,
            )
        except RuntimeError as e:
            raise SettlementOnChainFailed(f"Transaction submission failed: {e}") from e

        if not tx_hash:
            raise SettlementOnChainFailed("eth_sendRawTransaction returned empty result")

        # ── Step 3: Poll for receipt ──────────────────────────────────
        receipt = None
        start = time.monotonic()
        while time.monotonic() - start < RECEIPT_POLL_TIMEOUT:
            try:
                receipt = await _rpc_call(
                    "eth_getTransactionReceipt",
                    [tx_hash],
                    self._rpc_url,
                )
                if receipt is not None:
                    break
            except Exception:
                pass
            await _async_sleep(RECEIPT_POLL_INTERVAL)

        if receipt is None:
            # Transaction submitted but not yet confirmed — return tx_hash
            # anyway; the caller records it and the tx will confirm shortly.
            logger.warning("Settlement tx %s submitted but receipt not yet available", tx_hash)

        if receipt and receipt.get("status") != "0x1":
            raise SettlementOnChainFailed(
                f"Settlement transaction reverted: tx_hash={tx_hash}"
            )

        settle_result = {
            "success": True,
            "transaction": tx_hash,
            "network": "base",
            "payer": payer,
            "settlement_method": "local_eip3009",
        }

        # Build the payment_response_header (base64-encoded JSON, same as facilitator)
        payment_response_header = base64.b64encode(
            json.dumps(settle_result, separators=(",", ":")).encode("utf-8")
        ).decode("utf-8")

        return {
            "verify": verify_result,
            "settle": settle_result,
            "payer": payer,
            "transaction": tx_hash,
            "network": "base",
            "payment_response_header": payment_response_header,
        }


async def _async_sleep(seconds: float) -> None:
    """Async sleep helper."""
    import asyncio
    await asyncio.sleep(seconds)


# ── Exceptions ────────────────────────────────────────────────────────────


class SettlementVerificationFailed(Exception):
    """Off-chain verification of the authorization signature failed."""


class SettlementOnChainFailed(Exception):
    """On-chain settlement transaction failed."""
