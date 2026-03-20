"""Routing strategy + spend visibility endpoints.

GET  /v1/agent/routing-strategy — get current strategy
PUT  /v1/agent/routing-strategy — set strategy
GET  /v1/agent/spend            — spend breakdown
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from services.routing_engine import RoutingEngine

router = APIRouter(prefix="/v1/agent", tags=["routing"])

_engine = RoutingEngine()


async def _extract_agent_id(api_key: str | None) -> str:
    """Validate API key and extract agent identity."""
    if not api_key:
        raise HTTPException(401, "Missing X-Rhumb-Key header")
    from schemas.agent_identity import get_agent_identity_store
    store = get_agent_identity_store()
    agent = await store.verify_api_key_with_agent(api_key)
    if agent is None:
        raise HTTPException(401, "Invalid or expired API key")
    return agent.agent_id


# -- Routing Strategy --

class RoutingStrategyResponse(BaseModel):
    agent_id: str
    strategy: str
    quality_floor: float
    max_cost_per_call_usd: float | None = None
    weight_score: float
    weight_cost: float
    weight_health: float


class SetRoutingStrategyRequest(BaseModel):
    strategy: str = Field(
        "balanced",
        pattern="^(cheapest|fastest|highest_quality|balanced)$",
        description="Routing strategy",
    )
    quality_floor: float = Field(6.0, ge=0, le=10, description="Minimum AN score")
    max_cost_per_call_usd: float | None = Field(None, ge=0)


@router.get("/routing-strategy", response_model=RoutingStrategyResponse)
async def get_routing_strategy(
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
):
    """Get agent's current routing strategy."""
    agent_id = await _extract_agent_id(x_rhumb_key)
    strat = await _engine.get_strategy(agent_id)
    return RoutingStrategyResponse(
        agent_id=agent_id,
        strategy=strat.strategy,
        quality_floor=strat.quality_floor,
        max_cost_per_call_usd=strat.max_cost_per_call_usd,
        weight_score=strat.weight_score,
        weight_cost=strat.weight_cost,
        weight_health=strat.weight_health,
    )


@router.put("/routing-strategy", response_model=RoutingStrategyResponse)
async def set_routing_strategy(
    body: SetRoutingStrategyRequest,
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
):
    """Set agent's routing strategy."""
    agent_id = await _extract_agent_id(x_rhumb_key)
    strat = await _engine.set_strategy(
        agent_id=agent_id,
        strategy=body.strategy,
        quality_floor=body.quality_floor,
        max_cost_per_call_usd=body.max_cost_per_call_usd,
    )
    return RoutingStrategyResponse(
        agent_id=agent_id,
        strategy=strat.strategy,
        quality_floor=strat.quality_floor,
        max_cost_per_call_usd=strat.max_cost_per_call_usd,
        weight_score=strat.weight_score,
        weight_cost=strat.weight_cost,
        weight_health=strat.weight_health,
    )


# -- Spend Visibility --

class SpendResponse(BaseModel):
    agent_id: str
    period: str
    total_spend_usd: float
    total_executions: int
    by_capability: list[dict]
    by_provider: list[dict]


@router.get("/spend", response_model=SpendResponse)
async def get_spend(
    period: Optional[str] = Query(None, description="Period (YYYY-MM). Defaults to current month."),
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
):
    """Get spend breakdown for the authenticated agent."""
    agent_id = await _extract_agent_id(x_rhumb_key)
    summary = await _engine.get_spend_summary(agent_id, period)
    return SpendResponse(**summary)
