"""Probe runner scaffold and persistence integration."""

from __future__ import annotations

import hashlib
import json
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

    async def _execute_probe(
        self,
        service_slug: str,
        probe_type: str,
        target_url: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ProbeExecutionResult:
        started = perf_counter()
        metadata: dict[str, Any] = {"runner": "scaffold", "service_slug": service_slug}
        if payload:
            metadata["payload_keys"] = sorted(payload.keys())

        if not target_url:
            raw = {
                "message": "Probe runner scaffold executed",
                "service_slug": service_slug,
                "probe_type": probe_type,
            }
            latency_ms = int((perf_counter() - started) * 1000)
            return ProbeExecutionResult(
                status="ok",
                latency_ms=latency_ms,
                response_code=200,
                response_schema_hash=self._hash_payload(raw),
                raw_response=raw,
                probe_metadata=metadata,
            )

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(target_url)
        except httpx.HTTPError as exc:
            latency_ms = int((perf_counter() - started) * 1000)
            metadata["target_url"] = target_url
            return ProbeExecutionResult(
                status="error",
                latency_ms=latency_ms,
                response_code=None,
                response_schema_hash=None,
                raw_response={"error": str(exc)},
                probe_metadata=metadata,
                error_message=str(exc),
            )

        response_payload = {
            "url": str(response.url),
            "headers": dict(response.headers),
            "text_preview": response.text[:500],
        }
        metadata["target_url"] = target_url

        latency_ms = int((perf_counter() - started) * 1000)
        status = "ok" if response.is_success else "error"
        return ProbeExecutionResult(
            status=status,
            latency_ms=latency_ms,
            response_code=response.status_code,
            response_schema_hash=self._hash_payload(response_payload),
            raw_response=response_payload,
            probe_metadata=metadata,
            error_message=None if response.is_success else f"HTTP {response.status_code}",
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
    ) -> StoredProbe | None:
        execution = await self._execute_probe(
            service_slug=service_slug,
            probe_type=probe_type,
            target_url=target_url,
            payload=payload,
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
