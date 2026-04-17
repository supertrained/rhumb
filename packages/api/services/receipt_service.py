"""Execution Receipt Service — append-only, chain-hashed receipts.

Every capability execution produces an immutable receipt. Receipts are the
atomic unit of observability: the ground truth for billing, debugging,
compliance, and auditing.

Chain integrity:
  - Each receipt includes a SHA-256 hash of its own content.
  - Each receipt links to the previous receipt's hash, forming an
    append-only chain that makes retrospective tampering detectable.
  - Chain sequence is globally monotonic (PostgreSQL advisory lock or
    single-row counter).

Thread safety:
  - Chain state is advanced atomically via Supabase RPC or
    compare-and-swap on the single-row receipt_chain_state table.
  - If two receipts race, one will retry with the updated previous_hash.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from routes._supabase import supabase_fetch, supabase_insert, supabase_patch
from services.service_slugs import public_service_slug, public_service_slug_candidates

logger = logging.getLogger(__name__)

_RECEIPT_VERSION = "1.0"
_MAX_CHAIN_RETRIES = 3


def _public_receipt_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize provider identity for API-facing receipt reads."""
    if row is None:
        return None
    normalized = dict(row)
    provider_id = public_service_slug(normalized.get("provider_id"))
    if provider_id:
        normalized["provider_id"] = provider_id
    return normalized


def _generate_receipt_id() -> str:
    """Generate a receipt ID with the rcpt_ prefix."""
    import uuid
    return f"rcpt_{uuid.uuid4().hex[:24]}"


def _hash_content(content: str) -> str:
    """SHA-256 hash of the receipt content for integrity."""
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def _hash_payload(payload: Any) -> str | None:
    """Hash an arbitrary payload (request body or response body)."""
    if payload is None:
        return None
    try:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return _hash_content(serialized)
    except (TypeError, ValueError):
        return None


def _compute_receipt_hash(receipt_data: dict[str, Any]) -> str:
    """Compute the chain hash for a receipt.

    The hash covers all fields that constitute the receipt's content,
    excluding the receipt_hash itself (which is what we're computing).
    """
    # Deterministic field ordering for hash stability
    hash_fields = [
        "receipt_id",
        "receipt_version",
        "created_at",
        "execution_id",
        "layer",
        "capability_id",
        "capability_version",
        "status",
        "attempt_number",
        "agent_id",
        "org_id",
        "caller_ip_hash",
        "provider_id",
        "provider_name",
        "provider_model",
        "credential_mode",
        "provider_region",
        "router_version",
        "candidates_evaluated",
        "winner_reason",
        "total_latency_ms",
        "rhumb_overhead_ms",
        "provider_latency_ms",
        "provider_cost_usd",
        "rhumb_fee_usd",
        "total_cost_usd",
        "credits_deducted",
        "request_hash",
        "response_hash",
        "previous_receipt_hash",
        "chain_sequence",
        "x402_tx_hash",
        "x402_network",
        "x402_payer",
        "interface",
        "compat_mode",
        "idempotency_key",
        "error_code",
        "error_message",
    ]
    content_parts = []
    for key in hash_fields:
        value = receipt_data.get(key)
        if value is not None:
            content_parts.append(f"{key}={value}")
    content = "|".join(content_parts)
    return _hash_content(content)


@dataclass
class ReceiptInput:
    """Input for creating an execution receipt."""

    # Execution context
    execution_id: str
    capability_id: str
    status: str  # 'success', 'failure', 'timeout', 'rejected'

    # Identity
    agent_id: str
    provider_id: str
    credential_mode: str

    # Optional fields
    layer: int = 2
    capability_version: str | None = None
    attempt_number: int = 1
    org_id: str | None = None
    caller_ip_hash: str | None = None
    provider_name: str | None = None
    provider_model: str | None = None
    provider_region: str | None = None

    # Routing
    router_version: str | None = None
    candidates_evaluated: int | None = None
    winner_reason: str | None = None

    # Timing
    total_latency_ms: float | None = None
    rhumb_overhead_ms: float | None = None
    provider_latency_ms: float | None = None

    # Cost
    provider_cost_usd: float | None = None
    rhumb_fee_usd: float | None = None
    total_cost_usd: float | None = None
    credits_deducted: float | None = None

    # Payload hashes
    request_hash: str | None = None
    response_hash: str | None = None

    # x402
    x402_tx_hash: str | None = None
    x402_network: str | None = None
    x402_payer: str | None = None

    # Interface
    interface: str | None = None
    compat_mode: str | None = None
    idempotency_key: str | None = None

    # Error (for failure receipts)
    error_code: str | None = None
    error_message: str | None = None
    error_provider_raw: str | None = None


@dataclass
class Receipt:
    """Immutable execution receipt."""

    receipt_id: str
    receipt_version: str
    created_at: str
    execution_id: str
    layer: int
    capability_id: str
    status: str
    agent_id: str
    provider_id: str
    credential_mode: str
    receipt_hash: str
    previous_receipt_hash: str | None
    chain_sequence: int
    # All other fields from ReceiptInput carried through
    extra: dict[str, Any] = field(default_factory=dict)


class ReceiptService:
    """Service for creating and querying execution receipts."""

    async def create_receipt(self, input: ReceiptInput) -> Receipt:
        """Create an immutable receipt and append it to the chain.

        Returns the created Receipt with chain hash and sequence.
        """
        receipt_id = _generate_receipt_id()
        created_at = self._now_iso()
        provider_id = public_service_slug(input.provider_id) or input.provider_id

        # Advance chain state atomically
        chain_state = await self._advance_chain_state()
        chain_sequence = chain_state["sequence"]
        previous_hash = chain_state["previous_hash"]

        # Build receipt data
        receipt_data: dict[str, Any] = {
            "receipt_id": receipt_id,
            "receipt_version": _RECEIPT_VERSION,
            "created_at": created_at,
            "execution_id": input.execution_id,
            "layer": input.layer,
            "capability_id": input.capability_id,
            "capability_version": input.capability_version,
            "status": input.status,
            "attempt_number": input.attempt_number,
            "agent_id": input.agent_id,
            "org_id": input.org_id,
            "caller_ip_hash": input.caller_ip_hash,
            "provider_id": provider_id,
            "provider_name": input.provider_name,
            "provider_model": input.provider_model,
            "credential_mode": input.credential_mode,
            "provider_region": input.provider_region,
            "router_version": input.router_version,
            "candidates_evaluated": input.candidates_evaluated,
            "winner_reason": input.winner_reason,
            "total_latency_ms": input.total_latency_ms,
            "rhumb_overhead_ms": input.rhumb_overhead_ms,
            "provider_latency_ms": input.provider_latency_ms,
            "provider_cost_usd": input.provider_cost_usd,
            "rhumb_fee_usd": input.rhumb_fee_usd,
            "total_cost_usd": input.total_cost_usd,
            "credits_deducted": input.credits_deducted,
            "request_hash": input.request_hash,
            "response_hash": input.response_hash,
            "previous_receipt_hash": previous_hash,
            "chain_sequence": chain_sequence,
            "x402_tx_hash": input.x402_tx_hash,
            "x402_network": input.x402_network,
            "x402_payer": input.x402_payer,
            "interface": input.interface,
            "compat_mode": input.compat_mode,
            "idempotency_key": input.idempotency_key,
            "error_code": input.error_code,
            "error_message": input.error_message,
            "error_provider_raw": input.error_provider_raw,
        }

        # Compute chain hash
        receipt_hash = _compute_receipt_hash(receipt_data)
        receipt_data["receipt_hash"] = receipt_hash

        # Persist (append-only: INSERT only, never UPDATE)
        await supabase_insert("execution_receipts", {
            k: v for k, v in receipt_data.items() if v is not None
        })

        # Update chain state with the new receipt hash
        await self._update_chain_hash(chain_sequence, receipt_hash)

        logger.info(
            "receipt_created receipt_id=%s execution_id=%s chain_seq=%d provider=%s status=%s",
            receipt_id,
            input.execution_id,
            chain_sequence,
            provider_id,
            input.status,
        )

        return Receipt(
            receipt_id=receipt_id,
            receipt_version=_RECEIPT_VERSION,
            created_at=created_at,
            execution_id=input.execution_id,
            layer=input.layer,
            capability_id=input.capability_id,
            status=input.status,
            agent_id=input.agent_id,
            provider_id=provider_id,
            credential_mode=input.credential_mode,
            receipt_hash=receipt_hash,
            previous_receipt_hash=previous_hash,
            chain_sequence=chain_sequence,
            extra={
                k: v
                for k, v in receipt_data.items()
                if k
                not in {
                    "receipt_id",
                    "receipt_version",
                    "created_at",
                    "execution_id",
                    "layer",
                    "capability_id",
                    "status",
                    "agent_id",
                    "provider_id",
                    "credential_mode",
                    "receipt_hash",
                    "previous_receipt_hash",
                    "chain_sequence",
                }
                and v is not None
            },
        )

    async def get_receipt(self, receipt_id: str) -> dict[str, Any] | None:
        """Fetch a receipt by ID."""
        rows = await supabase_fetch(
            f"execution_receipts?receipt_id=eq.{receipt_id}&limit=1"
        )
        if not rows:
            return None
        return _public_receipt_row(rows[0])

    async def get_receipt_by_execution(self, execution_id: str) -> dict[str, Any] | None:
        """Fetch the most recent receipt for an execution."""
        rows = await supabase_fetch(
            f"execution_receipts?execution_id=eq.{execution_id}"
            f"&order=chain_sequence.desc&limit=1"
        )
        if not rows:
            return None
        return _public_receipt_row(rows[0])

    async def query_receipts(
        self,
        *,
        agent_id: str | None = None,
        org_id: str | None = None,
        capability_id: str | None = None,
        provider_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query receipts with filters."""
        filters: list[str] = []
        if agent_id:
            filters.append(f"agent_id=eq.{agent_id}")
        if org_id:
            filters.append(f"org_id=eq.{org_id}")
        if capability_id:
            filters.append(f"capability_id=eq.{capability_id}")
        if provider_id:
            provider_candidates = public_service_slug_candidates(provider_id)
            if len(provider_candidates) == 1:
                filters.append(f"provider_id=eq.{provider_candidates[0]}")
            elif provider_candidates:
                filters.append(f"provider_id=in.({','.join(provider_candidates)})")
        if status:
            filters.append(f"status=eq.{status}")

        filter_str = "&".join(filters) if filters else ""
        query = (
            f"execution_receipts?{filter_str}"
            f"&order=chain_sequence.desc"
            f"&limit={limit}&offset={offset}"
        )
        rows = await supabase_fetch(query) or []
        return [_public_receipt_row(row) for row in rows]

    async def verify_chain(
        self,
        *,
        start_sequence: int | None = None,
        end_sequence: int | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Verify chain integrity for a range of receipts.

        Returns a summary of the verification including any broken links.
        """
        filters = []
        if start_sequence is not None:
            filters.append(f"chain_sequence=gte.{start_sequence}")
        if end_sequence is not None:
            filters.append(f"chain_sequence=lte.{end_sequence}")

        filter_str = "&".join(filters) if filters else ""
        query = (
            f"execution_receipts?{filter_str}"
            f"&order=chain_sequence.asc"
            f"&limit={limit}"
            f"&select=receipt_id,receipt_hash,previous_receipt_hash,chain_sequence"
        )
        rows = await supabase_fetch(query) or []

        verified = 0
        broken_links: list[dict[str, Any]] = []
        for i, row in enumerate(rows):
            if i == 0:
                verified += 1
                continue
            prev_row = rows[i - 1]
            expected_prev_hash = prev_row.get("receipt_hash")
            actual_prev_hash = row.get("previous_receipt_hash")
            if expected_prev_hash != actual_prev_hash:
                broken_links.append({
                    "receipt_id": row["receipt_id"],
                    "chain_sequence": row["chain_sequence"],
                    "expected_previous_hash": expected_prev_hash,
                    "actual_previous_hash": actual_prev_hash,
                })
            else:
                verified += 1

        return {
            "total_checked": len(rows),
            "verified": verified,
            "broken_links": broken_links,
            "chain_intact": len(broken_links) == 0,
            "range": {
                "start": rows[0]["chain_sequence"] if rows else None,
                "end": rows[-1]["chain_sequence"] if rows else None,
            },
        }

    async def _advance_chain_state(self) -> dict[str, Any]:
        """Atomically advance the chain sequence and return new state.

        Uses optimistic concurrency: read current state, increment,
        write back with WHERE clause on the old sequence.
        """
        for attempt in range(_MAX_CHAIN_RETRIES):
            rows = await supabase_fetch(
                "receipt_chain_state?id=eq.1&select=last_sequence,last_receipt_hash"
            )
            if not rows:
                # Seed the chain state
                await supabase_insert("receipt_chain_state", {
                    "id": 1,
                    "last_sequence": 0,
                    "last_receipt_hash": None,
                })
                current_sequence = 0
                current_hash = None
            else:
                current_sequence = rows[0]["last_sequence"]
                current_hash = rows[0].get("last_receipt_hash")

            new_sequence = current_sequence + 1

            # Optimistic update: only succeeds if sequence hasn't changed
            updated = await supabase_patch(
                f"receipt_chain_state?id=eq.1&last_sequence=eq.{current_sequence}",
                {
                    "last_sequence": new_sequence,
                    "updated_at": self._now_iso(),
                },
            )

            if updated:
                return {
                    "sequence": new_sequence,
                    "previous_hash": current_hash,
                }

            # Contention: another writer advanced the sequence. Retry.
            logger.info(
                "receipt_chain_contention attempt=%d current_seq=%d",
                attempt + 1,
                current_sequence,
            )

        # All retries exhausted — this is extremely unlikely in practice
        # but we must not silently drop receipts.
        raise RuntimeError(
            f"Failed to advance receipt chain state after {_MAX_CHAIN_RETRIES} retries. "
            "This indicates extreme write contention."
        )

    async def _update_chain_hash(self, sequence: int, receipt_hash: str) -> None:
        """Update the chain state with the latest receipt hash."""
        await supabase_patch(
            f"receipt_chain_state?id=eq.1&last_sequence=eq.{sequence}",
            {"last_receipt_hash": receipt_hash},
        )

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


# Module-level singleton
_receipt_service: ReceiptService | None = None


def get_receipt_service() -> ReceiptService:
    """Get or create the receipt service singleton."""
    global _receipt_service
    if _receipt_service is None:
        _receipt_service = ReceiptService()
    return _receipt_service


def hash_request_payload(payload: Any) -> str | None:
    """Hash a request payload for receipt integrity."""
    return _hash_payload(payload)


def hash_response_payload(payload: Any) -> str | None:
    """Hash a response payload for receipt integrity."""
    return _hash_payload(payload)


def hash_caller_ip(ip: str | None) -> str | None:
    """Hash a caller IP for privacy-preserving receipt storage."""
    if not ip:
        return None
    return f"sha256:{hashlib.sha256(ip.encode('utf-8')).hexdigest()[:16]}"
