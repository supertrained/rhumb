"""AUD-3 follow-on: durable head checkpoints for active chain streams.

These helpers let operators checkpoint the current head of an active chain stream
without waiting for a retention purge. The resulting checkpoint rows land in the
same durable checkpoint ledger as retention checkpoints, giving later external
anchoring work a stable ledger to consume.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
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
from services.score_audit_verification import describe_score_audit_entry_verification


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


async def _fetch_latest_score_audit_row() -> dict[str, Any] | None:
    rows = await supabase_fetch(
        "score_audit_chain?select=entry_id,chain_hash,key_version,created_at"
        "&order=created_at.desc&limit=1"
    )
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return None


async def _fetch_latest_anchor_eligible_score_audit_row() -> dict[str, Any] | None:
    rows = await supabase_fetch(
        "score_audit_chain?select=entry_id,chain_hash,key_version,created_at"
        "&order=created_at.desc&limit=25"
    )
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and describe_score_audit_entry_verification(row).get(
                "is_anchor_eligible"
            ):
                return row
    return None


async def _count_score_audit_rows_through(value: Any) -> int:
    timestamp = _parse_optional_timestamp(value)
    if timestamp is None:
        return 0
    encoded = quote(timestamp.isoformat(), safe="")
    return _parse_optional_int(
        await supabase_count(f"score_audit_chain?created_at=lte.{encoded}")
    ) or 0


async def _fetch_score_audit_quarantined_tail(
    after_value: Any,
    *,
    latest_row: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    timestamp = _parse_optional_timestamp(after_value)
    if timestamp is None:
        return [latest_row] if isinstance(latest_row, dict) else []

    encoded = quote(timestamp.isoformat(), safe="")
    rows = await supabase_fetch(
        "score_audit_chain?select=entry_id,key_version,created_at"
        f"&created_at=gt.{encoded}&order=created_at.asc"
    )
    if isinstance(rows, list):
        parsed_rows = [row for row in rows if isinstance(row, dict)]
        if parsed_rows:
            return parsed_rows
    return [latest_row] if isinstance(latest_row, dict) else []


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
    latest_verified_row: dict[str, Any] | None = None,
    row_count: int | None = None,
    verified_row_count: int | None = None,
    flush: bool = True,
) -> dict[str, Any] | None:
    """Persist a checkpoint for the current durable score-audit-chain head."""
    row = latest_row or await _fetch_latest_score_audit_row()

    if not isinstance(row, dict):
        return None

    source_row = row
    source_head_hash = source_row.get("chain_hash")
    if not source_head_hash:
        return None

    total_event_count = row_count if row_count is not None else await supabase_count("score_audit_chain")
    total_event_count = _parse_optional_int(total_event_count) or 0
    if total_event_count <= 0:
        raise RuntimeError("Unable to determine score_audit_chain length for checkpointing.")

    checkpoint_metadata = {
        **(metadata or {}),
        "latest_entry_id": row.get("entry_id"),
    }

    source_head_sequence = total_event_count
    source_key_version = _parse_optional_int(source_row.get("key_version"))
    latest_verification = describe_score_audit_entry_verification(row)

    if not latest_verification.get("is_anchor_eligible"):
        verified_row = latest_verified_row or await _fetch_latest_anchor_eligible_score_audit_row()
        if not isinstance(verified_row, dict):
            raise RuntimeError(
                "score_audit_chain latest row is unreconstructable and no verified head is available for checkpointing."
            )

        verified_row_verification = describe_score_audit_entry_verification(verified_row)
        if not verified_row_verification.get("is_anchor_eligible"):
            raise RuntimeError(
                "score_audit_chain latest eligible row is not anchor-eligible under the current verification policy."
            )

        verified_sequence = (
            verified_row_count
            if verified_row_count is not None
            else await _count_score_audit_rows_through(verified_row.get("created_at"))
        )
        verified_sequence = _parse_optional_int(verified_sequence) or 0
        if verified_sequence <= 0:
            raise RuntimeError("Unable to determine verified score_audit_chain head for checkpointing.")

        quarantined_tail_rows = await _fetch_score_audit_quarantined_tail(
            verified_row.get("created_at"),
            latest_row=row,
        )
        quarantined_tail = []
        for tail_row in quarantined_tail_rows:
            verification = describe_score_audit_entry_verification(tail_row)
            quarantined_tail.append(
                {
                    "entry_id": verification.get("entry_id") or tail_row.get("entry_id"),
                    "verification_status": verification.get("verification_status"),
                    "reason": verification.get("reason"),
                    "quarantine_decision": verification.get("quarantine_decision"),
                    "forensic_note": verification.get("forensic_note"),
                }
            )
        quarantined_tail_entry_ids = [
            str(tail_row["entry_id"])
            for tail_row in quarantined_tail
            if tail_row.get("entry_id")
        ]
        quarantined_tail_count = max(
            total_event_count - verified_sequence,
            len(quarantined_tail_entry_ids),
        )

        checkpoint_metadata.update(
            {
                "verification_status": "verified_with_quarantined_tail",
                "head_selection_mode": "latest_verified_head",
                "selected_head_entry_id": verified_row.get("entry_id"),
                "verified_event_count": verified_sequence,
                "total_observed_event_count": total_event_count,
                "latest_observed_entry_id": row.get("entry_id"),
                "latest_observed_verification_status": latest_verification.get("verification_status"),
                "quarantine_action": "excluded_from_verified_head",
                "quarantined_tail_count": quarantined_tail_count,
            }
        )
        if quarantined_tail_entry_ids:
            checkpoint_metadata["quarantined_tail_entry_ids"] = quarantined_tail_entry_ids
        if quarantined_tail:
            checkpoint_metadata["quarantined_tail"] = quarantined_tail

        source_row = verified_row
        source_head_hash = source_row.get("chain_hash")
        source_head_sequence = verified_sequence
        source_key_version = _parse_optional_int(source_row.get("key_version"))
    else:
        checkpoint_metadata.update(
            {
                "verification_status": latest_verification.get("verification_status", "verified"),
                "head_selection_mode": "latest_head",
                "selected_head_entry_id": row.get("entry_id"),
            }
        )

    if not source_head_hash:
        return None

    return await checkpoint_stream_head(
        stream_name="score_audit_chain",
        source_head_hash=str(source_head_hash),
        source_head_sequence=source_head_sequence,
        source_key_version=source_key_version,
        stream_event_count=source_head_sequence,
        latest_event_timestamp=_parse_optional_timestamp(source_row.get("created_at")),
        reason=reason,
        metadata=checkpoint_metadata,
        outbox=outbox,
        flush=flush,
    )
