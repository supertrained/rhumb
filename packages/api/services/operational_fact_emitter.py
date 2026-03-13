"""Operational fact emitter for runtime-verified proxy evidence."""

from __future__ import annotations

import asyncio
import logging
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any, Coroutine, Mapping, Optional

from services.usage_metering import MeteredUsageEvent

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "access_operational_fact_v1"
SOURCE_TYPE = "runtime_verified"
INGRESS_CHANNEL = "access_proxy"
COUNTABILITY_HINT = "countable_as_evidence_now"

LATENCY_EVENT_TYPE = "proxy_call_completed"
CIRCUIT_EVENT_TYPES = frozenset(
    {
        "circuit_opened",
        "circuit_half_opened",
        "circuit_closed",
    }
)
CREDENTIAL_EVENT_TYPES = frozenset(
    {
        "credential_injected",
        "credential_missing",
        "credential_lookup_failed",
        "credential_rejected_by_provider",
    }
)


def _environment_name() -> str:
    env = os.environ.get("RHUMB_ENV", "").strip().lower()
    if env == "production":
        return "production"
    if env == "staging":
        return "staging"
    return "local_test"


def _compact_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


class OperationalFactEmitter:
    """Emit operational fact packets to ``access_operational_facts``."""

    def __init__(self, supabase_client: Any = None) -> None:
        self._supabase = supabase_client
        self._emitted = 0
        self._failed = 0
        self._dropped = 0
        self._unavailable = 0
        self._by_fact_type: Counter[str] = Counter()

    @property
    def supabase(self) -> Any:
        return self._supabase

    @supabase.setter
    def supabase(self, value: Any) -> None:
        self._supabase = value

    async def emit_latency_snapshot(
        self,
        *,
        event: MeteredUsageEvent,
        path: str,
        upstream_latency_ms: float,
        response_parse_ms: float,
        schema_detect_ms: float,
        build_event_ms: float,
        persist_ms: float,
        identity_touch_ms: float,
        total_worker_ms: float,
        queue_depth: int,
        finalizer_mode: str,
    ) -> bool:
        observed_at = event.created_at
        payload = _compact_payload(
            {
                "path": path,
                "result": event.result,
                "upstream_latency_ms": upstream_latency_ms,
                "response_parse_ms": response_parse_ms,
                "schema_detect_ms": schema_detect_ms,
                "build_event_ms": build_event_ms,
                "persist_ms": persist_ms,
                "identity_touch_ms": identity_touch_ms,
                "total_worker_ms": total_worker_ms,
                "queue_depth": queue_depth,
                "finalizer_mode": finalizer_mode,
            }
        )
        packet = self._base_packet(
            fact_type="latency_snapshot",
            service_slug=event.service,
            provider_slug=event.service,
            agent_id=event.agent_id,
            event_type=LATENCY_EVENT_TYPE,
            observed_at=observed_at,
            confidence=0.95,
            fresh_until=observed_at + timedelta(minutes=10),
            payload=payload,
        )
        return await self._insert_packet(packet)

    async def emit_circuit_state(
        self,
        *,
        service: str,
        agent_id: str | None,
        event_type: str,
        new_state: str,
        failure_threshold: int,
        timeout_threshold_ms: float,
        cooldown_seconds: float,
        metrics: Mapping[str, Any],
    ) -> bool:
        if event_type not in CIRCUIT_EVENT_TYPES:
            raise ValueError(f"Unsupported circuit_state event_type: {event_type}")

        observed_at = datetime.now(tz=UTC)
        payload = _compact_payload(
            {
                "new_state": new_state,
                "failure_threshold": failure_threshold,
                "timeout_threshold_ms": timeout_threshold_ms,
                "cooldown_seconds": cooldown_seconds,
                **dict(metrics),
            }
        )
        packet = self._base_packet(
            fact_type="circuit_state",
            service_slug=service,
            provider_slug=service,
            agent_id=agent_id,
            event_type=event_type,
            observed_at=observed_at,
            confidence=0.98,
            fresh_until=observed_at + timedelta(minutes=30),
            payload=payload,
        )
        return await self._insert_packet(packet)

    async def emit_credential_lifecycle(
        self,
        *,
        service: str,
        agent_id: str | None,
        event_type: str,
        auth_method: str,
        outcome: str,
        header_name: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        notes: str | None = None,
    ) -> bool:
        if event_type not in CREDENTIAL_EVENT_TYPES:
            raise ValueError(f"Unsupported credential_lifecycle event_type: {event_type}")

        observed_at = datetime.now(tz=UTC)
        payload = _compact_payload(
            {
                "auth_method": auth_method,
                "header_name": header_name,
                "outcome": outcome,
                "error_type": error_type,
                "error_message": error_message,
            }
        )
        packet = self._base_packet(
            fact_type="credential_lifecycle",
            service_slug=service,
            provider_slug=service,
            agent_id=agent_id,
            event_type=event_type,
            observed_at=observed_at,
            confidence=0.96,
            fresh_until=observed_at + timedelta(hours=24),
            payload=payload,
            notes=notes,
        )
        return await self._insert_packet(packet)

    def schedule_latency_snapshot(self, **kwargs: Any) -> None:
        self._schedule(self.emit_latency_snapshot(**kwargs), fact_type="latency_snapshot")

    def schedule_circuit_state(self, **kwargs: Any) -> None:
        self._schedule(self.emit_circuit_state(**kwargs), fact_type="circuit_state")

    def schedule_credential_lifecycle(self, **kwargs: Any) -> None:
        self._schedule(
            self.emit_credential_lifecycle(**kwargs),
            fact_type="credential_lifecycle",
        )

    def get_stats(self) -> dict[str, Any]:
        return {
            "emitted": self._emitted,
            "failed": self._failed,
            "dropped": self._dropped,
            "unavailable": self._unavailable,
            "by_fact_type": dict(self._by_fact_type),
        }

    def _schedule(self, coro: Coroutine[Any, Any, bool], *, fact_type: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._dropped += 1
            logger.warning(
                "operational_fact_emitter: no running loop, dropping fact_type=%s",
                fact_type,
            )
            coro.close()
            return

        loop.create_task(self._run_safely(coro))

    async def _run_safely(self, coro: Coroutine[Any, Any, bool]) -> None:
        try:
            await coro
        except Exception:
            logger.warning("operational_fact_emitter: scheduled emit failed", exc_info=True)

    def _base_packet(
        self,
        *,
        fact_type: str,
        service_slug: str,
        provider_slug: str,
        agent_id: str | None,
        event_type: str,
        observed_at: datetime,
        confidence: float,
        fresh_until: datetime,
        payload: Mapping[str, Any],
        notes: str | None = None,
    ) -> dict[str, Any]:
        timestamp = observed_at.astimezone(UTC)
        return {
            "schema_version": SCHEMA_VERSION,
            "fact_type": fact_type,
            "service_slug": service_slug,
            "provider_slug": provider_slug,
            "agent_id": agent_id,
            "run_id": None,
            "event_type": event_type,
            "observed_at": timestamp.isoformat(),
            "environment": _environment_name(),
            "source_type": SOURCE_TYPE,
            "confidence": confidence,
            "fresh_until": fresh_until.astimezone(UTC).isoformat(),
            "artifact_ref": None,
            "notes": notes,
            "payload": dict(payload),
            "ingress_channel": INGRESS_CHANNEL,
            "raw_packet": None,
            "countability_hint": COUNTABILITY_HINT,
        }

    async def _insert_packet(self, packet: Mapping[str, Any]) -> bool:
        fact_type = str(packet["fact_type"])
        if self._supabase is None:
            self._dropped += 1
            self._unavailable += 1
            logger.warning(
                "operational_fact_emitter: supabase unavailable, dropping fact_type=%s",
                fact_type,
            )
            return False

        try:
            await self._supabase.table("access_operational_facts").insert(dict(packet)).execute()
        except Exception:
            self._failed += 1
            logger.warning(
                "operational_fact_emitter: failed to insert fact_type=%s",
                fact_type,
                exc_info=True,
            )
            return False

        self._emitted += 1
        self._by_fact_type[fact_type] += 1
        return True


_operational_fact_emitter: Optional[OperationalFactEmitter] = None


def get_operational_fact_emitter(
    supabase_client: Any | None = None,
) -> OperationalFactEmitter:
    """Get or create the global operational fact emitter singleton."""
    global _operational_fact_emitter
    if _operational_fact_emitter is None:
        _operational_fact_emitter = OperationalFactEmitter(supabase_client=supabase_client)
    elif supabase_client is not None:
        _operational_fact_emitter.supabase = supabase_client
    return _operational_fact_emitter


def reset_operational_fact_emitter() -> None:
    """Reset the global operational fact emitter singleton."""
    global _operational_fact_emitter
    _operational_fact_emitter = None
