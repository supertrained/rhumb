"""x402 protocol compliance — machine-readable 402 responses for agent-native payments.

See https://x402.org for the protocol specification.

All 402 responses from the execute endpoint use this module to return
a structured body that tells agents exactly how to pay.
"""

from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse

# USDC contract addresses (Base chain)
USDC_BASE_MAINNET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"  # Testnet


def build_x402_response(
    capability_id: str,
    cost_usd_cents: int,
    resource_url: str,
    error: str = "Payment required for capability execution",
) -> dict:
    """Build an x402-compliant 402 response body.

    Follows the x402 open standard (https://github.com/coinbase/x402):
    - ``network`` uses ``evm:<chainId>`` format (``evm:8453`` for Base mainnet)
    - ``amount`` is USDC atomic units (6 decimals)
    - Top-level ``resource`` describes the protected endpoint
    - ``accepts`` contains one entry per payment scheme

    Includes both Stripe credit purchase and USDC payment options.
    Wallet address and network come from env vars (with safe defaults for testnet).
    """
    # Convert cents to USDC atomic units (6 decimals): $0.15 = 150000
    usdc_amount = str(cost_usd_cents * 10000)

    wallet_address = os.environ.get("RHUMB_USDC_WALLET_ADDRESS", "")
    api_base = os.environ.get(
        "API_BASE_URL", "https://api.rhumb.dev"
    )
    is_production = os.environ.get("RAILWAY_ENVIRONMENT", "") == "production"

    accepts: list[dict] = []

    # Option 1: Stripe credit purchase (always available)
    accepts.append(
        {
            "scheme": "stripe_checkout",
            "checkoutUrl": f"{api_base}/v1/billing/checkout",
            "description": f"Purchase Rhumb credits to execute {capability_id}",
            "minAmountUsd": max(cost_usd_cents / 100, 5.0),  # Minimum $5 checkout
        }
    )

    # Option 2: USDC on Base (only if wallet configured)
    if wallet_address:
        # x402 standard: network = "evm:<chainId>"
        # Base mainnet = chain 8453, Base Sepolia = chain 84532
        network = "evm:8453" if is_production else "evm:84532"
        usdc_contract = USDC_BASE_MAINNET if is_production else USDC_BASE_SEPOLIA
        accepts.append(
            {
                "scheme": "exact",
                "network": network,
                "amount": usdc_amount,
                "payTo": wallet_address,
                "maxTimeoutSeconds": 300,
                "asset": usdc_contract,
                "extra": {"name": "Rhumb", "version": "1"},
            }
        )

    return {
        "x402Version": 1,
        "error": error,
        "resource": {
            "url": resource_url,
            "description": f"Rhumb capability execution: {capability_id}",
            "mimeType": "application/json",
        },
        "accepts": accepts,
    }


# ---------------------------------------------------------------------------
# Custom exception + FastAPI handler
# ---------------------------------------------------------------------------


class PaymentRequiredException(Exception):
    """Raised when capability execution requires payment.

    Caught by the global exception handler registered in app.py, which
    returns an x402-compliant JSON response with the X-Payment header.
    """

    def __init__(
        self,
        capability_id: str,
        cost_usd_cents: int,
        resource_url: str,
        detail: str = "",
    ):
        self.capability_id = capability_id
        self.cost_usd_cents = cost_usd_cents
        self.resource_url = resource_url
        self.detail = detail


async def payment_required_handler(
    request: Request, exc: PaymentRequiredException
) -> JSONResponse:
    """Global FastAPI exception handler for PaymentRequiredException."""
    body = build_x402_response(
        capability_id=exc.capability_id,
        cost_usd_cents=exc.cost_usd_cents,
        resource_url=exc.resource_url or str(request.url),
        error=exc.detail or "Payment required",
    )
    return JSONResponse(
        status_code=402,
        content=body,
        headers={"X-Payment": "required"},
    )
