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
