"""Self-service billing routes — checkout, balance, ledger, and auto-reload config.

Authenticated via X-Rhumb-Key (API key), not admin auth.
Mounted at /v1 prefix in app.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from routes._supabase import supabase_count, supabase_fetch, supabase_patch
from services.payment_health import get_payment_health
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


class AutoReloadRequest(BaseModel):
    enabled: bool
    threshold_usd: float | None = None
    amount_usd: float | None = None


def _require_org(api_key: str | None) -> str:
    """Extract org_id from API key.

    For Phase 0 the API key *is* the org_id.  A real implementation
    would decode a JWT or look up the key in the identity store.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-Rhumb-Key header")
    return api_key


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------


@router.get("/billing/balance")
async def get_balance(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict:
    """Return the org's current credit balance with auto-reload config."""
    org_id = _require_org(x_rhumb_key)

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
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: str | None = Query(None),
) -> dict:
    """Return paginated, optionally filtered ledger entries for the org."""
    org_id = _require_org(x_rhumb_key)

    base_filter = f"credit_ledger?org_id=eq.{org_id}"
    if event_type:
        base_filter += f"&event_type=eq.{event_type}"

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
    org_id = _require_org(x_rhumb_key)

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
