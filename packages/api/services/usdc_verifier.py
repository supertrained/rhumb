"""USDC payment verification via Base RPC.

Verifies that a canonical USDC transfer occurred on-chain for the
expected recipient, sender, and minimum amount. Uses
``eth_getTransactionReceipt`` + Transfer event topic decoding.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

# ERC-20 Transfer(address indexed from, address indexed to, uint256 value)
TRANSFER_EVENT_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)

# RPC endpoints
BASE_MAINNET_RPC = "https://mainnet.base.org"
BASE_SEPOLIA_RPC = "https://sepolia.base.org"

# USDC contract addresses on Base
USDC_BASE_MAINNET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


async def verify_usdc_payment(
    tx_hash: str,
    expected_to: str,
    expected_amount_atomic: str | None = None,
    expected_from: str | None = None,
    network: str = "base-sepolia",
) -> dict:
    """Verify a USDC transfer on Base chain.

    Fetches the transaction receipt from an RPC node, then scans logs for
    a canonical USDC Transfer event matching the expected recipient. The
    transaction is only accepted when exactly one such transfer exists.

    Args:
        tx_hash: Transaction hash (0x-prefixed hex).
        expected_to: Expected recipient wallet address.
        expected_amount_atomic: Minimum expected amount in USDC atomic units
            (6 decimals). ``None`` disables amount validation.
        expected_from: Expected sender wallet address. ``None`` disables sender
            validation.
        network: ``"base"`` or ``"base-sepolia"`` (also accepts
            ``"evm:8453"``, ``"evm:84532"``, and legacy ``"base-mainnet"``).

    Returns:
        ``{"valid": True, "from_address": "0x…", "to_address": "0x…", …}``
        on success, or ``{"valid": False, "error": "reason"}`` on failure.
    """
    # Accept seller-advertised names plus older aliases.
    if network in ("base", "evm:8453", "base-mainnet"):
        rpc_url = BASE_MAINNET_RPC
        usdc_contract = USDC_BASE_MAINNET
    elif network in ("evm:84532", "base-sepolia"):
        rpc_url = BASE_SEPOLIA_RPC
        usdc_contract = USDC_BASE_SEPOLIA
    else:
        return {"valid": False, "error": f"Unsupported network: {network}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            receipt_resp = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_getTransactionReceipt",
                    "params": [tx_hash],
                    "id": 1,
                },
            )
            receipt = receipt_resp.json().get("result")

            if not receipt:
                return {
                    "valid": False,
                    "error": "Transaction not found or not yet confirmed",
                }

            # Check transaction succeeded (status 0x1)
            if receipt.get("status") != "0x1":
                return {"valid": False, "error": "Transaction reverted"}

            block_number_hex = receipt.get("blockNumber")
            if not block_number_hex:
                return {"valid": False, "error": "Transaction receipt missing block number"}

            block_number = int(block_number_hex, 16)

            latest_block_resp = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_blockNumber",
                    "params": [],
                    "id": 2,
                },
            )
            latest_block = int(latest_block_resp.json().get("result", "0x0"), 16)
            confirmations = latest_block - block_number + 1
            if confirmations < 1:
                return {
                    "valid": False,
                    "error": "Transaction not yet finalized",
                }

            matching_transfers: list[dict[str, str]] = []

            # Scan logs for canonical USDC Transfer events to the Rhumb wallet.
            for log_entry in receipt.get("logs", []):
                if log_entry.get("address", "").lower() != usdc_contract.lower():
                    continue

                topics = log_entry.get("topics", [])
                if len(topics) < 3 or topics[0] != TRANSFER_EVENT_TOPIC:
                    continue

                # Decode Transfer(from, to, amount)
                # topics[1] = from address (zero-padded to 32 bytes)
                # topics[2] = to address (zero-padded to 32 bytes)
                # data     = amount (uint256)
                log_from = "0x" + topics[1][-40:]
                log_to = "0x" + topics[2][-40:]
                if log_to.lower() != expected_to.lower():
                    continue

                matching_transfers.append(
                    {
                        "from_address": log_from,
                        "to_address": log_to,
                        "amount_atomic": str(int(log_entry.get("data", "0x0"), 16)),
                    }
                )

            if not matching_transfers:
                return {
                    "valid": False,
                    "error": "No payment found for Rhumb wallet in transaction",
                }

            if len(matching_transfers) > 1:
                return {
                    "valid": False,
                    "error": "Ambiguous transaction: multiple transfers to Rhumb detected",
                }

            transfer = matching_transfers[0]

            if expected_from and transfer["from_address"].lower() != expected_from.lower():
                return {
                    "valid": False,
                    "error": "Payment sender does not match declared wallet",
                }

            if expected_amount_atomic is not None:
                paid_amount = int(transfer["amount_atomic"])
                expected_amount = int(expected_amount_atomic)
                if paid_amount < expected_amount:
                    return {
                        "valid": False,
                        "error": (
                            "Underpayment detected: "
                            f"paid {transfer['amount_atomic']} atomic, "
                            f"expected at least {expected_amount_atomic}"
                        ),
                    }

            return {
                "valid": True,
                "from_address": transfer["from_address"],
                "to_address": transfer["to_address"],
                "amount_atomic": transfer["amount_atomic"],
                "block_number": block_number,
                "confirmations": confirmations,
                "token_address": usdc_contract,
                "tx_hash": tx_hash,
            }

    except httpx.TimeoutException:
        return {"valid": False, "error": "RPC timeout"}
    except Exception as e:
        logger.error("USDC verification error: %s", e)
        return {"valid": False, "error": f"Verification failed: {str(e)}"}
