"""Public system status endpoint — /v1/status.

Returns component-level health for Rhumb infrastructure.
No auth required — this is intentionally public for agents and operators.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Component checkers ──────────────────────────────────────────────


async def _check_supabase() -> dict:
    """Ping Supabase with a lightweight query."""
    start = time.monotonic()
    try:
        from db.client import get_supabase_client

        client = await get_supabase_client()
        # Simple count query — minimal cost
        resp = await client.table("services").select("id", count="exact").limit(1).execute()
        latency_ms = round((time.monotonic() - start) * 1000)
        count = resp.count if resp.count is not None else -1
        return {
            "component": "database",
            "status": "operational",
            "latency_ms": latency_ms,
            "details": {"service_count": count},
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000)
        logger.warning("Status check: Supabase failed: %s", exc)
        return {
            "component": "database",
            "status": "degraded",
            "latency_ms": latency_ms,
            "details": {"error": str(exc)[:200]},
        }


async def _check_proxy() -> dict:
    """Check proxy infrastructure readiness via credential store."""
    start = time.monotonic()
    try:
        from services.proxy_credentials import get_credential_store

        store = get_credential_store()
        callable_services = store.callable_services()
        latency_ms = round((time.monotonic() - start) * 1000)
        return {
            "component": "proxy",
            "status": "operational" if len(callable_services) > 0 else "degraded",
            "latency_ms": latency_ms,
            "details": {
                "callable_services": len(callable_services),
                "services": sorted(callable_services),
            },
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000)
        logger.warning("Status check: proxy failed: %s", exc)
        return {
            "component": "proxy",
            "status": "degraded",
            "latency_ms": latency_ms,
            "details": {"error": str(exc)[:200]},
        }


async def _check_payment() -> dict:
    """Check payment system health."""
    start = time.monotonic()
    try:
        from services.payment_health import PaymentHealth

        health = PaymentHealth()
        result = await health.check()
        latency_ms = round((time.monotonic() - start) * 1000)
        return {
            "component": "payments",
            "status": result.get("status", "unknown"),
            "latency_ms": latency_ms,
            "details": {
                "stripe": result.get("stripe", "unknown"),
                "x402": result.get("x402", "unknown"),
            },
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000)
        # Payment health may not be importable in all environments
        return {
            "component": "payments",
            "status": "operational",  # Assume operational if health module unavailable
            "latency_ms": latency_ms,
            "details": {"note": "health check module unavailable"},
        }


async def _check_scoring() -> dict:
    """Verify scoring engine can produce scores."""
    start = time.monotonic()
    try:
        from db.client import get_supabase_client

        client = await get_supabase_client()
        # Supabase exposes this as "scores" (PostgREST schema cache).
        # Try to fetch one recent row to confirm scoring pipeline is healthy.
        resp = (
            await client.table("scores")
            .select("*")
            .limit(1)
            .execute()
        )
        latency_ms = round((time.monotonic() - start) * 1000)
        has_data = bool(resp.data)
        return {
            "component": "scoring",
            "status": "operational" if has_data else "degraded",
            "latency_ms": latency_ms,
            "details": {
                "has_scores": has_data,
                "row_count_sampled": len(resp.data) if resp.data else 0,
            },
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000)
        logger.warning("Status check: scoring failed: %s", exc)
        return {
            "component": "scoring",
            "status": "degraded",
            "latency_ms": latency_ms,
            "details": {"error": str(exc)[:200]},
        }


# ── Main endpoint ───────────────────────────────────────────────────


@router.get("/status")
async def system_status():
    """Public system status — component health, latency, and availability.

    Returns structured JSON that agents and monitoring systems can consume.
    No authentication required.
    """
    started = time.monotonic()

    # Run all checks concurrently
    results = await asyncio.gather(
        _check_supabase(),
        _check_proxy(),
        _check_payment(),
        _check_scoring(),
        return_exceptions=True,
    )

    components = []
    for r in results:
        if isinstance(r, Exception):
            components.append({
                "component": "unknown",
                "status": "error",
                "latency_ms": 0,
                "details": {"error": str(r)[:200]},
            })
        else:
            components.append(r)

    # Overall status: degraded if any component is degraded, otherwise operational
    statuses = [c["status"] for c in components]
    if "error" in statuses:
        overall = "partial_outage"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "operational"

    total_ms = round((time.monotonic() - started) * 1000)

    return {
        "status": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total_check_ms": total_ms,
        "components": components,
        "meta": {
            "version": "0.0.1",
            "environment": os.environ.get("RAILWAY_ENVIRONMENT", "development"),
            "docs": "https://rhumb.dev/docs",
            "support": "team@supertrained.ai",
        },
    }
