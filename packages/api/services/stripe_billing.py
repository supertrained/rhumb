"""Stripe billing service — checkout sessions, credit top-ups, and customer management.

Uses Supabase REST (PostgREST via httpx) for all DB access, matching the
pattern in routes/_supabase.py.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import stripe

from config import settings
from services.billing_bootstrap import ensure_org_billing_bootstrap
from services.payment_metrics import log_payment_event

logger = logging.getLogger(__name__)


def _stripe_to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj

    to_dict_recursive = getattr(obj, "to_dict_recursive", None)
    if callable(to_dict_recursive):
        try:
            payload = to_dict_recursive()
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        try:
            payload = to_dict()
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    return {}


def _sb_headers() -> dict[str, str]:
    """Supabase REST headers (service_role)."""
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


def _sb_url(path: str) -> str:
    return f"{settings.supabase_url}/rest/v1/{path}"


async def _sb_get(path: str) -> Any | None:
    """GET from Supabase REST API."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(_sb_url(path), headers=_sb_headers(), timeout=10.0)
        if resp.status_code != 200:
            return None
        return resp.json()


async def _sb_post(path: str, payload: dict[str, Any], *, prefer: str = "return=representation") -> Any | None:
    """POST to Supabase REST API."""
    headers = {**_sb_headers(), "Prefer": prefer}
    async with httpx.AsyncClient() as client:
        resp = await client.post(_sb_url(path), headers=headers, json=payload, timeout=10.0)
        if resp.status_code not in (200, 201):
            logger.warning("Supabase POST %s failed: %s %s", path, resp.status_code, resp.text)
            return None
        return resp.json()


async def _sb_patch(path: str, payload: dict[str, Any]) -> bool:
    """PATCH a Supabase REST resource."""
    headers = {**_sb_headers(), "Prefer": "return=minimal"}
    async with httpx.AsyncClient() as client:
        resp = await client.patch(_sb_url(path), headers=headers, json=payload, timeout=10.0)
        return resp.status_code in (200, 204)


# ── Stripe customer management ──────────────────────────────────────


async def get_or_create_stripe_customer(org_id: str, email: str) -> str:
    """Return the Stripe customer ID for an org, creating one if needed.

    If a stored customer belongs to the opposite Stripe mode (for example a
    lingering test-mode customer after prod switches to live keys), repair the
    mapping by creating a fresh customer in the active mode.
    """
    stripe.api_key = settings.stripe_secret_key

    # Check stripe_customers table first
    rows = await _sb_get(f"stripe_customers?org_id=eq.{org_id}&select=stripe_customer_id&limit=1")
    if rows:
        customer_id = rows[0]["stripe_customer_id"]
        try:
            stripe.Customer.retrieve(customer_id)
            return customer_id
        except stripe.InvalidRequestError as exc:
            message = str(exc)
            if "a similar object exists in test mode" not in message and "No such customer" not in message:
                raise

            logger.warning(
                "Stored Stripe customer %s for org %s is invalid for the active key; recreating",
                customer_id,
                org_id,
            )
            customer = stripe.Customer.create(email=email, metadata={"org_id": org_id})
            await _sb_patch(
                f"stripe_customers?org_id=eq.{org_id}",
                {"stripe_customer_id": customer.id},
            )
            return customer.id

    # Create in Stripe
    customer = stripe.Customer.create(email=email, metadata={"org_id": org_id})

    # Persist mapping
    await _sb_post("stripe_customers", {
        "org_id": org_id,
        "stripe_customer_id": customer.id,
    })

    return customer.id


# ── Checkout session ─────────────────────────────────────────────────


async def create_checkout_session(
    org_id: str,
    amount_cents: int,
    success_url: str,
    cancel_url: str,
) -> dict[str, str]:
    """Create a Stripe Checkout Session for a one-time credit purchase."""
    await ensure_org_billing_bootstrap(
        org_id,
        email=f"{org_id}@placeholder.rhumb.dev",
        name=org_id,
        starter_credits_cents=0,
    )

    # Look up org for email
    orgs = await _sb_get(f"orgs?id=eq.{org_id}&select=email&limit=1")
    email = orgs[0]["email"] if orgs else None

    customer_id = await get_or_create_stripe_customer(org_id, email or f"{org_id}@placeholder.rhumb.dev")

    stripe.api_key = settings.stripe_secret_key
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Rhumb API Credits"},
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
        metadata={"org_id": org_id, "amount_cents": str(amount_cents)},
        payment_intent_data={"setup_future_usage": "off_session"},
        success_url=success_url,
        cancel_url=cancel_url,
    )

    log_payment_event(
        "checkout_created",
        org_id=org_id,
        amount_usd_cents=amount_cents,
        provider="stripe",
    )

    return {"checkout_url": session.url, "session_id": session.id}


async def retrieve_checkout_session(session_id: str) -> dict[str, Any] | None:
    """Fetch a Stripe Checkout Session by id.

    Used as a fallback confirmation path when webhooks are delayed or misconfigured.
    """
    if not session_id:
        return None

    try:
        stripe.api_key = settings.stripe_secret_key
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["payment_intent"],
        )
    except Exception as exc:
        logger.warning("Unable to retrieve Stripe checkout session %s: %s", session_id, exc)
        return None

    payload = _stripe_to_dict(session)
    return payload or None


async def confirm_checkout_session(
    session_id: str,
    *,
    expected_org_id: str,
) -> bool:
    """Confirm a completed checkout session and apply credits if needed.

    Returns True if credits were applied (or already applied), False otherwise.
    Prefer `confirm_checkout_session_detailed()` for diagnostics.
    """
    result = await confirm_checkout_session_detailed(session_id, expected_org_id=expected_org_id)
    return bool(result.get("processed"))


async def _checkout_credit_exists(session_id: str) -> bool:
    """Return whether this checkout session already has a credit ledger entry."""
    if not session_id:
        return False

    existing = await _sb_get(
        f"credit_ledger?stripe_checkout_session_id=eq.{session_id}&select=id&limit=1"
    )
    return bool(existing)


async def confirm_checkout_session_detailed(
    session_id: str,
    *,
    expected_org_id: str,
) -> dict[str, Any]:
    """Confirm a checkout session and return a structured diagnostic result.

    Safe for returning to the authenticated caller: it only reveals details after
    verifying the Stripe session metadata matches the caller's org.
    """
    out: dict[str, Any] = {
        "processed": False,
        "reason": "unknown",
    }

    session = await retrieve_checkout_session(session_id)
    if session is None:
        out["reason"] = "stripe_retrieve_failed"
        return out

    out["stripe_session_status"] = session.get("status")
    out["stripe_payment_status"] = session.get("payment_status")
    out["stripe_livemode"] = bool(session.get("livemode"))

    metadata = session.get("metadata") or {}
    org_id = metadata.get("org_id")
    amount_cents = metadata.get("amount_cents")

    if not org_id or org_id != expected_org_id:
        # Do not reveal cross-org metadata.
        out["reason"] = "org_mismatch"
        return out

    out["org_id"] = org_id
    out["amount_cents"] = amount_cents

    if not amount_cents:
        out["reason"] = "missing_metadata"
        return out

    payment_status = str(session.get("payment_status") or "").lower()
    if payment_status != "paid":
        out["reason"] = "unpaid"
        return out

    payment_intent = session.get("payment_intent")
    if isinstance(payment_intent, dict):
        session["payment_intent"] = payment_intent.get("id")
        out["stripe_payment_intent_id"] = payment_intent.get("id")
    else:
        out["stripe_payment_intent_id"] = payment_intent

    if await _checkout_credit_exists(session_id):
        out["processed"] = True
        out["reason"] = "already_credited"
        return out

    applied = await handle_checkout_completed(session)
    if applied:
        out["processed"] = True
        out["reason"] = "credited"
        return out

    if await _checkout_credit_exists(session_id):
        out["processed"] = True
        out["reason"] = "already_credited"
        return out

    out["reason"] = "apply_failed"
    return out


async def _lookup_payment_method_id(payment_intent_id: str | None) -> str | None:
    """Resolve the saved payment method used for a checkout, if available."""
    if not payment_intent_id:
        return None

    try:
        stripe.api_key = settings.stripe_secret_key
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        payment_method = getattr(intent, "payment_method", None)
        if payment_method is None and isinstance(intent, dict):
            payment_method = intent.get("payment_method")

        if isinstance(payment_method, dict):
            return payment_method.get("id")
        if hasattr(payment_method, "id"):
            return getattr(payment_method, "id")
        if isinstance(payment_method, str) and payment_method:
            return payment_method
    except Exception as exc:
        logger.warning(
            "Unable to resolve Stripe payment method for intent %s: %s",
            payment_intent_id,
            exc,
        )

    return None


# ── Off-session PaymentIntent (auto-reload) ──────────────────────────


async def create_payment_intent(
    org_id: str,
    amount_cents: int,
    payment_method_id: str,
) -> dict[str, Any]:
    """Create a confirmed, off-session Stripe PaymentIntent for auto-reload.

    Returns a dict with at least ``{"id": "pi_..."}`` on success.
    Raises on Stripe API errors so the caller can handle gracefully.
    """
    # Look up Stripe customer for the org
    rows = await _sb_get(f"stripe_customers?org_id=eq.{org_id}&select=stripe_customer_id&limit=1")
    if not rows:
        raise ValueError(f"No Stripe customer found for org {org_id}")

    customer_id = rows[0]["stripe_customer_id"]

    stripe.api_key = settings.stripe_secret_key
    intent = stripe.PaymentIntent.create(
        amount=amount_cents,
        currency="usd",
        customer=customer_id,
        payment_method=payment_method_id,
        off_session=True,
        confirm=True,
        metadata={"org_id": org_id, "amount_cents": str(amount_cents), "trigger": "auto_reload"},
    )

    return {"id": intent.id, "status": intent.status}


# ── Webhook handler ──────────────────────────────────────────────────


async def handle_checkout_completed(session: dict[str, Any]) -> bool:
    """Process a completed checkout: credit the org and write a ledger entry.

    Returns True if credits were applied, False if skipped (idempotent).
    """
    session_id = session.get("id", "")
    metadata = session.get("metadata", {})
    org_id = metadata.get("org_id")
    amount_cents = int(metadata.get("amount_cents", 0))
    payment_intent_id = session.get("payment_intent")
    payment_method_id = await _lookup_payment_method_id(payment_intent_id)

    if not org_id or amount_cents <= 0:
        logger.warning("Checkout session %s missing org_id or amount_cents", session_id)
        return False

    # Idempotency: check if ledger entry already exists for this session
    existing = await _sb_get(
        f"credit_ledger?stripe_checkout_session_id=eq.{session_id}&select=id&limit=1"
    )
    if existing:
        logger.info("Checkout %s already processed, skipping", session_id)
        return False

    # Get current balance
    credits = await _sb_get(f"org_credits?org_id=eq.{org_id}&select=balance_usd_cents&limit=1")
    if not credits:
        # Auto-create org_credits row if it doesn't exist
        await _sb_post("org_credits", {"org_id": org_id, "balance_usd_cents": 0}, prefer="return=minimal")
        current_balance = 0
    else:
        current_balance = credits[0]["balance_usd_cents"]

    new_balance = current_balance + amount_cents

    # Update balance
    patch_payload: dict[str, Any] = {"balance_usd_cents": new_balance}
    if payment_method_id:
        patch_payload["stripe_payment_method_id"] = payment_method_id

    ok = await _sb_patch(f"org_credits?org_id=eq.{org_id}", patch_payload)
    if not ok:
        logger.error("Failed to update org_credits for %s", org_id)
        return False

    # Write ledger entry
    await _sb_post("credit_ledger", {
        "org_id": org_id,
        "event_type": "credit_added",
        "amount_usd_cents": amount_cents,
        "balance_after_usd_cents": new_balance,
        "stripe_payment_intent_id": payment_intent_id,
        "stripe_checkout_session_id": session_id,
        "description": f"Credit purchase via Stripe Checkout (${amount_cents / 100:.2f})",
    })

    logger.info("Credited %d cents to org %s (new balance: %d)", amount_cents, org_id, new_balance)
    log_payment_event(
        "credits_added",
        org_id=org_id,
        amount_usd_cents=amount_cents,
        provider="stripe",
    )
    return True
