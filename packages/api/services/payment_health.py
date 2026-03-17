"""Payment system health indicators."""

import os

import httpx


async def get_payment_health(supabase_url: str, supabase_key: str) -> dict:
    """
    Returns payment system health status.
    Called from a new GET /v1/billing/health endpoint.
    """
    health = {
        "stripe_configured": False,
        "usdc_configured": False,
        "billing_table_accessible": False,
    }

    # Check Stripe config
    health["stripe_configured"] = bool(os.getenv("STRIPE_SECRET_KEY"))
    health["usdc_configured"] = bool(os.getenv("RHUMB_USDC_WALLET_ADDRESS"))

    # Check billing table access
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"{supabase_url}/rest/v1/org_credits?select=org_id&limit=1",
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                },
                timeout=10.0,
            )
            health["billing_table_accessible"] = res.status_code == 200
    except Exception:
        health["billing_table_accessible"] = False

    health["status"] = (
        "operational" if health["billing_table_accessible"] else "degraded"
    )
    return health
