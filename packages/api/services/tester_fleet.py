"""Parser and runner utilities for tester fleet battery YAML definitions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
import yaml
from pydantic import ValidationError

from schemas.tester_fleet import (
    BatteryDefinition,
    BatteryRunArtifact,
    BatteryRunSummary,
    BatteryStepResult,
    HttpBatteryStep,
    SchemaCaptureBatteryStep,
)
from services.probes import ProbeService


class BatteryParseError(ValueError):
    """Raised when a battery definition cannot be parsed or validated."""


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


def _validate_payload(payload: dict[str, Any]) -> BatteryDefinition:
    try:
        return BatteryDefinition.model_validate(payload)
    except ValidationError as exc:
        raise BatteryParseError(f"Invalid battery definition: {exc}") from exc
