"""Schema change alert routing and deduplication pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

import httpx

from services.schema_change_detector import SchemaChange


@dataclass(frozen=True, slots=True)
class AlertRecord:
    """In-app alert record persisted for admin queries."""

    alert_id: str
    service: str
    endpoint: str
    severity: str
    change_detail: dict[str, Any]
    alert_sent_at: datetime | None
    webhook_url: str | None
    webhook_status: int | None
    retry_count: int
    retry_at: datetime | None
    created_at: datetime


class AlertDispatcher:
    """Dispatch schema alerts to webhook, email, and in-app channels."""

    def __init__(
        self,
        *,
        webhook_timeout_seconds: float = 3.0,
        dedupe_window_hours: int = 24,
    ) -> None:
        self._webhook_timeout = webhook_timeout_seconds
        self._dedupe_window = timedelta(hours=dedupe_window_hours)
        self._alerts: list[AlertRecord] = []
        self._dedupe_index: dict[str, tuple[datetime, str]] = {}
        self._email_log: list[dict[str, Any]] = []

    @staticmethod
    def _severity_rank(severity: str) -> int:
        ranks = {"advisory": 0, "non_breaking": 1, "breaking": 2}
        return ranks.get(severity, 0)

    def _dedupe_key(
        self,
        service: str,
        endpoint: str,
        changes: tuple[SchemaChange, ...],
    ) -> str:
        normalized = "|".join(
            sorted(
                f"{change.change_type}:{change.path}:{change.old_type}:{change.new_type}"
                for change in changes
            )
        )
        payload = f"{service}:{endpoint}:{normalized}"
        return sha256(payload.encode("utf-8")).hexdigest()

    async def dispatch(
        self,
        *,
        service: str,
        endpoint: str,
        changes: tuple[SchemaChange, ...],
        webhook_url: str | None = None,
        webhook_token: str | None = None,
        alert_mode: str = "breaking_only",
    ) -> dict[str, Any]:
        """Route alert across destinations with dedupe and retries."""
        highest_severity = self._highest_severity(changes)
        if highest_severity == "advisory":
            return {"status": "skipped", "reason": "advisory_only"}

        if highest_severity == "non_breaking" and alert_mode != "all":
            return {"status": "skipped", "reason": "non_breaking_filtered"}

        dedupe_key = self._dedupe_key(service, endpoint, changes)
        now = datetime.now(tz=UTC)
        existing = self._dedupe_index.get(dedupe_key)
        if existing is not None:
            last_sent_at, previous_severity = existing
            if now - last_sent_at < self._dedupe_window:
                if self._severity_rank(highest_severity) <= self._severity_rank(previous_severity):
                    return {"status": "deduped"}

        payload = self._build_payload(service, endpoint, changes, highest_severity, now)
        webhook_result = await self.webhook_dispatch(
            payload=payload,
            webhook_url=webhook_url,
            webhook_token=webhook_token,
        )
        email_result = self.email_dispatch(
            service=service,
            endpoint=endpoint,
            severity=highest_severity,
        )
        inapp_record = self.inapp_dispatch(
            service=service,
            endpoint=endpoint,
            severity=highest_severity,
            change_detail=payload,
            webhook_url=webhook_url,
            webhook_status=webhook_result["status_code"],
            retry_count=webhook_result["retry_count"],
            retry_at=webhook_result["retry_at"],
            sent=webhook_result["sent"],
        )

        self._dedupe_index[dedupe_key] = (now, highest_severity)

        return {
            "status": "sent" if webhook_result["sent"] else "pending",
            "payload": payload,
            "webhook": webhook_result,
            "email": email_result,
            "alert_id": inapp_record.alert_id,
        }

    @staticmethod
    def _highest_severity(changes: tuple[SchemaChange, ...]) -> str:
        severities = [change.severity for change in changes]
        if "breaking" in severities:
            return "breaking"
        if "non_breaking" in severities:
            return "non_breaking"
        return "advisory"

    @staticmethod
    def _build_payload(
        service: str,
        endpoint: str,
        changes: tuple[SchemaChange, ...],
        severity: str,
        timestamp: datetime,
    ) -> dict[str, Any]:
        return {
            "service": service,
            "endpoint": endpoint,
            "severity": severity,
            "timestamp": timestamp.isoformat(),
            "changes": [
                {
                    "change_type": change.change_type,
                    "path": change.path,
                    "old_type": change.old_type,
                    "new_type": change.new_type,
                    "detail": change.detail,
                    "similarity": change.similarity,
                    "severity": change.severity,
                }
                for change in changes
            ],
        }

    async def webhook_dispatch(
        self,
        *,
        payload: dict[str, Any],
        webhook_url: str | None,
        webhook_token: str | None,
    ) -> dict[str, Any]:
        """POST alert payload to operator webhook with retry scheduling."""
        if not webhook_url:
            return {
                "sent": False,
                "status_code": None,
                "retry_count": 0,
                "retry_at": None,
            }

        headers = {"Content-Type": "application/json"}
        if webhook_token:
            headers["Authorization"] = f"Bearer {webhook_token}"

        try:
            async with httpx.AsyncClient(timeout=self._webhook_timeout) as client:
                response = await client.post(webhook_url, json=payload, headers=headers)
            if 200 <= response.status_code < 300:
                return {
                    "sent": True,
                    "status_code": int(response.status_code),
                    "retry_count": 0,
                    "retry_at": None,
                }

            retry_count = 1
            retry_at = self._compute_retry_at(retry_count)
            return {
                "sent": False,
                "status_code": int(response.status_code),
                "retry_count": retry_count,
                "retry_at": retry_at,
            }
        except Exception:
            retry_count = 1
            retry_at = self._compute_retry_at(retry_count)
            return {
                "sent": False,
                "status_code": 500,
                "retry_count": retry_count,
                "retry_at": retry_at,
            }

    def email_dispatch(self, *, service: str, endpoint: str, severity: str) -> dict[str, Any]:
        """Mock email/Slack dispatch for Phase 2."""
        record = {
            "service": service,
            "endpoint": endpoint,
            "severity": severity,
            "recipient": "operators@rhumb.dev",
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        self._email_log.append(record)
        return {"sent": True, "recipient": record["recipient"]}

    def inapp_dispatch(
        self,
        *,
        service: str,
        endpoint: str,
        severity: str,
        change_detail: dict[str, Any],
        webhook_url: str | None,
        webhook_status: int | None,
        retry_count: int,
        retry_at: datetime | None,
        sent: bool,
    ) -> AlertRecord:
        """Persist in-app alert record."""
        now = datetime.now(tz=UTC)
        digest = sha256(f"{service}:{endpoint}:{now.timestamp()}".encode("utf-8")).hexdigest()[:16]
        record = AlertRecord(
            alert_id=digest,
            service=service,
            endpoint=endpoint,
            severity=severity,
            change_detail=change_detail,
            alert_sent_at=now if sent else None,
            webhook_url=webhook_url,
            webhook_status=webhook_status,
            retry_count=retry_count,
            retry_at=retry_at,
            created_at=now,
        )
        self._alerts.append(record)
        return record

    def _compute_retry_at(self, retry_count: int) -> datetime:
        delay_seconds = min(3600, 60 * (2 ** max(0, retry_count - 1)))
        return datetime.now(tz=UTC) + timedelta(seconds=delay_seconds)

    def query_alerts(
        self,
        *,
        service: str | None = None,
        severity: str | None = None,
        limit: int = 10,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[AlertRecord]:
        """Query recent in-app schema alerts."""
        filtered = self._alerts
        if service:
            filtered = [record for record in filtered if record.service == service]
        if severity:
            filtered = [record for record in filtered if record.severity == severity]
        if start:
            filtered = [record for record in filtered if record.created_at >= start]
        if end:
            filtered = [record for record in filtered if record.created_at <= end]

        filtered = sorted(filtered, key=lambda item: item.created_at, reverse=True)
        return filtered[: max(1, limit)]

    def backdate_dedupe_for_test(
        self,
        service: str,
        endpoint: str,
        changes: tuple[SchemaChange, ...],
        *,
        hours_ago: int,
        severity: str,
    ) -> None:
        """Backdate dedupe index (test helper)."""
        key = self._dedupe_key(service, endpoint, changes)
        self._dedupe_index[key] = (
            datetime.now(tz=UTC) - timedelta(hours=hours_ago),
            severity,
        )


_dispatcher_singleton: AlertDispatcher | None = None


def get_alert_dispatcher() -> AlertDispatcher:
    """Return singleton alert dispatcher."""
    global _dispatcher_singleton
    if _dispatcher_singleton is None:
        _dispatcher_singleton = AlertDispatcher()
    return _dispatcher_singleton


def reset_alert_dispatcher() -> None:
    """Reset singleton dispatcher for tests."""
    global _dispatcher_singleton
    _dispatcher_singleton = None


async def dispatch_async(*, dispatcher: AlertDispatcher, kwargs: dict[str, Any]) -> None:
    """Background helper for fire-and-forget dispatch."""
    await dispatcher.dispatch(**kwargs)


def schedule_dispatch(dispatcher: AlertDispatcher, kwargs: dict[str, Any]) -> None:
    """Schedule async dispatch without blocking caller."""
    asyncio.create_task(dispatch_async(dispatcher=dispatcher, kwargs=kwargs))
