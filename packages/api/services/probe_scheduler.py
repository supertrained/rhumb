"""Scheduler entrypoint for recurring probe runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from services.probes import ProbeService


@dataclass(frozen=True, slots=True)
class ProbeSpec:
    """Declarative probe specification for a service."""

    service_slug: str
    probe_type: str = "health"
    target_url: str | None = None
    payload: dict[str, Any] | None = None


DEFAULT_PROBE_SPECS: tuple[ProbeSpec, ...] = (
    ProbeSpec(service_slug="stripe", probe_type="health", target_url="https://status.stripe.com/api/v2/status.json"),
    ProbeSpec(service_slug="openai", probe_type="health", target_url="https://status.openai.com/api/v2/status.json"),
    ProbeSpec(service_slug="hubspot", probe_type="health", target_url="https://status.hubspot.com/api/v2/status.json"),
)


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


class ProbeScheduler:
    """Runs probe specs in a deterministic batch for cron/scheduler integration."""

    def __init__(
        self,
        probe_service: ProbeService,
        specs: Sequence[ProbeSpec] | None = None,
    ) -> None:
        self._probe_service = probe_service
        self._specs = tuple(specs or DEFAULT_PROBE_SPECS)

    def list_specs(self, service_slugs: list[str] | None = None) -> list[ProbeSpec]:
        """Return selected probe specs, optionally filtered by service slug."""
        if not service_slugs:
            return list(self._specs)

        allowed = set(service_slugs)
        return [spec for spec in self._specs if spec.service_slug in allowed]

    async def run_once(
        self,
        service_slugs: list[str] | None = None,
        sample_count: int = 3,
    ) -> ProbeBatchRunSummary:
        """Execute one scheduler batch and return a summary payload."""
        selected = self.list_specs(service_slugs=service_slugs)

        succeeded = 0
        failed = 0
        executed = 0
        probe_ids: list[str] = []
        by_service: dict[str, str] = {}

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
                continue

            probe_ids.append(str(stored.id))
            by_service[spec.service_slug] = stored.status

            if stored.status == "ok":
                succeeded += 1
            else:
                failed += 1

        return ProbeBatchRunSummary(
            total_specs=len(self._specs),
            selected_services=[spec.service_slug for spec in selected],
            executed=executed,
            succeeded=succeeded,
            failed=failed,
            probe_ids=probe_ids,
            by_service=by_service,
        )
