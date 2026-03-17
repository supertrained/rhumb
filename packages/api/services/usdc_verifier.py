"""USDC payment verification via Base RPC.

Verifies that a USDC transfer occurred on-chain matching the expected
amount, recipient, and asset. Uses eth_getTransactionReceipt + Transfer
event topic decoding.
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
    expected_amount_atomic: str,
    network: str = "base-sepolia",
) -> dict:
    """Verify a USDC transfer on Base chain.

    Fetches the transaction receipt from an RPC node, then scans logs for
    a Transfer event matching the expected recipient and amount.

    Args:
        tx_hash: Transaction hash (0x-prefixed hex).
        expected_to: Expected recipient wallet address.
        expected_amount_atomic: Expected amount in USDC atomic units (6 decimals).
        network: ``"base-mainnet"`` or ``"base-sepolia"``.

    Returns:
        ``{"valid": True, "from_address": "0x…", "to_address": "0x…", …}``
        on success, or ``{"valid": False, "error": "reason"}`` on failure.
    """
    rpc_url = BASE_MAINNET_RPC if network == "base-mainnet" else BASE_SEPOLIA_RPC
    usdc_contract = USDC_BASE_MAINNET if network == "base-mainnet" else USDC_BASE_SEPOLIA

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_getTransactionReceipt",
                    "params": [tx_hash],
                    "id": 1,
                },
            )
            data = resp.json()
            receipt = data.get("result")

            if not receipt:
                return {
                    "valid": False,
                    "error": "Transaction not found or not yet confirmed",
                }

            # Check transaction succeeded (status 0x1)
            if receipt.get("status") != "0x1":
                return {"valid": False, "error": "Transaction reverted"}

            # Scan logs for a matching USDC Transfer event
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
                log_amount = str(int(log_entry.get("data", "0x0"), 16))

                # Match recipient and amount
                if log_to.lower() != expected_to.lower():
                    continue
                if log_amount != expected_amount_atomic:
                    continue

                block_number = int(receipt.get("blockNumber", "0x0"), 16)

                return {
                    "valid": True,
                    "from_address": log_from,
                    "to_address": log_to,
                    "amount_atomic": log_amount,
                    "block_number": block_number,
                    "tx_hash": tx_hash,
                }

            return {
                "valid": False,
                "error": "No matching USDC Transfer event found in transaction",
            }

    except httpx.TimeoutException:
        return {"valid": False, "error": "RPC timeout"}
    except Exception as e:
        logger.error("USDC verification error: %s", e)
        return {"valid": False, "error": f"Verification failed: {str(e)}"}
