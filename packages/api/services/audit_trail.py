"""Unified audit trail — append-only, chain-hashed, 15 event types (WU-42.5).

Central audit log for SOC2 preparation. All security-relevant, billing-relevant,
and governance-relevant operations are recorded here as immutable typed events.

Consumers:
- Compliance dashboards
- SOC2 audit exports
- Incident investigation
- Trust dashboard enrichment

Architectural invariant: this service is write-once. No updates, no deletes.
Chain-hash integrity is verifiable by any consumer at any time.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import threading
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from services.chain_integrity import (
    build_audit_payload,
    build_chain_checkpoint_payload,
    compute_chain_hmac,
    get_signing_key_version,
    verify_chain_hmac,
)

logger = logging.getLogger(__name__)


# ── Event Types ──────────────────────────────────────────────────────


class AuditEventType(str, Enum):
    """15 canonical audit event types per spec §11-12."""

    # Execution lifecycle
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"

    # Kill switch operations
    KILL_SWITCH_ACTIVATED = "kill_switch.activated"
    KILL_SWITCH_APPROVED = "kill_switch.approved"
    KILL_SWITCH_RESTORED = "kill_switch.restored"
    KILL_SWITCH_LIFTED = "kill_switch.lifted"

    # Policy changes
    POLICY_UPDATED = "policy.updated"
    POLICY_VIOLATION = "policy.violation"

    # Budget events
    BUDGET_THRESHOLD = "budget.threshold"
    BUDGET_EXCEEDED = "budget.exceeded"

    # Score changes
    SCORE_UPDATED = "score.updated"

    # Recipe lifecycle
    RECIPE_EXECUTED = "recipe.executed"
    RECIPE_STEP_FAILED = "recipe.step_failed"

    # Agent lifecycle
    AGENT_LIFECYCLE = "agent.lifecycle"

    # AUD-7: Auth/credential/config events
    AUTH_LOGIN = "auth.login"
    AUTH_FAILED = "auth.failed"
    AUTH_LOGOUT = "auth.logout"
    CREDENTIAL_ACCESSED = "credential.accessed"
    CREDENTIAL_ROTATED = "credential.rotated"
    CREDENTIAL_REVOKED = "credential.revoked"
    CONFIG_CHANGED = "config.changed"
    ADMIN_ACTION = "admin.action"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# ── Event type metadata ──────────────────────────────────────────────

_EVENT_METADATA: dict[AuditEventType, dict[str, Any]] = {
    AuditEventType.EXECUTION_STARTED: {
        "severity": AuditSeverity.INFO,
        "category": "execution",
        "description": "Capability execution initiated",
        "retention_days": 90,
    },
    AuditEventType.EXECUTION_COMPLETED: {
        "severity": AuditSeverity.INFO,
        "category": "execution",
        "description": "Capability execution completed successfully",
        "retention_days": 90,
    },
    AuditEventType.EXECUTION_FAILED: {
        "severity": AuditSeverity.WARNING,
        "category": "execution",
        "description": "Capability execution failed",
        "retention_days": 180,
    },
    AuditEventType.KILL_SWITCH_ACTIVATED: {
        "severity": AuditSeverity.CRITICAL,
        "category": "security",
        "description": "Kill switch activated",
        "retention_days": 365,
    },
    AuditEventType.KILL_SWITCH_APPROVED: {
        "severity": AuditSeverity.CRITICAL,
        "category": "security",
        "description": "Global kill switch approved by second principal",
        "retention_days": 365,
    },
    AuditEventType.KILL_SWITCH_RESTORED: {
        "severity": AuditSeverity.WARNING,
        "category": "security",
        "description": "Kill switch entering restoration phase",
        "retention_days": 365,
    },
    AuditEventType.KILL_SWITCH_LIFTED: {
        "severity": AuditSeverity.WARNING,
        "category": "security",
        "description": "Kill switch lifted",
        "retention_days": 365,
    },
    AuditEventType.POLICY_UPDATED: {
        "severity": AuditSeverity.INFO,
        "category": "governance",
        "description": "Execution policy updated",
        "retention_days": 365,
    },
    AuditEventType.POLICY_VIOLATION: {
        "severity": AuditSeverity.WARNING,
        "category": "governance",
        "description": "Execution blocked by policy constraint",
        "retention_days": 180,
    },
    AuditEventType.BUDGET_THRESHOLD: {
        "severity": AuditSeverity.WARNING,
        "category": "billing",
        "description": "Budget threshold warning triggered",
        "retention_days": 90,
    },
    AuditEventType.BUDGET_EXCEEDED: {
        "severity": AuditSeverity.CRITICAL,
        "category": "billing",
        "description": "Budget limit exceeded — execution blocked",
        "retention_days": 180,
    },
    AuditEventType.SCORE_UPDATED: {
        "severity": AuditSeverity.INFO,
        "category": "trust",
        "description": "AN Score updated for a provider",
        "retention_days": 365,
    },
    AuditEventType.RECIPE_EXECUTED: {
        "severity": AuditSeverity.INFO,
        "category": "execution",
        "description": "Recipe execution completed",
        "retention_days": 90,
    },
    AuditEventType.RECIPE_STEP_FAILED: {
        "severity": AuditSeverity.WARNING,
        "category": "execution",
        "description": "Recipe step failed during execution",
        "retention_days": 180,
    },
    AuditEventType.AGENT_LIFECYCLE: {
        "severity": AuditSeverity.INFO,
        "category": "identity",
        "description": "Agent created, disabled, or re-enabled",
        "retention_days": 365,
    },
    # AUD-7: Auth/credential/config event metadata
    AuditEventType.AUTH_LOGIN: {
        "severity": AuditSeverity.INFO,
        "category": "auth",
        "description": "Successful authentication",
        "retention_days": 90,
    },
    AuditEventType.AUTH_FAILED: {
        "severity": AuditSeverity.WARNING,
        "category": "auth",
        "description": "Failed authentication attempt",
        "retention_days": 180,
    },
    AuditEventType.AUTH_LOGOUT: {
        "severity": AuditSeverity.INFO,
        "category": "auth",
        "description": "Session terminated",
        "retention_days": 90,
    },
    AuditEventType.CREDENTIAL_ACCESSED: {
        "severity": AuditSeverity.INFO,
        "category": "credential",
        "description": "Credential accessed for execution",
        "retention_days": 180,
    },
    AuditEventType.CREDENTIAL_ROTATED: {
        "severity": AuditSeverity.WARNING,
        "category": "credential",
        "description": "Credential rotated or updated",
        "retention_days": 365,
    },
    AuditEventType.CREDENTIAL_REVOKED: {
        "severity": AuditSeverity.WARNING,
        "category": "credential",
        "description": "Credential revoked or deleted",
        "retention_days": 365,
    },
    AuditEventType.CONFIG_CHANGED: {
        "severity": AuditSeverity.WARNING,
        "category": "config",
        "description": "System or org configuration changed",
        "retention_days": 365,
    },
    AuditEventType.ADMIN_ACTION: {
        "severity": AuditSeverity.WARNING,
        "category": "admin",
        "description": "Administrative action performed",
        "retention_days": 365,
    },
}


# ── Data structures ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Immutable audit event record.

    Every field is frozen after creation. Chain hashing provides
    tamper-evidence for the entire log.
    """

    event_id: str
    event_type: AuditEventType
    severity: AuditSeverity
    category: str
    timestamp: datetime
    # Who / what
    org_id: str | None
    agent_id: str | None
    principal: str | None  # human or system actor
    # What happened
    resource_type: str | None  # "capability", "recipe", "provider", "agent", "policy"
    resource_id: str | None  # the ID of the affected resource
    action: str  # human-readable action description
    detail: dict[str, Any]  # structured payload (event-type-specific)
    # Linkage
    receipt_id: str | None = None
    execution_id: str | None = None
    provider_slug: str | None = None
    # Chain integrity
    chain_sequence: int = 0
    chain_hash: str = ""
    prev_hash: str = ""
    key_version: int | None = None


@dataclass(frozen=True, slots=True)
class AuditExportResult:
    """Result of an audit trail export operation."""

    format: str  # "json" or "csv"
    event_count: int
    data: str  # serialized export data
    chain_verified: bool
    exported_at: datetime


@dataclass(frozen=True, slots=True)
class AuditChainStatus:
    """Health status of the audit chain."""

    total_events: int
    chain_verified: bool
    latest_hash: str
    latest_sequence: int
    earliest_event: datetime | None
    latest_event: datetime | None
    events_by_type: dict[str, int]
    events_by_severity: dict[str, int]
    events_by_category: dict[str, int]


# ── Audit Trail Service ─────────────────────────────────────────────


class AuditTrail:
    """Append-only audit trail with chain-hash integrity.

    Thread-safe. Write-once semantics — no event modification or deletion.
    Chain integrity is verifiable at any time via verify_chain().
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, *, outbox: Any | None = None) -> None:
        self._events: list[AuditEvent] = []
        self._lock = threading.Lock()
        self._prev_hash: str = self.GENESIS_HASH
        self._sequence: int = 0
        self._outbox = outbox
        # Indexes for efficient querying
        self._org_index: dict[str, list[int]] = {}
        self._type_index: dict[AuditEventType, list[int]] = {}
        self._severity_index: dict[AuditSeverity, list[int]] = {}
        self._category_index: dict[str, list[int]] = {}

    # ── Write ─────────────────────────────────────────────────────

    def record(
        self,
        event_type: AuditEventType,
        action: str,
        *,
        org_id: str | None = None,
        agent_id: str | None = None,
        principal: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        detail: dict[str, Any] | None = None,
        receipt_id: str | None = None,
        execution_id: str | None = None,
        provider_slug: str | None = None,
    ) -> AuditEvent:
        """Record an audit event. Returns the immutable event.

        This is the ONLY write path. Events cannot be modified or deleted.
        """
        meta = _EVENT_METADATA.get(event_type, {})
        severity = meta.get("severity", AuditSeverity.INFO)
        category = meta.get("category", "unknown")

        with self._lock:
            self._sequence += 1
            event_id = f"aud_{uuid4().hex[:16]}"
            now = datetime.now(timezone.utc)
            key_version = get_signing_key_version()

            chain_hash = self._compute_hash(
                self._prev_hash,
                {
                    "event_id": event_id,
                    "event_type": event_type,
                    "severity": severity,
                    "category": category,
                    "timestamp": now,
                    "org_id": org_id,
                    "agent_id": agent_id,
                    "principal": principal,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "action": action,
                    "detail": detail or {},
                    "receipt_id": receipt_id,
                    "execution_id": execution_id,
                    "provider_slug": provider_slug,
                    "metadata": {},
                    "key_version": key_version,
                },
            )

            event = AuditEvent(
                event_id=event_id,
                event_type=event_type,
                severity=severity,
                category=category,
                timestamp=now,
                org_id=org_id,
                agent_id=agent_id,
                principal=principal,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                detail=detail or {},
                receipt_id=receipt_id,
                execution_id=execution_id,
                provider_slug=provider_slug,
                chain_sequence=self._sequence,
                chain_hash=chain_hash,
                prev_hash=self._prev_hash,
                key_version=key_version,
            )

            if self._outbox is not None:
                self._outbox.append_audit_event(event)

            idx = len(self._events)
            self._events.append(event)
            self._prev_hash = chain_hash

            # Update indexes
            if org_id:
                self._org_index.setdefault(org_id, []).append(idx)
            self._type_index.setdefault(event_type, []).append(idx)
            self._severity_index.setdefault(severity, []).append(idx)
            self._category_index.setdefault(category, []).append(idx)

        if severity == AuditSeverity.CRITICAL:
            logger.critical(
                "AUDIT_CRITICAL event_type=%s action=%s org=%s agent=%s",
                event_type.value, action, org_id, agent_id,
            )
        elif severity == AuditSeverity.WARNING:
            logger.warning(
                "AUDIT_WARNING event_type=%s action=%s org=%s",
                event_type.value, action, org_id,
            )
        else:
            logger.info(
                "AUDIT event_type=%s action=%s org=%s",
                event_type.value, action, org_id,
            )

        return event

    # ── Query ─────────────────────────────────────────────────────

    def query(
        self,
        *,
        org_id: str | None = None,
        event_type: AuditEventType | None = None,
        severity: AuditSeverity | None = None,
        category: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEvent]:
        """Query audit events with filters. Returns newest first."""
        with self._lock:
            # Start with the full event set
            indices: set[int] | None = None

            # Each indexed filter either narrows (intersect) or short-circuits
            # to empty when the requested key is absent from the index.
            for key, index in (
                (org_id, self._org_index),
                (event_type, self._type_index),
                (severity, self._severity_index),
                (category, self._category_index),
            ):
                if key is None:
                    continue
                if key not in index:
                    # Requested filter value does not exist → zero matches
                    indices = set()
                    break
                matched = set(index[key])
                indices = matched if indices is None else indices & matched

            if indices is None:
                # No indexed filters applied → start from all events
                indices = set(range(len(self._events)))

            candidates = [self._events[i] for i in indices]

        # Apply non-indexed filters
        if since:
            candidates = [e for e in candidates if e.timestamp >= since]
        if until:
            candidates = [e for e in candidates if e.timestamp <= until]
        if resource_type:
            candidates = [e for e in candidates if e.resource_type == resource_type]
        if resource_id:
            candidates = [e for e in candidates if e.resource_id == resource_id]

        # Sort newest first
        candidates.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply pagination
        return candidates[offset : offset + limit]

    def count(
        self,
        *,
        org_id: str | None = None,
        event_type: AuditEventType | None = None,
        severity: AuditSeverity | None = None,
        category: str | None = None,
    ) -> int:
        """Count events matching filters (for pagination)."""
        return len(
            self.query(
                org_id=org_id,
                event_type=event_type,
                severity=severity,
                category=category,
                limit=1_000_000,
            )
        )

    # ── Chain integrity ───────────────────────────────────────────

    def verify_chain(self) -> tuple[bool, int]:
        """Verify integrity of the entire audit chain.

        Returns (is_valid, events_checked).
        """
        with self._lock:
            prev_hash = self.GENESIS_HASH
            for i, event in enumerate(self._events):
                payload = build_audit_payload(event)
                if not verify_chain_hmac(
                    prev_hash,
                    payload,
                    event.chain_hash,
                    key_version=event.key_version,
                ):
                    logger.error(
                        "audit_chain_broken at sequence=%d event_id=%s",
                        event.chain_sequence, event.event_id,
                    )
                    return False, i
                if event.prev_hash != prev_hash:
                    logger.error(
                        "audit_chain_prev_mismatch at sequence=%d event_id=%s",
                        event.chain_sequence, event.event_id,
                    )
                    return False, i
                prev_hash = event.chain_hash
            return True, len(self._events)

    def status(self) -> AuditChainStatus:
        """Return chain health status and statistics."""
        with self._lock:
            events_by_type: dict[str, int] = {}
            events_by_severity: dict[str, int] = {}
            events_by_category: dict[str, int] = {}

            for event in self._events:
                events_by_type[event.event_type.value] = (
                    events_by_type.get(event.event_type.value, 0) + 1
                )
                events_by_severity[event.severity.value] = (
                    events_by_severity.get(event.severity.value, 0) + 1
                )
                events_by_category[event.category] = (
                    events_by_category.get(event.category, 0) + 1
                )

            earliest = self._events[0].timestamp if self._events else None
            latest = self._events[-1].timestamp if self._events else None

        is_valid, _ = self.verify_chain()

        return AuditChainStatus(
            total_events=len(self._events),
            chain_verified=is_valid,
            latest_hash=self._prev_hash,
            latest_sequence=self._sequence,
            earliest_event=earliest,
            latest_event=latest,
            events_by_type=events_by_type,
            events_by_severity=events_by_severity,
            events_by_category=events_by_category,
        )

    # ── Export ────────────────────────────────────────────────────

    def export(
        self,
        format: str = "json",
        *,
        org_id: str | None = None,
        event_type: AuditEventType | None = None,
        severity: AuditSeverity | None = None,
        category: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> AuditExportResult:
        """Export audit events in JSON or CSV format.

        Includes chain verification status in the export metadata.
        """
        events = self.query(
            org_id=org_id,
            event_type=event_type,
            severity=severity,
            category=category,
            since=since,
            until=until,
            limit=1_000_000,  # Export all matching
        )

        # Sort chronologically for export (oldest first)
        events.sort(key=lambda e: e.timestamp)

        is_valid, _ = self.verify_chain()

        if format == "csv":
            data = self._export_csv(events)
        else:
            data = self._export_json(events, is_valid)

        return AuditExportResult(
            format=format,
            event_count=len(events),
            data=data,
            chain_verified=is_valid,
            exported_at=datetime.now(timezone.utc),
        )

    def _export_json(self, events: list[AuditEvent], chain_verified: bool) -> str:
        """Export events as JSON.

        AUD-24: exports always redact sensitive payload content.
        """
        export_data = {
            "export_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "chain_verified": chain_verified,
            "event_count": len(events),
            "events": [self._event_to_dict(e, redact=True) for e in events],
        }
        return json.dumps(export_data, indent=2, default=str)

    def _export_csv(self, events: list[AuditEvent]) -> str:
        """Export events as CSV."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "event_id",
            "event_type",
            "severity",
            "category",
            "timestamp",
            "org_id",
            "agent_id",
            "principal",
            "resource_type",
            "resource_id",
            "action",
            "receipt_id",
            "execution_id",
            "provider_slug",
            "chain_sequence",
            "chain_hash",
        ])

        for event in events:
            writer.writerow([
                event.event_id,
                event.event_type.value,
                event.severity.value,
                event.category,
                event.timestamp.isoformat(),
                event.org_id or "",
                event.agent_id or "",
                event.principal or "",
                event.resource_type or "",
                event.resource_id or "",
                event.action,
                event.receipt_id or "",
                event.execution_id or "",
                event.provider_slug or "",
                event.chain_sequence,
                event.chain_hash,
            ])

        return output.getvalue()

    @staticmethod
    def serialize_event(event: AuditEvent, *, redact: bool = True) -> dict[str, Any]:
        """Convert an event to a JSON-safe dict for external/API-facing use."""
        return AuditTrail._event_to_dict(event, redact=redact)

    @staticmethod
    def _event_to_dict(event: AuditEvent, *, redact: bool = False) -> dict[str, Any]:
        """Convert an event to a JSON-serializable dict.

        AUD-24: when redact=True, sensitive values in detail/metadata
        are replaced with [REDACTED] before export.
        """
        detail = event.detail
        metadata = getattr(event, "metadata", None) or {}

        if redact:
            from services.payload_redactor import redact_event_detail, redact_event_metadata
            detail = redact_event_detail(detail)
            metadata = redact_event_metadata(metadata)

        return {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "severity": event.severity.value,
            "category": event.category,
            "timestamp": event.timestamp.isoformat(),
            "org_id": event.org_id,
            "agent_id": event.agent_id,
            "principal": event.principal,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "action": event.action,
            "detail": detail,
            "receipt_id": event.receipt_id,
            "execution_id": event.execution_id,
            "provider_slug": event.provider_slug,
            "chain_sequence": event.chain_sequence,
            "chain_hash": event.chain_hash,
            "prev_hash": event.prev_hash,
            "key_version": event.key_version,
        }

    # ── Internal ──────────────────────────────────────────────────

    @staticmethod
    def _compute_hash(
        prev_hash: str,
        event: AuditEvent | dict[str, Any],
    ) -> str:
        payload = build_audit_payload(event)
        key_version = event.get("key_version") if isinstance(event, dict) else getattr(event, "key_version", None)
        return compute_chain_hmac(prev_hash, payload, key_version=key_version)

    def enforce_retention(self) -> dict[str, int]:
        """AUD-7 + AUD-3: purge expired events while checkpointing the old head.

        Each event type has a configured retention_days in _EVENT_METADATA.
        Events older than their retention period are removed from the in-memory store.

        If an outbox is configured, a signed chain-checkpoint payload is emitted
        before the chain is rewritten so purge boundaries remain durable.

        Returns a summary of purged events by type.
        """
        now = datetime.now(timezone.utc)
        purged: dict[str, int] = {}

        with self._lock:
            surviving = []
            for event in self._events:
                meta = _EVENT_METADATA.get(event.event_type, {})
                retention_days = meta.get("retention_days", 365)
                age_days = (now - event.timestamp).days
                if age_days > retention_days:
                    type_key = event.event_type.value
                    purged[type_key] = purged.get(type_key, 0) + 1
                else:
                    surviving.append(event)

            if purged:
                if self._outbox is not None and hasattr(self._outbox, "append_chain_checkpoint"):
                    checkpoint_payload = self._build_retention_checkpoint_payload(
                        surviving=surviving,
                        purged=purged,
                        created_at=now,
                    )
                    self._outbox.append_chain_checkpoint(checkpoint_payload)

                self._events = self._rechain_events(surviving)
                self._rebuild_indexes()
                logger.info(
                    "audit_retention_enforced purged=%d types=%s",
                    sum(purged.values()),
                    purged,
                )

        return purged

    @staticmethod
    def _surviving_segment_digest(events: list[AuditEvent]) -> str:
        rows = [
            {
                "event_id": event.event_id,
                "chain_sequence": event.chain_sequence,
                "prev_hash": event.prev_hash,
                "chain_hash": event.chain_hash,
                "key_version": event.key_version,
            }
            for event in events
        ]
        canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _build_retention_checkpoint_payload(
        self,
        *,
        surviving: list[AuditEvent],
        purged: dict[str, int],
        created_at: datetime,
    ) -> dict[str, Any]:
        latest_event = self._events[-1] if self._events else None
        source_key_version = getattr(latest_event, "key_version", None)
        checkpoint_key_version = get_signing_key_version()
        metadata: dict[str, Any] = {
            "purged_by_type": purged,
            "purged_count": sum(purged.values()),
            "surviving_count": len(surviving),
            "surviving_segment_digest": self._surviving_segment_digest(surviving),
        }
        if surviving:
            first_survivor = surviving[0]
            metadata["first_survivor_event_id"] = first_survivor.event_id
            metadata["first_survivor_original_hash"] = first_survivor.chain_hash
            metadata["first_survivor_original_prev_hash"] = first_survivor.prev_hash

        payload = build_chain_checkpoint_payload(
            {
                "checkpoint_id": f"chk_{uuid4().hex[:16]}",
                "stream_name": "audit_events",
                "reason": "retention_purge",
                "source_head_hash": self._prev_hash,
                "source_head_sequence": self._sequence,
                "source_key_version": source_key_version,
                "created_at": created_at,
                "metadata": metadata,
            }
        )
        checkpoint_hash = compute_chain_hmac(
            self.GENESIS_HASH,
            payload,
            key_version=checkpoint_key_version,
        )
        return {
            **payload,
            "checkpoint_hash": checkpoint_hash,
            "key_version": checkpoint_key_version,
        }

    def _rebuild_indexes(self) -> None:
        """Rebuild internal indexes after retention purge (call under lock)."""
        self._org_index = {}
        self._type_index = {}
        self._severity_index = {}
        self._category_index = {}

        for idx, event in enumerate(self._events):
            if event.org_id:
                self._org_index.setdefault(event.org_id, []).append(idx)
            self._type_index.setdefault(event.event_type, []).append(idx)
            self._severity_index.setdefault(event.severity, []).append(idx)
            self._category_index.setdefault(event.category, []).append(idx)

        self._sequence = self._events[-1].chain_sequence if self._events else 0
        self._prev_hash = self._events[-1].chain_hash if self._events else self.GENESIS_HASH

    def _rechain_events(self, events: list[AuditEvent]) -> list[AuditEvent]:
        """Recompute chain linkage after retention purges.

        This preserves a valid, self-consistent chain over the retained segment.
        """
        rechained: list[AuditEvent] = []
        prev_hash = self.GENESIS_HASH

        for sequence, event in enumerate(events, start=1):
            chain_hash = self._compute_hash(prev_hash, event)
            rechained.append(
                replace(
                    event,
                    chain_sequence=sequence,
                    prev_hash=prev_hash,
                    chain_hash=chain_hash,
                )
            )
            prev_hash = chain_hash

        return rechained

    @property
    def length(self) -> int:
        with self._lock:
            return len(self._events)

    @property
    def latest_hash(self) -> str:
        with self._lock:
            return self._prev_hash

    @property
    def latest_sequence(self) -> int:
        with self._lock:
            return self._sequence

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
            self._rebuild_indexes()

    @staticmethod
    def _event_from_payload(payload: dict[str, Any]) -> AuditEvent:
        return AuditEvent(
            event_id=str(payload["event_id"]),
            event_type=AuditEventType(str(payload["event_type"])),
            severity=AuditSeverity(str(payload["severity"])),
            category=str(payload["category"]),
            timestamp=datetime.fromisoformat(str(payload["timestamp"])),
            org_id=payload.get("org_id"),
            agent_id=payload.get("agent_id"),
            principal=payload.get("principal"),
            resource_type=payload.get("resource_type"),
            resource_id=payload.get("resource_id"),
            action=str(payload["action"]),
            detail=dict(payload.get("detail") or {}),
            receipt_id=payload.get("receipt_id"),
            execution_id=payload.get("execution_id"),
            provider_slug=payload.get("provider_slug"),
            chain_sequence=int(payload.get("chain_sequence", 0)),
            chain_hash=str(payload.get("chain_hash", "")),
            prev_hash=str(payload.get("prev_hash", "")),
            key_version=(
                int(payload["key_version"])
                if payload.get("key_version") is not None
                else None
            ),
        )


# ── Module-level singleton ───────────────────────────────────────────

_audit_trail: AuditTrail | None = None


def init_audit_trail(
    *,
    outbox: Any | None = None,
    replay_payloads: list[dict[str, Any]] | None = None,
) -> AuditTrail:
    """Initialize the module-level audit trail with durable replay."""
    global _audit_trail
    _audit_trail = AuditTrail(outbox=outbox)
    if replay_payloads:
        _audit_trail.load_replay_payloads(replay_payloads)
    return _audit_trail


def get_audit_trail() -> AuditTrail:
    """Return the module-level audit trail singleton."""
    global _audit_trail
    if _audit_trail is None:
        _audit_trail = AuditTrail()
    return _audit_trail
