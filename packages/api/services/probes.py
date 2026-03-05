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

    @classmethod
    def _schema_descriptor(
        cls,
        value: Any,
        *,
        depth: int = 0,
        max_depth: int = 4,
        max_keys: int = 40,
        max_items: int = 10,
    ) -> dict[str, Any]:
        """Build a shape descriptor that captures nested semantic schema, not just top-level keys."""
        if depth >= max_depth:
            return {"type": "max_depth"}

        if value is None:
            return {"type": "null"}

        if isinstance(value, bool):
            return {"type": "boolean"}

        if isinstance(value, (int, float)):
            return {"type": "number"}

        if isinstance(value, str):
            return {"type": "string"}

        if isinstance(value, list):
            sampled = value[:max_items]
            item_descriptors = [
                cls._schema_descriptor(item, depth=depth + 1, max_depth=max_depth)
                for item in sampled
            ]
            unique_items = sorted(
                {
                    json.dumps(item, sort_keys=True, separators=(",", ":"))
                    for item in item_descriptors
                }
            )
            return {
                "type": "array",
                "sample_size": len(sampled),
                "item_variants": [json.loads(item) for item in unique_items[:5]],
            }

        if isinstance(value, dict):
            keys = sorted(value.keys())
            limited_keys = keys[:max_keys]
            return {
                "type": "object",
                "keys": limited_keys,
                "truncated_keys": max(0, len(keys) - len(limited_keys)),
                "properties": {
                    key: cls._schema_descriptor(
                        value[key],
                        depth=depth + 1,
                        max_depth=max_depth,
                        max_keys=max_keys,
                        max_items=max_items,
                    )
                    for key in limited_keys
                },
            }

        return {"type": type(value).__name__}

    @staticmethod
    def _hash_any(payload: Any) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _schema_fingerprint(cls, payload: Any) -> tuple[str, dict[str, Any]]:
        descriptor = cls._schema_descriptor(payload)
        return cls._hash_any(descriptor), descriptor

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
            "probe_type": probe_type,
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
                "mode": "no_target_url",
            }
            if probe_type == "auth":
                raw["expected_behavior"] = "Target should reject unauthenticated requests (401/403)"
            elif probe_type == "schema":
                raw["expected_behavior"] = "Target response schema hash should remain stable"
                schema_fingerprint, schema_descriptor = self._schema_fingerprint(raw)
                metadata["schema_signature_version"] = "v2"
                metadata["schema_fingerprint_v2"] = schema_fingerprint
                metadata["schema_descriptor"] = schema_descriptor
            latency_ms = int((perf_counter() - started) * 1000)
            distribution = self._latency_distribution([latency_ms])
            if distribution:
                metadata["latency_distribution_ms"] = distribution

            return ProbeExecutionResult(
                status="ok",
                latency_ms=latency_ms,
                response_code=200,
                response_schema_hash=(
                    metadata.get("schema_fingerprint_v2")
                    if probe_type == "schema"
                    else self._hash_any(raw)
                ),
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

        parsed_json: dict[str, Any] | list[Any] | None = None
        try:
            parsed_json = last_response.json()
        except ValueError:
            parsed_json = None

        response_payload = {
            "url": str(last_response.url),
            "headers": dict(last_response.headers),
            "text_preview": last_response.text[:500],
            "json": parsed_json,
        }

        response_schema_hash: str | None = self._hash_any(response_payload)
        if probe_type == "schema":
            schema_target = (
                parsed_json
                if parsed_json is not None
                else {"text_preview": response_payload["text_preview"]}
            )
            schema_fingerprint, schema_descriptor = self._schema_fingerprint(schema_target)
            metadata["schema_signature_version"] = "v2"
            metadata["schema_fingerprint_v2"] = schema_fingerprint
            metadata["schema_descriptor"] = schema_descriptor
            response_schema_hash = schema_fingerprint

            if isinstance(parsed_json, dict):
                metadata["schema_keys"] = sorted(parsed_json.keys())
            elif isinstance(parsed_json, list):
                metadata["schema_kind"] = "list"
            else:
                metadata["schema_kind"] = "text"

        distribution = self._latency_distribution(latencies)
        if distribution:
            metadata["latency_distribution_ms"] = distribution

        status = "ok" if last_response.is_success else "error"
        error_message = None if last_response.is_success else f"HTTP {last_response.status_code}"

        if probe_type == "auth":
            expected_codes = {401, 403}
            metadata["expected_response_codes"] = sorted(expected_codes)
            if last_response.status_code in expected_codes:
                status = "ok"
                error_message = None
            else:
                status = "error"
                error_message = (
                    f"Auth probe expected 401/403, received HTTP {last_response.status_code}"
                )

        return ProbeExecutionResult(
            status=status,
            latency_ms=self._percentile(latencies, 50),
            response_code=last_response.status_code,
            response_schema_hash=response_schema_hash,
            raw_response=response_payload,
            probe_metadata=metadata,
            error_message=error_message,
        )

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

    @property
    def repository(self) -> ProbeRepository | None:
        """Expose the configured repository for bridge integrations."""
        return self._repository

    def fetch_latest_probe(
        self, service_slug: str, probe_type: str | None = None
    ) -> StoredProbe | None:
        """Fetch the latest stored probe for a service."""
        if self._repository is None:
            return None
        return self._repository.fetch_latest_probe(service_slug=service_slug, probe_type=probe_type)

    def list_recent_probes(
        self,
        service_slug: str,
        probe_type: str | None = None,
        limit: int = 10,
    ) -> list[StoredProbe]:
        """Fetch a descending list of recent probes for a service."""
        if self._repository is None:
            return []
        return self._repository.list_recent_probes(
            service_slug=service_slug,
            probe_type=probe_type,
            limit=limit,
        )
