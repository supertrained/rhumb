"""Scheduler entrypoint for recurring probe runs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Sequence

from services.probes import ProbeService

MIN_INTERVAL_MINUTES = 5
MAX_INTERVAL_MINUTES = 24 * 60
MAX_BACKOFF_POWER = 3
MAX_JITTER_SHARE = 0.1


@dataclass(frozen=True, slots=True)
class ProbeSpec:
    """Declarative probe specification for a service."""

    service_slug: str
    probe_type: str = "health"
    target_url: str | None = None
    payload: dict[str, Any] | None = None


DEFAULT_PROBE_SPECS: tuple[ProbeSpec, ...] = (
    ProbeSpec(
        service_slug="stripe",
        probe_type="health",
        target_url="https://status.stripe.com/api/v2/status.json",
    ),
    ProbeSpec(
        service_slug="openai",
        probe_type="health",
        target_url="https://status.openai.com/api/v2/status.json",
    ),
    ProbeSpec(
        service_slug="hubspot",
        probe_type="health",
        target_url="https://status.hubspot.com/api/v2/status.json",
    ),
)


@dataclass(frozen=True, slots=True)
class ProbeCadenceDecision:
    """Cadence policy output for a service after probe execution."""

    base_interval_minutes: int
    next_interval_minutes: int
    consecutive_failures: int
    jitter_seconds: int


@dataclass(slots=True)
class ProbeBatchRunSummary:
    """Execution summary for a scheduler-triggered probe batch."""

    total_specs: int
    selected_services: list[str]
    executed: int
    succeeded: int
    failed: int
    probe_ids: list[str]
    by_service: dict[str, str]
    cadence_by_service: dict[str, dict[str, int]]


class ProbeScheduler:
    """Runs probe specs in a deterministic batch for cron/scheduler integration."""

    def __init__(
        self,
        probe_service: ProbeService,
        specs: Sequence[ProbeSpec] | None = None,
    ) -> None:
        self._probe_service = probe_service
        self._specs = tuple(specs or DEFAULT_PROBE_SPECS)

    @staticmethod
    def _normalize_interval_minutes(interval_minutes: int) -> int:
        return max(MIN_INTERVAL_MINUTES, min(MAX_INTERVAL_MINUTES, int(interval_minutes)))

    @classmethod
    def _deterministic_jitter_seconds(cls, service_slug: str, interval_minutes: int) -> int:
        max_jitter = int(interval_minutes * 60 * MAX_JITTER_SHARE)
        if max_jitter <= 0:
            return 0

        digest = hashlib.sha256(service_slug.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % (max_jitter + 1)

    @classmethod
    def _decision_from_failure_count(
        cls,
        service_slug: str,
        base_interval_minutes: int,
        consecutive_failures: int,
    ) -> ProbeCadenceDecision:
        normalized_base = cls._normalize_interval_minutes(base_interval_minutes)
        bounded_failures = max(0, int(consecutive_failures))
        backoff_multiplier = 2 ** min(bounded_failures, MAX_BACKOFF_POWER)
        next_interval = cls._normalize_interval_minutes(normalized_base * backoff_multiplier)

        return ProbeCadenceDecision(
            base_interval_minutes=normalized_base,
            next_interval_minutes=next_interval,
            consecutive_failures=bounded_failures,
            jitter_seconds=cls._deterministic_jitter_seconds(service_slug, next_interval),
        )

    def _consecutive_failures(self, service_slug: str, probe_type: str) -> int:
        recent = self._probe_service.list_recent_probes(
            service_slug=service_slug,
            probe_type=probe_type,
            limit=6,
        )
        failures = 0
        for probe in recent:
            if probe.status == "ok":
                break
            failures += 1
        return failures

    def list_specs(self, service_slugs: list[str] | None = None) -> list[ProbeSpec]:
        """Return selected probe specs, optionally filtered by service slug."""
        if service_slugs:
            allowed = set(service_slugs)
            candidate = [spec for spec in self._specs if spec.service_slug in allowed]
        else:
            candidate = list(self._specs)

        selected: list[ProbeSpec] = []
        seen_services: set[str] = set()
        for spec in candidate:
            if spec.service_slug in seen_services:
                continue
            seen_services.add(spec.service_slug)
            selected.append(spec)

        return selected

    def preview_cadence(
        self,
        selected_specs: Sequence[ProbeSpec],
        base_interval_minutes: int,
    ) -> dict[str, dict[str, int]]:
        """Compute cadence decisions without executing probes."""
        cadence_by_service: dict[str, dict[str, int]] = {}
        for spec in selected_specs:
            failure_count = self._consecutive_failures(spec.service_slug, spec.probe_type)
            cadence = self._decision_from_failure_count(
                spec.service_slug,
                base_interval_minutes,
                consecutive_failures=failure_count,
            )
            cadence_by_service[spec.service_slug] = {
                "base_interval_minutes": cadence.base_interval_minutes,
                "next_interval_minutes": cadence.next_interval_minutes,
                "consecutive_failures": cadence.consecutive_failures,
                "jitter_seconds": cadence.jitter_seconds,
            }
        return cadence_by_service

    async def run_once(
        self,
        service_slugs: list[str] | None = None,
        sample_count: int = 3,
        base_interval_minutes: int = 30,
    ) -> ProbeBatchRunSummary:
        """Execute one scheduler batch and return a summary payload."""
        selected = self.list_specs(service_slugs=service_slugs)

        succeeded = 0
        failed = 0
        executed = 0
        probe_ids: list[str] = []
        by_service: dict[str, str] = {}
        cadence_by_service: dict[str, dict[str, int]] = {}

        for spec in selected:
            stored = await self._probe_service.run_probe(
                service_slug=spec.service_slug,
                probe_type=spec.probe_type,
                target_url=spec.target_url,
                payload=spec.payload,
                trigger_source="scheduler",
                sample_count=sample_count,
            )
            executed += 1

            if stored is None:
                failed += 1
                by_service[spec.service_slug] = "not_persisted"
                cadence = self._decision_from_failure_count(
                    spec.service_slug,
                    base_interval_minutes,
                    consecutive_failures=1,
                )
                cadence_by_service[spec.service_slug] = {
                    "base_interval_minutes": cadence.base_interval_minutes,
                    "next_interval_minutes": cadence.next_interval_minutes,
                    "consecutive_failures": cadence.consecutive_failures,
                    "jitter_seconds": cadence.jitter_seconds,
                }
                continue

            probe_ids.append(str(stored.id))
            by_service[spec.service_slug] = stored.status

            if stored.status == "ok":
                succeeded += 1
            else:
                failed += 1

            failure_count = self._consecutive_failures(spec.service_slug, spec.probe_type)
            cadence = self._decision_from_failure_count(
                spec.service_slug,
                base_interval_minutes,
                consecutive_failures=failure_count,
            )
            cadence_by_service[spec.service_slug] = {
                "base_interval_minutes": cadence.base_interval_minutes,
                "next_interval_minutes": cadence.next_interval_minutes,
                "consecutive_failures": cadence.consecutive_failures,
                "jitter_seconds": cadence.jitter_seconds,
            }

        return ProbeBatchRunSummary(
            total_specs=len(self._specs),
            selected_services=[spec.service_slug for spec in selected],
            executed=executed,
            succeeded=succeeded,
            failed=failed,
            probe_ids=probe_ids,
            by_service=by_service,
            cadence_by_service=cadence_by_service,
        )
