"""Probe schema definitions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProbeRunRequestSchema(BaseModel):
    """Input payload for POST /v1/probes/run."""

    service_slug: str = Field(min_length=1)
    probe_type: str = Field(default="health", min_length=1)
    target_url: str | None = None
    payload: dict[str, Any] | None = None
    trigger_source: str = Field(default="internal", min_length=1)
    sample_count: int = Field(default=1, ge=1, le=20)


class ProbeBatchRunRequestSchema(BaseModel):
    """Input payload for POST /v1/probes/schedule/run."""

    service_slugs: list[str] | None = None
    sample_count: int = Field(default=3, ge=1, le=20)
    base_interval_minutes: int = Field(default=30, ge=1, le=1440)
    dry_run: bool = False


class ProbeBatchRunResponseSchema(BaseModel):
    """Serialized scheduler batch run summary."""

    total_specs: int
    selected_services: list[str]
    executed: int
    succeeded: int
    failed: int
    probe_ids: list[str]
    by_service: dict[str, str]
    cadence_by_service: dict[str, dict[str, int]]


class ProbeResultSchema(BaseModel):
    """Serialized probe payload."""

    probe_id: str
    run_id: str | None = None
    service_slug: str
    probe_type: str
    status: str
    latency_ms: int | None = None
    response_code: int | None = None
    response_schema_hash: str | None = None
    raw_response: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    runner_version: str | None = None
    trigger_source: str | None = None
    probed_at: str | None = None
