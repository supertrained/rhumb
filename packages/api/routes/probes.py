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
from schemas.probe import ProbeResultSchema, ProbeRunRequestSchema
from services.probes import ProbeService

router = APIRouter()


@lru_cache
def get_probe_service() -> ProbeService:
    """Create singleton probe service for API routes."""
    repository: ProbeRepository
    try:
        repository = SQLAlchemyProbeRepository.from_url(settings.database_url)
    except Exception:
        repository = InMemoryProbeRepository()
    return ProbeService(repository=repository)


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
    stored = await probe_service.run_probe(
        service_slug=payload.service_slug,
        probe_type=payload.probe_type,
        target_url=payload.target_url,
        payload=payload.payload,
        trigger_source=payload.trigger_source,
    )

    if stored is None:
        raise HTTPException(status_code=500, detail="Probe repository is not configured")

    return _stored_to_schema(stored)


@router.get("/services/{slug}/probes/latest", response_model=ProbeResultSchema)
async def get_latest_probe(slug: str, probe_type: str | None = None) -> ProbeResultSchema:
    """Fetch the latest probe result for a service."""
    probe_service = get_probe_service()
    stored = probe_service.fetch_latest_probe(slug, probe_type=probe_type)

    if stored is None:
        raise HTTPException(status_code=404, detail=f"No probe result found for service '{slug}'")

    return _stored_to_schema(stored)
