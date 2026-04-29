"""Internal probe runner routes."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from config import settings
from routes.admin_auth import require_admin_key
from db.repository import (
    InMemoryProbeRepository,
    ProbeRepository,
    SQLAlchemyProbeRepository,
    StoredProbe,
)
from schemas.probe import (
    ProbeBatchRunRequestSchema,
    ProbeBatchRunResponseSchema,
    ProbeResultSchema,
    ProbeRunRequestSchema,
)
from services.error_envelope import RhumbError
from services.probe_scheduler import ProbeScheduler
from services.probes import ProbeService
from services.service_slugs import public_service_slug

router = APIRouter()


@lru_cache
def get_probe_service() -> ProbeService:
    """Create singleton probe service for API routes."""
    repository: ProbeRepository
    try:
        sql_repository = SQLAlchemyProbeRepository.from_url(settings.database_url)
        sql_repository.create_tables()
        repository = sql_repository
    except Exception:
        repository = InMemoryProbeRepository()
    return ProbeService(repository=repository)


@lru_cache
def get_probe_scheduler() -> ProbeScheduler:
    """Create singleton scheduler object for recurring probe batches."""
    return ProbeScheduler(probe_service=get_probe_service())


def _stored_to_schema(stored: StoredProbe) -> ProbeResultSchema:
    probed_at = stored.probed_at.isoformat() if stored.probed_at else None
    return ProbeResultSchema(
        probe_id=str(stored.id),
        run_id=str(stored.run_id) if stored.run_id else None,
        service_slug=stored.service_slug,
        probe_type=stored.probe_type,
        status=stored.status,
        latency_ms=stored.latency_ms,
        response_code=stored.response_code,
        response_schema_hash=stored.response_schema_hash,
        raw_response=stored.raw_response,
        metadata=stored.probe_metadata,
        runner_version=stored.runner_version,
        trigger_source=stored.trigger_source,
        probed_at=probed_at,
    )


def _validated_probe_service_slug(slug: str | None) -> str:
    canonical_slug = public_service_slug(slug)
    if canonical_slug is not None:
        return canonical_slug

    cleaned = str(slug or "").strip().lower()
    if cleaned:
        return cleaned

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'service_slug' path parameter.",
        detail="Provide a non-empty service slug from GET /v1/services.",
    )


def _validated_probe_type_filter(probe_type: str | None) -> str | None:
    if probe_type is None:
        return None

    cleaned = str(probe_type).strip().lower()
    if cleaned:
        return cleaned

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'probe_type' filter.",
        detail="Provide a non-empty probe_type value or omit the filter.",
    )


def _validated_probe_text_field(value: str | None, *, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if cleaned:
        return cleaned

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field_name}' field.",
        detail=f"Provide a non-empty {field_name} value.",
    )


def _validated_probe_run_service_slug(service_slug: str | None) -> str:
    canonical_slug = public_service_slug(service_slug)
    if canonical_slug is not None:
        return canonical_slug

    return _validated_probe_text_field(service_slug, field_name="service_slug").lower()


def _validated_schedule_service_slugs(service_slugs: list[str] | None) -> list[str] | None:
    if service_slugs is None:
        return None

    normalized: list[str] = []
    for service_slug in service_slugs:
        normalized.append(_validated_probe_run_service_slug(service_slug))
    return normalized


@router.post("/probes/run", response_model=ProbeResultSchema, dependencies=[Depends(require_admin_key)])
async def run_probe(payload: ProbeRunRequestSchema) -> ProbeResultSchema:
    """Run a single internal probe and persist the result."""
    service_slug = _validated_probe_run_service_slug(payload.service_slug)
    probe_type = _validated_probe_text_field(payload.probe_type, field_name="probe_type")
    trigger_source = _validated_probe_text_field(payload.trigger_source, field_name="trigger_source")

    probe_service = get_probe_service()
    try:
        stored = await probe_service.run_probe(
            service_slug=service_slug,
            probe_type=probe_type,
            target_url=payload.target_url,
            payload=payload.payload,
            trigger_source=trigger_source,
            sample_count=payload.sample_count,
        )
    except Exception:
        fallback_service = ProbeService(repository=InMemoryProbeRepository())
        stored = await fallback_service.run_probe(
            service_slug=service_slug,
            probe_type=probe_type,
            target_url=payload.target_url,
            payload=payload.payload,
            trigger_source=trigger_source,
            sample_count=payload.sample_count,
        )

    if stored is None:
        raise HTTPException(status_code=500, detail="Probe repository is not configured")

    return _stored_to_schema(stored)


@router.post("/probes/schedule/run", response_model=ProbeBatchRunResponseSchema, dependencies=[Depends(require_admin_key)])
async def run_scheduled_probe_batch(
    payload: ProbeBatchRunRequestSchema,
) -> ProbeBatchRunResponseSchema:
    """Run one scheduler batch for recurring probe specifications."""
    service_slugs = _validated_schedule_service_slugs(payload.service_slugs)
    scheduler = get_probe_scheduler()
    selected = scheduler.list_specs(service_slugs=service_slugs)

    if payload.dry_run:
        cadence_preview = scheduler.preview_cadence(
            selected_specs=selected,
            base_interval_minutes=payload.base_interval_minutes,
        )
        return ProbeBatchRunResponseSchema(
            total_specs=len(scheduler.list_specs()),
            selected_services=[spec.service_slug for spec in selected],
            executed=0,
            succeeded=0,
            failed=0,
            probe_ids=[],
            by_service={},
            cadence_by_service=cadence_preview,
        )

    summary = await scheduler.run_once(
        service_slugs=service_slugs,
        sample_count=payload.sample_count,
        base_interval_minutes=payload.base_interval_minutes,
    )

    return ProbeBatchRunResponseSchema(
        total_specs=summary.total_specs,
        selected_services=summary.selected_services,
        executed=summary.executed,
        succeeded=summary.succeeded,
        failed=summary.failed,
        probe_ids=summary.probe_ids,
        by_service=summary.by_service,
        cadence_by_service=summary.cadence_by_service,
    )


@router.get("/services/{slug}/probes/latest", response_model=ProbeResultSchema)
async def get_latest_probe(slug: str, probe_type: str | None = None) -> ProbeResultSchema:
    """Fetch the latest probe result for a service."""
    canonical_slug = _validated_probe_service_slug(slug)
    normalized_probe_type = _validated_probe_type_filter(probe_type)
    probe_service = get_probe_service()
    stored = probe_service.fetch_latest_probe(canonical_slug, probe_type=normalized_probe_type)

    if stored is None:
        raise HTTPException(
            status_code=404,
            detail=f"No probe result found for service '{canonical_slug}'",
        )

    return _stored_to_schema(stored)
