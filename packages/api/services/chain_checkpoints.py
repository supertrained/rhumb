"""AUD-3 follow-on: durable head checkpoints for active chain streams.

These helpers let operators checkpoint the current head of an active chain stream
without waiting for a retention purge. The resulting checkpoint rows land in the
same durable checkpoint ledger as retention checkpoints, giving later external
anchoring work a stable ledger to consume.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from routes._supabase import supabase_count, supabase_fetch
from services.audit_trail import AuditTrail, get_audit_trail
from services.billing_events import BillingEventStream, get_billing_event_stream
from services.chain_integrity import (
    build_chain_checkpoint_payload,
    compute_chain_hmac,
    get_signing_key_version,
)
from services.durable_event_persistence import get_event_outbox


def _parse_optional_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def _parse_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def checkpoint_stream_head(
    *,
    stream_name: str,
    source_head_hash: str,
    source_head_sequence: int,
    source_key_version: int | None,
    stream_event_count: int,
    latest_event_timestamp: datetime | None,
    reason: str,
    metadata: dict[str, Any] | None = None,
    outbox: Any | None = None,
    flush: bool = True,
    created_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Create and persist a signed checkpoint for an active chain head.

    Returns the persisted payload, or ``None`` when the stream is empty.
    Raises ``RuntimeError`` when durable checkpoint persistence is unavailable.
    """
    if source_head_sequence <= 0 or not source_head_hash or source_head_hash == ("0" * 64):
        return None

    checkpoint_outbox = outbox or get_event_outbox()
    if checkpoint_outbox is None or not hasattr(checkpoint_outbox, "append_chain_checkpoint"):
        raise RuntimeError("Durable checkpoint outbox is unavailable.")

    if not isinstance(metadata, dict):
        metadata = {}

    created_at = created_at or datetime.now(timezone.utc)
    checkpoint_key_version = get_signing_key_version()
    checkpoint_metadata = {
        **metadata,
        "checkpoint_origin": "manual_head_snapshot",
        "event_count": stream_event_count,
    }
    if latest_event_timestamp is not None:
        checkpoint_metadata["latest_event_timestamp"] = latest_event_timestamp.isoformat()

    payload = build_chain_checkpoint_payload(
        {
            "checkpoint_id": f"chk_{uuid4().hex[:16]}",
            "stream_name": stream_name,
            "reason": reason,
            "source_head_hash": source_head_hash,
            "source_head_sequence": source_head_sequence,
            "source_key_version": source_key_version,
            "created_at": created_at,
            "metadata": checkpoint_metadata,
        }
    )
    checkpoint_hash = compute_chain_hmac(
        AuditTrail.GENESIS_HASH,
        payload,
        key_version=checkpoint_key_version,
    )
    final_payload = {
        **payload,
        "checkpoint_hash": checkpoint_hash,
        "key_version": checkpoint_key_version,
    }
    checkpoint_outbox.append_chain_checkpoint(final_payload)
    if flush and hasattr(checkpoint_outbox, "flush_once"):
        await checkpoint_outbox.flush_once()
    return final_payload


async def checkpoint_audit_head(
    *,
    reason: str,
    metadata: dict[str, Any] | None = None,
    outbox: Any | None = None,
    audit_trail: AuditTrail | None = None,
    flush: bool = True,
) -> dict[str, Any] | None:
    """Persist a checkpoint for the current audit stream head."""
    stream = audit_trail or get_audit_trail()
    return await checkpoint_stream_head(
        stream_name="audit_events",
        source_head_hash=stream.latest_hash,
        source_head_sequence=stream.latest_sequence,
        source_key_version=stream.latest_key_version,
        stream_event_count=stream.length,
        latest_event_timestamp=stream.latest_timestamp,
        reason=reason,
        metadata=metadata,
        outbox=outbox,
        flush=flush,
    )


async def checkpoint_billing_head(
    *,
    reason: str,
    metadata: dict[str, Any] | None = None,
    outbox: Any | None = None,
    billing_stream: BillingEventStream | None = None,
    flush: bool = True,
) -> dict[str, Any] | None:
    """Persist a checkpoint for the current billing stream head."""
    stream = billing_stream or get_billing_event_stream()
    return await checkpoint_stream_head(
        stream_name="billing_events",
        source_head_hash=stream.latest_hash,
        source_head_sequence=stream.length,
        source_key_version=stream.latest_key_version,
        stream_event_count=stream.length,
        latest_event_timestamp=stream.latest_timestamp,
        reason=reason,
        metadata=metadata,
        outbox=outbox,
        flush=flush,
    )


async def checkpoint_score_audit_head(
    *,
    reason: str,
    metadata: dict[str, Any] | None = None,
    outbox: Any | None = None,
    latest_row: dict[str, Any] | None = None,
    row_count: int | None = None,
    flush: bool = True,
) -> dict[str, Any] | None:
    """Persist a checkpoint for the current durable score-audit-chain head."""
    row = latest_row
    if row is None:
        rows = await supabase_fetch(
            "score_audit_chain?select=entry_id,chain_hash,key_version,created_at"
            "&order=created_at.desc&limit=1"
        )
        row = rows[0] if isinstance(rows, list) and rows else None

    if not isinstance(row, dict):
        return None

    source_head_hash = row.get("chain_hash")
    if not source_head_hash:
        return None

    event_count = row_count if row_count is not None else await supabase_count("score_audit_chain")
    event_count = _parse_optional_int(event_count) or 0
    if event_count <= 0:
        raise RuntimeError("Unable to determine score_audit_chain length for checkpointing.")

    checkpoint_metadata = {
        **(metadata or {}),
        "latest_entry_id": row.get("entry_id"),
    }

    return await checkpoint_stream_head(
        stream_name="score_audit_chain",
        source_head_hash=str(source_head_hash),
        source_head_sequence=event_count,
        source_key_version=_parse_optional_int(row.get("key_version")),
        stream_event_count=event_count,
        latest_event_timestamp=_parse_optional_timestamp(row.get("created_at")),
        reason=reason,
        metadata=checkpoint_metadata,
        outbox=outbox,
        flush=flush,
    )
