"""Wallet x402 top-up routes — prefund a wallet-linked balance (DF-18 / WU-W4).

Endpoints:
1. ``POST /auth/wallet/topup/request`` — create a prefund payment request (minimum $0.25)
2. ``POST /auth/wallet/topup/verify`` — settle x402 payment + credit org balance
3. ``GET /auth/wallet/balance`` — current spendable balance

All endpoints require a wallet session (Bearer token from ``/auth/wallet/verify``).

The top-up flow:
1. Wallet holder calls ``/topup/request`` with desired amount
2. Rhumb returns an x402 payment envelope (same as execution 402s)
3. Wallet signs the EIP-3009 authorization and sends it to ``/topup/verify``
4. Rhumb settles on-chain via ``x402_local_settlement.py``
5. On success: records ``usdc_receipts``, marks ``wallet_balance_topups`` as credited,
   increments ``org_credits.balance_usd_cents``, writes ``credit_ledger`` event
6. Wallet can now execute capabilities via ``X-Rhumb-Key`` spending from org balance

Anti-fraud: the wallet address in the x402 payment authorization must match
the authenticated wallet address. No cross-wallet crediting.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from routes._supabase import supabase_fetch, supabase_insert, supabase_insert_returning, supabase_patch
from routes.auth_wallet import _json_object_body, _require_wallet_session
from services.payment_requests import PaymentRequestService
from services.wallet_auth import normalize_address
from services.x402 import build_x402_response
from services.x402_settlement import (
    X402FacilitatorNotConfigured,
    X402SettlementFailed,
    X402SettlementService,
    X402VerificationFailed,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/wallet", tags=["wallet-topup"])

# ── Constants ────────────────────────────────────────────────────────

MIN_TOPUP_USD_CENTS = 25  # $0.25
MAX_TOPUP_USD_CENTS = 100_00  # $100.00

# ── Service singletons ──────────────────────────────────────────────

_payment_requests = PaymentRequestService()
_settlement = X402SettlementService()


# ── Routes ───────────────────────────────────────────────────────────


@router.post("/topup/request")
async def topup_request(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """Create a prefund payment request and return x402 payment envelope.

    Input:
        ``{"amount_usd_cents": 25}``  (minimum 25 = $0.25)

    Returns an x402-style response body with payment requirements
    that the wallet can sign and submit to ``/topup/verify``.
    """
    claims = await _require_wallet_session(authorization)

    payload = await _json_object_body(request)

    amount_cents = int(payload.get("amount_usd_cents", 0))

    if amount_cents < MIN_TOPUP_USD_CENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum top-up is ${MIN_TOPUP_USD_CENTS / 100:.2f} ({MIN_TOPUP_USD_CENTS} cents)",
        )

    if amount_cents > MAX_TOPUP_USD_CENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum top-up is ${MAX_TOPUP_USD_CENTS / 100:.2f}",
        )

    org_id = claims["org_id"]
    wallet_identity_id = claims["wallet_identity_id"]

    # Create a payment request with purpose=prefund
    payment_req = await _payment_requests.create_payment_request(
        org_id=org_id,
        capability_id=None,  # no capability — this is a balance top-up
        amount_usd_cents=amount_cents,
        purpose="prefund",
    )

    payment_request_id = payment_req.get("id")

    # Create the wallet_balance_topups row (pending)
    topup_row = {
        "wallet_identity_id": wallet_identity_id,
        "org_id": org_id,
        "payment_request_id": payment_request_id,
        "amount_usd_cents": amount_cents,
        "amount_usdc_atomic": payment_req.get("amount_usdc_atomic", str(amount_cents * 10000)),
        "status": "pending",
    }

    topup_stored = await supabase_insert_returning("wallet_balance_topups", topup_row)
    topup_id = topup_stored.get("id") if topup_stored else None

    # Build x402 payment envelope (same format as execution 402s)
    x402_body = build_x402_response(
        capability_id="billing.topup",
        cost_usd_cents=amount_cents,
        resource_url="/v1/auth/wallet/topup/verify",
        error="Payment required for balance top-up",
        payment_request=payment_req,
    )

    return JSONResponse({
        "data": {
            "topup_id": topup_id,
            "payment_request_id": payment_request_id,
            "amount_usd_cents": amount_cents,
            "amount_usd": amount_cents / 100,
            "x402": x402_body,
        },
        "error": None,
    })


@router.post("/topup/verify")
async def topup_verify(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """Settle an x402 payment proof and credit the wallet-linked balance.

    Input:
        ``{"payment_request_id": "...", "x_payment": {...}}``

    The ``x_payment`` field is the standard x402 payment payload containing
    the EIP-3009 ``authorization`` + ``signature``.

    Anti-fraud: the ``authorization.from`` address must match the
    authenticated wallet address.
    """
    claims = await _require_wallet_session(authorization)

    payload = await _json_object_body(request)

    payment_request_id = str(payload.get("payment_request_id", "")).strip()
    x_payment = payload.get("x_payment", {})

    if not payment_request_id:
        raise HTTPException(status_code=400, detail="payment_request_id is required")
    if not x_payment or not isinstance(x_payment, dict):
        raise HTTPException(status_code=400, detail="x_payment payload is required")

    org_id = claims["org_id"]
    wallet_address = claims["wallet_address"]
    wallet_identity_id = claims["wallet_identity_id"]

    # ── Load and validate the payment request ────────────────────────

    payment_req = await _payment_requests.get_pending_request(payment_request_id)
    if payment_req is None:
        raise HTTPException(status_code=400, detail="Payment request not found or already processed")

    if payment_req.get("org_id") != org_id:
        raise HTTPException(status_code=403, detail="Payment request does not belong to this wallet")

    if payment_req.get("purpose") != "prefund":
        raise HTTPException(status_code=400, detail="Payment request is not a prefund top-up")

    amount_cents = payment_req.get("amount_usd_cents", 0)

    # ── Anti-fraud: verify payer wallet matches authenticated wallet ──

    payment_inner = x_payment.get("payload", {})
    auth_block = payment_inner.get("authorization", {})
    payer_from = auth_block.get("from", "")

    if payer_from:
        try:
            payer_normalized = normalize_address(payer_from)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payer address in authorization")

        if payer_normalized != wallet_address:
            raise HTTPException(
                status_code=403,
                detail="Payer wallet does not match authenticated wallet. "
                       "Top-up must come from the same wallet that authenticated.",
            )

    # ── Settle via the existing x402 settlement service ──────────────

    # Build payment requirements from the stored payment request
    payment_requirements = {
        "maxAmountRequired": payment_req.get("amount_usdc_atomic"),
        "amount": payment_req.get("amount_usdc_atomic"),
        "network": payment_req.get("network"),
        "asset": payment_req.get("asset_address"),
        "payTo": payment_req.get("pay_to_address"),
        "resource": "/v1/auth/wallet/topup/verify",
    }

    try:
        settlement_result = await _settlement.verify_and_settle(
            payment_payload=x_payment,
            payment_requirements=payment_requirements,
        )
    except X402VerificationFailed as exc:
        # Update topup status to failed
        await _update_topup_status(wallet_identity_id, payment_request_id, "failed")
        raise HTTPException(status_code=400, detail=f"Payment verification failed: {exc}")
    except X402SettlementFailed as exc:
        await _update_topup_status(wallet_identity_id, payment_request_id, "failed")
        raise HTTPException(status_code=502, detail=f"Settlement failed: {exc}")
    except X402FacilitatorNotConfigured:
        raise HTTPException(
            status_code=503,
            detail="Settlement service not configured. Contact support.",
        )

    tx_hash = settlement_result.get("transaction", "")
    payer = settlement_result.get("payer", "")
    network = settlement_result.get("network", "base")

    # ── Record the USDC receipt ──────────────────────────────────────

    receipt_row = {
        "payment_request_id": payment_request_id,
        "tx_hash": tx_hash,
        "network": network,
        "from_address": payer,
        "to_address": payment_req.get("pay_to_address", ""),
        "amount_usdc_atomic": payment_req.get("amount_usdc_atomic", "0"),
        "settled": True,
        "settled_at": datetime.now(tz=UTC).isoformat(),
    }

    receipt_stored = await supabase_insert_returning("usdc_receipts", receipt_row)
    receipt_id = receipt_stored.get("id") if receipt_stored else None

    # ── Mark payment request as verified ─────────────────────────────

    await _payment_requests.mark_verified(payment_request_id, tx_hash)

    # ── Credit the org balance ───────────────────────────────────────

    new_balance = await _credit_org_balance(
        org_id=org_id,
        amount_cents=amount_cents,
        wallet_identity_id=wallet_identity_id,
        wallet_address=wallet_address,
        payment_request_id=payment_request_id,
        receipt_id=receipt_id,
        tx_hash=tx_hash,
        network=network,
    )

    # ── Update top-up row to credited ────────────────────────────────

    now_iso = datetime.now(tz=UTC).isoformat()
    await supabase_patch(
        f"wallet_balance_topups?wallet_identity_id=eq.{wallet_identity_id}"
        f"&payment_request_id=eq.{payment_request_id}"
        f"&status=eq.pending",
        {
            "status": "credited",
            "receipt_id": receipt_id,
            "credited_at": now_iso,
        },
    )

    return JSONResponse({
        "data": {
            "status": "credited",
            "amount_usd_cents": amount_cents,
            "amount_usd": amount_cents / 100,
            "balance_usd_cents": new_balance,
            "balance_usd": new_balance / 100,
            "transaction": tx_hash,
            "network": network,
            "receipt_id": receipt_id,
            "payment_request_id": payment_request_id,
        },
        "error": None,
    })


@router.get("/balance")
async def wallet_balance(
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """Return current spendable balance for the wallet-linked org.

    Also returns top-up history summary.
    """
    claims = await _require_wallet_session(authorization)
    org_id = claims["org_id"]
    wallet_identity_id = claims["wallet_identity_id"]

    # Current balance
    balance_usd_cents = 0
    credits = await supabase_fetch(
        f"org_credits?org_id=eq.{org_id}&select=balance_usd_cents&limit=1"
    )
    if credits:
        balance_usd_cents = credits[0].get("balance_usd_cents", 0)

    # Recent top-ups
    topups = await supabase_fetch(
        f"wallet_balance_topups?wallet_identity_id=eq.{wallet_identity_id}"
        f"&select=id,amount_usd_cents,status,credited_at,created_at"
        f"&order=created_at.desc"
        f"&limit=10"
    ) or []

    total_topped_up_cents = sum(
        t.get("amount_usd_cents", 0)
        for t in topups
        if t.get("status") == "credited"
    )

    return JSONResponse({
        "data": {
            "balance_usd_cents": balance_usd_cents,
            "balance_usd": balance_usd_cents / 100,
            "total_topped_up_usd_cents": total_topped_up_cents,
            "total_topped_up_usd": total_topped_up_cents / 100,
            "recent_topups": [
                {
                    "id": t.get("id"),
                    "amount_usd_cents": t.get("amount_usd_cents"),
                    "amount_usd": (t.get("amount_usd_cents", 0)) / 100,
                    "status": t.get("status"),
                    "credited_at": t.get("credited_at"),
                    "created_at": t.get("created_at"),
                }
                for t in topups
            ],
        },
        "error": None,
    })


# ── Helpers ──────────────────────────────────────────────────────────


async def _credit_org_balance(
    *,
    org_id: str,
    amount_cents: int,
    wallet_identity_id: str,
    wallet_address: str,
    payment_request_id: str | None,
    receipt_id: str | None,
    tx_hash: str,
    network: str,
) -> int:
    """Increment org_credits balance and write credit_ledger event.

    Returns the new balance in cents.
    Uses the same pattern as ``stripe_billing.process_checkout_completed``.
    """
    # Read current balance
    credits = await supabase_fetch(
        f"org_credits?org_id=eq.{org_id}&select=balance_usd_cents&limit=1"
    )
    if not credits:
        # Should not happen — billing bootstrap creates this row.
        # Defensive: create it.
        await supabase_insert("org_credits", {"org_id": org_id, "balance_usd_cents": 0})
        current_balance = 0
    else:
        current_balance = credits[0].get("balance_usd_cents", 0)

    new_balance = current_balance + amount_cents

    # Update balance
    patched = await supabase_patch(
        f"org_credits?org_id=eq.{org_id}",
        {"balance_usd_cents": new_balance},
    )
    if patched is None:
        logger.error("Failed to update org_credits for org %s during top-up", org_id)

    # Write ledger entry
    await supabase_insert("credit_ledger", {
        "org_id": org_id,
        "event_type": "wallet_topup_added",
        "amount_usd_cents": amount_cents,
        "balance_after_usd_cents": new_balance,
        "description": f"Wallet x402 top-up (${amount_cents / 100:.2f})",
        "metadata": {
            "source": "wallet_x402_topup",
            "wallet_identity_id": wallet_identity_id,
            "wallet_address": wallet_address,
            "payment_request_id": payment_request_id,
            "receipt_id": receipt_id,
            "tx_hash": tx_hash,
            "network": network,
            "topup_type": "prefund",
        },
    })

    logger.info(
        "Wallet top-up credited: org=%s amount=%d cents new_balance=%d cents tx=%s",
        org_id, amount_cents, new_balance, tx_hash,
    )

    return new_balance


async def _update_topup_status(
    wallet_identity_id: str,
    payment_request_id: str,
    status: str,
) -> None:
    """Update a pending wallet_balance_topups row to the given status."""
    await supabase_patch(
        f"wallet_balance_topups?wallet_identity_id=eq.{wallet_identity_id}"
        f"&payment_request_id=eq.{payment_request_id}"
        f"&status=eq.pending",
        {"status": status},
    )
