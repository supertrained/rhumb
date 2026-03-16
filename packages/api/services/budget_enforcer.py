"""Budget enforcement service for capability execution.

Pre-execution atomic check-and-decrement. Post-failure release.
Uses Supabase RPC for atomic budget operations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class BudgetStatus:
    """Result of a budget check or operation."""

    allowed: bool
    remaining_usd: float | None  # None = no budget configured (unlimited)
    budget_usd: float | None
    spent_usd: float | None
    period: str | None
    hard_limit: bool | None
    alert_threshold_pct: int | None
    alert_fired: bool | None


@dataclass
class BudgetCheckResult:
    """Result of a pre-execution budget check."""

    allowed: bool
    remaining_usd: float | None
    reason: str | None = None  # set when not allowed


class BudgetEnforcer:
    """Pre-execution budget enforcement via Supabase RPC.

    Usage:
        enforcer = BudgetEnforcer()

        # Pre-execution check + decrement
        result = await enforcer.check_and_decrement(agent_id, cost_usd)
        if not result.allowed:
            raise HTTPException(402, result.reason)

        # Execute capability...

        # On failure, release the reservation
        await enforcer.release(agent_id, cost_usd)
    """

    def _get_headers(self) -> dict[str, str]:
        return {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
        }

    async def check_and_decrement(
        self, agent_id: str, cost_usd: float
    ) -> BudgetCheckResult:
        """Atomically check budget and decrement if allowed.

        Returns BudgetCheckResult with allowed=True if execution should proceed.
        Returns allowed=False with reason if budget would be exceeded.
        """
        if cost_usd <= 0:
            return BudgetCheckResult(allowed=True, remaining_usd=None)

        url = f"{settings.supabase_url}/rest/v1/rpc/check_and_decrement_budget"
        payload = {"p_agent_id": agent_id, "p_cost": cost_usd}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=10.0,
                )

                if resp.status_code != 200:
                    logger.warning(
                        "Budget check RPC failed: %s %s",
                        resp.status_code,
                        resp.text,
                    )
                    # Fail open: if budget system is down, allow execution
                    return BudgetCheckResult(allowed=True, remaining_usd=None)

                remaining = float(resp.json())

                if remaining == -1:
                    return BudgetCheckResult(
                        allowed=False,
                        remaining_usd=0,
                        reason=f"Budget exceeded. Estimated cost: ${cost_usd:.4f}. Agent budget exhausted.",
                    )

                if remaining >= 999999:
                    # No budget configured — unlimited
                    return BudgetCheckResult(allowed=True, remaining_usd=None)

                return BudgetCheckResult(allowed=True, remaining_usd=remaining)

        except Exception as e:
            logger.warning("Budget check failed, allowing execution: %s", e)
            # Fail open
            return BudgetCheckResult(allowed=True, remaining_usd=None)

    async def release(self, agent_id: str, cost_usd: float) -> float | None:
        """Release a budget reservation on execution failure.

        Returns remaining_usd after release, or None on error.
        """
        if cost_usd <= 0:
            return None

        url = f"{settings.supabase_url}/rest/v1/rpc/release_budget"
        payload = {"p_agent_id": agent_id, "p_cost": cost_usd}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=10.0,
                )

                if resp.status_code != 200:
                    logger.warning(
                        "Budget release RPC failed: %s %s",
                        resp.status_code,
                        resp.text,
                    )
                    return None

                remaining = float(resp.json())
                return remaining if remaining < 999999 else None

        except Exception as e:
            logger.warning("Budget release failed: %s", e)
            return None

    async def get_budget(self, agent_id: str) -> BudgetStatus:
        """Get current budget status for an agent."""
        url = f"{settings.supabase_url}/rest/v1/agent_budgets?agent_id=eq.{agent_id}&select=*"

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    url,
                    headers=self._get_headers(),
                    timeout=10.0,
                )

                if resp.status_code != 200 or not resp.json():
                    return BudgetStatus(
                        allowed=True,
                        remaining_usd=None,
                        budget_usd=None,
                        spent_usd=None,
                        period=None,
                        hard_limit=None,
                        alert_threshold_pct=None,
                        alert_fired=None,
                    )

                row = resp.json()[0]
                budget = float(row["budget_usd"])
                spent = float(row["spent_usd"])
                remaining = budget - spent

                return BudgetStatus(
                    allowed=remaining > 0 or not row["hard_limit"],
                    remaining_usd=remaining,
                    budget_usd=budget,
                    spent_usd=spent,
                    period=row["period"],
                    hard_limit=row["hard_limit"],
                    alert_threshold_pct=row["alert_threshold_pct"],
                    alert_fired=row["alert_fired"],
                )

        except Exception as e:
            logger.warning("Budget status fetch failed: %s", e)
            return BudgetStatus(
                allowed=True,
                remaining_usd=None,
                budget_usd=None,
                spent_usd=None,
                period=None,
                hard_limit=None,
                alert_threshold_pct=None,
                alert_fired=None,
            )

    async def set_budget(
        self,
        agent_id: str,
        budget_usd: float,
        period: str = "monthly",
        hard_limit: bool = True,
        alert_threshold_pct: int = 80,
    ) -> BudgetStatus:
        """Create or update budget for an agent. Upserts."""
        url = f"{settings.supabase_url}/rest/v1/agent_budgets"
        headers = {
            **self._get_headers(),
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        payload = {
            "agent_id": agent_id,
            "budget_usd": budget_usd,
            "period": period,
            "hard_limit": hard_limit,
            "alert_threshold_pct": alert_threshold_pct,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=10.0,
                )

                if resp.status_code in (200, 201):
                    rows = resp.json()
                    if rows:
                        row = rows[0]
                        return BudgetStatus(
                            allowed=True,
                            remaining_usd=float(row["budget_usd"]) - float(row["spent_usd"]),
                            budget_usd=float(row["budget_usd"]),
                            spent_usd=float(row["spent_usd"]),
                            period=row["period"],
                            hard_limit=row["hard_limit"],
                            alert_threshold_pct=row["alert_threshold_pct"],
                            alert_fired=row["alert_fired"],
                        )

                logger.warning("Budget upsert response: %s %s", resp.status_code, resp.text)

        except Exception as e:
            logger.warning("Budget set failed: %s", e)

        # Return a best-effort status
        return await self.get_budget(agent_id)
