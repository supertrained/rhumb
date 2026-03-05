"""Tester fleet battery schema definitions."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


class HttpBatteryStep(BaseModel):
    """HTTP request step for tester fleet batteries."""

    id: str = Field(min_length=1)
    kind: Literal["http"]
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    url: str = Field(min_length=1)
    expect_status: list[int] = Field(default_factory=lambda: [200], min_length=1)
    timeout_ms: int = Field(default=8000, ge=100, le=120000)
    retries: int = Field(default=0, ge=0, le=5)


class SchemaCaptureBatteryStep(BaseModel):
    """Schema capture step that fingerprints a previous response payload."""

    id: str = Field(min_length=1)
    kind: Literal["schema_capture"]
    source_step: str = Field(min_length=1)
    fingerprint: Literal["semantic_v2"] = "semantic_v2"


class IdempotencyCheckBatteryStep(BaseModel):
    """Replay/idempotency validation against a prior HTTP step."""

    id: str = Field(min_length=1)
    kind: Literal["idempotency_check"]
    source_step: str = Field(min_length=1)
    compare: Literal["status_class", "body_hash"] = "status_class"


BatteryStep = Annotated[
    HttpBatteryStep | SchemaCaptureBatteryStep | IdempotencyCheckBatteryStep,
    Field(discriminator="kind"),
]


class BatteryDefinition(BaseModel):
    """Top-level battery document parsed from YAML."""

    version: Literal[1]
    service_slug: str = Field(min_length=1)
    profile: str = Field(default="default", min_length=1)
    steps: list[BatteryStep] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_step_graph(self) -> "BatteryDefinition":
        """Ensure deterministic, valid step references and unique IDs."""
        step_by_id: dict[str, BatteryStep] = {}

        for step in self.steps:
            if step.id in step_by_id:
                raise ValueError(f"Duplicate step id: {step.id}")

            if isinstance(step, SchemaCaptureBatteryStep | IdempotencyCheckBatteryStep):
                source = step_by_id.get(step.source_step)
                if source is None:
                    raise ValueError(
                        f"Step '{step.id}' references unknown or future source_step '{step.source_step}'"
                    )

                if isinstance(step, IdempotencyCheckBatteryStep) and not isinstance(
                    source, HttpBatteryStep
                ):
                    raise ValueError(
                        f"Step '{step.id}' requires source_step '{step.source_step}' to be an http step"
                    )

            step_by_id[step.id] = step

        if not any(isinstance(step, HttpBatteryStep) for step in self.steps):
            raise ValueError("Battery must include at least one http step")

        return self


class BatteryStepResult(BaseModel):
    """Serialized result payload for a single executed battery step."""

    id: str
    kind: str
    status: Literal["ok", "error"]
    latency_ms: int | None = None
    response_code: int | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class BatteryRunSummary(BaseModel):
    """Aggregate execution summary for a battery run."""

    success_rate: float = Field(ge=0, le=1)
    p95_latency_ms: int | None = None
    failures: int = Field(ge=0)


class BatteryRunArtifact(BaseModel):
    """Top-level runner output contract for tester fleet batteries."""

    service_slug: str
    battery_version: int
    profile: str
    started_at: datetime
    completed_at: datetime
    status: Literal["ok", "error"]
    steps: list[BatteryStepResult]
    summary: BatteryRunSummary
