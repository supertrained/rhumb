"""Score schema definitions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from services.scoring import ACCESS_DIMENSION_WEIGHTS, DIMENSION_WEIGHTS


class ScoreRequestSchema(BaseModel):
    """Input payload for POST /v1/score."""

    service_slug: str = Field(min_length=1)
    dimensions: dict[str, float | None]
    access_dimensions: dict[str, float | None] | None = None
    evidence_count: int = Field(default=0, ge=0)
    freshness: str = Field(default="unknown")
    probe_types: list[str] = Field(default_factory=list)
    production_telemetry: bool = False
    probe_freshness: str | None = None
    probe_latency_distribution_ms: dict[str, int] | None = None
    hydrate_probe_telemetry: bool = False

    @field_validator("dimensions")
    @classmethod
    def validate_dimensions(cls, value: dict[str, float | None]) -> dict[str, float | None]:
        unknown = sorted(set(value.keys()) - set(DIMENSION_WEIGHTS.keys()))
        if unknown:
            raise ValueError(f"Unknown dimensions: {', '.join(unknown)}")

        for dimension, score in value.items():
            if score is None:
                continue
            if score < 0.0 or score > 10.0:
                raise ValueError(f"{dimension} must be between 0.0 and 10.0")
        return value

    @field_validator("access_dimensions")
    @classmethod
    def validate_access_dimensions(
        cls, value: dict[str, float | None] | None
    ) -> dict[str, float | None] | None:
        if value is None:
            return value

        unknown = sorted(set(value.keys()) - set(ACCESS_DIMENSION_WEIGHTS.keys()))
        if unknown:
            raise ValueError(f"Unknown access dimensions: {', '.join(unknown)}")

        for dimension, score in value.items():
            if score is None:
                continue
            if score < 0.0 or score > 10.0:
                raise ValueError(f"{dimension} must be between 0.0 and 10.0")

        return value


class ANScoreSchema(BaseModel):
    """Serialized AN score payload."""

    service_slug: str
    score: float
    execution_score: float
    access_readiness_score: float | None = None
    aggregate_recommendation_score: float
    an_score_version: str = "0.2"
    confidence: float
    tier: str
    tier_label: str
    explanation: str
    dimension_snapshot: dict[str, Any]
    score_id: str | None = None
    calculated_at: str | None = None
