"""Score, compare, evaluation, and alert routes."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from config import settings
from db.repository import (
    DirectPostgresScorePublisherRepository,
    InMemoryProbeRepository,
    InMemoryScoreRepository,
    ProbeRepository,
    SQLAlchemyProbeRepository,
    SQLAlchemyScoreRepository,
    ScoreRepository,
    StoredProbe,
    StoredScore,
    SupabaseScoreRepository,
)
from routes._supabase import SupabaseWriteUnavailable
from routes.admin_auth import require_admin_key
from schemas.score import ANScoreSchema, ScoreRequestSchema
from services.alerts import ProbeAlertService
from services.fixtures import HAND_SCORED_FIXTURES
from services.probe_scheduler import DEFAULT_PROBE_SPECS
from services.scoring import EvidenceInput, ScoringService, TIER_LABELS
from services.service_slugs import (
    CANONICAL_TO_PROXY,
    canonicalize_service_slug,
    public_service_slug,
    public_service_slug_candidates,
)

router = APIRouter()


def _canonicalize_known_service_aliases(
    text: str | None,
    *,
    preserve_canonical: str | None = None,
) -> str | None:
    if text is None:
        return None

    preserved = str(preserve_canonical or "").strip().lower() or None
    replacements: dict[str, str] = {}
    for canonical in CANONICAL_TO_PROXY:
        if preserved and canonical.lower() == preserved:
            continue
        for candidate in public_service_slug_candidates(canonical):
            cleaned = str(candidate or "").strip()
            if not cleaned or cleaned.lower() == canonical.lower():
                continue
            replacements[cleaned.lower()] = canonical

    if not replacements:
        return text

    pattern = re.compile(
        rf"(?<![a-z0-9-])(?:{'|'.join(re.escape(candidate) for candidate in sorted(replacements, key=len, reverse=True))})(?![a-z0-9-])",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: replacements[match.group(0).lower()], text)


def _canonicalize_service_text(
    text: str | None,
    response_service_slug: str | None,
    stored_service_slug: str | None,
) -> str | None:
    if text is None:
        return None

    canonical = public_service_slug(response_service_slug)
    if canonical is None:
        return text

    raw_stored_slug = str(stored_service_slug).strip().lower() if stored_service_slug else None
    preserve_human_shorthand = raw_stored_slug == canonical.lower()

    canonicalized = text
    for candidate in sorted(public_service_slug_candidates(canonical), key=len, reverse=True):
        cleaned = str(candidate or "").strip()
        if not cleaned or cleaned.lower() == canonical.lower():
            continue

        pattern = re.compile(
            rf"(?<![a-z0-9-]){re.escape(cleaned)}(?![a-z0-9-])",
            re.IGNORECASE,
        )

        def _replace(match: re.Match[str]) -> str:
            matched = match.group(0)
            if preserve_human_shorthand and cleaned.isalpha() and matched == cleaned.upper():
                return matched
            return canonical

        canonicalized = pattern.sub(_replace, canonicalized)

    return _canonicalize_known_service_aliases(
        canonicalized,
        preserve_canonical=canonical if preserve_human_shorthand else None,
    )


def _canonicalize_service_payload(
    value: object,
    response_service_slug: str | None,
    stored_service_slug: str | None,
) -> object:
    if isinstance(value, str):
        return _canonicalize_service_text(value, response_service_slug, stored_service_slug)
    if isinstance(value, list):
        return [
            _canonicalize_service_payload(item, response_service_slug, stored_service_slug)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _canonicalize_service_payload(item, response_service_slug, stored_service_slug)
            for key, item in value.items()
        }
    return value


@lru_cache
def get_scoring_service() -> ScoringService:
    """Create singleton scoring service for API routes."""
    repository: ScoreRepository
    try:
        if settings.supabase_score_publisher_database_url:
            repository = DirectPostgresScorePublisherRepository.from_url(
                settings.supabase_score_publisher_database_url
            )
        elif settings.supabase_service_role_key != "replace-me":
            repository = SupabaseScoreRepository()
        else:
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
    autonomy_score: float | None,
    aggregate_recommendation_score: float,
    an_score_version: str,
    confidence: float,
    tier: str,
    explanation: str,
    dimension_snapshot: dict,
    score_id: str | None,
    calculated_at: str | None,
) -> ANScoreSchema:
    canonical_service_slug = public_service_slug(service_slug) or canonicalize_service_slug(service_slug)
    canonical_dimension_snapshot = _canonicalize_service_payload(
        dimension_snapshot,
        canonical_service_slug,
        service_slug,
    )
    if not isinstance(canonical_dimension_snapshot, dict):
        canonical_dimension_snapshot = dimension_snapshot

    autonomy_section = None
    if isinstance(canonical_dimension_snapshot, dict):
        candidate = canonical_dimension_snapshot.get("autonomy")
        if isinstance(candidate, dict):
            autonomy_section = candidate

    resolved_autonomy_score = autonomy_score
    if resolved_autonomy_score is None and autonomy_section is not None:
        avg_value = autonomy_section.get("avg")
        resolved_autonomy_score = float(avg_value) if avg_value is not None else None

    return ANScoreSchema(
        service_slug=canonical_service_slug,
        score=round(score, 1),
        execution_score=round(execution_score, 1),
        access_readiness_score=(
            None if access_readiness_score is None else round(access_readiness_score, 1)
        ),
        autonomy_score=(
            None if resolved_autonomy_score is None else round(float(resolved_autonomy_score), 1)
        ),
        autonomy=autonomy_section,
        an_score=round(aggregate_recommendation_score, 1),
        an_score_version=an_score_version,
        confidence=round(confidence, 2),
        tier=tier,
        tier_label=TIER_LABELS.get(tier, tier),
        explanation=_canonicalize_service_text(
            explanation,
            canonical_service_slug,
            service_slug,
        )
        or explanation,
        dimension_snapshot=canonical_dimension_snapshot,
        score_id=score_id,
        calculated_at=calculated_at,
    )


def _stored_score_sort_key(stored: StoredScore) -> datetime:
    calculated_at = stored.calculated_at
    if calculated_at is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if calculated_at.tzinfo is None:
        return calculated_at.replace(tzinfo=timezone.utc)
    return calculated_at.astimezone(timezone.utc)


async def _fetch_latest_score_for_public_slug(
    scoring_service: ScoringService,
    service_slug: str,
) -> StoredScore | None:
    latest: StoredScore | None = None
    for candidate in public_service_slug_candidates(service_slug):
        try:
            stored = await scoring_service.fetch_latest_score(candidate)
        except Exception:
            stored = None
        if stored is None:
            continue
        if latest is None or _stored_score_sort_key(stored) > _stored_score_sort_key(latest):
            latest = stored
    return latest


def _stored_to_schema(stored: StoredScore) -> ANScoreSchema:
    breakdown = (stored.dimension_snapshot or {}).get("score_breakdown", {})
    execution_score = float(breakdown.get("execution", stored.score))
    access_readiness_score = breakdown.get("access_readiness")
    autonomy_score = breakdown.get("autonomy")
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
        autonomy_score=float(autonomy_score) if autonomy_score is not None else None,
        aggregate_recommendation_score=aggregate_recommendation_score,
        an_score_version=score_version,
        confidence=stored.confidence,
        tier=stored.tier,
        explanation=stored.explanation,
        dimension_snapshot=stored.dimension_snapshot,
        score_id=str(stored.id),
        calculated_at=calculated_at,
    )


async def _persist_score_or_raise(
    scoring_service: ScoringService,
    service_slug: str,
    result,
) -> str | None:
    try:
        persisted_id = await scoring_service.save_score(service_slug, result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SupabaseWriteUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Score publication failed before the audit chain could be durably recorded.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Score publication failed.",
        ) from exc

    return str(persisted_id) if persisted_id else None


def _public_score_service_slug(service_slug: str) -> str:
    """Normalize score-route service ids onto canonical public slugs."""
    return public_service_slug(service_slug) or str(service_slug).strip().lower()


def _fetch_latest_probe_for_public_slug(
    probe_repository: ProbeRepository,
    service_slug: str,
) -> StoredProbe | None:
    """Fetch the latest probe across canonical and legacy alias candidates."""
    matches = [
        probe_repository.fetch_latest_probe(candidate)
        for candidate in public_service_slug_candidates(service_slug)
    ]
    available = [match for match in matches if match is not None]
    if not available:
        return None

    min_utc = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(available, key=lambda row: row.probed_at or min_utc)[-1]


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


@router.post("/score", response_model=ANScoreSchema, dependencies=[Depends(require_admin_key)])
async def score_service(payload: ScoreRequestSchema) -> ANScoreSchema:
    """Calculate and persist an AN score from dimensional inputs."""
    scoring_service = get_scoring_service()
    canonical_service_slug = _public_score_service_slug(payload.service_slug)

    probe_freshness = payload.probe_freshness
    probe_latency_distribution_ms = payload.probe_latency_distribution_ms

    if payload.hydrate_probe_telemetry and (
        probe_freshness is None or probe_latency_distribution_ms is None
    ):
        probe_repository = get_probe_repository()
        try:
            latest_probe = _fetch_latest_probe_for_public_slug(
                probe_repository,
                canonical_service_slug,
            )
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
        service_slug=canonical_service_slug,
        dimensions=payload.dimensions,
        evidence=evidence,
        access_dimensions=payload.access_dimensions,
        autonomy_dimensions=payload.autonomy_dimensions,
    )

    score_id = await _persist_score_or_raise(scoring_service, canonical_service_slug, result)

    return _result_to_schema(
        service_slug=result.service_slug,
        score=result.score,
        execution_score=result.execution_score,
        access_readiness_score=result.access_readiness_score,
        autonomy_score=result.autonomy_score,
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
    canonical_slug = _public_score_service_slug(slug)
    scoring_service = get_scoring_service()

    stored = await _fetch_latest_score_for_public_slug(scoring_service, canonical_slug)
    if stored is not None:
        return _stored_to_schema(stored)

    fixture = HAND_SCORED_FIXTURES.get(canonical_slug)
    if fixture is not None:
        evidence = EvidenceInput(
            evidence_count=fixture["evidence_count"],
            freshness=fixture["freshness"],
            probe_types=list(fixture["probe_types"]),
            production_telemetry=bool(fixture["production_telemetry"]),
        )
        result = await scoring_service.score_service(
            service_slug=canonical_slug,
            dimensions=dict(fixture["dimensions"]),
            evidence=evidence,
            access_dimensions=fixture.get("access_dimensions"),
        )

        result.dimension_snapshot["active_failures"] = fixture.get("active_failures", [])
        result.dimension_snapshot["alternatives"] = fixture.get("alternatives", [])

        score_id = await _persist_score_or_raise(scoring_service, canonical_slug, result)

        return _result_to_schema(
            service_slug=result.service_slug,
            score=result.score,
            execution_score=result.execution_score,
            access_readiness_score=result.access_readiness_score,
            autonomy_score=result.autonomy_score,
            aggregate_recommendation_score=result.aggregate_recommendation_score,
            an_score_version=result.an_score_version,
            confidence=result.confidence,
            tier=result.tier,
            explanation=result.explanation,
            dimension_snapshot=result.dimension_snapshot,
            score_id=score_id,
            calculated_at=result.calculated_at.isoformat(),
        )

    raise HTTPException(status_code=404, detail=f"No AN score found for service '{canonical_slug}'")


@router.get("/compare")
async def compare_services(services: str) -> dict:
    """Compare a comma-separated set of services."""
    scoring_service = get_scoring_service()
    requested: list[str] = []
    for service in services.split(","):
        cleaned = service.strip()
        if not cleaned:
            continue
        canonical_slug = public_service_slug(cleaned) or cleaned.lower()
        if canonical_slug not in requested:
            requested.append(canonical_slug)

    comparisons: list[dict[str, float | str | None]] = []
    for service_slug in requested:
        schema_payload: ANScoreSchema | None = None

        latest = await _fetch_latest_score_for_public_slug(scoring_service, service_slug)
        if latest is not None:
            schema_payload = _stored_to_schema(latest)
        else:
            fixture = HAND_SCORED_FIXTURES.get(service_slug)
            if fixture is not None:
                evidence = EvidenceInput(
                    evidence_count=fixture["evidence_count"],
                    freshness=fixture["freshness"],
                    probe_types=list(fixture["probe_types"]),
                    production_telemetry=bool(fixture["production_telemetry"]),
                )
                result = await scoring_service.score_service(
                    service_slug=service_slug,
                    dimensions=dict(fixture["dimensions"]),
                    evidence=evidence,
                    access_dimensions=fixture.get("access_dimensions"),
                )
                schema_payload = _result_to_schema(
                    service_slug=service_slug,
                    score=result.score,
                    execution_score=result.execution_score,
                    access_readiness_score=result.access_readiness_score,
                    autonomy_score=result.autonomy_score,
                    aggregate_recommendation_score=result.aggregate_recommendation_score,
                    an_score_version=result.an_score_version,
                    confidence=result.confidence,
                    tier=result.tier,
                    explanation=result.explanation,
                    dimension_snapshot=result.dimension_snapshot,
                    score_id=None,
                    calculated_at=result.calculated_at.isoformat(),
                )

        if schema_payload is None:
            continue

        comparisons.append(
            {
                "service_slug": schema_payload.service_slug,
                "an_score": schema_payload.an_score,
                "score": schema_payload.score,
                "execution_score": schema_payload.execution_score,
                "access_readiness_score": schema_payload.access_readiness_score,
                "autonomy_score": schema_payload.autonomy_score,
                "an_score_version": schema_payload.an_score_version,
                "confidence": schema_payload.confidence,
                "tier": schema_payload.tier,
                "tier_label": schema_payload.tier_label,
            }
        )

    return {"data": {"services": requested, "comparison": comparisons}, "error": None}


@router.post("/evaluate", dependencies=[Depends(require_admin_key)])
async def evaluate_stack() -> dict:
    """Evaluate an agent tool stack."""
    return {"data": {"accepted": True, "result": None}, "error": None}


@router.get("/alerts")
async def get_alerts(limit: int = 50) -> dict:
    """Fetch schema/score change alerts derived from probe telemetry."""
    safe_limit = max(1, min(limit, 100))
    service_slugs = [spec.service_slug for spec in DEFAULT_PROBE_SPECS]
    alert_service = ProbeAlertService(
        repository=get_probe_repository(),
        watched_services=service_slugs,
    )
    alerts = alert_service.generate_alerts(limit=safe_limit)

    return {
        "data": {
            "alerts": [
                {
                    "id": alert.id,
                    "type": alert.type,
                    "severity": alert.severity,
                    "service_slug": alert.service_slug,
                    "probe_type": alert.probe_type,
                    "title": alert.title,
                    "summary": alert.summary,
                    "details": alert.details,
                    "detected_at": alert.detected_at,
                }
                for alert in alerts
            ]
        },
        "error": None,
    }
