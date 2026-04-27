"""Self-service billing routes — checkout, balance, ledger, wallet top-ups, and auto-reload config.

Authenticated via X-Rhumb-Key (API key) for standard billing routes.
Wallet-prefund top-up routes use wallet Bearer sessions from ``/auth/wallet``.
Mounted at /v1 prefix in app.py.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from routes._supabase import (
    supabase_count,
    supabase_fetch,
    supabase_insert,
    supabase_insert_returning,
    supabase_patch,
)
from routes.auth_wallet import _require_wallet_session
from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.error_envelope import RhumbError
from services.payment_health import get_payment_health
from services.payment_requests import PaymentRequestService
from services.stripe_billing import create_checkout_session
from services.usdc_verifier import verify_usdc_payment
from services.x402_middleware import decode_x_payment_header, inspect_x_payment_header
from services.x402_settlement import (
    X402FacilitatorNotConfigured,
    X402SettlementFailed,
    X402SettlementService,
    X402VerificationFailed,
)

router = APIRouter(tags=["billing"])
logger = logging.getLogger(__name__)

MIN_AMOUNT_USD = 5.0
MAX_AMOUNT_USD = 5000.0
MIN_WALLET_TOPUP_USD_CENTS = 25
MAX_WALLET_TOPUP_USD_CENTS = int(MAX_AMOUNT_USD * 100)

DEFAULT_SUCCESS_URL = "https://rhumb.dev/billing/success"
DEFAULT_CANCEL_URL = "https://rhumb.dev/billing/cancel"

VALID_LEDGER_EVENT_TYPES = (
    "auto_reload_triggered",
    "credit_added",
    "debit",
    "reservation_released",
    "wallet_topup",
    "wallet_topup_added",
    "x402_payment",
)

_identity_store: Optional[AgentIdentityStore] = None
_payment_requests = PaymentRequestService()
_x402_settlement = X402SettlementService()


def _get_identity_store() -> AgentIdentityStore:
    global _identity_store
    if _identity_store is None:
        _identity_store = get_agent_identity_store()
    return _identity_store


class CheckoutRequest(BaseModel):
    amount_usd: float = Field(..., description="Amount in USD to purchase")
    success_url: str | None = None
    cancel_url: str | None = None


class WalletTopupRequest(BaseModel):
    amount_usd_cents: int = Field(
        ...,
        ge=MIN_WALLET_TOPUP_USD_CENTS,
        le=MAX_WALLET_TOPUP_USD_CENTS,
        description="Top-up amount in USD cents (minimum $0.25)",
    )


class WalletTopupVerifyRequest(BaseModel):
    payment_request_id: str = Field(..., min_length=1)
    x_payment: str = Field(..., min_length=1, description="x402 payment proof")


class AutoReloadRequest(BaseModel):
    enabled: bool
    threshold_usd: float | None = None
    amount_usd: float | None = None


async def _require_org(api_key: str | None) -> str:
    """Validate API key against the identity store and return org_id.

    Returns the organization_id associated with the key, or raises 401.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-Rhumb-Key header")
    agent = await _get_identity_store().verify_api_key_with_agent(api_key)
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    return agent.organization_id


def _wallet_topup_resource_url() -> str:
    api_base = os.environ.get("API_BASE_URL", "https://api.rhumb.dev")
    return f"{api_base}/v1/billing/x402/topup/verify"


def _validated_ledger_event_type(event_type: str | None) -> str | None:
    if event_type is None:
        return None

    normalized = event_type.strip()
    if not normalized:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'event_type' filter.",
            detail="Provide a non-empty event_type or omit the filter.",
        )

    if normalized not in VALID_LEDGER_EVENT_TYPES:
        valid_types = ", ".join(VALID_LEDGER_EVENT_TYPES)
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'event_type' filter.",
            detail=f"Use one of: {valid_types}.",
        )

    return normalized


def _validated_ledger_limit(limit: int) -> int:
    if 1 <= limit <= 200:
        return limit

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'limit' filter.",
        detail="Provide an integer between 1 and 200.",
    )


def _validated_ledger_offset(offset: int) -> int:
    if offset >= 0:
        return offset

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'offset' filter.",
        detail="Provide an integer greater than or equal to 0.",
    )


async def _load_wallet_topup(
    *,
    wallet_identity_id: str,
    payment_request_id: str,
) -> dict[str, Any] | None:
    rows = await supabase_fetch(
        f"wallet_balance_topups?wallet_identity_id=eq.{quote(wallet_identity_id)}"
        f"&payment_request_id=eq.{quote(payment_request_id)}"
        f"&select=*"
        f"&limit=1"
    )
    return rows[0] if rows else None


async def _load_payment_request(payment_request_id: str) -> dict[str, Any] | None:
    rows = await supabase_fetch(
        f"payment_requests?id=eq.{quote(payment_request_id)}"
        f"&select=*"
        f"&limit=1"
    )
    return rows[0] if rows else None


async def _load_org_balance(org_id: str) -> tuple[int, bool]:
    rows = await supabase_fetch(
        f"org_credits?org_id=eq.{quote(org_id)}&select=balance_usd_cents&limit=1"
    )
    if rows:
        return int(rows[0].get("balance_usd_cents", 0)), True
    return 0, False


def _extract_standard_x402_authorization(payment_data: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = payment_data.get("payload") if isinstance(payment_data, dict) else None
    if not isinstance(payload, dict):
        return None
    authorization = payload.get("authorization")
    return authorization if isinstance(authorization, dict) else None


def _extract_standard_x402_payment_request_id(payment_data: dict[str, Any] | None) -> str | None:
    if not isinstance(payment_data, dict):
        return None
    accepted = payment_data.get("accepted")
    accepted_extra = accepted.get("extra") if isinstance(accepted, dict) else None
    for candidate in (
        payment_data.get("paymentRequestId"),
        payment_data.get("payment_request_id"),
        accepted_extra.get("paymentRequestId") if isinstance(accepted_extra, dict) else None,
        accepted_extra.get("payment_request_id") if isinstance(accepted_extra, dict) else None,
    ):
        if candidate:
            return str(candidate)
    return None


def _build_wallet_topup_payment_requirements(payment_request: dict[str, Any]) -> dict[str, Any]:
    return {
        "scheme": "exact",
        "network": payment_request.get("network"),
        "maxAmountRequired": payment_request.get("amount_usdc_atomic"),
        "amount": payment_request.get("amount_usdc_atomic"),
        "resource": _wallet_topup_resource_url(),
        "description": "Rhumb wallet balance top-up",
        "mimeType": "application/json",
        "payTo": payment_request.get("pay_to_address"),
        "maxTimeoutSeconds": 300,
        "asset": payment_request.get("asset_address"),
        "extra": {
            "name": "Rhumb",
            "version": "1",
            "paymentRequestId": payment_request.get("id"),
        },
    }


def _build_wallet_topup_x402_response(
    *,
    amount_usd_cents: int,
    payment_request: dict[str, Any],
) -> dict[str, Any]:
    exact_option = _build_wallet_topup_payment_requirements(payment_request)
    return {
        "x402Version": 1,
        "error": "Payment required to top up wallet balance",
        "resource": {
            "url": _wallet_topup_resource_url(),
            "description": "Rhumb wallet balance top-up",
            "mimeType": "application/json",
        },
        "accepts": [exact_option],
        "paymentRequestId": payment_request.get("id"),
        "paymentRequest": {
            "id": payment_request.get("id"),
            "network": payment_request.get("network"),
            "asset": payment_request.get("asset_address"),
            "payTo": payment_request.get("pay_to_address"),
            "amount": payment_request.get("amount_usdc_atomic"),
            "expiresAt": payment_request.get("expires_at"),
        },
        "topup": {
            "amount_usd_cents": amount_usd_cents,
            "amount_usd": amount_usd_cents / 100,
            "payment_request_id": payment_request.get("id"),
        },
    }


async def _record_wallet_topup_credit(
    *,
    org_id: str,
    wallet_identity_id: str,
    topup_id: str,
    payment_request_id: str,
    receipt_id: str,
    amount_usd_cents: int,
    tx_hash: str,
    network: str,
    payer: str,
) -> int:
    current_balance, balance_exists = await _load_org_balance(org_id)
    new_balance = current_balance + amount_usd_cents

    await supabase_insert(
        "credit_ledger",
        {
            "org_id": org_id,
            "event_type": "wallet_topup",
            "amount_usd_cents": amount_usd_cents,
            "balance_after_usd_cents": new_balance,
            "description": f"Wallet x402 top-up tx:{tx_hash[:16]}…",
            "metadata": {
                "source": "wallet_x402_topup",
                "wallet_identity_id": wallet_identity_id,
                "payment_request_id": payment_request_id,
                "receipt_id": receipt_id,
                "network": network,
                "payer": payer,
            },
        },
    )

    if balance_exists:
        await supabase_patch(
            f"org_credits?org_id=eq.{quote(org_id)}",
            {"balance_usd_cents": new_balance},
        )
    else:
        await supabase_insert(
            "org_credits",
            {
                "org_id": org_id,
                "balance_usd_cents": new_balance,
            },
        )

    await supabase_patch(
        f"wallet_balance_topups?id=eq.{quote(topup_id)}",
        {
            "status": "credited",
            "receipt_id": receipt_id,
            "credited_at": datetime.now(tz=UTC).isoformat(),
        },
    )

    return new_balance


async def _create_wallet_topup_receipt(
    *,
    payment_request_id: str,
    org_id: str,
    tx_hash: str,
    payer: str,
    pay_to: str,
    amount_usdc_atomic: str,
    amount_usd_cents: int,
    network: str,
    block_number: int | None,
) -> dict[str, Any]:
    existing = await supabase_fetch(
        f"usdc_receipts?tx_hash=eq.{quote(tx_hash)}&select=id,payment_request_id&limit=1"
    )
    if existing:
        raise HTTPException(status_code=409, detail="Transaction already used")

    receipt = await supabase_insert_returning(
        "usdc_receipts",
        {
            "payment_request_id": payment_request_id,
            "tx_hash": tx_hash,
            "from_address": payer,
            "to_address": pay_to,
            "amount_usdc_atomic": amount_usdc_atomic,
            "amount_usd_cents": amount_usd_cents,
            "network": network,
            "block_number": block_number,
            "org_id": org_id,
            "status": "confirmed",
        },
    )
    if receipt is None:
        raise HTTPException(status_code=500, detail="Failed to record payment receipt")
    return receipt


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


@router.post("/billing/checkout")
async def checkout(
    body: CheckoutRequest,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict:
    """Create a Stripe Checkout Session to purchase credits."""
    org_id = await _require_org(x_rhumb_key)

    if body.amount_usd < MIN_AMOUNT_USD or body.amount_usd > MAX_AMOUNT_USD:
        raise HTTPException(
            status_code=400,
            detail=f"amount_usd must be between {MIN_AMOUNT_USD:.0f} and {MAX_AMOUNT_USD:.0f}",
        )

    amount_cents = int(round(body.amount_usd * 100))
    result = await create_checkout_session(
        org_id=org_id,
        amount_cents=amount_cents,
        success_url=body.success_url or DEFAULT_SUCCESS_URL,
        cancel_url=body.cancel_url or DEFAULT_CANCEL_URL,
    )

    return result


# ---------------------------------------------------------------------------
# Wallet x402 top-up
# ---------------------------------------------------------------------------


@router.post("/billing/x402/topup/request")
async def wallet_topup_request(
    body: WalletTopupRequest,
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """Mint an x402 payment request for a wallet-scoped prefund top-up."""
    claims = await _require_wallet_session(authorization)

    wallet_identity_id = str(claims.get("wallet_identity_id", "")).strip()
    org_id = str(claims.get("org_id", "")).strip()
    wallet_address = str(claims.get("wallet_address", "")).strip().lower()
    chain = str(claims.get("chain", "base")).strip() or "base"

    if not wallet_identity_id or not org_id:
        raise HTTPException(status_code=400, detail="Wallet session is missing required identity claims")

    payment_request = await _payment_requests.create_payment_request(
        org_id=org_id,
        capability_id=None,
        amount_usd_cents=body.amount_usd_cents,
        purpose="prefund",
    )
    payment_request_id = str(payment_request.get("id", "")).strip()
    if not payment_request_id:
        raise HTTPException(status_code=503, detail="Failed to create payment request")

    topup = await supabase_insert_returning(
        "wallet_balance_topups",
        {
            "wallet_identity_id": wallet_identity_id,
            "org_id": org_id,
            "payment_request_id": payment_request_id,
            "amount_usd_cents": body.amount_usd_cents,
            "amount_usdc_atomic": payment_request.get("amount_usdc_atomic") or str(body.amount_usd_cents * 10000),
            "status": "pending",
            "metadata": {
                "purpose": "prefund",
                "chain": chain,
                "wallet_address": wallet_address,
            },
        },
    )
    if topup is None:
        raise HTTPException(status_code=500, detail="Failed to create wallet top-up record")

    return {
        "data": {
            "topup_id": topup.get("id"),
            "payment_request_id": payment_request_id,
            "amount_usd_cents": body.amount_usd_cents,
            "amount_usd": body.amount_usd_cents / 100,
            "status": topup.get("status", "pending"),
            "x402": _build_wallet_topup_x402_response(
                amount_usd_cents=body.amount_usd_cents,
                payment_request=payment_request,
            ),
        },
        "error": None,
    }


@router.post("/billing/x402/topup/verify")
async def wallet_topup_verify(
    body: WalletTopupVerifyRequest,
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """Verify an x402 wallet top-up payment and credit the linked org balance."""
    claims = await _require_wallet_session(authorization)

    wallet_identity_id = str(claims.get("wallet_identity_id", "")).strip()
    org_id = str(claims.get("org_id", "")).strip()
    wallet_address = str(claims.get("wallet_address", "")).strip().lower()

    if not wallet_identity_id or not org_id or not wallet_address:
        raise HTTPException(status_code=400, detail="Wallet session is missing required identity claims")

    topup = await _load_wallet_topup(
        wallet_identity_id=wallet_identity_id,
        payment_request_id=body.payment_request_id,
    )
    if topup is None:
        raise HTTPException(status_code=404, detail="Wallet top-up not found")

    if topup.get("status") != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Wallet top-up already processed with status={topup.get('status')}",
        )

    payment_request = await _load_payment_request(body.payment_request_id)
    if payment_request is None:
        raise HTTPException(status_code=404, detail="Payment request not found")

    if payment_request.get("status") != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Payment request already processed with status={payment_request.get('status')}",
        )

    if payment_request.get("org_id") != org_id:
        raise HTTPException(status_code=403, detail="Payment request does not belong to this wallet org")

    if payment_request.get("purpose") not in (None, "prefund"):
        raise HTTPException(status_code=400, detail="Payment request is not a wallet top-up request")

    payment_trace = inspect_x_payment_header(body.x_payment)
    payment_data = payment_trace.get("payment_data") or decode_x_payment_header(body.x_payment)
    if not isinstance(payment_data, dict):
        raise HTTPException(status_code=400, detail="Invalid X-Payment payload")

    expected_payment_request_id = _extract_standard_x402_payment_request_id(payment_data)
    if expected_payment_request_id and expected_payment_request_id != body.payment_request_id:
        raise HTTPException(status_code=400, detail="Payment request mismatch")

    amount_usd_cents = int(topup.get("amount_usd_cents") or payment_request.get("amount_usd_cents") or 0)
    expected_atomic = str(
        payment_request.get("amount_usdc_atomic") or topup.get("amount_usdc_atomic") or amount_usd_cents * 10000
    )
    pay_to = str(payment_request.get("pay_to_address") or "").strip()
    if not pay_to:
        raise HTTPException(status_code=500, detail="Payment request missing pay-to address")

    network = str(payment_request.get("network") or payment_trace.get("declared_network") or "base")

    if payment_trace.get("proof_format") == "standard_authorization_payload":
        authorization_payload = _extract_standard_x402_authorization(payment_data)
        declared_payer = str((authorization_payload or {}).get("from") or "").strip().lower()
        if declared_payer and declared_payer != wallet_address:
            raise HTTPException(status_code=403, detail="Signed x402 authorization does not match wallet session")

        try:
            settlement = await _x402_settlement.verify_and_settle(
                payment_data,
                _build_wallet_topup_payment_requirements(payment_request),
            )
        except X402FacilitatorNotConfigured as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Standard x402 authorization settlement is not configured: {exc}",
            ) from exc
        except X402VerificationFailed as exc:
            raise HTTPException(status_code=402, detail=f"Payment verification failed: {exc}") from exc
        except X402SettlementFailed as exc:
            raise HTTPException(status_code=402, detail=f"Payment settlement failed: {exc}") from exc

        payer = str(settlement.get("payer") or declared_payer or "").strip().lower()
        if not payer:
            raise HTTPException(status_code=400, detail="Settled payment did not expose a payer wallet")
        if payer != wallet_address:
            raise HTTPException(status_code=403, detail="Settled x402 payment came from a different wallet")

        tx_hash = str(settlement.get("transaction") or "").strip()
        if not tx_hash:
            raise HTTPException(status_code=400, detail="Settled payment is missing a transaction hash")

        network = str(settlement.get("network") or network)
        receipt = await _create_wallet_topup_receipt(
            payment_request_id=body.payment_request_id,
            org_id=org_id,
            tx_hash=tx_hash,
            payer=payer,
            pay_to=pay_to,
            amount_usdc_atomic=expected_atomic,
            amount_usd_cents=amount_usd_cents,
            network=network,
            block_number=None,
        )
    elif payment_data.get("tx_hash"):
        tx_hash = str(payment_data.get("tx_hash") or "").strip()
        declared_wallet = str(
            payment_data.get("wallet_address") or payment_data.get("from") or ""
        ).strip().lower()
        if not declared_wallet:
            raise HTTPException(status_code=400, detail="Payment verification failed: payer wallet not declared")
        if declared_wallet != wallet_address:
            raise HTTPException(status_code=403, detail="Payment proof does not match wallet session")

        network = str(payment_data.get("network") or network)
        verification = await verify_usdc_payment(
            tx_hash=tx_hash,
            expected_to=pay_to,
            expected_amount_atomic=expected_atomic,
            expected_from=wallet_address,
            network=network,
        )
        if not verification.get("valid"):
            raise HTTPException(
                status_code=402,
                detail=f"Payment verification failed: {verification.get('error', 'unknown')}",
            )

        payer = str(verification.get("from_address") or "").strip().lower()
        receipt = await _create_wallet_topup_receipt(
            payment_request_id=body.payment_request_id,
            org_id=org_id,
            tx_hash=tx_hash,
            payer=payer,
            pay_to=str(verification.get("to_address") or pay_to),
            amount_usdc_atomic=str(verification.get("amount_atomic") or expected_atomic),
            amount_usd_cents=amount_usd_cents,
            network=network,
            block_number=verification.get("block_number"),
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported X-Payment proof format")

    await _payment_requests.mark_verified(body.payment_request_id, receipt["tx_hash"])

    new_balance = await _record_wallet_topup_credit(
        org_id=org_id,
        wallet_identity_id=wallet_identity_id,
        topup_id=str(topup.get("id")),
        payment_request_id=body.payment_request_id,
        receipt_id=str(receipt.get("id")),
        amount_usd_cents=amount_usd_cents,
        tx_hash=str(receipt.get("tx_hash")),
        network=str(receipt.get("network") or network),
        payer=str(receipt.get("from_address") or wallet_address),
    )

    return {
        "data": {
            "payment_request_id": body.payment_request_id,
            "topup_id": topup.get("id"),
            "receipt_id": receipt.get("id"),
            "tx_hash": receipt.get("tx_hash"),
            "network": receipt.get("network") or network,
            "amount_usd_cents": amount_usd_cents,
            "amount_usd": amount_usd_cents / 100,
            "balance_usd_cents": new_balance,
            "balance_usd": new_balance / 100,
            "status": "credited",
        },
        "error": None,
    }


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------


@router.get("/billing/balance")
async def get_balance(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict:
    """Return the org's current credit balance with auto-reload config."""
    org_id = await _require_org(x_rhumb_key)

    rows = await supabase_fetch(
        f"org_credits?org_id=eq.{org_id}"
        f"&select=balance_usd_cents,reserved_usd_cents,"
        f"auto_reload_enabled,auto_reload_threshold_cents,auto_reload_amount_cents"
        f"&limit=1"
    )

    if not rows:
        return {
            "org_id": org_id,
            "balance_usd_cents": 0,
            "balance_usd": 0.0,
            "reserved_usd_cents": 0,
            "available_usd_cents": 0,
            "available_usd": 0.0,
            "auto_reload_enabled": False,
            "auto_reload_threshold_usd": None,
            "auto_reload_amount_usd": None,
            # Backward-compat keys
            "balance_cents": 0,
            "reserved_cents": 0,
        }

    row = rows[0]
    balance_cents = row["balance_usd_cents"]
    reserved_cents = row.get("reserved_usd_cents", 0)
    available_cents = balance_cents - reserved_cents

    auto_reload_threshold_cents = row.get("auto_reload_threshold_cents")
    auto_reload_amount_cents = row.get("auto_reload_amount_cents")

    return {
        "org_id": org_id,
        "balance_usd_cents": balance_cents,
        "balance_usd": balance_cents / 100,
        "reserved_usd_cents": reserved_cents,
        "available_usd_cents": available_cents,
        "available_usd": available_cents / 100,
        "auto_reload_enabled": row.get("auto_reload_enabled", False),
        "auto_reload_threshold_usd": (
            auto_reload_threshold_cents / 100
            if auto_reload_threshold_cents is not None
            else None
        ),
        "auto_reload_amount_usd": (
            auto_reload_amount_cents / 100
            if auto_reload_amount_cents is not None
            else None
        ),
        # Backward-compat keys (Phase 0 callers may rely on these)
        "balance_cents": balance_cents,
        "reserved_cents": reserved_cents,
    }


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


@router.get("/billing/ledger")
async def get_ledger(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
    limit: int = Query(50),
    offset: int = Query(0),
    event_type: str | None = Query(None),
) -> dict:
    """Return paginated, optionally filtered ledger entries for the org."""
    limit = _validated_ledger_limit(limit)
    offset = _validated_ledger_offset(offset)
    org_id = await _require_org(x_rhumb_key)
    normalized_event_type = _validated_ledger_event_type(event_type)

    base_filter = f"credit_ledger?org_id=eq.{org_id}"
    if normalized_event_type:
        base_filter += f"&event_type=eq.{normalized_event_type}"

    # Fetch paginated entries (never expose stripe_payment_intent_id)
    entries = await supabase_fetch(
        f"{base_filter}"
        f"&select=id,event_type,amount_usd_cents,balance_after_usd_cents,"
        f"capability_execution_id,stripe_checkout_session_id,description,created_at"
        f"&order=created_at.desc&limit={limit}&offset={offset}"
    )

    if entries is None:
        entries = []

    # Enrich each entry with dollar amounts
    events = []
    for entry in entries:
        events.append({
            **entry,
            "amount_usd": entry["amount_usd_cents"] / 100,
            "balance_after_usd": entry["balance_after_usd_cents"] / 100,
        })

    # Efficient server-side count via Content-Range header
    total = await supabase_count(base_filter)

    return {
        "events": events,
        # Backward-compat alias
        "entries": events,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Auto-reload config
# ---------------------------------------------------------------------------


@router.put("/billing/auto-reload")
async def update_auto_reload(
    body: AutoReloadRequest,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict:
    """Update the auto-reload configuration for an org's credit wallet."""
    org_id = await _require_org(x_rhumb_key)

    if body.enabled:
        if body.threshold_usd is None or body.threshold_usd <= 0:
            raise HTTPException(
                status_code=400,
                detail="threshold_usd must be > 0 when auto-reload is enabled",
            )
        if body.amount_usd is None or body.amount_usd < 5.0:
            raise HTTPException(
                status_code=400,
                detail="amount_usd must be >= 5.0 when auto-reload is enabled",
            )

    payload: dict = {
        "auto_reload_enabled": body.enabled,
        "auto_reload_threshold_cents": (
            int(round(body.threshold_usd * 100)) if body.threshold_usd is not None else None
        ),
        "auto_reload_amount_cents": (
            int(round(body.amount_usd * 100)) if body.amount_usd is not None else None
        ),
    }

    result = await supabase_patch(
        f"org_credits?org_id=eq.{org_id}",
        payload,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Org credits not found")

    row = result[0] if isinstance(result, list) and result else result

    threshold_cents = row.get("auto_reload_threshold_cents")
    amount_cents = row.get("auto_reload_amount_cents")

    return {
        "org_id": org_id,
        "auto_reload_enabled": row.get("auto_reload_enabled", False),
        "auto_reload_threshold_usd": (
            threshold_cents / 100 if threshold_cents is not None else None
        ),
        "auto_reload_amount_usd": (
            amount_cents / 100 if amount_cents is not None else None
        ),
    }


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@router.get("/billing/health")
async def billing_health() -> dict:
    """Payment system health check. No auth required."""
    from config import settings

    health = await get_payment_health(
        settings.supabase_url, settings.supabase_service_role_key
    )
    return health
