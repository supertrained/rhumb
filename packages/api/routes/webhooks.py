"""Stripe webhook receiver.

Mounted at root (no /v1 prefix, no auth) — Stripe calls this directly.
Raw body is read before JSON parsing for signature verification.
"""

from __future__ import annotations

import logging

import stripe
from fastapi import APIRouter, Header, HTTPException, Request

from config import settings
from services.stripe_billing import handle_checkout_completed

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
) -> dict:
    """Receive and process Stripe webhook events."""
    # Read raw body for signature verification
    raw_body = await request.body()

    webhook_secret = settings.stripe_webhook_secret
    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(status_code=500, detail="Webhook not configured")

    try:
        event = stripe.Webhook.construct_event(
            payload=raw_body,
            sig_header=stripe_signature,
            secret=webhook_secret,
        )
    except stripe.SignatureVerificationError:
        logger.warning("Invalid Stripe webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Dispatch by event type
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        await handle_checkout_completed(session)

    return {"received": True}
