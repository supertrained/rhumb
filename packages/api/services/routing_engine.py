"""Routing engine — cost-optimal provider selection with quality floor.

Strategies:
- cheapest: lowest cost per call that meets quality floor
- fastest: lowest latency (uses circuit breaker health as proxy)
- highest_quality: highest AN score
- balanced: weighted combination of score, cost, health
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from config import settings
from services.service_slugs import public_service_slug

logger = logging.getLogger(__name__)


@dataclass
class RoutingStrategy:
    """Agent's routing preference."""

    strategy: str = "balanced"
    quality_floor: float = 6.0
    max_cost_per_call_usd: float | None = None
    weight_score: float = 0.40
    weight_cost: float = 0.30
    weight_health: float = 0.30


@dataclass
class RoutedProvider:
    """Result of routing: which provider was selected and why."""

    service_slug: str
    an_score: float
    cost_per_call: float | None
    circuit_state: str
    strategy_used: str
    composite_score: float  # the blended routing score


class RoutingEngine:
    """Provider selection engine with pluggable strategies."""

    def _get_headers(self) -> dict[str, str]:
        return {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
        }

    async def get_strategy(self, agent_id: str) -> RoutingStrategy:
        """Fetch agent's routing strategy. Returns default 'balanced' if none set."""
        url = (
            f"{settings.supabase_url}/rest/v1/agent_routing_strategies"
            f"?agent_id=eq.{agent_id}&select=*&limit=1"
        )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._get_headers(), timeout=10.0)
                if resp.status_code == 200 and resp.json():
                    row = resp.json()[0]
                    return RoutingStrategy(
                        strategy=row["strategy"],
                        quality_floor=float(row["quality_floor"]),
                        max_cost_per_call_usd=(
                            float(row["max_cost_per_call_usd"])
                            if row.get("max_cost_per_call_usd") is not None
                            else None
                        ),
                        weight_score=float(row["weight_score"]),
                        weight_cost=float(row["weight_cost"]),
                        weight_health=float(row["weight_health"]),
                    )
        except Exception as e:
            logger.warning("Failed to fetch routing strategy: %s", e)

        return RoutingStrategy()  # default balanced

    async def set_strategy(
        self,
        agent_id: str,
        strategy: str = "balanced",
        quality_floor: float = 6.0,
        max_cost_per_call_usd: float | None = None,
    ) -> RoutingStrategy:
        """Create or update agent's routing strategy."""
        url = f"{settings.supabase_url}/rest/v1/agent_routing_strategies"
        headers = {
            **self._get_headers(),
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "strategy": strategy,
            "quality_floor": quality_floor,
        }
        if max_cost_per_call_usd is not None:
            payload["max_cost_per_call_usd"] = max_cost_per_call_usd

        # Set weights based on strategy
        if strategy == "cheapest":
            payload.update(weight_score=0.10, weight_cost=0.80, weight_health=0.10)
        elif strategy == "fastest":
            payload.update(weight_score=0.10, weight_cost=0.10, weight_health=0.80)
        elif strategy == "highest_quality":
            payload.update(weight_score=0.80, weight_cost=0.10, weight_health=0.10)
        else:  # balanced
            payload.update(weight_score=0.40, weight_cost=0.30, weight_health=0.30)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url, headers=headers, json=payload, timeout=10.0
                )
                if resp.status_code in (200, 201) and resp.json():
                    row = resp.json()[0]
                    return RoutingStrategy(
                        strategy=row["strategy"],
                        quality_floor=float(row["quality_floor"]),
                        max_cost_per_call_usd=(
                            float(row["max_cost_per_call_usd"])
                            if row.get("max_cost_per_call_usd") is not None
                            else None
                        ),
                        weight_score=float(row["weight_score"]),
                        weight_cost=float(row["weight_cost"]),
                        weight_health=float(row["weight_health"]),
                    )
        except Exception as e:
            logger.warning("Failed to set routing strategy: %s", e)

        return await self.get_strategy(agent_id)

    def select_provider(
        self,
        mappings: list[dict],
        scores_by_slug: dict[str, float],
        circuit_states: dict[str, str],
        strategy: RoutingStrategy,
    ) -> RoutedProvider | None:
        """Select the best provider using the given strategy.

        Args:
            mappings: capability_services rows
            scores_by_slug: {slug: AN score}
            circuit_states: {slug: 'closed'|'open'|'half_open'}
            strategy: agent's routing preference

        Returns:
            RoutedProvider or None if no viable provider
        """
        candidates: list[tuple[float, dict]] = []

        # Find max cost for normalization
        costs = [
            float(m["cost_per_call"])
            for m in mappings
            if m.get("cost_per_call") is not None
        ]
        max_cost = max(costs) if costs else 1.0
        if max_cost == 0:
            max_cost = 1.0

        for m in mappings:
            slug = m["service_slug"]
            an_score = scores_by_slug.get(slug, 0.0)
            cost = float(m["cost_per_call"]) if m.get("cost_per_call") is not None else 0.0
            circuit = circuit_states.get(slug, "closed")

            # Skip open circuits
            if circuit == "open":
                continue

            # Quality floor filter
            if an_score < strategy.quality_floor:
                continue

            # Max cost filter
            if strategy.max_cost_per_call_usd is not None and cost > strategy.max_cost_per_call_usd:
                continue

            # Health score: closed=1.0, half_open=0.5, open=0.0
            health = 1.0 if circuit == "closed" else 0.5

            # Normalize score to 0-1 range (assuming max 10)
            norm_score = min(an_score / 10.0, 1.0)

            # Normalize cost (inverted: cheaper = higher score)
            norm_cost = 1.0 - (cost / max_cost) if max_cost > 0 else 1.0

            # Compute composite score
            composite = (
                strategy.weight_score * norm_score
                + strategy.weight_cost * norm_cost
                + strategy.weight_health * health
            )

            candidates.append((composite, m))

        if not candidates:
            return None

        # Sort by composite score descending
        candidates.sort(key=lambda t: -t[0])
        best_composite, best_mapping = candidates[0]
        best_slug = best_mapping["service_slug"]

        return RoutedProvider(
            service_slug=best_slug,
            an_score=scores_by_slug.get(best_slug, 0.0),
            cost_per_call=(
                float(best_mapping["cost_per_call"])
                if best_mapping.get("cost_per_call") is not None
                else None
            ),
            circuit_state=circuit_states.get(best_slug, "closed"),
            strategy_used=strategy.strategy,
            composite_score=round(best_composite, 4),
        )

    async def get_spend_summary(
        self, agent_id: str, period: str | None = None
    ) -> dict[str, Any]:
        """Get spend breakdown from capability_executions.

        Aggregates by capability and provider for the given period.
        """
        # Default to current month
        if not period:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            period = now.strftime("%Y-%m")

        year, month = period.split("-")
        start = f"{year}-{month}-01T00:00:00Z"

        # Fetch executions for this agent/period
        url = (
            f"{settings.supabase_url}/rest/v1/capability_executions"
            f"?agent_id=eq.{agent_id}"
            f"&created_at=gte.{start}"
            f"&select=capability_id,provider_used,cost_estimate_usd,success"
            f"&order=created_at.asc"
            f"&limit=10000"
        )

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._get_headers(), timeout=15.0)
                if resp.status_code != 200:
                    return {
                        "agent_id": agent_id,
                        "period": period,
                        "total_spend_usd": 0,
                        "total_executions": 0,
                        "by_capability": [],
                        "by_provider": [],
                    }

                rows = resp.json()

        except Exception as e:
            logger.warning("Failed to fetch spend data: %s", e)
            return {
                "agent_id": agent_id,
                "period": period,
                "total_spend_usd": 0,
                "total_executions": 0,
                "by_capability": [],
                "by_provider": [],
            }

        # Aggregate
        total_spend = 0.0
        total_executions = len(rows)
        by_cap: dict[str, dict] = {}
        by_provider: dict[str, dict] = {}

        for row in rows:
            cost = float(row.get("cost_estimate_usd") or 0)
            cap_id = row.get("capability_id", "unknown")
            raw_provider = str(row.get("provider_used") or "").strip().lower()
            provider = public_service_slug(raw_provider) or raw_provider or "unknown"

            total_spend += cost

            if cap_id not in by_cap:
                by_cap[cap_id] = {"capability_id": cap_id, "spend_usd": 0, "executions": 0}
            by_cap[cap_id]["spend_usd"] += cost
            by_cap[cap_id]["executions"] += 1

            if provider not in by_provider:
                by_provider[provider] = {"provider": provider, "spend_usd": 0, "executions": 0}
            by_provider[provider]["spend_usd"] += cost
            by_provider[provider]["executions"] += 1

        # Round values
        for v in by_cap.values():
            v["spend_usd"] = round(v["spend_usd"], 4)
            v["avg_cost"] = round(v["spend_usd"] / v["executions"], 4) if v["executions"] > 0 else 0
        for v in by_provider.values():
            v["spend_usd"] = round(v["spend_usd"], 4)

        return {
            "agent_id": agent_id,
            "period": period,
            "total_spend_usd": round(total_spend, 4),
            "total_executions": total_executions,
            "by_capability": sorted(by_cap.values(), key=lambda x: -x["spend_usd"]),
            "by_provider": sorted(by_provider.values(), key=lambda x: -x["spend_usd"]),
        }
