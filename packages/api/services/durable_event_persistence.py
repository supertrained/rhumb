"""AUD-1: Durable persistence adapter for event streams.

Persists billing events, audit trail events, and kill switch audit entries
to Supabase so they survive restarts and are visible across workers.

Design:
- Write-through: events are persisted to DB on every record() call
- Startup replay: load recent events from DB on initialization
- Fail-safe: DB write failures are logged but don't block event recording
  (the in-memory chain continues, and events are retried on next persist)
- Batch replay: bulk load from DB for chain verification
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class DurableBillingPersistence:
    """Persist billing events to the billing_events table."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    async def persist_event(self, event: Any) -> bool:
        """Write a billing event to the database.

        Returns True if persisted, False if DB write failed.
        """
        try:
            row = {
                "event_id": event.event_id,
                "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                "org_id": event.org_id,
                "amount_usd_cents": event.amount_usd_cents,
                "balance_after_usd_cents": event.balance_after_usd_cents,
                "metadata": json.dumps(event.metadata) if isinstance(event.metadata, dict) else "{}",
                "receipt_id": event.receipt_id,
                "execution_id": event.execution_id,
                "capability_id": event.capability_id,
                "provider_slug": event.provider_slug,
                "chain_hash": event.chain_hash,
                "prev_hash": event.prev_hash,
                "created_at": event.timestamp.isoformat() if isinstance(event.timestamp, datetime) else str(event.timestamp),
            }
            await self._db.table("billing_events").insert(row).execute()
            return True
        except Exception:
            logger.warning(
                "durable_billing_persist_failed event_id=%s",
                getattr(event, "event_id", "unknown"),
                exc_info=True,
            )
            return False

    async def load_recent(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Load recent billing events for startup replay.

        Returns raw dicts — the caller reconstructs BillingEvent objects.
        """
        try:
            result = await self._db.table("billing_events").select("*").order(
                "created_at", desc=False
            ).limit(limit).execute()
            return result.data or []
        except Exception:
            logger.warning("durable_billing_load_failed", exc_info=True)
            return []

    async def load_chain_segment(
        self, since: datetime | None = None, limit: int = 10000
    ) -> list[dict[str, Any]]:
        """Load events for chain verification."""
        try:
            query = self._db.table("billing_events").select("*").order(
                "created_at", desc=False
            ).limit(limit)
            if since:
                query = query.gte("created_at", since.isoformat())
            result = await query.execute()
            return result.data or []
        except Exception:
            logger.warning("durable_billing_chain_load_failed", exc_info=True)
            return []


class DurableAuditPersistence:
    """Persist audit trail events to the audit_events table."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    async def persist_event(self, event: Any) -> bool:
        """Write an audit event to the database."""
        try:
            row = {
                "event_id": event.event_id,
                "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                "severity": event.severity.value if hasattr(event.severity, "value") else str(event.severity),
                "category": event.category,
                "org_id": event.org_id,
                "agent_id": getattr(event, "agent_id", None),
                "principal": getattr(event, "principal", None),
                "resource_type": getattr(event, "resource_type", None),
                "resource_id": getattr(event, "resource_id", None),
                "action": event.action,
                "detail": json.dumps(getattr(event, "detail", {}) or {}),
                "receipt_id": getattr(event, "receipt_id", None),
                "execution_id": getattr(event, "execution_id", None),
                "provider_slug": getattr(event, "provider_slug", None),
                "chain_sequence": event.chain_sequence,
                "chain_hash": event.chain_hash,
                "prev_hash": event.prev_hash,
                "created_at": event.timestamp.isoformat() if isinstance(event.timestamp, datetime) else str(event.timestamp),
            }
            await self._db.table("audit_events").insert(row).execute()
            return True
        except Exception:
            logger.warning(
                "durable_audit_persist_failed event_id=%s",
                getattr(event, "event_id", "unknown"),
                exc_info=True,
            )
            return False

    async def load_recent(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Load recent audit events for startup replay."""
        try:
            result = await self._db.table("audit_events").select("*").order(
                "created_at", desc=False
            ).limit(limit).execute()
            return result.data or []
        except Exception:
            logger.warning("durable_audit_load_failed", exc_info=True)
            return []


class DurableKillSwitchPersistence:
    """Persist kill switch state + audit entries."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    async def persist_switch_state(self, key: str, entry: Any) -> bool:
        """Write or update a kill switch entry."""
        try:
            row = {
                "switch_key": key,
                "switch_id": entry.switch_id,
                "level": entry.level.value if hasattr(entry.level, "value") else str(entry.level),
                "target": entry.target,
                "state": entry.state.value if hasattr(entry.state, "value") else str(entry.state),
                "reason": entry.reason,
                "activated_by": entry.activated_by,
                "activated_at": entry.activated_at.isoformat() if isinstance(entry.activated_at, datetime) else str(entry.activated_at),
                "restoration_phase": getattr(entry, "restoration_phase", None),
            }
            await self._db.table("kill_switch_state").upsert(row).execute()
            return True
        except Exception:
            logger.warning(
                "durable_kill_switch_persist_failed key=%s", key, exc_info=True,
            )
            return False

    async def load_active_switches(self) -> list[dict[str, Any]]:
        """Load all active kill switches for startup replay."""
        try:
            result = await self._db.table("kill_switch_state").select("*").execute()
            return result.data or []
        except Exception:
            logger.warning("durable_kill_switch_load_failed", exc_info=True)
            return []

    async def remove_switch(self, key: str) -> bool:
        """Remove a lifted kill switch."""
        try:
            await self._db.table("kill_switch_state").delete().eq(
                "switch_key", key
            ).execute()
            return True
        except Exception:
            logger.warning("durable_kill_switch_remove_failed key=%s", key, exc_info=True)
            return False
