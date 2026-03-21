"""Payment system health indicators."""

from __future__ import annotations

import os

import httpx

from config import settings

_BILLING_HEALTH_PATH = "org_credits?select=org_id&limit=1"


def _billing_headers(supabase_key: str) -> dict[str, str]:
    return {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }


async def _probe_billing_health(supabase_url: str, supabase_key: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{supabase_url}/rest/v1/{_BILLING_HEALTH_PATH}",
                headers=_billing_headers(supabase_key),
                timeout=2.0,
            )
    except httpx.TimeoutException:
        return False, "timeout"
    except httpx.HTTPError:
        return False, "connection_error"
    except Exception:
        return False, "connection_error"

    if response.status_code != 200:
        return False, "connection_error"

    try:
        payload = response.json()
    except ValueError:
        return False, "connection_error"

    if not isinstance(payload, list):
        return False, "connection_error"

    return True, "ok"


async def check_billing_health() -> tuple[bool, str]:
    """Returns billing health for the live Supabase billing backend."""
    return await _probe_billing_health(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )


async def get_payment_health(supabase_url: str, supabase_key: str) -> dict:
    """Return payment system health for the billing health endpoint."""
    billing_healthy, billing_reason = await _probe_billing_health(supabase_url, supabase_key)
    health = {
        "stripe_configured": bool(os.getenv("STRIPE_SECRET_KEY")),
        "usdc_configured": bool(os.getenv("RHUMB_USDC_WALLET_ADDRESS")),
        "billing_table_accessible": billing_healthy,
        "billing_reason": billing_reason,
    }
    health["status"] = "operational" if billing_healthy else "degraded"
    return health
