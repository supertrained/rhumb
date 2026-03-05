"""Probe-derived alert primitives (schema drift + latency regression)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from db.repository import ProbeRepository, StoredProbe


@dataclass(frozen=True, slots=True)
class ProbeAlert:
    """Serializable alert payload for `/v1/alerts`."""

    id: str
    type: str
    severity: str
    service_slug: str
    probe_type: str
    title: str
    summary: str
    details: dict[str, object]
    detected_at: str


class ProbeAlertService:
    """Derive lightweight user-facing alerts from probe telemetry."""

    def __init__(
        self,
        repository: ProbeRepository,
        watched_services: list[str],
        latency_regression_ratio: float = 1.5,
        latency_regression_min_delta_ms: int = 75,
    ) -> None:
        self._repository = repository
        self._watched_services = watched_services
        self._latency_regression_ratio = latency_regression_ratio
        self._latency_regression_min_delta_ms = latency_regression_min_delta_ms

    @staticmethod
    def _iso(value: datetime | None) -> str:
        now = datetime.now(timezone.utc)
        if value is None:
            return now.isoformat()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()

    @staticmethod
    def _alert_id(*parts: object) -> str:
        payload = "::".join(str(part) for part in parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _schema_fingerprint(probe: StoredProbe | None) -> str | None:
        if probe is None:
            return None
        metadata = probe.probe_metadata or {}
        v2 = metadata.get("schema_fingerprint_v2")
        if isinstance(v2, str) and v2:
            return v2
        fallback = probe.response_schema_hash
        return fallback if isinstance(fallback, str) and fallback else None

    @staticmethod
    def _latency_p95(probe: StoredProbe | None) -> int | None:
        if probe is None:
            return None
        metadata = probe.probe_metadata or {}
        distribution = metadata.get("latency_distribution_ms")
        if isinstance(distribution, dict):
            p95 = distribution.get("p95")
            if p95 is not None:
                try:
                    return int(p95)
                except (TypeError, ValueError):
                    return None

        if probe.latency_ms is None:
            return None
        return int(probe.latency_ms)

    def _schema_alert(self, service_slug: str) -> ProbeAlert | None:
        recent = self._repository.list_recent_probes(
            service_slug=service_slug,
            probe_type="schema",
            limit=2,
        )
        if len(recent) < 2:
            return None

        latest, previous = recent[0], recent[1]
        latest_fp = self._schema_fingerprint(latest)
        previous_fp = self._schema_fingerprint(previous)
        if not latest_fp or not previous_fp:
            return None
        if latest_fp == previous_fp:
            return None

        detected_at = self._iso(latest.probed_at)
        return ProbeAlert(
            id=self._alert_id("schema", service_slug, latest_fp, previous_fp),
            type="schema_drift",
            severity="high",
            service_slug=service_slug,
            probe_type="schema",
            title=f"Schema drift detected for {service_slug}",
            summary="Latest schema fingerprint changed from the prior probe run.",
            details={
                "latest_fingerprint": latest_fp,
                "previous_fingerprint": previous_fp,
                "latest_probe_id": str(latest.id),
                "previous_probe_id": str(previous.id),
            },
            detected_at=detected_at,
        )

    def _latency_alert(self, service_slug: str) -> ProbeAlert | None:
        recent = self._repository.list_recent_probes(
            service_slug=service_slug,
            probe_type="health",
            limit=2,
        )
        if len(recent) < 2:
            return None

        latest, previous = recent[0], recent[1]
        latest_p95 = self._latency_p95(latest)
        previous_p95 = self._latency_p95(previous)
        if latest_p95 is None or previous_p95 is None or previous_p95 <= 0:
            return None

        ratio = latest_p95 / previous_p95
        delta = latest_p95 - previous_p95
        if ratio < self._latency_regression_ratio:
            return None
        if delta < self._latency_regression_min_delta_ms:
            return None

        detected_at = self._iso(latest.probed_at)
        return ProbeAlert(
            id=self._alert_id("latency", service_slug, latest_p95, previous_p95),
            type="latency_regression",
            severity="medium",
            service_slug=service_slug,
            probe_type="health",
            title=f"Latency regression for {service_slug}",
            summary="Probe p95 latency regressed versus the previous probe.",
            details={
                "latest_p95_ms": latest_p95,
                "previous_p95_ms": previous_p95,
                "regression_ratio": round(ratio, 2),
                "delta_ms": delta,
                "latest_probe_id": str(latest.id),
                "previous_probe_id": str(previous.id),
            },
            detected_at=detected_at,
        )

    def generate_alerts(self, limit: int = 50) -> list[ProbeAlert]:
        alerts: list[ProbeAlert] = []

        for service_slug in self._watched_services:
            schema_alert = self._schema_alert(service_slug)
            if schema_alert is not None:
                alerts.append(schema_alert)

            latency_alert = self._latency_alert(service_slug)
            if latency_alert is not None:
                alerts.append(latency_alert)

        alerts.sort(key=lambda alert: alert.detected_at, reverse=True)
        return alerts[: max(1, limit)]
