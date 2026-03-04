"""Internal probe runner routes."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from config import settings
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
from services.probe_scheduler import ProbeScheduler
from services.probes import ProbeService

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


@router.post("/probes/run", response_model=ProbeResultSchema)
async def run_probe(payload: ProbeRunRequestSchema) -> ProbeResultSchema:
    """Run a single internal probe and persist the result."""
    probe_service = get_probe_service()
    try:
        stored = await probe_service.run_probe(
            service_slug=payload.service_slug,
            probe_type=payload.probe_type,
            target_url=payload.target_url,
            payload=payload.payload,
            trigger_source=payload.trigger_source,
            sample_count=payload.sample_count,
        )
    except Exception:
        fallback_service = ProbeService(repository=InMemoryProbeRepository())
        stored = await fallback_service.run_probe(
            service_slug=payload.service_slug,
            probe_type=payload.probe_type,
            target_url=payload.target_url,
            payload=payload.payload,
            trigger_source=payload.trigger_source,
            sample_count=payload.sample_count,
        )

    if stored is None:
        raise HTTPException(status_code=500, detail="Probe repository is not configured")

    return _stored_to_schema(stored)


@router.post("/probes/schedule/run", response_model=ProbeBatchRunResponseSchema)
async def run_scheduled_probe_batch(
    payload: ProbeBatchRunRequestSchema,
) -> ProbeBatchRunResponseSchema:
    """Run one scheduler batch for recurring probe specifications."""
    scheduler = get_probe_scheduler()
    selected = scheduler.list_specs(service_slugs=payload.service_slugs)

    if payload.dry_run:
        return ProbeBatchRunResponseSchema(
            total_specs=len(scheduler.list_specs()),
            selected_services=[spec.service_slug for spec in selected],
            executed=0,
            succeeded=0,
            failed=0,
            probe_ids=[],
            by_service={},
        )

    summary = await scheduler.run_once(
        service_slugs=payload.service_slugs,
        sample_count=payload.sample_count,
    )

    return ProbeBatchRunResponseSchema(
        total_specs=summary.total_specs,
        selected_services=summary.selected_services,
        executed=summary.executed,
        succeeded=summary.succeeded,
        failed=summary.failed,
        probe_ids=summary.probe_ids,
        by_service=summary.by_service,
    )


@router.get("/services/{slug}/probes/latest", response_model=ProbeResultSchema)
async def get_latest_probe(slug: str, probe_type: str | None = None) -> ProbeResultSchema:
    """Fetch the latest probe result for a service."""
    probe_service = get_probe_service()
    stored = probe_service.fetch_latest_probe(slug, probe_type=probe_type)

    if stored is None:
        raise HTTPException(status_code=404, detail=f"No probe result found for service '{slug}'")

    return _stored_to_schema(stored)
