"""Score, compare, evaluation, and alert routes."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from config import settings
from db.repository import (
    InMemoryProbeRepository,
    InMemoryScoreRepository,
    ProbeRepository,
    SQLAlchemyProbeRepository,
    SQLAlchemyScoreRepository,
    ScoreRepository,
    StoredProbe,
    StoredScore,
)
from schemas.score import ANScoreSchema, ScoreRequestSchema
from services.fixtures import HAND_SCORED_FIXTURES
from services.scoring import EvidenceInput, ScoringService, TIER_LABELS

router = APIRouter()


@lru_cache
def get_scoring_service() -> ScoringService:
    """Create singleton scoring service for API routes."""
    repository: ScoreRepository
    try:
        repository = SQLAlchemyScoreRepository.from_url(settings.database_url)
    except Exception:
        repository = InMemoryScoreRepository()
    return ScoringService(repository=repository)


@lru_cache
def get_probe_repository() -> ProbeRepository:
    """Create singleton probe repository for score telemetry hydration."""
    try:
        return SQLAlchemyProbeRepository.from_url(settings.database_url)
    except Exception:
        return InMemoryProbeRepository()


def _result_to_schema(
    service_slug: str,
    score: float,
    execution_score: float,
    access_readiness_score: float | None,
    aggregate_recommendation_score: float,
    an_score_version: str,
    confidence: float,
    tier: str,
    explanation: str,
    dimension_snapshot: dict,
    score_id: str | None,
    calculated_at: str | None,
) -> ANScoreSchema:
    return ANScoreSchema(
        service_slug=service_slug,
        score=round(score, 1),
        execution_score=round(execution_score, 1),
        access_readiness_score=(
            None if access_readiness_score is None else round(access_readiness_score, 1)
        ),
        aggregate_recommendation_score=round(aggregate_recommendation_score, 1),
        an_score_version=an_score_version,
        confidence=round(confidence, 2),
        tier=tier,
        tier_label=TIER_LABELS.get(tier, tier),
        explanation=explanation,
        dimension_snapshot=dimension_snapshot,
        score_id=score_id,
        calculated_at=calculated_at,
    )


def _stored_to_schema(stored: StoredScore) -> ANScoreSchema:
    breakdown = (stored.dimension_snapshot or {}).get("score_breakdown", {})
    execution_score = float(breakdown.get("execution", stored.score))
    access_readiness_score = breakdown.get("access_readiness")
    aggregate_recommendation_score = float(breakdown.get("aggregate_recommendation", stored.score))
    score_version = str(breakdown.get("version", "0.1"))

    calculated_at = stored.calculated_at.isoformat() if stored.calculated_at else None
    return _result_to_schema(
        service_slug=stored.service_slug,
        score=stored.score,
        execution_score=execution_score,
        access_readiness_score=(
            float(access_readiness_score) if access_readiness_score is not None else None
        ),
        aggregate_recommendation_score=aggregate_recommendation_score,
        an_score_version=score_version,
        confidence=stored.confidence,
        tier=stored.tier,
        explanation=stored.explanation,
        dimension_snapshot=stored.dimension_snapshot,
        score_id=str(stored.id),
        calculated_at=calculated_at,
    )


def _coerce_latency_distribution(value: dict | None) -> dict[str, int] | None:
    if not value or not isinstance(value, dict):
        return None

    p50 = value.get("p50")
    p95 = value.get("p95")
    p99 = value.get("p99")
    samples = value.get("samples", 1)

    if p50 is None or p95 is None or p99 is None:
        return None

    try:
        normalized = {
            "p50": int(p50),
            "p95": int(p95),
            "p99": int(p99),
            "samples": max(1, int(samples)),
        }
    except (TypeError, ValueError):
        return None

    return normalized


def _extract_probe_latency_distribution(probe: StoredProbe) -> dict[str, int] | None:
    metadata = probe.probe_metadata or {}
    from_metadata = _coerce_latency_distribution(metadata.get("latency_distribution_ms"))
    if from_metadata is not None:
        return from_metadata

    if probe.latency_ms is None:
        return None

    latency = int(probe.latency_ms)
    return {
        "p50": latency,
        "p95": latency,
        "p99": latency,
        "samples": 1,
    }


def _format_probe_freshness(probed_at: datetime | None) -> str | None:
    if probed_at is None:
        return None

    normalized = probed_at
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)

    delta_seconds = max(0, int((datetime.now(timezone.utc) - normalized).total_seconds()))

    if delta_seconds < 60:
        return "just now"

    if delta_seconds < 3600:
        minutes = max(1, delta_seconds // 60)
        return f"{minutes} minutes ago"

    if delta_seconds < 86400:
        hours = max(1, delta_seconds // 3600)
        return f"{hours} hours ago"

    if delta_seconds < 86400 * 7:
        days = max(1, delta_seconds // 86400)
        return f"{days} days ago"

    weeks = max(1, delta_seconds // (86400 * 7))
    return f"{weeks} weeks ago"


@router.post("/score", response_model=ANScoreSchema)
async def score_service(payload: ScoreRequestSchema) -> ANScoreSchema:
    """Calculate and persist an AN score from dimensional inputs."""
    scoring_service = get_scoring_service()

    probe_freshness = payload.probe_freshness
    probe_latency_distribution_ms = payload.probe_latency_distribution_ms

    if payload.hydrate_probe_telemetry and (
        probe_freshness is None or probe_latency_distribution_ms is None
    ):
        probe_repository = get_probe_repository()
        try:
            latest_probe = probe_repository.fetch_latest_probe(payload.service_slug)
        except Exception:
            latest_probe = None

        if latest_probe is not None:
            if probe_freshness is None:
                probe_freshness = _format_probe_freshness(latest_probe.probed_at)
            if probe_latency_distribution_ms is None:
                probe_latency_distribution_ms = _extract_probe_latency_distribution(latest_probe)

    evidence = EvidenceInput(
        evidence_count=payload.evidence_count,
        freshness=payload.freshness,
        probe_types=payload.probe_types,
        production_telemetry=payload.production_telemetry,
        probe_freshness=probe_freshness,
        probe_latency_distribution_ms=probe_latency_distribution_ms,
    )

    result = await scoring_service.score_service(
        service_slug=payload.service_slug,
        dimensions=payload.dimensions,
        evidence=evidence,
        access_dimensions=payload.access_dimensions,
    )

    score_id: str | None = None
    try:
        persisted_id = scoring_service.save_score(payload.service_slug, result)
        score_id = str(persisted_id) if persisted_id else None
    except Exception:
        score_id = None

    return _result_to_schema(
        service_slug=result.service_slug,
        score=result.score,
        execution_score=result.execution_score,
        access_readiness_score=result.access_readiness_score,
        aggregate_recommendation_score=result.aggregate_recommendation_score,
        an_score_version=result.an_score_version,
        confidence=result.confidence,
        tier=result.tier,
        explanation=result.explanation,
        dimension_snapshot=result.dimension_snapshot,
        score_id=score_id,
        calculated_at=result.calculated_at.isoformat(),
    )


@router.get("/services/{slug}/score", response_model=ANScoreSchema)
async def get_score(slug: str) -> ANScoreSchema:
    """Get the latest AN score for a service."""
    scoring_service = get_scoring_service()

    try:
        stored = scoring_service.fetch_latest_score(slug)
    except Exception:
        stored = None

    if stored is not None:
        return _stored_to_schema(stored)

    fixture = HAND_SCORED_FIXTURES.get(slug)
    if fixture is not None:
        evidence = EvidenceInput(
            evidence_count=fixture["evidence_count"],
            freshness=fixture["freshness"],
            probe_types=list(fixture["probe_types"]),
            production_telemetry=bool(fixture["production_telemetry"]),
        )
        result = await scoring_service.score_service(
            service_slug=slug,
            dimensions=dict(fixture["dimensions"]),
            evidence=evidence,
        )

        result.dimension_snapshot["active_failures"] = fixture.get("active_failures", [])
        result.dimension_snapshot["alternatives"] = fixture.get("alternatives", [])

        score_id: str | None = None
        try:
            persisted_id = scoring_service.save_score(slug, result)
            score_id = str(persisted_id) if persisted_id else None
        except Exception:
            score_id = None

        return _result_to_schema(
            service_slug=slug,
            score=result.score,
            execution_score=result.execution_score,
            access_readiness_score=result.access_readiness_score,
            aggregate_recommendation_score=result.aggregate_recommendation_score,
            an_score_version=result.an_score_version,
            confidence=result.confidence,
            tier=result.tier,
            explanation=result.explanation,
            dimension_snapshot=result.dimension_snapshot,
            score_id=score_id,
            calculated_at=result.calculated_at.isoformat(),
        )

    raise HTTPException(status_code=404, detail=f"No AN score found for service '{slug}'")


@router.get("/compare")
async def compare_services(services: str) -> dict:
    """Compare a comma-separated set of services."""
    scoring_service = get_scoring_service()
    requested = [service.strip() for service in services.split(",") if service.strip()]

    comparisons: list[dict[str, float | str]] = []
    for service_slug in requested:
        try:
            latest = scoring_service.fetch_latest_score(service_slug)
        except Exception:
            latest = None
        if latest is None:
            continue
        comparisons.append(
            {
                "service_slug": service_slug,
                "score": latest.score,
                "confidence": latest.confidence,
                "tier": latest.tier,
            }
        )

    return {"data": {"services": requested, "comparison": comparisons}, "error": None}


@router.post("/evaluate")
async def evaluate_stack() -> dict:
    """Evaluate an agent tool stack."""
    return {"data": {"accepted": True, "result": None}, "error": None}


@router.get("/alerts")
async def get_alerts() -> dict:
    """Fetch schema/score change alerts for authenticated users."""
    return {"data": {"alerts": []}, "error": None}
