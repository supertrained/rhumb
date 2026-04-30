"""Budget management endpoints.

GET  /v1/agent/budget  — current budget status
PUT  /v1/agent/budget  — create/update budget
"""

from __future__ import annotations

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from services.budget_enforcer import BudgetEnforcer
from services.error_envelope import RhumbError

router = APIRouter(prefix="/v1/agent", tags=["budget"])

_enforcer = BudgetEnforcer()


class BudgetResponse(BaseModel):
    agent_id: str
    budget_usd: float | None = None
    spent_usd: float | None = None
    remaining_usd: float | None = None
    period: str | None = None
    hard_limit: bool | None = None
    alert_threshold_pct: int | None = None
    alert_fired: bool | None = None
    unlimited: bool = False


class SetBudgetRequest(BaseModel):
    budget_usd: float = Field(..., description="Budget amount in USD")
    period: str = Field("monthly")
    hard_limit: bool = Field(True, description="If true, reject executions over budget")
    alert_threshold_pct: int = Field(80)


_VALID_BUDGET_PERIODS = {"daily", "weekly", "monthly", "total"}


def _validated_budget_amount(value: float) -> float:
    """Reject invalid budget amounts before governed-key auth runs."""
    normalized = float(value)
    if normalized > 0:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'budget_usd' field.",
        detail="Provide a budget_usd value greater than 0.",
    )


def _validated_budget_period(value: str) -> str:
    """Normalize and validate budget periods before governed-key auth runs."""
    normalized = str(value or "").strip().lower()
    if normalized in _VALID_BUDGET_PERIODS:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'period' field.",
        detail="Use one of: daily, weekly, monthly, total.",
    )


def _validated_alert_threshold_pct(value: int) -> int:
    """Reject invalid alert thresholds before governed-key auth runs."""
    normalized = int(value)
    if 1 <= normalized <= 100:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'alert_threshold_pct' field.",
        detail="Provide an integer between 1 and 100.",
    )


async def _extract_agent_id(api_key: str | None) -> str:
    """Validate API key and extract agent identity.

    Returns the agent_id from the identity store, or raises a canonical 401.
    """
    normalized_key = str(api_key or "").strip()
    if not normalized_key:
        raise RhumbError(
            "CREDENTIAL_MISSING",
            message="Missing X-Rhumb-Key header.",
            detail="Provide a non-empty governed API key in the X-Rhumb-Key header.",
        )

    from schemas.agent_identity import get_agent_identity_store
    store = get_agent_identity_store()
    agent = await store.verify_api_key_with_agent(normalized_key)
    if agent is None:
        raise RhumbError(
            "CREDENTIAL_INVALID",
            message="Invalid or expired API key.",
            detail="Create or rotate a governed key, then retry with X-Rhumb-Key.",
        )
    return agent.agent_id


@router.get("/budget", response_model=BudgetResponse)
async def get_budget(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
):
    """Get current budget status for the authenticated agent."""
    agent_id = await _extract_agent_id(x_rhumb_key)
    status = await _enforcer.get_budget(agent_id)

    if status.budget_usd is None:
        return BudgetResponse(agent_id=agent_id, unlimited=True)

    return BudgetResponse(
        agent_id=agent_id,
        budget_usd=status.budget_usd,
        spent_usd=status.spent_usd,
        remaining_usd=status.remaining_usd,
        period=status.period,
        hard_limit=status.hard_limit,
        alert_threshold_pct=status.alert_threshold_pct,
        alert_fired=status.alert_fired,
    )


@router.put("/budget", response_model=BudgetResponse)
async def set_budget(
    body: SetBudgetRequest,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
):
    """Create or update budget for the authenticated agent."""
    budget_usd = _validated_budget_amount(body.budget_usd)
    period = _validated_budget_period(body.period)
    alert_threshold_pct = _validated_alert_threshold_pct(body.alert_threshold_pct)

    agent_id = await _extract_agent_id(x_rhumb_key)
    status = await _enforcer.set_budget(
        agent_id=agent_id,
        budget_usd=budget_usd,
        period=period,
        hard_limit=body.hard_limit,
        alert_threshold_pct=alert_threshold_pct,
    )

    return BudgetResponse(
        agent_id=agent_id,
        budget_usd=status.budget_usd,
        spent_usd=status.spent_usd,
        remaining_usd=status.remaining_usd,
        period=status.period,
        hard_limit=status.hard_limit,
        alert_threshold_pct=status.alert_threshold_pct,
        alert_fired=status.alert_fired,
    )
