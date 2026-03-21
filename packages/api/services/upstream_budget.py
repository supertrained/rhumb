"""Upstream provider budget tracking for managed execution.

Tracks our API credit usage against each provider's free-tier limits.
In-memory implementation (single-instance Railway deployment).
When a provider hits its limit, managed executions through that provider
are blocked until the budget resets.

Kill hierarchy:
  MANAGED_EXECUTION_ENABLED=false  → blocks ALL execution (nuclear)
  MANAGED_ONLY_KILL=true           → blocks all managed, allows BYOK/x402
  upstream_budget exhausted         → blocks specific provider only
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Optional

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

# ── In-Memory Usage Tracking ───────────────────────────────────────
# Key: provider slug, Value: list of Unix timestamps of executions
_provider_usage: dict[str, list[float]] = defaultdict(list)


def _current_month_start() -> float:
    """Return Unix timestamp of the start of the current UTC month."""
    now = datetime.now(tz=UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC).timestamp()


def _current_day_start() -> float:
    """Return Unix timestamp of the start of the current UTC day."""
    now = datetime.now(tz=UTC)
    return datetime(now.year, now.month, now.day, tzinfo=UTC).timestamp()


def _prune_old_entries(provider: str) -> None:
    """Remove entries older than the current reset window."""
    budget = PROVIDER_BUDGETS.get(provider)
    if not budget:
        return

    reset = budget.get("reset", "monthly")
    if reset == "daily":
        cutoff = _current_day_start()
    elif reset == "monthly":
        cutoff = _current_month_start()
    elif reset == "never":
        cutoff = 0.0  # lifetime — never prune
    else:
        cutoff = _current_month_start()

    _provider_usage[provider] = [
        ts for ts in _provider_usage[provider] if ts >= cutoff
    ]


def record_provider_usage(provider: str) -> None:
    """Record one execution against a provider's budget."""
    _provider_usage[provider].append(time.time())


def get_provider_usage(provider: str) -> dict:
    """Get current usage status for a provider.

    Returns:
        dict with keys: provider, used, limit, percentage, status, unit, reset
    """
    budget = PROVIDER_BUDGETS.get(provider)
    if not budget:
        return {
            "provider": provider,
            "used": len(_provider_usage.get(provider, [])),
            "limit": None,
            "percentage": 0.0,
            "status": "untracked",
            "unit": "unknown",
            "reset": "unknown",
        }

    _prune_old_entries(provider)

    limit_key = "daily_limit" if "daily_limit" in budget else "monthly_limit"
    limit = budget[limit_key]
    used = len(_provider_usage[provider])

    if limit == 0:
        # Pay-per-use: no free tier, every call costs money
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
    }


def check_provider_budget(provider: str) -> tuple[bool, str]:
    """Check if a provider has budget remaining for managed execution.

    Returns:
        (allowed, reason) — allowed=True if execution should proceed.
    """
    usage = get_provider_usage(provider)

    if usage["status"] == "exhausted":
        logger.warning(
            "Provider %s budget exhausted: %d/%d %s used",
            provider, usage["used"], usage["limit"], usage["unit"],
        )
        return False, (
            f"Provider '{provider}' free-tier budget exhausted "
            f"({usage['used']}/{usage['limit']} {usage['unit']}). "
            "Use BYO credentials or try again after budget reset."
        )

    if usage["status"] == "critical":
        logger.warning(
            "Provider %s budget critical: %d/%d %s (%.0f%%)",
            provider, usage["used"], usage["limit"], usage["unit"],
            usage["percentage"] * 100,
        )

    return True, "ok"


def get_all_provider_budgets() -> list[dict]:
    """Get budget status for all tracked providers."""
    results = []
    for provider in sorted(PROVIDER_BUDGETS.keys()):
        results.append(get_provider_usage(provider))
    return results


def reset_provider_usage(provider: Optional[str] = None) -> None:
    """Reset usage tracking. If provider is None, resets all."""
    if provider:
        _provider_usage[provider] = []
    else:
        _provider_usage.clear()
