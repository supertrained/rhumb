"""Budget management endpoints.

GET  /v1/agent/budget  — current budget status
PUT  /v1/agent/budget  — create/update budget
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from services.budget_enforcer import BudgetEnforcer

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
    budget_usd: float = Field(..., gt=0, description="Budget amount in USD")
    period: str = Field("monthly", pattern="^(daily|weekly|monthly|total)$")
    hard_limit: bool = Field(True, description="If true, reject executions over budget")
    alert_threshold_pct: int = Field(80, ge=1, le=100)


def _extract_agent_id(api_key: str | None) -> str:
    """Extract agent identity from API key.

    For now, uses the API key itself as the agent identifier.
    In production, this would decode a JWT or look up the agent.
    """
    if not api_key:
        raise HTTPException(401, "Missing X-Rhumb-Key header")
    # Use a hash prefix as agent_id to avoid storing the full key
    import hashlib

    return f"agent_{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"


@router.get("/budget", response_model=BudgetResponse)
async def get_budget(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
):
    """Get current budget status for the authenticated agent."""
    agent_id = _extract_agent_id(x_rhumb_key)
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
    agent_id = _extract_agent_id(x_rhumb_key)
    status = await _enforcer.set_budget(
        agent_id=agent_id,
        budget_usd=body.budget_usd,
        period=body.period,
        hard_limit=body.hard_limit,
        alert_threshold_pct=body.alert_threshold_pct,
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
