"""Per-agent monthly spend-cap enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional, Tuple

from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.usage_metering import UsageMeterEngine, get_usage_meter_engine

DEFAULT_MONTHLY_SPEND_CAP_USD = 100.0


@dataclass
class SpendCapAlert:
    """Alert emitted when an agent approaches or exceeds spend cap."""

    agent_id: str
    spend_current: float
    spend_limit: float
    percent_used: float
    alert_type: str


class SpendCapManager:
    """Enforce per-agent monthly spend caps based on metered usage."""

    def __init__(
        self,
        usage_meter: Optional[UsageMeterEngine] = None,
        identity_store: Optional[AgentIdentityStore] = None,
    ) -> None:
        self._usage_meter = usage_meter
        self._identity_store = identity_store

    @property
    def usage_meter(self) -> UsageMeterEngine:
        """Get usage meter dependency."""
        if self._usage_meter is None:
            self._usage_meter = get_usage_meter_engine(identity_store=self.identity_store)
        return self._usage_meter

    @property
    def identity_store(self) -> AgentIdentityStore:
        """Get identity store dependency."""
        if self._identity_store is None:
            self._identity_store = get_agent_identity_store()
        return self._identity_store

    async def check_spend_cap(self, agent_id: str) -> Tuple[bool, Optional[SpendCapAlert]]:
        """Check if an agent is allowed to continue spending this month.

        Returns:
            ``(allowed, alert)`` where alert is ``None`` under 80% usage,
            ``warning`` at >=80%, and ``critical`` above 100%.
        """
        agent = await self.identity_store.get_agent(agent_id)
        if agent is None:
            return False, None

        month = datetime.now(tz=UTC).strftime("%Y-%m")
        usage = await self.usage_meter.get_monthly_usage(agent_id, month)

        spend_limit = _resolve_spend_limit(agent)
        spend_current = usage.cost_estimate
        percent_used = (spend_current / spend_limit * 100.0) if spend_limit > 0 else 0.0

        alert: Optional[SpendCapAlert] = None
        if percent_used > 100.0:
            alert = SpendCapAlert(
                agent_id=agent_id,
                spend_current=spend_current,
                spend_limit=spend_limit,
                percent_used=percent_used,
                alert_type="critical",
            )
            return False, alert

        if percent_used >= 80.0:
            alert = SpendCapAlert(
                agent_id=agent_id,
                spend_current=spend_current,
                spend_limit=spend_limit,
                percent_used=percent_used,
                alert_type="warning",
            )

        return True, alert


def _resolve_spend_limit(agent: object) -> float:
    """Resolve spend cap from agent metadata with sane defaults."""
    default = DEFAULT_MONTHLY_SPEND_CAP_USD

    custom_attributes = getattr(agent, "custom_attributes", {})
    if isinstance(custom_attributes, dict):
        value = custom_attributes.get("monthly_spend_cap_usd")
        if value is not None:
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                return default

    explicit = getattr(agent, "monthly_spend_cap_usd", None)
    if explicit is not None:
        try:
            return max(0.0, float(explicit))
        except (TypeError, ValueError):
            return default

    return default


_spend_cap_manager: Optional[SpendCapManager] = None


def get_spend_cap_manager(
    usage_meter: Optional[UsageMeterEngine] = None,
    identity_store: Optional[AgentIdentityStore] = None,
) -> SpendCapManager:
    """Return (or create) the global :class:`SpendCapManager`."""
    global _spend_cap_manager
    if _spend_cap_manager is None:
        _spend_cap_manager = SpendCapManager(usage_meter, identity_store)
    return _spend_cap_manager


def reset_spend_cap_manager() -> None:
    """Reset spend cap singleton (for tests)."""
    global _spend_cap_manager
    _spend_cap_manager = None
