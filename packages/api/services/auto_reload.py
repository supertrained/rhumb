"""Auto-reload service — triggers Stripe PaymentIntent when balance drops below threshold.

Called after a successful credit deduction. Fire-and-forget: never blocks
execution, catches all errors.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from routes._supabase import supabase_fetch
from services.stripe_billing import create_payment_intent

logger = logging.getLogger(__name__)


async def check_and_trigger_auto_reload(
    org_id: str,
    current_balance_cents: int,
) -> dict | None:
    """Check if auto-reload should fire, and trigger it if so.

    Returns ``None`` if no reload needed, or a dict with reload status.
    Called AFTER a successful credit deduction.
    Never blocks execution — catches all errors.
    """
    try:
        # 1. Fetch auto-reload config
        rows = await supabase_fetch(
            f"org_credits?org_id=eq.{org_id}"
            f"&select=auto_reload_enabled,auto_reload_threshold_cents,"
            f"auto_reload_amount_cents,stripe_payment_method_id"
        )
        if not rows:
            return None

        config = rows[0]
        if not config.get("auto_reload_enabled"):
            return None

        threshold = config.get("auto_reload_threshold_cents")
        if threshold is None or current_balance_cents >= threshold:
            return None

        # 2. Check for recent reload (60-second guard against concurrent triggers)
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        recent = await supabase_fetch(
            f"credit_ledger?org_id=eq.{org_id}"
            f"&event_type=eq.auto_reload_triggered"
            f"&created_at=gte.{cutoff}"
            f"&limit=1"
        )
        if recent:
            logger.info("Auto-reload skipped for %s: recent reload within 60s", org_id)
            return {"status": "skipped", "reason": "recent_reload"}

        # 3. Validate payment method
        amount_cents = config.get("auto_reload_amount_cents", 5000)
        payment_method_id = config.get("stripe_payment_method_id")

        if not payment_method_id:
            logger.warning("Auto-reload for %s: no payment method configured", org_id)
            return {"status": "skipped", "reason": "no_payment_method"}

        # 4. Create Stripe PaymentIntent (off-session, confirmed)
        #    The actual credit will be added when the webhook fires.
        try:
            intent = await create_payment_intent(
                org_id=org_id,
                amount_cents=amount_cents,
                payment_method_id=payment_method_id,
            )
            logger.info(
                "Auto-reload triggered for %s: %d cents (PI %s)",
                org_id,
                amount_cents,
                intent.get("id"),
            )
            return {
                "status": "triggered",
                "amount_cents": amount_cents,
                "payment_intent_id": intent.get("id"),
            }
        except Exception as e:
            logger.error("Auto-reload payment failed for %s: %s", org_id, e)
            return {"status": "failed", "error": str(e)}

    except Exception as e:
        logger.error("Auto-reload check failed for %s: %s", org_id, e)
        return None  # Never block execution
