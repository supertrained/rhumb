"""Parser and runner utilities for tester fleet battery YAML definitions."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
import yaml
from pydantic import ValidationError

from db.repository import ProbeRepository, StoredProbe
from schemas.tester_fleet import (
    BatteryDefinition,
    BatteryRunArtifact,
    BatteryRunSummary,
    BatteryStepResult,
    HttpBatteryStep,
    SchemaCaptureBatteryStep,
)
from services.probes import ProbeService
from services.service_slugs import public_service_slug


class BatteryParseError(ValueError):
    """Raised when a battery definition cannot be parsed or validated."""


def _normalize_service_slug(service_slug: str | None) -> str | None:
    normalized = public_service_slug(service_slug)
    if normalized is not None:
        return normalized
    cleaned = str(service_slug or "").strip().lower()
    return cleaned or None


@dataclass(slots=True)
class _StepExecutionState:
    """Internal execution context retained for downstream dependent steps."""

    schema_target: Any | None = None


def parse_battery_yaml(raw_yaml: str) -> BatteryDefinition:
    """Parse and validate a tester fleet battery definition from YAML text."""
    try:
        payload = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise BatteryParseError(f"Invalid YAML syntax: {exc}") from exc

    if payload is None:
        raise BatteryParseError("Battery YAML is empty")

    if not isinstance(payload, dict):
        raise BatteryParseError("Battery YAML root must be an object")

    return _validate_payload(payload)


def load_battery_file(path: str | Path) -> BatteryDefinition:
    """Read, parse, and validate a battery YAML file from disk."""
    file_path = Path(path)
    try:
        raw_yaml = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BatteryParseError(f"Unable to read battery file '{file_path}': {exc}") from exc

    return parse_battery_yaml(raw_yaml)


class BatteryRunner:
    """Single-target battery runner for `http` + `schema_capture` steps (Slice B)."""

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self._client = client

    @staticmethod
    def _percentile(latencies: list[int], percentile: int) -> int | None:
        if not latencies:
            return None

        sorted_latencies = sorted(latencies)
        rank = max(1, math.ceil((percentile / 100) * len(sorted_latencies)))
        index = min(len(sorted_latencies) - 1, rank - 1)
        return sorted_latencies[index]

    @staticmethod
    def _schema_target_from_response(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"text_preview": response.text[:500]}

    def _run_http_step(
        self,
        step: HttpBatteryStep,
        *,
        client: httpx.Client,
    ) -> tuple[BatteryStepResult, _StepExecutionState]:
        last_latency_ms: int | None = None
        max_attempts = step.retries + 1

        for attempt in range(1, max_attempts + 1):
            started = perf_counter()
            try:
                response = client.request(
                    method=step.method,
                    url=step.url,
                    timeout=step.timeout_ms / 1000,
                )
            except httpx.HTTPError as exc:
                last_latency_ms = int((perf_counter() - started) * 1000)
                if attempt < max_attempts:
                    continue

                return (
                    BatteryStepResult(
                        id=step.id,
                        kind=step.kind,
                        status="error",
                        latency_ms=last_latency_ms,
                        response_code=None,
                        error=f"HTTP request failed: {exc}",
                        metadata={"attempts": attempt, "retries": step.retries},
                    ),
                    _StepExecutionState(schema_target=None),
                )

            last_latency_ms = int((perf_counter() - started) * 1000)
            schema_target = self._schema_target_from_response(response)

            if response.status_code in step.expect_status:
                return (
                    BatteryStepResult(
                        id=step.id,
                        kind=step.kind,
                        status="ok",
                        latency_ms=last_latency_ms,
                        response_code=response.status_code,
                        error=None,
                        metadata={"attempts": attempt, "retries": step.retries},
                    ),
                    _StepExecutionState(schema_target=schema_target),
                )

            if attempt < max_attempts:
                continue

            return (
                BatteryStepResult(
                    id=step.id,
                    kind=step.kind,
                    status="error",
                    latency_ms=last_latency_ms,
                    response_code=response.status_code,
                    error=(
                        f"Expected status {step.expect_status}, received HTTP {response.status_code}"
                    ),
                    metadata={"attempts": attempt, "retries": step.retries},
                ),
                _StepExecutionState(schema_target=schema_target),
            )

        return (
            BatteryStepResult(
                id=step.id,
                kind=step.kind,
                status="error",
                latency_ms=last_latency_ms,
                response_code=None,
                error="HTTP step failed unexpectedly",
                metadata={"attempts": max_attempts, "retries": step.retries},
            ),
            _StepExecutionState(schema_target=None),
        )

    def _run_schema_capture_step(
        self,
        step: SchemaCaptureBatteryStep,
        *,
        states_by_step_id: dict[str, _StepExecutionState],
    ) -> tuple[BatteryStepResult, _StepExecutionState]:
        source_state = states_by_step_id.get(step.source_step)
        if source_state is None or source_state.schema_target is None:
            return (
                BatteryStepResult(
                    id=step.id,
                    kind=step.kind,
                    status="error",
                    latency_ms=None,
                    response_code=None,
                    error=f"Source step '{step.source_step}' has no capturable payload",
                    metadata={"source_step": step.source_step},
                ),
                _StepExecutionState(schema_target=None),
            )

        fingerprint, descriptor = ProbeService._schema_fingerprint(source_state.schema_target)

        metadata: dict[str, Any] = {
            "source_step": step.source_step,
            "schema_signature_version": "v2",
            "schema_fingerprint_v2": fingerprint,
            "schema_descriptor": descriptor,
        }

        return (
            BatteryStepResult(
                id=step.id,
                kind=step.kind,
                status="ok",
                latency_ms=None,
                response_code=None,
                error=None,
                metadata=metadata,
            ),
            _StepExecutionState(schema_target=descriptor),
        )

    def run_battery(self, battery: BatteryDefinition) -> BatteryRunArtifact:
        """Execute battery steps deterministically and return the run artifact."""
        started_at = datetime.now(timezone.utc)
        step_results: list[BatteryStepResult] = []
        states_by_step_id: dict[str, _StepExecutionState] = {}

        owns_client = self._client is None
        client = self._client or httpx.Client(follow_redirects=True)

        try:
            for step in battery.steps:
                if isinstance(step, HttpBatteryStep):
                    step_result, state = self._run_http_step(step, client=client)
                elif isinstance(step, SchemaCaptureBatteryStep):
                    step_result, state = self._run_schema_capture_step(
                        step,
                        states_by_step_id=states_by_step_id,
                    )
                else:
                    step_result = BatteryStepResult(
                        id=step.id,
                        kind=step.kind,
                        status="error",
                        latency_ms=None,
                        response_code=None,
                        error=(f"Step kind '{step.kind}' is not implemented in Slice B runner"),
                        metadata=None,
                    )
                    state = _StepExecutionState(schema_target=None)

                step_results.append(step_result)
                states_by_step_id[step.id] = state
        finally:
            if owns_client:
                client.close()

        completed_at = datetime.now(timezone.utc)
        failures = sum(1 for step in step_results if step.status != "ok")
        latencies = [step.latency_ms for step in step_results if step.latency_ms is not None]
        p95_latency_ms = self._percentile(latencies, 95)
        success_rate = ((len(step_results) - failures) / len(step_results)) if step_results else 0.0

        summary = BatteryRunSummary(
            success_rate=success_rate,
            p95_latency_ms=p95_latency_ms,
            failures=failures,
        )

        return BatteryRunArtifact(
            service_slug=battery.service_slug,
            battery_version=battery.version,
            profile=battery.profile,
            started_at=started_at,
            completed_at=completed_at,
            status="ok" if failures == 0 else "error",
            steps=step_results,
            summary=summary,
        )


class BatteryArtifactWriter:
    """Persist battery run artifacts as JSON documents on disk."""

    def __init__(self, output_dir: str | Path) -> None:
        self._output_dir = Path(output_dir)

    @staticmethod
    def _filename_for(artifact: BatteryRunArtifact) -> str:
        service_slug = _normalize_service_slug(artifact.service_slug) or artifact.service_slug
        stamp = artifact.completed_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return (
            f"{service_slug}-{artifact.profile}-v{artifact.battery_version}-{stamp}.json"
        )

    def write(self, artifact: BatteryRunArtifact) -> Path:
        """Write a battery artifact JSON file and return the absolute path."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._output_dir / self._filename_for(artifact)
        payload = artifact.model_dump(mode="json")
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return output_path.resolve()


class BatteryProbeBridge:
    """Translate battery artifacts into probe-compatible metadata and records."""

    def __init__(self, repository: ProbeRepository) -> None:
        self._repository = repository

    @staticmethod
    def _http_steps(artifact: BatteryRunArtifact) -> list[BatteryStepResult]:
        return [step for step in artifact.steps if step.kind == "http"]

    @staticmethod
    def _schema_step(artifact: BatteryRunArtifact) -> BatteryStepResult | None:
        for step in artifact.steps:
            if step.kind == "schema_capture":
                return step
        return None

    @classmethod
    def _latency_distribution(cls, artifact: BatteryRunArtifact) -> dict[str, int] | None:
        latencies = [
            step.latency_ms for step in cls._http_steps(artifact) if step.latency_ms is not None
        ]
        if not latencies:
            return None

        p50 = BatteryRunner._percentile(latencies, 50)
        p95 = BatteryRunner._percentile(latencies, 95)
        p99 = BatteryRunner._percentile(latencies, 99)

        if p50 is None or p95 is None or p99 is None:
            return None

        return {
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "samples": len(latencies),
        }

    @classmethod
    def build_probe_metadata(
        cls,
        artifact: BatteryRunArtifact,
        *,
        artifact_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Build a probe metadata payload that nests tester-fleet details."""
        normalized_service_slug = _normalize_service_slug(artifact.service_slug) or artifact.service_slug
        step_status = {step.id: step.status for step in artifact.steps}
        tester_fleet_metadata: dict[str, Any] = {
            "battery_version": artifact.battery_version,
            "profile": artifact.profile,
            "status": artifact.status,
            "summary": artifact.summary.model_dump(mode="json"),
            "step_status": step_status,
        }
        if artifact_path is not None:
            tester_fleet_metadata["artifact_path"] = str(Path(artifact_path))

        metadata: dict[str, Any] = {
            "runner": "tester-fleet-v0",
            "service_slug": normalized_service_slug,
            "tester_fleet": tester_fleet_metadata,
        }

        latency_distribution = cls._latency_distribution(artifact)
        if latency_distribution is not None:
            metadata["latency_distribution_ms"] = latency_distribution

        schema_step = cls._schema_step(artifact)
        schema_metadata = schema_step.metadata if schema_step else None
        if isinstance(schema_metadata, dict):
            schema_fingerprint = schema_metadata.get("schema_fingerprint_v2")
            if isinstance(schema_fingerprint, str) and schema_fingerprint:
                metadata["schema_signature_version"] = schema_metadata.get(
                    "schema_signature_version", "v2"
                )
                metadata["schema_fingerprint_v2"] = schema_fingerprint
                metadata["schema_descriptor"] = schema_metadata.get("schema_descriptor")

        return metadata

    def persist(
        self,
        artifact: BatteryRunArtifact,
        *,
        artifact_path: str | Path | None = None,
        trigger_source: str = "tester_fleet",
    ) -> list[StoredProbe]:
        """Persist bridge probe records (`health` + optional `schema`) for an artifact."""
        normalized_service_slug = _normalize_service_slug(artifact.service_slug) or artifact.service_slug
        probe_metadata = self.build_probe_metadata(artifact, artifact_path=artifact_path)

        persisted: list[StoredProbe] = []
        http_steps = self._http_steps(artifact)
        http_latencies = [step.latency_ms for step in http_steps if step.latency_ms is not None]
        latest_http = http_steps[-1] if http_steps else None
        health_error = next((step.error for step in http_steps if step.status != "ok"), None)

        if latest_http is not None:
            persisted.append(
                self._repository.save_probe(
                    service_slug=normalized_service_slug,
                    probe_type="health",
                    status="ok" if all(step.status == "ok" for step in http_steps) else "error",
                    latency_ms=BatteryRunner._percentile(http_latencies, 50),
                    response_code=latest_http.response_code,
                    response_schema_hash=None,
                    raw_response={
                        "tester_fleet": {
                            "artifact_status": artifact.status,
                            "summary": artifact.summary.model_dump(mode="json"),
                        }
                    },
                    probe_metadata=probe_metadata,
                    trigger_source=trigger_source,
                    runner_version="tester-fleet-v0",
                    error_message=health_error,
                )
            )

        schema_step = self._schema_step(artifact)
        if schema_step is not None:
            schema_metadata = schema_step.metadata or {}
            schema_fingerprint = schema_metadata.get("schema_fingerprint_v2")
            response_schema_hash = (
                schema_fingerprint if isinstance(schema_fingerprint, str) else None
            )
            persisted.append(
                self._repository.save_probe(
                    service_slug=normalized_service_slug,
                    probe_type="schema",
                    status=schema_step.status,
                    latency_ms=None,
                    response_code=None,
                    response_schema_hash=response_schema_hash,
                    raw_response={"tester_fleet_schema_step": schema_step.model_dump(mode="json")},
                    probe_metadata=probe_metadata,
                    trigger_source=trigger_source,
                    runner_version="tester-fleet-v0",
                    error_message=schema_step.error,
                )
            )

        return persisted


def _validate_payload(payload: dict[str, Any]) -> BatteryDefinition:
    try:
        return BatteryDefinition.model_validate(payload)
    except ValidationError as exc:
        raise BatteryParseError(f"Invalid battery definition: {exc}") from exc
