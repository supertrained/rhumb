"""Tester fleet execution routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from routes.probes import get_probe_service
from services.error_envelope import RhumbError
from schemas.tester_fleet import BatteryRunRequestSchema, BatteryRunResponseSchema
from services.service_slugs import public_service_slug, public_service_slug_candidates
from services.tester_fleet import (
    BatteryArtifactWriter,
    BatteryParseError,
    BatteryProbeBridge,
    BatteryRunner,
    load_battery_file,
)

router = APIRouter()


def _normalize_service_slug(service_slug: str | None) -> str | None:
    normalized = public_service_slug(service_slug)
    if normalized is not None:
        return normalized
    cleaned = str(service_slug or "").strip().lower()
    return cleaned or None


def _batteries_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "batteries"


def _artifacts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "artifacts" / "tester_fleet"


def _resolve_battery_file(service_slug: str, profile: str) -> Path | None:
    base_dir = _batteries_dir()
    normalized_profile = profile.strip().lower()
    candidates: list[str] = []

    for slug_candidate in public_service_slug_candidates(service_slug) or [service_slug]:
        if normalized_profile and normalized_profile != "default":
            candidates.append(f"{slug_candidate}-{normalized_profile}.yaml")

        candidates.extend(
            [
                f"{slug_candidate}-health.yaml",
                f"{slug_candidate}.yaml",
            ]
        )

    for candidate in candidates:
        path = base_dir / candidate
        if path.exists():
            return path

    return None


@router.post("/tester-fleet/run", response_model=BatteryRunResponseSchema)
async def run_tester_fleet_battery(payload: BatteryRunRequestSchema) -> BatteryRunResponseSchema:
    """Run a seeded tester-fleet battery for one service and persist evidence."""
    normalized_service_slug = _normalize_service_slug(payload.service_slug)
    if normalized_service_slug is None:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'service_slug' field.",
            detail="Provide a non-empty service_slug value.",
        )

    battery_file = _resolve_battery_file(normalized_service_slug, payload.profile)
    if battery_file is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No battery found for service '{normalized_service_slug}' "
                f"(profile '{payload.profile}')"
            ),
        )

    try:
        battery = load_battery_file(battery_file)
    except BatteryParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    battery_service_slug = _normalize_service_slug(battery.service_slug)
    if battery_service_slug != normalized_service_slug:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Battery service mismatch: requested '{normalized_service_slug}', "
                f"battery defines '{battery_service_slug or battery.service_slug}'"
            ),
        )

    battery = battery.model_copy(update={"service_slug": normalized_service_slug})

    artifact = BatteryRunner().run_battery(battery)
    artifact_writer = BatteryArtifactWriter(output_dir=_artifacts_dir())
    artifact_path = artifact_writer.write(artifact)

    persisted_probe_ids: list[str] = []
    persisted_probe_types: list[str] = []

    if payload.persist_probes:
        probe_service = get_probe_service()
        probe_repository = probe_service.repository
        if probe_repository is not None:
            persisted = BatteryProbeBridge(probe_repository).persist(
                artifact,
                artifact_path=artifact_path,
                trigger_source=payload.trigger_source,
            )
            persisted_probe_ids = [str(probe.id) for probe in persisted]
            persisted_probe_types = [probe.probe_type for probe in persisted]

    return BatteryRunResponseSchema(
        service_slug=normalized_service_slug,
        battery_file=str(battery_file),
        artifact_path=str(artifact_path),
        run=artifact,
        persisted_probe_ids=persisted_probe_ids,
        persisted_probe_types=persisted_probe_types,
    )
