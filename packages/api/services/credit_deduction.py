"""Org credit deduction service (Supabase RPC wrapper).

Uses PostgREST RPC endpoints for atomic credit deduction/release.
Falls back to BudgetEnforcer when no org wallet exists to preserve
backward compatibility with pre-credit agents.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from config import settings
from services.budget_enforcer import BudgetEnforcer
from services.payment_metrics import log_payment_event

logger = logging.getLogger(__name__)


@dataclass
class CreditDeductionResult:
    allowed: bool
    remaining_cents: int | None
    ledger_id: str | None = None
    reason: str | None = None
    used_budget_fallback: bool = False
    billing_unavailable: bool = False


@dataclass
class CreditReleaseResult:
    released: bool
    remaining_cents: int | None
    ledger_id: str | None = None
    idempotent: bool = False
    reason: str | None = None
    used_budget_fallback: bool = False


class CreditDeductionService:
    """Wrapper around deduct_org_credits/release_org_credits RPCs."""

    def __init__(self, budget_enforcer: BudgetEnforcer | None = None) -> None:
        self._budget_enforcer = budget_enforcer or BudgetEnforcer()

    def _get_headers(self) -> dict[str, str]:
        return {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
        }

    async def deduct(
        self,
        org_id: str,
        amount_cents: int,
        *,
        execution_id: str | None = None,
        agent_id: str | None = None,
        fallback_cost_usd: float = 0.0,
        skip_budget_fallback: bool = False,
    ) -> CreditDeductionResult:
        """Attempt org-credit deduction.

        Fail closed on billing RPC/system errors.
        If org credits do not exist, optionally fall back to BudgetEnforcer.
        """
        if amount_cents <= 0:
            return CreditDeductionResult(allowed=True, remaining_cents=None)

        payload = {
            "p_org_id": org_id,
            "p_amount_cents": amount_cents,
            "p_execution_id": execution_id,
        }
        url = f"{settings.supabase_url}/rest/v1/rpc/deduct_org_credits"

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=10.0,
                )

            if resp.status_code != 200:
                logger.error(
                    "Credit deduction RPC failed (%s): %s",
                    resp.status_code,
                    resp.text,
                )
                return CreditDeductionResult(
                    allowed=False,
                    remaining_cents=None,
                    reason="billing_unavailable",
                    billing_unavailable=True,
                )

            data_raw = resp.json()
            if not isinstance(data_raw, dict):
                logger.error("Credit deduction RPC returned malformed payload: %r", data_raw)
                return CreditDeductionResult(
                    allowed=False,
                    remaining_cents=None,
                    reason="billing_unavailable",
                    billing_unavailable=True,
                )
            data = data_raw
            allowed = bool(data.get("allowed", False))
            if allowed:
                remaining = data.get("remaining_cents")
                log_payment_event(
                    "credit_deducted",
                    org_id=org_id,
                    amount_usd_cents=amount_cents,
                    execution_id=execution_id,
                )
                return CreditDeductionResult(
                    allowed=True,
                    remaining_cents=int(remaining) if remaining is not None else None,
                    ledger_id=data.get("ledger_id"),
                )

            reason = data.get("reason")
            if reason == "no_org_credits":
                if not skip_budget_fallback and agent_id and fallback_cost_usd > 0:
                    budget_result = await self._budget_enforcer.check_and_decrement(
                        agent_id,
                        fallback_cost_usd,
                    )
                    if budget_result.allowed:
                        return CreditDeductionResult(
                            allowed=True,
                            remaining_cents=None,
                            used_budget_fallback=True,
                            reason="no_org_credits",
                        )
                    return CreditDeductionResult(
                        allowed=False,
                        remaining_cents=None,
                        reason=budget_result.reason or "Budget exceeded",
                        used_budget_fallback=True,
                    )

                # Backward compatibility in paths that already checked agent budget.
                return CreditDeductionResult(
                    allowed=False,
                    remaining_cents=None,
                    reason="no_org_credits",
                    used_budget_fallback=False,
                )

            log_payment_event(
                "credit_insufficient",
                org_id=org_id,
                amount_usd_cents=amount_cents,
                execution_id=execution_id,
                success=False,
                error=reason or "insufficient_credits",
            )
            return CreditDeductionResult(
                allowed=False,
                remaining_cents=(
                    int(data["balance_cents"]) if data.get("balance_cents") is not None else None
                ),
                reason=reason or "insufficient_credits",
            )

        except Exception as e:
            logger.error("Credit deduction failed, blocking execution: %s", e)
            return CreditDeductionResult(
                allowed=False,
                remaining_cents=None,
                reason="billing_unavailable",
                billing_unavailable=True,
            )

    async def release(
        self,
        org_id: str,
        amount_cents: int,
        *,
        execution_id: str | None = None,
        agent_id: str | None = None,
        fallback_cost_usd: float = 0.0,
        skip_budget_fallback: bool = False,
    ) -> CreditReleaseResult:
        """Release previously reserved org credits."""
        if amount_cents <= 0:
            return CreditReleaseResult(released=True, remaining_cents=None, idempotent=True)

        payload = {
            "p_org_id": org_id,
            "p_amount_cents": amount_cents,
            "p_execution_id": execution_id,
        }
        url = f"{settings.supabase_url}/rest/v1/rpc/release_org_credits"

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
                    "Credit release RPC failed (%s): %s",
                    resp.status_code,
                    resp.text,
                )
                return CreditReleaseResult(released=False, remaining_cents=None)

            data: dict[str, Any] = resp.json() if isinstance(resp.json(), dict) else {}
            released = bool(data.get("released", False))
            reason = data.get("reason")

            if reason == "no_org_credits" and not skip_budget_fallback and agent_id and fallback_cost_usd > 0:
                await self._budget_enforcer.release(agent_id, fallback_cost_usd)
                return CreditReleaseResult(
                    released=True,
                    remaining_cents=None,
                    idempotent=True,
                    reason=reason,
                    used_budget_fallback=True,
                )

            return CreditReleaseResult(
                released=released,
                remaining_cents=(
                    int(data["remaining_cents"]) if data.get("remaining_cents") is not None else None
                ),
                ledger_id=data.get("ledger_id"),
                idempotent=bool(data.get("idempotent", False)),
                reason=reason,
            )

        except Exception as e:
            logger.warning("Credit release failed: %s", e)
            return CreditReleaseResult(released=False, remaining_cents=None)
