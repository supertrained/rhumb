"""Routing strategy + spend visibility endpoints.

GET  /v1/agent/routing-strategy — get current strategy
PUT  /v1/agent/routing-strategy — set strategy
GET  /v1/agent/spend            — spend breakdown
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query
from pydantic import BaseModel, Field

from services.error_envelope import RhumbError
from services.routing_engine import RoutingEngine
from services.service_slugs import public_service_slug

router = APIRouter(prefix="/v1/agent", tags=["routing"])

_engine = RoutingEngine()


def _normalize_spend_period(period: str | None) -> str | None:
    """Validate and normalize the public spend period filter."""
    if period is None:
        return None

    normalized = str(period).strip()
    if not normalized:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'period' filter.",
            detail="Provide a period in YYYY-MM format or omit the filter.",
        )

    try:
        datetime.strptime(normalized, "%Y-%m")
    except ValueError as exc:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'period' filter.",
            detail="Provide a period in YYYY-MM format or omit the filter.",
        ) from exc

    return normalized


async def _extract_agent_id(api_key: str | None) -> str:
    """Validate API key and extract agent identity."""
    normalized_key = str(api_key or "").strip()
    if not normalized_key:
        raise HTTPException(401, "Missing X-Rhumb-Key header")
    from schemas.agent_identity import get_agent_identity_store
    store = get_agent_identity_store()
    agent = await store.verify_api_key_with_agent(normalized_key)
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


def _routing_strategy_payload_error(message: str, detail: str) -> RhumbError:
    return RhumbError("INVALID_PARAMETERS", message=message, detail=detail)


def _parse_non_negative_float(value: Any, field_name: str, *, max_value: float | None = None) -> float:
    if isinstance(value, bool):
        raise _routing_strategy_payload_error(
            f"Invalid '{field_name}'.",
            f"Provide {field_name} as a number"
            + (f" between 0 and {max_value:g}." if max_value is not None else " greater than or equal to 0."),
        )

    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise _routing_strategy_payload_error(
            f"Invalid '{field_name}'.",
            f"Provide {field_name} as a number"
            + (f" between 0 and {max_value:g}." if max_value is not None else " greater than or equal to 0."),
        ) from exc

    if parsed < 0 or (max_value is not None and parsed > max_value):
        raise _routing_strategy_payload_error(
            f"Invalid '{field_name}'.",
            f"Provide {field_name} as a number"
            + (f" between 0 and {max_value:g}." if max_value is not None else " greater than or equal to 0."),
        )
    return parsed


def _validate_routing_strategy_payload(body: Any) -> SetRoutingStrategyRequest:
    """Normalize route-owned routing strategy input before auth/state reads."""
    if not isinstance(body, dict):
        raise _routing_strategy_payload_error(
            "Invalid routing strategy payload.",
            "Provide a JSON object payload.",
        )

    raw_strategy = body.get("strategy", "balanced")
    strategy = str(raw_strategy or "").strip().lower() if isinstance(raw_strategy, str) else ""
    if strategy not in {"cheapest", "fastest", "highest_quality", "balanced"}:
        raise _routing_strategy_payload_error(
            "Invalid 'strategy'.",
            "Provide one of: cheapest, fastest, highest_quality, balanced.",
        )

    quality_floor = _parse_non_negative_float(body.get("quality_floor", 6.0), "quality_floor", max_value=10)

    max_cost_per_call_usd: float | None = None
    if body.get("max_cost_per_call_usd") is not None:
        max_cost_per_call_usd = _parse_non_negative_float(
            body.get("max_cost_per_call_usd"),
            "max_cost_per_call_usd",
        )

    return SetRoutingStrategyRequest(
        strategy=strategy,
        quality_floor=quality_floor,
        max_cost_per_call_usd=max_cost_per_call_usd,
    )


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
    body: Any = Body(default=None),
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
):
    """Set agent's routing strategy."""
    validated = _validate_routing_strategy_payload(body)
    agent_id = await _extract_agent_id(x_rhumb_key)
    strat = await _engine.set_strategy(
        agent_id=agent_id,
        strategy=validated.strategy,
        quality_floor=validated.quality_floor,
        max_cost_per_call_usd=validated.max_cost_per_call_usd,
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


def _public_provider_breakdown(rows: list[dict]) -> list[dict]:
    merged: dict[str, dict[str, float | int | str]] = {}
    for row in rows:
        provider = public_service_slug(row.get("provider")) or str(row.get("provider") or "").strip().lower()
        if not provider:
            continue
        if provider not in merged:
            merged[provider] = {"provider": provider, "spend_usd": 0.0, "executions": 0}
        merged[provider]["spend_usd"] = float(merged[provider]["spend_usd"]) + float(row.get("spend_usd") or 0)
        merged[provider]["executions"] = int(merged[provider]["executions"]) + int(row.get("executions") or 0)

    ordered = sorted(merged.values(), key=lambda item: -float(item["spend_usd"]))
    return [
        {
            "provider": str(item["provider"]),
            "spend_usd": round(float(item["spend_usd"]), 4),
            "executions": int(item["executions"]),
        }
        for item in ordered
    ]


@router.get("/spend", response_model=SpendResponse)
async def get_spend(
    period: Optional[str] = Query(None, description="Period (YYYY-MM). Defaults to current month."),
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
):
    """Get spend breakdown for the authenticated agent."""
    normalized_period = _normalize_spend_period(period)
    agent_id = await _extract_agent_id(x_rhumb_key)
    summary = await _engine.get_spend_summary(agent_id, normalized_period)
    return SpendResponse(
        **{
            **summary,
            "by_provider": _public_provider_breakdown(list(summary.get("by_provider") or [])),
        }
    )
