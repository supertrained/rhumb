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
    payment_request: dict | None = None,
) -> dict:
    """Build an x402-compliant 402 response body.

    Follows the x402 open standard (https://github.com/coinbase/x402):
    - ``network`` uses Coinbase buyer-compatible names (``base`` or ``base-sepolia``)
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
    payment_request_id = payment_request.get("id") if payment_request else None
    payment_network = payment_request.get("network") if payment_request else None
    payment_asset = payment_request.get("asset_address") if payment_request else None
    payment_pay_to = payment_request.get("pay_to_address") if payment_request else None
    payment_amount = payment_request.get("amount_usdc_atomic") if payment_request else None

    # Option 1: USDC on Base (first — x402 buyers expect exact scheme first)
    if wallet_address:
        network = payment_network or ("base" if is_production else "base-sepolia")
        usdc_contract = payment_asset or (USDC_BASE_MAINNET if is_production else USDC_BASE_SEPOLIA)
        pay_to = payment_pay_to or wallet_address
        amount = payment_amount or usdc_amount
        exact_option = {
            "scheme": "exact",
            "network": network,
            # Coinbase reference uses maxAmountRequired; include both for compat
            "maxAmountRequired": amount,
            "amount": amount,
            "resource": resource_url,
            "description": f"Rhumb capability execution: {capability_id}",
            "mimeType": "application/json",
            "payTo": pay_to,
            "maxTimeoutSeconds": 300,
            "asset": usdc_contract,
            "extra": {"name": "USD Coin", "version": "2"},
        }
        if payment_request_id:
            exact_option["extra"]["paymentRequestId"] = payment_request_id
        accepts.append(exact_option)

    # Option 2: Stripe credit purchase (fallback for non-crypto users)
    accepts.append(
        {
            "scheme": "stripe_checkout",
            "checkoutUrl": f"{api_base}/v1/billing/checkout",
            "description": f"Purchase Rhumb credits to execute {capability_id}",
            "minAmountUsd": max(cost_usd_cents / 100, 5.0),  # Minimum $5 checkout
        }
    )

    response = {
        "x402Version": 1,
        "error": error,
        # Keep top-level resource for our own consumers
        "resource": {
            "url": resource_url,
            "description": f"Rhumb capability execution: {capability_id}",
            "mimeType": "application/json",
        },
        "accepts": accepts,
    }
    if payment_request_id:
        response["paymentRequestId"] = payment_request_id
        response["paymentRequest"] = {
            "id": payment_request_id,
            "network": payment_network,
            "asset": payment_asset,
            "payTo": payment_pay_to,
            "amount": payment_amount,
            "expiresAt": payment_request.get("expires_at"),
        }
    return response


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
        payment_request: dict | None = None,
    ):
        self.capability_id = capability_id
        self.cost_usd_cents = cost_usd_cents
        self.resource_url = resource_url
        self.detail = detail
        self.payment_request = payment_request


async def payment_required_handler(
    request: Request, exc: PaymentRequiredException
) -> JSONResponse:
    """Global FastAPI exception handler for PaymentRequiredException."""
    body = build_x402_response(
        capability_id=exc.capability_id,
        cost_usd_cents=exc.cost_usd_cents,
        resource_url=exc.resource_url or str(request.url),
        error=exc.detail or "Payment required",
        payment_request=exc.payment_request,
    )
    return JSONResponse(
        status_code=402,
        content=body,
        headers={"X-Payment": "required"},
    )
