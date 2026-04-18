"""Billing event stream — structured event log for all payment activity (WU-41.5).

All billing-relevant operations (executions, credit purchases, top-ups,
refunds, budget alerts) are recorded as typed events with full context.

This feeds:
- Trust dashboard API (WU-41.6)
- Ledger reconciliation
- Usage analytics
- Anomaly detection (future)

Event types follow a consistent schema so consumers can filter, aggregate,
and build dashboards without parsing heterogeneous ledger entries.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from services.chain_integrity import get_signing_key_version
from services.service_slugs import public_service_slug, public_service_slug_candidates

logger = logging.getLogger(__name__)

_PROVIDER_VALUE_FIELDS = {
    "provider",
    "provider_id",
    "provider_slug",
    "provider_used",
    "fallback_provider",
    "selected_provider",
    "service",
    "service_slug",
}

_PROVIDER_LIST_FIELDS = {
    "allow_only",
    "fallback_providers",
    "provider_deny",
    "provider_ids",
    "provider_preference",
    "providers",
    "service_slugs",
}

_PROVIDER_TEXT_FIELDS = {
    "detail",
    "error",
    "error_message",
    "message",
    "reason",
}


def _canonicalize_provider_value(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = value.strip()
        return public_service_slug(cleaned) or cleaned
    return value


def _canonicalize_provider_text(text: Any, provider_slugs: set[str]) -> str | None:
    if text is None:
        return None

    canonicalized = str(text)
    replacements: dict[str, str] = {}
    for provider_slug in provider_slugs:
        canonical = public_service_slug(provider_slug)
        if canonical is None:
            continue
        for candidate in public_service_slug_candidates(canonical):
            if not candidate or candidate.lower() == canonical.lower():
                continue
            replacements[candidate.lower()] = canonical

    if not replacements:
        return canonicalized

    pattern = re.compile(
        rf"(?<![a-z0-9-])(?:{'|'.join(re.escape(candidate) for candidate in sorted(replacements, key=len, reverse=True))})(?![a-z0-9-])",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: replacements[match.group(0).lower()], canonicalized)


def _collect_provider_contexts(value: Any, *, provider_slugs: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _PROVIDER_VALUE_FIELDS and isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    provider_slugs.add(cleaned)
                continue
            if key in _PROVIDER_LIST_FIELDS and isinstance(item, list):
                for entry in item:
                    if isinstance(entry, str):
                        cleaned = entry.strip()
                        if cleaned:
                            provider_slugs.add(cleaned)
                    else:
                        _collect_provider_contexts(entry, provider_slugs=provider_slugs)
                continue
            _collect_provider_contexts(item, provider_slugs=provider_slugs)
        return

    if isinstance(value, list):
        for item in value:
            _collect_provider_contexts(item, provider_slugs=provider_slugs)


def _canonicalize_provider_payload(value: Any, *, provider_slugs: set[str]) -> Any:
    if isinstance(value, dict):
        canonicalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in _PROVIDER_VALUE_FIELDS:
                canonicalized[key] = _canonicalize_provider_value(item)
            elif key in _PROVIDER_LIST_FIELDS and isinstance(item, list):
                canonicalized[key] = [
                    _canonicalize_provider_value(entry)
                    if isinstance(entry, str)
                    else _canonicalize_provider_payload(entry, provider_slugs=provider_slugs)
                    for entry in item
                ]
            elif key in _PROVIDER_TEXT_FIELDS and not isinstance(item, (dict, list)):
                canonicalized[key] = _canonicalize_provider_text(item, provider_slugs)
            else:
                canonicalized[key] = _canonicalize_provider_payload(item, provider_slugs=provider_slugs)
        return canonicalized

    if isinstance(value, list):
        return [_canonicalize_provider_payload(item, provider_slugs=provider_slugs) for item in value]

    return value


def _canonicalize_billing_metadata(
    metadata: dict[str, Any] | None,
    *,
    provider_slug: str | None,
) -> dict[str, Any]:
    raw_metadata = dict(metadata or {})
    provider_contexts: set[str] = set()
    if provider_slug:
        provider_contexts.add(provider_slug)
    _collect_provider_contexts(raw_metadata, provider_slugs=provider_contexts)
    canonicalized = _canonicalize_provider_payload(raw_metadata, provider_slugs=provider_contexts)
    return canonicalized if isinstance(canonicalized, dict) else {}


class BillingEventType(str, Enum):
    """Canonical billing event types."""

    # Execution billing
    EXECUTION_CHARGED = "execution.charged"
    EXECUTION_REFUNDED = "execution.refunded"
    EXECUTION_FAILED_NO_CHARGE = "execution.failed_no_charge"

    # Credit operations
    CREDIT_PURCHASED = "credit.purchased"
    CREDIT_EXPIRED = "credit.expired"
    CREDIT_ADJUSTED = "credit.adjusted"

    # x402 / wallet operations
    X402_PAYMENT_RECEIVED = "x402.payment_received"
    X402_SETTLEMENT_COMPLETED = "x402.settlement_completed"
    X402_SETTLEMENT_FAILED = "x402.settlement_failed"
    WALLET_TOPUP_COMPLETED = "wallet.topup_completed"
    WALLET_TOPUP_FAILED = "wallet.topup_failed"

    # Budget events
    BUDGET_THRESHOLD_WARNING = "budget.threshold_warning"
    BUDGET_LIMIT_REACHED = "budget.limit_reached"
    BUDGET_RESET = "budget.reset"

    # Administrative
    AUTO_RELOAD_TRIGGERED = "auto_reload.triggered"
    AUTO_RELOAD_FAILED = "auto_reload.failed"


@dataclass(frozen=True, slots=True)
class BillingEvent:
    """Immutable billing event record."""

    event_id: str
    event_type: BillingEventType
    org_id: str
    timestamp: datetime
    amount_usd_cents: int  # positive = charge, negative = credit
    balance_after_usd_cents: int | None
    metadata: dict[str, Any]
    # Linkage
    receipt_id: str | None = None
    execution_id: str | None = None
    capability_id: str | None = None
    provider_slug: str | None = None
    # Chain integrity
    chain_hash: str = ""
    prev_hash: str = ""
    key_version: int | None = None


@dataclass(frozen=True, slots=True)
class BillingEventSummary:
    """Aggregated billing summary for a time period."""

    org_id: str
    period: str  # e.g. "2026-03" or "2026-03-31"
    total_charged_usd_cents: int
    total_credited_usd_cents: int
    execution_count: int
    x402_payment_count: int
    credit_purchase_count: int
    by_provider: dict[str, int]  # provider_slug → charged cents
    by_capability: dict[str, int]  # capability_id → charged cents
    events_count: int


class BillingEventStream:
    """Append-only billing event stream with chain hashing.

    All billing operations should emit events through this service.
    Events are immutable and chain-linked for auditability.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, *, outbox: Any | None = None) -> None:
        self._events: list[BillingEvent] = []
        self._lock = threading.Lock()
        self._prev_hash: str = self.GENESIS_HASH
        self._org_index: dict[str, list[int]] = {}  # org_id → event indices
        self._outbox = outbox

    @staticmethod
    def _compute_hash(
        prev_hash: str,
        event_id: str,
        event_type: str,
        org_id: str,
        amount: int,
        timestamp: str,
        *,
        event: Any = None,
    ) -> str:
        """Compute chain hash for a billing event.

        AUD-3: uses HMAC-SHA256 with full semantic payload when event is provided.
        Falls back to legacy SHA-256 on header fields when event is None (backward compat).
        """
        if event is not None:
            from services.chain_integrity import build_billing_payload, compute_chain_hmac
            payload = build_billing_payload(event)
            return compute_chain_hmac(
                prev_hash,
                payload,
                key_version=getattr(event, "key_version", None),
            )
        # Legacy fallback (for verify_chain on old events)
        payload = f"{prev_hash}|{event_id}|{event_type}|{org_id}|{amount}|{timestamp}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def emit(
        self,
        event_type: BillingEventType,
        org_id: str,
        amount_usd_cents: int,
        balance_after_usd_cents: int | None = None,
        metadata: dict[str, Any] | None = None,
        receipt_id: str | None = None,
        execution_id: str | None = None,
        capability_id: str | None = None,
        provider_slug: str | None = None,
    ) -> BillingEvent:
        """Record a billing event. Returns the event for confirmation."""
        canonical_provider_slug = public_service_slug(provider_slug) or provider_slug
        canonical_metadata = _canonicalize_billing_metadata(
            metadata,
            provider_slug=canonical_provider_slug,
        )
        with self._lock:
            event_id = f"bevt_{uuid4().hex[:16]}"
            now = datetime.now(timezone.utc)
            key_version = get_signing_key_version()

            # AUD-3: build event first (without hash), then compute HMAC over full payload
            event_without_hash = BillingEvent(
                event_id=event_id,
                event_type=event_type,
                org_id=org_id,
                timestamp=now,
                amount_usd_cents=amount_usd_cents,
                balance_after_usd_cents=balance_after_usd_cents,
                metadata=canonical_metadata,
                receipt_id=receipt_id,
                execution_id=execution_id,
                capability_id=capability_id,
                provider_slug=canonical_provider_slug,
                chain_hash="",  # placeholder
                prev_hash=self._prev_hash,
                key_version=key_version,
            )

            chain_hash = self._compute_hash(
                self._prev_hash,
                event_id,
                event_type.value,
                org_id,
                amount_usd_cents,
                now.isoformat(),
                event=event_without_hash,
            )

            event = BillingEvent(
                event_id=event_id,
                event_type=event_type,
                org_id=org_id,
                timestamp=now,
                amount_usd_cents=amount_usd_cents,
                balance_after_usd_cents=balance_after_usd_cents,
                metadata=canonical_metadata,
                receipt_id=receipt_id,
                execution_id=execution_id,
                capability_id=capability_id,
                provider_slug=canonical_provider_slug,
                chain_hash=chain_hash,
                prev_hash=self._prev_hash,
                key_version=key_version,
            )

            if self._outbox is not None:
                self._outbox.append_billing_event(event)

            idx = len(self._events)
            self._events.append(event)
            self._prev_hash = chain_hash

            if org_id not in self._org_index:
                self._org_index[org_id] = []
            self._org_index[org_id].append(idx)

            return event

    def query(
        self,
        org_id: str | None = None,
        event_type: BillingEventType | None = None,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[BillingEvent]:
        """Query events with optional filters. Returns newest first."""
        with self._lock:
            if org_id is not None:
                if org_id not in self._org_index:
                    return []
                indices = self._org_index[org_id]
                candidates = [self._events[i] for i in indices]
            else:
                candidates = list(self._events)

        # Apply filters
        if event_type:
            candidates = [e for e in candidates if e.event_type == event_type]
        if since:
            candidates = [e for e in candidates if e.timestamp >= since]

        # Newest first, limited
        candidates.sort(key=lambda e: e.timestamp, reverse=True)
        return candidates[:limit]

    def summarize(
        self,
        org_id: str,
        period: str | None = None,
    ) -> BillingEventSummary:
        """Build an aggregate summary for an org, optionally filtered to a period.

        ``period`` can be "2026-03" (month) or "2026-03-31" (day).
        """
        events = self.query(org_id=org_id, limit=100_000)

        if period:
            events = [e for e in events if e.timestamp.strftime("%Y-%m").startswith(period[:7])
                       and (len(period) <= 7 or e.timestamp.strftime("%Y-%m-%d") == period)]

        total_charged = 0
        total_credited = 0
        execution_count = 0
        x402_count = 0
        credit_purchase_count = 0
        by_provider: dict[str, int] = {}
        by_capability: dict[str, int] = {}

        for event in events:
            if event.amount_usd_cents > 0:
                total_charged += event.amount_usd_cents
            else:
                total_credited += abs(event.amount_usd_cents)

            if event.event_type == BillingEventType.EXECUTION_CHARGED:
                execution_count += 1
                public_provider_slug = public_service_slug(event.provider_slug)
                if public_provider_slug:
                    by_provider[public_provider_slug] = (
                        by_provider.get(public_provider_slug, 0) + event.amount_usd_cents
                    )
                if event.capability_id:
                    by_capability[event.capability_id] = (
                        by_capability.get(event.capability_id, 0) + event.amount_usd_cents
                    )
            elif event.event_type in (
                BillingEventType.X402_PAYMENT_RECEIVED,
                BillingEventType.X402_SETTLEMENT_COMPLETED,
            ):
                x402_count += 1
            elif event.event_type == BillingEventType.CREDIT_PURCHASED:
                credit_purchase_count += 1

        return BillingEventSummary(
            org_id=org_id,
            period=period or "all",
            total_charged_usd_cents=total_charged,
            total_credited_usd_cents=total_credited,
            execution_count=execution_count,
            x402_payment_count=x402_count,
            credit_purchase_count=credit_purchase_count,
            by_provider=by_provider,
            by_capability=by_capability,
            events_count=len(events),
        )

    def verify_chain(self) -> bool:
        """Verify integrity of the entire event chain.

        AUD-3: uses HMAC with full semantic payload for verification.
        """
        with self._lock:
            from services.chain_integrity import build_billing_payload, verify_chain_hmac

            prev_hash = self.GENESIS_HASH
            for event in self._events:
                payload = build_billing_payload(event)
                if (
                    not verify_chain_hmac(
                        prev_hash,
                        payload,
                        event.chain_hash,
                        key_version=event.key_version,
                    )
                    or event.prev_hash != prev_hash
                ):
                    return False
                prev_hash = event.chain_hash
            return True

    @property
    def length(self) -> int:
        with self._lock:
            return len(self._events)

    @property
    def latest_hash(self) -> str:
        with self._lock:
            return self._prev_hash

    @property
    def latest_key_version(self) -> int | None:
        with self._lock:
            return self._events[-1].key_version if self._events else None

    @property
    def latest_timestamp(self) -> datetime | None:
        with self._lock:
            return self._events[-1].timestamp if self._events else None

    def configure_outbox(self, outbox: Any | None) -> None:
        """Attach or replace the durable outbox."""
        with self._lock:
            self._outbox = outbox

    def load_replay_payloads(self, payloads: list[dict[str, Any]]) -> None:
        """Rebuild in-memory state from durable outbox payloads."""
        with self._lock:
            self._events = [self._event_from_payload(payload) for payload in payloads]
            self._org_index = {}
            self._prev_hash = self.GENESIS_HASH
            for idx, event in enumerate(self._events):
                self._org_index.setdefault(event.org_id, []).append(idx)
                self._prev_hash = event.chain_hash

    @staticmethod
    def _event_from_payload(payload: dict[str, Any]) -> BillingEvent:
        return BillingEvent(
            event_id=str(payload["event_id"]),
            event_type=BillingEventType(str(payload["event_type"])),
            org_id=str(payload["org_id"]),
            timestamp=datetime.fromisoformat(str(payload["timestamp"])),
            amount_usd_cents=int(payload["amount_usd_cents"]),
            balance_after_usd_cents=(
                int(payload["balance_after_usd_cents"])
                if payload.get("balance_after_usd_cents") is not None
                else None
            ),
            metadata=dict(payload.get("metadata") or {}),
            receipt_id=payload.get("receipt_id"),
            execution_id=payload.get("execution_id"),
            capability_id=payload.get("capability_id"),
            provider_slug=payload.get("provider_slug"),
            chain_hash=str(payload.get("chain_hash", "")),
            prev_hash=str(payload.get("prev_hash", "")),
            key_version=(
                int(payload["key_version"])
                if payload.get("key_version") is not None
                else None
            ),
        )


# ── Module-level singleton ────────────────────────────────────────

_billing_stream: BillingEventStream | None = None


def init_billing_event_stream(
    *,
    outbox: Any | None = None,
    replay_payloads: list[dict[str, Any]] | None = None,
) -> BillingEventStream:
    """Initialize the module-level stream with durable replay."""
    global _billing_stream
    _billing_stream = BillingEventStream(outbox=outbox)
    if replay_payloads:
        _billing_stream.load_replay_payloads(replay_payloads)
    return _billing_stream


def get_billing_event_stream() -> BillingEventStream:
    """Return the module-level billing event stream singleton."""
    global _billing_stream
    if _billing_stream is None:
        _billing_stream = BillingEventStream()
    return _billing_stream
