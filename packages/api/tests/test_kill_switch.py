"""Tests for kill switches and upstream budget tracking."""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.upstream_budget as upstream_budget_module
from services.upstream_budget import (
    PROVIDER_BUDGETS,
    DurableUpstreamBudgetTracker,
    claim_provider_budget,
    get_all_provider_budgets,
    get_provider_usage,
    reset_provider_usage,
)


class _MockQueryResult:
    def __init__(self, data=None):
        self.data = data


class _MockBudgetRPC:
    def __init__(self, rows: dict[tuple[str, str], dict], payload: dict):
        self._rows = rows
        self._payload = payload

    async def execute(self):
        provider = str(self._payload["p_provider_slug"])
        window_key = str(self._payload["p_window_key"])
        limit = int(self._payload.get("p_limit") or 0)
        enforce_limit = bool(self._payload.get("p_enforce_limit", True))
        key = (provider, window_key)
        row = self._rows.get(key)

        if row is None:
            row = {
                "provider_slug": provider,
                "window_key": window_key,
                "usage_count": 1,
                "window_start": self._payload["p_window_start"],
                "window_end": self._payload.get("p_window_end"),
            }
            self._rows[key] = row
            return _MockQueryResult([
                {
                    "allowed": True,
                    "remaining": max(limit - 1, 0) if limit > 0 else 0,
                    "usage_count": 1,
                    "window_start": row["window_start"],
                    "window_end": row["window_end"],
                }
            ])

        used = int(row["usage_count"])
        if enforce_limit and limit > 0 and used >= limit:
            return _MockQueryResult([
                {
                    "allowed": False,
                    "remaining": 0,
                    "usage_count": used,
                    "window_start": row["window_start"],
                    "window_end": row["window_end"],
                }
            ])

        row["usage_count"] = used + 1
        return _MockQueryResult([
            {
                "allowed": True,
                "remaining": max(limit - row["usage_count"], 0) if limit > 0 else 0,
                "usage_count": row["usage_count"],
                "window_start": row["window_start"],
                "window_end": row["window_end"],
            }
        ])


class _MockBudgetTable:
    def __init__(self, rows: dict[tuple[str, str], dict]):
        self._rows = rows
        self._filters: dict[str, str] = {}
        self._mode = "select"
        self._single = False

    def select(self, *_args):
        self._mode = "select"
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def eq(self, column: str, value):
        self._filters[column] = str(value)
        return self

    def maybe_single(self):
        self._single = True
        return self

    async def execute(self):
        matches = []
        for row in self._rows.values():
            if all(str(row.get(key)) == value for key, value in self._filters.items()):
                matches.append(row)

        if self._mode == "delete":
            if self._filters:
                doomed = [key for key, row in self._rows.items() if all(str(row.get(k)) == v for k, v in self._filters.items())]
            else:
                doomed = list(self._rows.keys())
            for key in doomed:
                self._rows.pop(key, None)
            return _MockQueryResult([])

        if self._single:
            return _MockQueryResult(matches[0] if matches else None)
        return _MockQueryResult(matches)


class _MockBudgetSupabase:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}

    def rpc(self, name: str, payload: dict):
        assert name == "upstream_budget_check_and_increment"
        return _MockBudgetRPC(self.rows, payload)

    def table(self, name: str):
        assert name == "upstream_budget_windows"
        return _MockBudgetTable(self.rows)


# ── Upstream Budget Tests ──────────────────────────────────────────


@pytest.fixture
def mock_budget_tracker(monkeypatch: pytest.MonkeyPatch) -> _MockBudgetSupabase:
    db = _MockBudgetSupabase()
    tracker = DurableUpstreamBudgetTracker(db)
    monkeypatch.setattr(upstream_budget_module, "_tracker", tracker)
    monkeypatch.setattr(upstream_budget_module, "_tracker_init_attempted", True)
    return db


class TestUpstreamBudget:
    """Test durable upstream provider budget tracking."""

    @pytest.mark.anyio
    async def test_initial_usage_is_zero(self, mock_budget_tracker) -> None:
        usage = await get_provider_usage("tavily")
        assert usage["used"] == 0
        assert usage["status"] == "ok"
        assert usage["limit"] == 1000
        assert usage["durable"] is True

    @pytest.mark.anyio
    async def test_claim_usage(self, mock_budget_tracker) -> None:
        allowed, _ = await claim_provider_budget("tavily")
        assert allowed is True
        allowed, _ = await claim_provider_budget("tavily")
        assert allowed is True
        usage = await get_provider_usage("tavily")
        assert usage["used"] == 2
        assert usage["status"] == "ok"

    @pytest.mark.anyio
    async def test_exhausted_blocks_execution(self, mock_budget_tracker) -> None:
        for _ in range(500):
            allowed, _ = await claim_provider_budget("firecrawl")
            assert allowed is True
        allowed, reason = await claim_provider_budget("firecrawl")
        assert not allowed
        assert "exhausted" in reason.lower()

    @pytest.mark.anyio
    async def test_warning_threshold(self, mock_budget_tracker) -> None:
        for _ in range(401):
            allowed, _ = await claim_provider_budget("firecrawl")
            assert allowed is True
        usage = await get_provider_usage("firecrawl")
        assert usage["status"] == "warning"

    @pytest.mark.anyio
    async def test_critical_threshold(self, mock_budget_tracker) -> None:
        for _ in range(476):
            allowed, _ = await claim_provider_budget("firecrawl")
            assert allowed is True
        usage = await get_provider_usage("firecrawl")
        assert usage["status"] == "critical"

    @pytest.mark.anyio
    async def test_pay_per_use_always_allowed(self, mock_budget_tracker) -> None:
        for _ in range(1000):
            allowed, _ = await claim_provider_budget("replicate")
            assert allowed is True
        usage = await get_provider_usage("replicate")
        assert usage["status"] == "pay_per_use"
        assert usage["used"] == 1000

    @pytest.mark.anyio
    async def test_untracked_provider(self, mock_budget_tracker) -> None:
        usage = await get_provider_usage("unknown-provider")
        assert usage["status"] == "untracked"

    @pytest.mark.anyio
    async def test_get_all_budgets(self, mock_budget_tracker) -> None:
        budgets = await get_all_provider_budgets()
        assert len(budgets) == len(PROVIDER_BUDGETS)
        providers = [b["provider"] for b in budgets]
        assert "tavily" in providers
        assert "firecrawl" in providers

    @pytest.mark.anyio
    async def test_reset_single_provider(self, mock_budget_tracker) -> None:
        await claim_provider_budget("tavily")
        await claim_provider_budget("exa")
        await reset_provider_usage("tavily")
        assert (await get_provider_usage("tavily"))["used"] == 0
        assert (await get_provider_usage("exa"))["used"] == 1

    @pytest.mark.anyio
    async def test_reset_all(self, mock_budget_tracker) -> None:
        await claim_provider_budget("tavily")
        await claim_provider_budget("exa")
        await reset_provider_usage()
        upstream_budget_module._tracker = DurableUpstreamBudgetTracker(mock_budget_tracker)
        upstream_budget_module._tracker_init_attempted = True
        assert (await get_provider_usage("tavily"))["used"] == 0
        assert (await get_provider_usage("exa"))["used"] == 0

    @pytest.mark.anyio
    async def test_daily_limit_provider(self, mock_budget_tracker) -> None:
        usage = await get_provider_usage("resend")
        assert usage["limit"] == 100
        assert usage["reset"] == "daily"

    @pytest.mark.anyio
    async def test_claim_fails_closed_when_durable_authority_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(upstream_budget_module, "_tracker", None)
        monkeypatch.setattr(upstream_budget_module, "_tracker_init_attempted", True)
        allowed, reason = await claim_provider_budget("tavily")
        assert allowed is False
        assert "temporarily unavailable" in reason.lower()
