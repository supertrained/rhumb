"""Tests for kill switches and upstream budget tracking."""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.upstream_budget import (
    PROVIDER_BUDGETS,
    check_provider_budget,
    get_all_provider_budgets,
    get_provider_usage,
    record_provider_usage,
    reset_provider_usage,
)


# ── Upstream Budget Tests ──────────────────────────────────────────


class TestUpstreamBudget:
    """Test upstream provider budget tracking."""

    def setup_method(self) -> None:
        reset_provider_usage()

    def test_initial_usage_is_zero(self) -> None:
        usage = get_provider_usage("tavily")
        assert usage["used"] == 0
        assert usage["status"] == "ok"
        assert usage["limit"] == 1000

    def test_record_usage(self) -> None:
        record_provider_usage("tavily")
        record_provider_usage("tavily")
        usage = get_provider_usage("tavily")
        assert usage["used"] == 2
        assert usage["status"] == "ok"

    def test_exhausted_blocks_execution(self) -> None:
        # Simulate exhausting firecrawl (500/mo limit)
        for _ in range(500):
            record_provider_usage("firecrawl")
        allowed, reason = check_provider_budget("firecrawl")
        assert not allowed
        assert "exhausted" in reason.lower()

    def test_warning_threshold(self) -> None:
        # Firecrawl: 500 limit, 80% = 400
        for _ in range(401):
            record_provider_usage("firecrawl")
        usage = get_provider_usage("firecrawl")
        assert usage["status"] == "warning"
        # Still allowed
        allowed, reason = check_provider_budget("firecrawl")
        assert allowed

    def test_critical_threshold(self) -> None:
        # Firecrawl: 500 limit, 95% = 475
        for _ in range(476):
            record_provider_usage("firecrawl")
        usage = get_provider_usage("firecrawl")
        assert usage["status"] == "critical"
        # Still allowed (critical warns but doesn't block)
        allowed, _ = check_provider_budget("firecrawl")
        assert allowed

    def test_pay_per_use_always_allowed(self) -> None:
        # Replicate has no free tier (monthly_limit=0)
        for _ in range(1000):
            record_provider_usage("replicate")
        allowed, _ = check_provider_budget("replicate")
        assert allowed
        usage = get_provider_usage("replicate")
        assert usage["status"] == "pay_per_use"

    def test_untracked_provider(self) -> None:
        usage = get_provider_usage("unknown-provider")
        assert usage["status"] == "untracked"

    def test_get_all_budgets(self) -> None:
        budgets = get_all_provider_budgets()
        assert len(budgets) == len(PROVIDER_BUDGETS)
        providers = [b["provider"] for b in budgets]
        assert "tavily" in providers
        assert "firecrawl" in providers

    def test_reset_single_provider(self) -> None:
        record_provider_usage("tavily")
        record_provider_usage("exa")
        reset_provider_usage("tavily")
        assert get_provider_usage("tavily")["used"] == 0
        assert get_provider_usage("exa")["used"] == 1

    def test_reset_all(self) -> None:
        record_provider_usage("tavily")
        record_provider_usage("exa")
        reset_provider_usage()
        assert get_provider_usage("tavily")["used"] == 0
        assert get_provider_usage("exa")["used"] == 0

    def test_daily_limit_provider(self) -> None:
        # Resend has daily_limit of 100
        usage = get_provider_usage("resend")
        assert usage["limit"] == 100
        assert usage["reset"] == "daily"
