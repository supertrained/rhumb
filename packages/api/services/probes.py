"""Probe runner scaffold and persistence integration."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx

from db.repository import ProbeRepository, StoredProbe


@dataclass(slots=True)
class ProbeExecutionResult:
    """Result returned by the lightweight probe runner scaffold."""

    status: str
    latency_ms: int | None
    response_code: int | None
    response_schema_hash: str | None
    raw_response: dict[str, Any] | None
    probe_metadata: dict[str, Any] | None
    error_message: str | None = None


class ProbeService:
    """Service object that executes probes and stores the latest result."""

    def __init__(self, repository: ProbeRepository | None = None) -> None:
        self._repository = repository

    @staticmethod
    def _percentile(latencies: list[int], percentile: int) -> int | None:
        if not latencies:
            return None

        sorted_latencies = sorted(latencies)
        rank = max(1, math.ceil((percentile / 100) * len(sorted_latencies)))
        index = min(len(sorted_latencies) - 1, rank - 1)
        return sorted_latencies[index]

    @classmethod
    def _latency_distribution(cls, latencies: list[int]) -> dict[str, int] | None:
        if not latencies:
            return None

        p50 = cls._percentile(latencies, 50)
        p95 = cls._percentile(latencies, 95)
        p99 = cls._percentile(latencies, 99)
        if p50 is None or p95 is None or p99 is None:
            return None

        return {
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "samples": len(latencies),
        }

    async def _execute_probe(
        self,
        service_slug: str,
        probe_type: str,
        target_url: str | None = None,
        payload: dict[str, Any] | None = None,
        sample_count: int = 1,
    ) -> ProbeExecutionResult:
        sample_count = max(1, sample_count)
        metadata: dict[str, Any] = {
            "runner": "scaffold",
            "service_slug": service_slug,
            "sample_count": sample_count,
        }
        if payload:
            metadata["payload_keys"] = sorted(payload.keys())

        if not target_url:
            started = perf_counter()
            raw = {
                "message": "Probe runner scaffold executed",
                "service_slug": service_slug,
                "probe_type": probe_type,
            }
            latency_ms = int((perf_counter() - started) * 1000)
            distribution = self._latency_distribution([latency_ms])
            if distribution:
                metadata["latency_distribution_ms"] = distribution

            return ProbeExecutionResult(
                status="ok",
                latency_ms=latency_ms,
                response_code=200,
                response_schema_hash=self._hash_payload(raw),
                raw_response=raw,
                probe_metadata=metadata,
            )

        metadata["target_url"] = target_url
        latencies: list[int] = []
        last_response: httpx.Response | None = None
        last_error: str | None = None

        async with httpx.AsyncClient(timeout=8.0) as client:
            for _ in range(sample_count):
                attempt_started = perf_counter()
                try:
                    response = await client.get(target_url)
                except httpx.HTTPError as exc:
                    last_error = str(exc)
                    metadata["attempts_completed"] = len(latencies)
                    distribution = self._latency_distribution(latencies)
                    if distribution:
                        metadata["latency_distribution_ms"] = distribution

                    return ProbeExecutionResult(
                        status="error",
                        latency_ms=self._percentile(latencies, 50),
                        response_code=None,
                        response_schema_hash=None,
                        raw_response={"error": last_error},
                        probe_metadata=metadata,
                        error_message=last_error,
                    )

                latencies.append(int((perf_counter() - attempt_started) * 1000))
                last_response = response

        if last_response is None:
            return ProbeExecutionResult(
                status="error",
                latency_ms=None,
                response_code=None,
                response_schema_hash=None,
                raw_response={"error": "Probe returned no response"},
                probe_metadata=metadata,
                error_message="Probe returned no response",
            )

        response_payload = {
            "url": str(last_response.url),
            "headers": dict(last_response.headers),
            "text_preview": last_response.text[:500],
        }

        distribution = self._latency_distribution(latencies)
        if distribution:
            metadata["latency_distribution_ms"] = distribution

        status = "ok" if last_response.is_success else "error"
        return ProbeExecutionResult(
            status=status,
            latency_ms=self._percentile(latencies, 50),
            response_code=last_response.status_code,
            response_schema_hash=self._hash_payload(response_payload),
            raw_response=response_payload,
            probe_metadata=metadata,
            error_message=None if last_response.is_success else f"HTTP {last_response.status_code}",
        )

    @staticmethod
    def _hash_payload(payload: dict[str, Any] | None) -> str | None:
        if payload is None:
            return None
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    async def run_probe(
        self,
        service_slug: str,
        probe_type: str = "health",
        target_url: str | None = None,
        payload: dict[str, Any] | None = None,
        trigger_source: str = "internal",
        sample_count: int = 1,
    ) -> StoredProbe | None:
        execution = await self._execute_probe(
            service_slug=service_slug,
            probe_type=probe_type,
            target_url=target_url,
            payload=payload,
            sample_count=sample_count,
        )

        if self._repository is None:
            return None

        return self._repository.save_probe(
            service_slug=service_slug,
            probe_type=probe_type,
            status=execution.status,
            latency_ms=execution.latency_ms,
            response_code=execution.response_code,
            response_schema_hash=execution.response_schema_hash,
            raw_response=execution.raw_response,
            probe_metadata=execution.probe_metadata,
            trigger_source=trigger_source,
            runner_version="scaffold-v1",
            error_message=execution.error_message,
        )

    def fetch_latest_probe(self, service_slug: str, probe_type: str | None = None) -> StoredProbe | None:
        """Fetch the latest stored probe for a service."""
        if self._repository is None:
            return None
        return self._repository.fetch_latest_probe(service_slug=service_slug, probe_type=probe_type)
