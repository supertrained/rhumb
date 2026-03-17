"""Self-service billing routes — checkout, balance, and ledger.

Authenticated via X-Rhumb-Key (API key), not admin auth.
Mounted at /v1 prefix in app.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from routes._supabase import supabase_fetch
from services.stripe_billing import create_checkout_session

router = APIRouter(tags=["billing"])

MIN_AMOUNT_USD = 5.0
MAX_AMOUNT_USD = 5000.0

DEFAULT_SUCCESS_URL = "https://rhumb.dev/billing/success"
DEFAULT_CANCEL_URL = "https://rhumb.dev/billing/cancel"


class CheckoutRequest(BaseModel):
    amount_usd: float = Field(..., description="Amount in USD to purchase")
    success_url: str | None = None
    cancel_url: str | None = None


def _require_org(api_key: str | None) -> str:
    """Extract org_id from API key.

    For Phase 0 the API key *is* the org_id.  A real implementation
    would decode a JWT or look up the key in the identity store.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-Rhumb-Key header")
    return api_key


@router.post("/billing/checkout")
async def checkout(
    body: CheckoutRequest,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict:
    """Create a Stripe Checkout Session to purchase credits."""
    org_id = _require_org(x_rhumb_key)

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


@router.get("/billing/balance")
async def get_balance(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict:
    """Return the org's current credit balance."""
    org_id = _require_org(x_rhumb_key)

    rows = await supabase_fetch(
        f"org_credits?org_id=eq.{org_id}&select=balance_usd_cents,reserved_usd_cents&limit=1"
    )

    if not rows:
        return {"balance_usd": 0.0, "balance_cents": 0, "reserved_cents": 0}

    row = rows[0]
    balance_cents = row["balance_usd_cents"]
    reserved_cents = row.get("reserved_usd_cents", 0)

    return {
        "balance_usd": balance_cents / 100,
        "balance_cents": balance_cents,
        "reserved_cents": reserved_cents,
    }


@router.get("/billing/ledger")
async def get_ledger(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict:
    """Return the most recent 50 ledger entries for the org."""
    org_id = _require_org(x_rhumb_key)

    entries = await supabase_fetch(
        f"credit_ledger?org_id=eq.{org_id}"
        f"&select=id,event_type,amount_usd_cents,balance_after_usd_cents,"
        f"stripe_checkout_session_id,description,created_at"
        f"&order=created_at.desc&limit=50"
    )

    if entries is None:
        entries = []

    # Get total count via a separate HEAD-style query
    all_entries = await supabase_fetch(
        f"credit_ledger?org_id=eq.{org_id}&select=id"
    )
    total = len(all_entries) if all_entries else 0

    return {"entries": entries, "total": total}
