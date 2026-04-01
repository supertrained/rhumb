"""Durable upstream provider budget tracking for managed execution.

Tracks our API credit usage against each provider's free-tier limits.
Managed execution now claims provider budget units through shared durable
storage so budget exhaustion survives restarts and coordinates across workers.

Kill hierarchy:
  MANAGED_EXECUTION_ENABLED=false  → blocks ALL execution (nuclear)
  MANAGED_ONLY_KILL=true           → blocks all managed, allows BYOK/x402
  upstream_budget exhausted         → blocks specific provider only
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ── Provider Free-Tier Budgets ──────────────────────────────────────
# Monthly limits for each provider whose credentials we manage.
# These are our actual free-tier allowances — exceeding them costs money
# or cuts off access.
PROVIDER_BUDGETS: dict[str, dict] = {
    "tavily": {"monthly_limit": 1000, "unit": "requests", "reset": "monthly"},
    "exa": {"monthly_limit": 1000, "unit": "requests", "reset": "monthly"},
    "brave-search": {"monthly_limit": 2000, "unit": "requests", "reset": "monthly"},
    "e2b": {"monthly_limit": 6000, "unit": "minutes", "reset": "monthly"},
    "replicate": {"monthly_limit": 0, "unit": "requests", "reset": "never"},  # pay-per-use only
    "algolia": {"monthly_limit": 10000, "unit": "records", "reset": "monthly"},
    "unstructured": {"monthly_limit": 15000, "unit": "pages", "reset": "never"},  # lifetime
    "firecrawl": {"monthly_limit": 500, "unit": "requests", "reset": "monthly"},
    "apify": {"monthly_limit": 5, "unit": "usd", "reset": "monthly"},
    "ipinfo": {"monthly_limit": 50000, "unit": "requests", "reset": "monthly"},
    "scraperapi": {"monthly_limit": 5000, "unit": "credits", "reset": "monthly"},
    "deepgram": {"monthly_limit": 200, "unit": "usd_credits", "reset": "never"},  # one-time
    "resend": {"daily_limit": 100, "unit": "emails", "reset": "daily"},
    "twilio": {"monthly_limit": 0, "unit": "requests", "reset": "never"},  # pay-per-use only
}

# Status thresholds
_WARN_THRESHOLD = 0.80
_CRITICAL_THRESHOLD = 0.95

# ── In-memory fallback state for diagnostics/tests ──────────────────
_provider_usage: dict[str, list[float]] = defaultdict(list)
_tracker: DurableUpstreamBudgetTracker | None = None
_tracker_init_attempted = False


def _current_month_start() -> float:
    """Return Unix timestamp of the start of the current UTC month."""
    now = datetime.now(tz=UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC).timestamp()


def _current_day_start() -> float:
    """Return Unix timestamp of the start of the current UTC day."""
    now = datetime.now(tz=UTC)
    return datetime(now.year, now.month, now.day, tzinfo=UTC).timestamp()


def _prune_old_entries(provider: str) -> None:
    """Remove fallback entries older than the current reset window."""
    budget = PROVIDER_BUDGETS.get(provider)
    if not budget:
        return

    reset = budget.get("reset", "monthly")
    if reset == "daily":
        cutoff = _current_day_start()
    elif reset == "monthly":
        cutoff = _current_month_start()
    elif reset == "never":
        cutoff = 0.0
    else:
        cutoff = _current_month_start()

    _provider_usage[provider] = [ts for ts in _provider_usage[provider] if ts >= cutoff]


def _fallback_record_provider_usage(provider: str) -> None:
    _provider_usage[provider].append(time.time())


def _fallback_reset_provider_usage(provider: str | None = None) -> None:
    if provider:
        _provider_usage[provider] = []
    else:
        _provider_usage.clear()


def _usage_shape(
    provider: str,
    used: int,
    *,
    durable: bool,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    budget = PROVIDER_BUDGETS.get(provider)
    if not budget:
        return {
            "provider": provider,
            "used": used,
            "limit": None,
            "percentage": 0.0,
            "status": "untracked",
            "unit": "unknown",
            "reset": "unknown",
            "durable": durable,
            "reason": unavailable_reason or "",
        }

    limit_key = "daily_limit" if "daily_limit" in budget else "monthly_limit"
    limit = int(budget[limit_key])

    if limit == 0:
        status = "pay_per_use"
        percentage = 0.0
    else:
        percentage = used / limit if limit > 0 else 0.0
        if percentage >= 1.0:
            status = "exhausted"
        elif percentage >= _CRITICAL_THRESHOLD:
            status = "critical"
        elif percentage >= _WARN_THRESHOLD:
            status = "warning"
        else:
            status = "ok"

    return {
        "provider": provider,
        "used": used,
        "limit": limit,
        "percentage": round(percentage, 4),
        "status": status,
        "unit": budget.get("unit", "requests"),
        "reset": budget.get("reset", "monthly"),
        "durable": durable,
        "reason": unavailable_reason or "",
    }


def _budget_window(provider: str) -> tuple[str, datetime, datetime | None]:
    budget = PROVIDER_BUDGETS.get(provider) or {}
    reset = budget.get("reset", "monthly")
    now = datetime.now(tz=UTC)

    if reset == "daily":
        start = datetime(now.year, now.month, now.day, tzinfo=UTC)
        return start.strftime("%Y-%m-%d"), start, start + timedelta(days=1)
    if reset == "monthly":
        start = datetime(now.year, now.month, 1, tzinfo=UTC)
        if now.month == 12:
            end = datetime(now.year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
        return start.strftime("%Y-%m"), start, end
    return "lifetime", datetime(1970, 1, 1, tzinfo=UTC), None


class DurableUpstreamBudgetTracker:
    """Shared durable tracker for managed upstream budget usage."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    async def claim(self, provider: str) -> tuple[bool, str]:
        """Atomically claim one provider budget unit before managed execution."""
        allowed, usage = await self._check_and_increment(provider)

        if not allowed:
            logger.warning(
                "Provider %s budget exhausted: %d/%d %s used",
                provider,
                usage["used"],
                usage["limit"],
                usage["unit"],
            )
            return False, (
                f"Provider '{provider}' free-tier budget exhausted "
                f"({usage['used']}/{usage['limit']} {usage['unit']}). "
                "Use BYO credentials or try again after budget reset."
            )

        if usage["status"] in {"critical", "exhausted"}:
            logger.warning(
                "Provider %s budget critical: %d/%d %s (%.0f%%)",
                provider,
                usage["used"],
                usage["limit"],
                usage["unit"],
                usage["percentage"] * 100,
            )

        return True, "ok"

    async def get_provider_usage(self, provider: str) -> dict[str, Any]:
        """Get current durable usage for a provider's active window."""
        window_key, _, _ = _budget_window(provider)
        result = await self._db.table("upstream_budget_windows").select(
            "usage_count"
        ).eq("provider_slug", provider).eq("window_key", window_key).maybe_single().execute()

        used = 0
        if result.data:
            used = int(result.data.get("usage_count") or 0)
        return _usage_shape(provider, used, durable=True)

    async def get_all_provider_budgets(self) -> list[dict[str, Any]]:
        budgets: list[dict[str, Any]] = []
        for provider in sorted(PROVIDER_BUDGETS.keys()):
            budgets.append(await self.get_provider_usage(provider))
        return budgets

    async def reset(self, provider: str | None = None) -> bool:
        """Reset durable usage state for tests/admin operations."""
        try:
            if provider:
                await self._db.table("upstream_budget_windows").delete().eq(
                    "provider_slug", provider
                ).execute()
            else:
                await self._db.table("upstream_budget_windows").delete().execute()
            return True
        except Exception:
            logger.warning("durable_upstream_budget_reset_failed", exc_info=True)
            return False

    async def _check_and_increment(self, provider: str) -> tuple[bool, dict[str, Any]]:
        budget = PROVIDER_BUDGETS.get(provider)
        if not budget:
            return True, _usage_shape(provider, 0, durable=True)

        limit_key = "daily_limit" if "daily_limit" in budget else "monthly_limit"
        limit = int(budget[limit_key])
        window_key, window_start, window_end = _budget_window(provider)
        enforce_limit = limit > 0

        result = await self._db.rpc(
            "upstream_budget_check_and_increment",
            {
                "p_provider_slug": provider,
                "p_window_key": window_key,
                "p_limit": limit,
                "p_window_start": window_start.isoformat(),
                "p_window_end": window_end.isoformat() if window_end else None,
                "p_enforce_limit": enforce_limit,
            },
        ).execute()

        if result.data and isinstance(result.data, list) and len(result.data) > 0:
            row = result.data[0]
            used = int(row.get("usage_count") or 0)
            allowed = bool(row.get("allowed", False))
            return allowed, _usage_shape(provider, used, durable=True)

        raise RuntimeError("Unexpected upstream budget RPC response")


async def _get_tracker() -> DurableUpstreamBudgetTracker | None:
    global _tracker, _tracker_init_attempted
    if _tracker is not None:
        return _tracker
    if _tracker_init_attempted:
        return None

    _tracker_init_attempted = True
    try:
        from db.client import get_supabase_client

        supabase = await get_supabase_client()
        _tracker = DurableUpstreamBudgetTracker(supabase)
    except Exception:
        logger.warning("durable_upstream_budget_init_failed", exc_info=True)
        _tracker = None
    return _tracker


async def claim_provider_budget(provider: str) -> tuple[bool, str]:
    """Claim one managed-provider budget unit or fail closed if authority is unavailable."""
    tracker = await _get_tracker()
    if tracker is None:
        return False, (
            "Managed provider budget authority is temporarily unavailable. "
            "Try again shortly or use BYO credentials."
        )

    try:
        return await tracker.claim(provider)
    except Exception:
        logger.warning("durable_upstream_budget_claim_failed provider=%s", provider, exc_info=True)
        return False, (
            "Managed provider budget authority is temporarily unavailable. "
            "Try again shortly or use BYO credentials."
        )


async def get_provider_usage(provider: str) -> dict[str, Any]:
    """Get provider usage, preferring durable state and falling back for diagnostics."""
    tracker = await _get_tracker()
    if tracker is not None:
        try:
            return await tracker.get_provider_usage(provider)
        except Exception:
            logger.warning("durable_upstream_budget_get_failed provider=%s", provider, exc_info=True)

    _prune_old_entries(provider)
    return _usage_shape(
        provider,
        len(_provider_usage.get(provider, [])),
        durable=False,
        unavailable_reason="Durable upstream budget authority unavailable.",
    )


async def get_all_provider_budgets() -> list[dict[str, Any]]:
    """Get budget status for all tracked providers."""
    tracker = await _get_tracker()
    if tracker is not None:
        try:
            return await tracker.get_all_provider_budgets()
        except Exception:
            logger.warning("durable_upstream_budget_list_failed", exc_info=True)

    return [await get_provider_usage(provider) for provider in sorted(PROVIDER_BUDGETS.keys())]


async def reset_provider_usage(provider: str | None = None) -> None:
    """Reset usage tracking for tests/admin operations."""
    global _tracker, _tracker_init_attempted

    _fallback_reset_provider_usage(provider)

    tracker = _tracker
    if tracker is not None:
        await tracker.reset(provider)

    if provider is None:
        _tracker = None
        _tracker_init_attempted = False
