"""Score, compare, evaluation, and alert routes."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from config import settings
from db.repository import (
    InMemoryScoreRepository,
    SQLAlchemyScoreRepository,
    ScoreRepository,
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


def _result_to_schema(
    service_slug: str,
    score: float,
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
        confidence=round(confidence, 2),
        tier=tier,
        tier_label=TIER_LABELS.get(tier, tier),
        explanation=explanation,
        dimension_snapshot=dimension_snapshot,
        score_id=score_id,
        calculated_at=calculated_at,
    )


def _stored_to_schema(stored: StoredScore) -> ANScoreSchema:
    calculated_at = stored.calculated_at.isoformat() if stored.calculated_at else None
    return _result_to_schema(
        service_slug=stored.service_slug,
        score=stored.score,
        confidence=stored.confidence,
        tier=stored.tier,
        explanation=stored.explanation,
        dimension_snapshot=stored.dimension_snapshot,
        score_id=str(stored.id),
        calculated_at=calculated_at,
    )


@router.post("/score", response_model=ANScoreSchema)
async def score_service(payload: ScoreRequestSchema) -> ANScoreSchema:
    """Calculate and persist an AN score from dimensional inputs."""
    scoring_service = get_scoring_service()
    evidence = EvidenceInput(
        evidence_count=payload.evidence_count,
        freshness=payload.freshness,
        probe_types=payload.probe_types,
        production_telemetry=payload.production_telemetry,
        probe_freshness=payload.probe_freshness,
        probe_latency_distribution_ms=payload.probe_latency_distribution_ms,
    )

    result = await scoring_service.score_service(
        service_slug=payload.service_slug,
        dimensions=payload.dimensions,
        evidence=evidence,
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
