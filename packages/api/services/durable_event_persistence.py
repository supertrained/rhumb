"""AUD-1 / AUD-R1-03 durable persistence adapters and local event outbox."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


class MandatoryWriteUnavailable(RuntimeError):
    """Raised when the local durable outbox cannot accept writes."""


@dataclass(frozen=True, slots=True)
class EventOutboxHealth:
    """Operational health for the local durable outbox."""

    available: bool
    writable: bool
    pending_count: int
    max_pending_count: int
    oldest_pending_age_seconds: float | None
    reason: str = ""

    @property
    def allows_risky_writes(self) -> bool:
        return self.available and self.writable and self.pending_count <= self.max_pending_count


class DurableBillingPersistence:
    """Persist billing events to the billing_events table."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    async def persist_event(self, event: Any) -> bool:
        """Write a billing event to the database."""
        return await self.persist_payload(self._payload_from_event(event))

    async def persist_payload(self, payload: dict[str, Any]) -> bool:
        """Persist an already-serialized billing payload."""
        try:
            await self._db.table("billing_events").insert(
                self._build_row_from_payload(payload)
            ).execute()
            return True
        except Exception:
            logger.warning(
                "durable_billing_persist_failed event_id=%s",
                payload.get("event_id", "unknown"),
                exc_info=True,
            )
            return False

    async def load_recent(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Load recent billing events for startup replay."""
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

    @staticmethod
    def _payload_from_event(event: Any) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
            "org_id": event.org_id,
            "timestamp": _isoformat(getattr(event, "timestamp", None)),
            "amount_usd_cents": event.amount_usd_cents,
            "balance_after_usd_cents": event.balance_after_usd_cents,
            "metadata": event.metadata if isinstance(event.metadata, dict) else {},
            "receipt_id": event.receipt_id,
            "execution_id": event.execution_id,
            "capability_id": event.capability_id,
            "provider_slug": event.provider_slug,
            "chain_hash": event.chain_hash,
            "prev_hash": event.prev_hash,
            "key_version": getattr(event, "key_version", None),
        }

    @staticmethod
    def _build_row_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": payload.get("event_id"),
            "event_type": payload.get("event_type"),
            "org_id": payload.get("org_id"),
            "amount_usd_cents": payload.get("amount_usd_cents"),
            "balance_after_usd_cents": payload.get("balance_after_usd_cents"),
            "metadata": json.dumps(payload.get("metadata") or {}),
            "receipt_id": payload.get("receipt_id"),
            "execution_id": payload.get("execution_id"),
            "capability_id": payload.get("capability_id"),
            "provider_slug": payload.get("provider_slug"),
            "chain_hash": payload.get("chain_hash", ""),
            "prev_hash": payload.get("prev_hash", ""),
            "key_version": payload.get("key_version"),
            "created_at": payload.get("timestamp"),
        }


class DurableAuditPersistence:
    """Persist audit trail events to the audit_events table."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    async def persist_event(self, event: Any) -> bool:
        """Write an audit event to the database."""
        return await self.persist_payload(self._payload_from_event(event))

    async def persist_payload(self, payload: dict[str, Any]) -> bool:
        """Persist an already-serialized audit payload."""
        try:
            await self._db.table("audit_events").insert(
                self._build_row_from_payload(payload)
            ).execute()
            return True
        except Exception:
            logger.warning(
                "durable_audit_persist_failed event_id=%s",
                payload.get("event_id", "unknown"),
                exc_info=True,
            )
            return False

    async def load_recent(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Load recent audit events for startup replay."""
        try:
            result = await self._db.table("audit_events").select("*").order(
                "timestamp", desc=False
            ).limit(limit).execute()
            return result.data or []
        except Exception:
            logger.warning("durable_audit_load_failed", exc_info=True)
            return []

    @staticmethod
    def _payload_from_event(event: Any) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
            "severity": event.severity.value if hasattr(event.severity, "value") else str(event.severity),
            "category": event.category,
            "timestamp": _isoformat(getattr(event, "timestamp", None)),
            "org_id": event.org_id,
            "agent_id": getattr(event, "agent_id", None),
            "principal": getattr(event, "principal", None),
            "resource_type": getattr(event, "resource_type", None),
            "resource_id": getattr(event, "resource_id", None),
            "action": event.action,
            "detail": getattr(event, "detail", {}) or {},
            "receipt_id": getattr(event, "receipt_id", None),
            "execution_id": getattr(event, "execution_id", None),
            "provider_slug": getattr(event, "provider_slug", None),
            "chain_sequence": event.chain_sequence,
            "chain_hash": event.chain_hash,
            "prev_hash": event.prev_hash,
            "key_version": getattr(event, "key_version", None),
        }

    @staticmethod
    def _build_row_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": payload.get("event_id"),
            "event_type": payload.get("event_type"),
            "severity": payload.get("severity"),
            "category": payload.get("category"),
            "org_id": payload.get("org_id"),
            "agent_id": payload.get("agent_id"),
            "principal": payload.get("principal"),
            "resource_type": payload.get("resource_type"),
            "resource_id": payload.get("resource_id"),
            "action": payload.get("action"),
            "detail": json.dumps(payload.get("detail") or {}),
            "receipt_id": payload.get("receipt_id"),
            "execution_id": payload.get("execution_id"),
            "provider_slug": payload.get("provider_slug"),
            "chain_sequence": payload.get("chain_sequence"),
            "chain_hash": payload.get("chain_hash", ""),
            "prev_hash": payload.get("prev_hash", ""),
            "key_version": payload.get("key_version"),
            "timestamp": payload.get("timestamp"),
        }


class DurableChainCheckpointPersistence:
    """Persist signed chain checkpoints to the chain_checkpoints table."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    async def persist_payload(self, payload: dict[str, Any]) -> bool:
        """Persist an already-serialized checkpoint payload."""
        try:
            await self._db.table("chain_checkpoints").insert(
                self._build_row_from_payload(payload)
            ).execute()
            return True
        except Exception:
            logger.warning(
                "durable_chain_checkpoint_persist_failed checkpoint_id=%s",
                payload.get("checkpoint_id", "unknown"),
                exc_info=True,
            )
            return False

    @staticmethod
    def _build_row_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "checkpoint_id": payload.get("checkpoint_id"),
            "stream_name": payload.get("stream_name"),
            "reason": payload.get("reason"),
            "source_head_hash": payload.get("source_head_hash", ""),
            "source_head_sequence": payload.get("source_head_sequence"),
            "source_key_version": payload.get("source_key_version"),
            "checkpoint_hash": payload.get("checkpoint_hash", ""),
            "key_version": payload.get("key_version"),
            "metadata": json.dumps(payload.get("metadata") or {}),
            "created_at": payload.get("created_at"),
        }


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
                "second_approver": getattr(entry, "second_approver", None),
                "restoration_phase": getattr(entry, "restoration_phase", None),
                "chain_hash": getattr(entry, "chain_hash", ""),
            }
            await self._db.table("kill_switch_state").upsert(row).execute()
            return True
        except Exception:
            logger.warning("durable_kill_switch_persist_failed key=%s", key, exc_info=True)
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
            await self._db.table("kill_switch_state").delete().eq("switch_key", key).execute()
            return True
        except Exception:
            logger.warning("durable_kill_switch_remove_failed key=%s", key, exc_info=True)
            return False

    async def persist_pending_global(self, pending: Any) -> bool:
        """Write or update a pending global kill approval request."""
        try:
            requester = getattr(pending, "requester")
            row = {
                "request_id": pending.request_id,
                "reason": pending.reason,
                "requester_type": (
                    requester.principal_type.value
                    if hasattr(requester.principal_type, "value")
                    else str(requester.principal_type)
                ),
                "requester_unique_id": requester.unique_id,
                "requester_display_name": requester.display_name,
                "requester_verified_at": (
                    requester.verified_at.isoformat()
                    if isinstance(requester.verified_at, datetime)
                    else str(requester.verified_at)
                ),
                "requested_at": (
                    pending.requested_at.isoformat()
                    if isinstance(pending.requested_at, datetime)
                    else str(pending.requested_at)
                ),
                "expires_at": (
                    pending.expires_at.isoformat()
                    if isinstance(pending.expires_at, datetime)
                    else str(pending.expires_at)
                ),
            }
            await self._db.table("kill_switch_pending_global").upsert(row).execute()
            return True
        except Exception:
            logger.warning(
                "durable_kill_switch_pending_persist_failed request_id=%s",
                getattr(pending, "request_id", "unknown"),
                exc_info=True,
            )
            return False

    async def load_pending_globals(self) -> list[dict[str, Any]]:
        """Load pending global kill approval requests for startup replay."""
        try:
            result = await self._db.table("kill_switch_pending_global").select("*").execute()
            return result.data or []
        except Exception:
            logger.warning("durable_kill_switch_pending_load_failed", exc_info=True)
            return []

    async def remove_pending_global(self, request_id: str) -> bool:
        """Remove a resolved or expired pending global kill request."""
        try:
            await self._db.table("kill_switch_pending_global").delete().eq(
                "request_id", request_id
            ).execute()
            return True
        except Exception:
            logger.warning(
                "durable_kill_switch_pending_remove_failed request_id=%s",
                request_id,
                exc_info=True,
            )
            return False


class DurableEventOutbox:
    """Local SQLite-backed durable outbox for billing + audit events."""

    def __init__(
        self,
        *,
        billing_persistence: DurableBillingPersistence | None = None,
        audit_persistence: DurableAuditPersistence | None = None,
        checkpoint_persistence: DurableChainCheckpointPersistence | None = None,
        sqlite_path: str | None = None,
        max_pending_count: int | None = None,
        flush_batch_size: int | None = None,
        flush_interval_seconds: float | None = None,
    ) -> None:
        self._billing_persistence = billing_persistence
        self._audit_persistence = audit_persistence
        self._checkpoint_persistence = checkpoint_persistence
        self._sqlite_path = sqlite_path or os.environ.get(
            "RHUMB_EVENT_OUTBOX_PATH",
            os.path.join(tempfile.gettempdir(), "rhumb_event_outbox.sqlite3"),
        )
        self._max_pending_count = max_pending_count or int(
            os.environ.get("RHUMB_EVENT_OUTBOX_MAX_PENDING", "1000")
        )
        self._flush_batch_size = flush_batch_size or int(
            os.environ.get("RHUMB_EVENT_OUTBOX_FLUSH_BATCH_SIZE", "100")
        )
        self._flush_interval_seconds = flush_interval_seconds or float(
            os.environ.get("RHUMB_EVENT_OUTBOX_FLUSH_INTERVAL_SECONDS", "2.0")
        )
        self._lock = threading.RLock()
        self._flush_task: asyncio.Task[None] | None = None
        self._last_write_error = ""
        self._connection = self._open_connection()
        self._initialize_schema()

    def append_billing_event(self, event: Any) -> None:
        self._append(
            stream="billing",
            event_id=getattr(event, "event_id", "unknown"),
            event_timestamp=_isoformat(getattr(event, "timestamp", None)),
            payload=DurableBillingPersistence._payload_from_event(event),
        )

    def append_audit_event(self, event: Any) -> None:
        self._append(
            stream="audit",
            event_id=getattr(event, "event_id", "unknown"),
            event_timestamp=_isoformat(getattr(event, "timestamp", None)),
            payload=DurableAuditPersistence._payload_from_event(event),
        )

    def append_chain_checkpoint(self, payload: dict[str, Any]) -> None:
        self._append(
            stream="chain_checkpoint",
            event_id=str(payload.get("checkpoint_id") or "unknown"),
            event_timestamp=_isoformat(payload.get("created_at")),
            payload=payload,
        )

    def load_billing_payloads(self) -> list[dict[str, Any]]:
        return self._load_payloads("billing")

    def load_audit_payloads(self) -> list[dict[str, Any]]:
        return self._load_payloads("audit")

    def health(self) -> EventOutboxHealth:
        """Return local outbox health and backlog metrics."""
        try:
            with self._lock:
                row = self._connection.execute(
                    """
                    SELECT COUNT(*) AS pending_count, MIN(enqueued_at) AS oldest_pending
                    FROM event_outbox
                    WHERE flushed_at IS NULL
                    """
                ).fetchone()
        except sqlite3.Error as exc:
            return EventOutboxHealth(
                available=False,
                writable=False,
                pending_count=0,
                max_pending_count=self._max_pending_count,
                oldest_pending_age_seconds=None,
                reason=f"Local durable outbox unavailable: {exc}",
            )

        pending_count = int(row["pending_count"] or 0)
        oldest_pending = row["oldest_pending"]
        oldest_pending_age_seconds: float | None = None
        if oldest_pending:
            oldest_pending_age_seconds = max(
                0.0,
                (_utc_now() - datetime.fromisoformat(str(oldest_pending))).total_seconds(),
            )

        if self._last_write_error:
            return EventOutboxHealth(
                available=True,
                writable=False,
                pending_count=pending_count,
                max_pending_count=self._max_pending_count,
                oldest_pending_age_seconds=oldest_pending_age_seconds,
                reason=self._last_write_error,
            )

        if pending_count > self._max_pending_count:
            return EventOutboxHealth(
                available=True,
                writable=True,
                pending_count=pending_count,
                max_pending_count=self._max_pending_count,
                oldest_pending_age_seconds=oldest_pending_age_seconds,
                reason=(
                    "Durable event backlog exceeded safe threshold "
                    f"({pending_count}>{self._max_pending_count})."
                ),
            )

        return EventOutboxHealth(
            available=True,
            writable=True,
            pending_count=pending_count,
            max_pending_count=self._max_pending_count,
            oldest_pending_age_seconds=oldest_pending_age_seconds,
            reason="",
        )

    async def flush_once(self) -> int:
        """Flush a bounded batch of pending events to the remote durable store."""
        rows = self._pending_rows(limit=self._flush_batch_size)
        flushed = 0
        for row in rows:
            payload = json.loads(row["payload"])
            stream = row["stream"]
            if stream == "billing":
                persistence = self._billing_persistence
            elif stream == "audit":
                persistence = self._audit_persistence
            elif stream == "chain_checkpoint":
                persistence = self._checkpoint_persistence
            else:
                self._mark_failure(row["id"], f"unknown stream: {stream}")
                continue

            if persistence is None:
                break

            try:
                ok = await persistence.persist_payload(payload)
            except Exception as exc:
                ok = False
                self._mark_failure(row["id"], str(exc))
            else:
                if ok:
                    self._mark_flushed(row["id"])
                    flushed += 1
                else:
                    self._mark_failure(row["id"], "remote persistence failed")

            if not ok:
                break
        return flushed

    async def start(self) -> None:
        """Start the periodic background flush worker."""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self, *, drain: bool = False) -> None:
        """Stop the background flush worker."""
        if drain:
            try:
                await self.flush_once()
            except Exception:
                logger.warning("durable_event_outbox_drain_failed", exc_info=True)

        task = self._flush_task
        self._flush_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _open_connection(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self._sqlite_path), exist_ok=True)
        connection = sqlite3.connect(self._sqlite_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize_schema(self) -> None:
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS event_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stream TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    event_timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    enqueued_at TEXT NOT NULL,
                    flushed_at TEXT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_event_outbox_pending
                    ON event_outbox(stream, flushed_at, id);
                """
            )
            self._connection.commit()

    def _append(
        self,
        *,
        stream: str,
        event_id: str,
        event_timestamp: str | None,
        payload: dict[str, Any],
    ) -> None:
        try:
            with self._lock:
                self._connection.execute(
                    """
                    INSERT INTO event_outbox (
                        stream, event_id, event_timestamp, payload, enqueued_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        stream,
                        event_id,
                        event_timestamp or _utc_now().isoformat(),
                        json.dumps(payload, separators=(",", ":"), sort_keys=True),
                        _utc_now().isoformat(),
                    ),
                )
                self._connection.commit()
                self._last_write_error = ""
        except sqlite3.Error as exc:
            self._last_write_error = f"Local durable outbox write failed: {exc}"
            raise MandatoryWriteUnavailable(self._last_write_error) from exc

    def _load_payloads(self, stream: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM event_outbox WHERE stream = ? ORDER BY id ASC",
                (stream,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def _pending_rows(self, *, limit: int) -> list[sqlite3.Row]:
        with self._lock:
            return list(
                self._connection.execute(
                    """
                    SELECT id, stream, payload
                    FROM event_outbox
                    WHERE flushed_at IS NULL
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            )

    def _mark_flushed(self, row_id: int) -> None:
        with self._lock:
            self._connection.execute(
                """
                UPDATE event_outbox
                SET flushed_at = ?, attempts = attempts + 1, last_error = NULL
                WHERE id = ?
                """,
                (_utc_now().isoformat(), row_id),
            )
            self._connection.commit()

    def _mark_failure(self, row_id: int, error: str) -> None:
        with self._lock:
            self._connection.execute(
                """
                UPDATE event_outbox
                SET attempts = attempts + 1, last_error = ?
                WHERE id = ?
                """,
                (error[:500], row_id),
            )
            self._connection.commit()

    async def _flush_loop(self) -> None:
        try:
            while True:
                try:
                    await self.flush_once()
                except Exception:
                    logger.warning("durable_event_outbox_flush_failed", exc_info=True)
                await asyncio.sleep(self._flush_interval_seconds)
        except asyncio.CancelledError:
            raise


_event_outbox: DurableEventOutbox | None = None
_event_outbox_init_attempted = False


async def init_event_outbox(supabase_client: Any | None = None) -> DurableEventOutbox | None:
    """Initialize the module-level durable outbox and hydrate event streams."""
    global _event_outbox, _event_outbox_init_attempted
    _event_outbox_init_attempted = True
    if _event_outbox is not None:
        return _event_outbox

    try:
        if supabase_client is None:
            from db.client import get_supabase_client

            supabase_client = await get_supabase_client()

        _event_outbox = DurableEventOutbox(
            billing_persistence=DurableBillingPersistence(supabase_client),
            audit_persistence=DurableAuditPersistence(supabase_client),
            checkpoint_persistence=DurableChainCheckpointPersistence(supabase_client),
        )

        from services.audit_trail import init_audit_trail
        from services.billing_events import init_billing_event_stream

        init_billing_event_stream(
            outbox=_event_outbox,
            replay_payloads=_event_outbox.load_billing_payloads(),
        )
        init_audit_trail(
            outbox=_event_outbox,
            replay_payloads=_event_outbox.load_audit_payloads(),
        )
        return _event_outbox
    except Exception:
        logger.warning("durable_event_outbox_init_failed", exc_info=True)
        _event_outbox = None
        return None


def get_event_outbox() -> DurableEventOutbox | None:
    return _event_outbox


def get_event_outbox_health() -> EventOutboxHealth:
    if not _event_outbox_init_attempted:
        return EventOutboxHealth(
            available=True,
            writable=True,
            pending_count=0,
            max_pending_count=int(os.environ.get("RHUMB_EVENT_OUTBOX_MAX_PENDING", "1000")),
            oldest_pending_age_seconds=None,
            reason="",
        )
    if _event_outbox is None:
        return EventOutboxHealth(
            available=False,
            writable=False,
            pending_count=0,
            max_pending_count=int(os.environ.get("RHUMB_EVENT_OUTBOX_MAX_PENDING", "1000")),
            oldest_pending_age_seconds=None,
            reason="Billing/audit durable outbox is not initialized.",
        )
    return _event_outbox.health()


async def shutdown_event_outbox(*, drain: bool = True) -> None:
    """Stop and close the module-level durable outbox."""
    global _event_outbox, _event_outbox_init_attempted
    if _event_outbox is None:
        _event_outbox_init_attempted = False
        return
    outbox = _event_outbox
    _event_outbox = None
    _event_outbox_init_attempted = False
    await outbox.stop(drain=drain)
    outbox.close()
