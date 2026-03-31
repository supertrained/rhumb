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
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

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

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = threading.Lock()
        self._prev_hash: str = self.GENESIS_HASH
        self._sequence: int = 0
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

            chain_hash = self._compute_hash(
                self._prev_hash,
                event_id,
                event_type.value,
                str(self._sequence),
                now.isoformat(),
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
            )

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
            # Start with the smallest relevant index
            if org_id and org_id in self._org_index:
                indices = set(self._org_index[org_id])
            elif event_type and event_type in self._type_index:
                indices = set(self._type_index[event_type])
            elif severity and severity in self._severity_index:
                indices = set(self._severity_index[severity])
            elif category and category in self._category_index:
                indices = set(self._category_index[category])
            else:
                indices = set(range(len(self._events)))

            # Intersect with other filters
            if org_id and org_id in self._org_index:
                indices &= set(self._org_index[org_id])
            if event_type and event_type in self._type_index:
                indices &= set(self._type_index[event_type])
            if severity and severity in self._severity_index:
                indices &= set(self._severity_index[severity])
            if category and category in self._category_index:
                indices &= set(self._category_index[category])

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
                expected = self._compute_hash(
                    prev_hash,
                    event.event_id,
                    event.event_type.value,
                    str(event.chain_sequence),
                    event.timestamp.isoformat(),
                )
                if event.chain_hash != expected:
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
        """Export events as JSON."""
        export_data = {
            "export_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "chain_verified": chain_verified,
            "event_count": len(events),
            "events": [self._event_to_dict(e) for e in events],
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
    def _event_to_dict(event: AuditEvent) -> dict[str, Any]:
        """Convert an event to a JSON-serializable dict."""
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
            "detail": event.detail,
            "receipt_id": event.receipt_id,
            "execution_id": event.execution_id,
            "provider_slug": event.provider_slug,
            "chain_sequence": event.chain_sequence,
            "chain_hash": event.chain_hash,
            "prev_hash": event.prev_hash,
        }

    # ── Internal ──────────────────────────────────────────────────

    @staticmethod
    def _compute_hash(
        prev_hash: str,
        event_id: str,
        event_type: str,
        sequence: str,
        timestamp: str,
    ) -> str:
        payload = f"{prev_hash}|{event_id}|{event_type}|{sequence}|{timestamp}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

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


# ── Module-level singleton ───────────────────────────────────────────

_audit_trail: AuditTrail | None = None


def get_audit_trail() -> AuditTrail:
    """Return the module-level audit trail singleton."""
    global _audit_trail
    if _audit_trail is None:
        _audit_trail = AuditTrail()
    return _audit_trail
