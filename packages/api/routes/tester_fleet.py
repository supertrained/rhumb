"""Tester fleet execution routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from routes.probes import get_probe_service
from schemas.tester_fleet import BatteryRunRequestSchema, BatteryRunResponseSchema
from services.tester_fleet import (
    BatteryArtifactWriter,
    BatteryParseError,
    BatteryProbeBridge,
    BatteryRunner,
    load_battery_file,
)

router = APIRouter()


def _batteries_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "batteries"


def _artifacts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "artifacts" / "tester_fleet"


def _resolve_battery_file(service_slug: str, profile: str) -> Path | None:
    base_dir = _batteries_dir()
    candidates: list[str] = []

    normalized_profile = profile.strip().lower()
    if normalized_profile and normalized_profile != "default":
        candidates.append(f"{service_slug}-{normalized_profile}.yaml")

    candidates.extend(
        [
            f"{service_slug}-health.yaml",
            f"{service_slug}.yaml",
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
    battery_file = _resolve_battery_file(payload.service_slug, payload.profile)
    if battery_file is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No battery found for service '{payload.service_slug}' "
                f"(profile '{payload.profile}')"
            ),
        )

    try:
        battery = load_battery_file(battery_file)
    except BatteryParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if battery.service_slug != payload.service_slug:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Battery service mismatch: requested '{payload.service_slug}', "
                f"battery defines '{battery.service_slug}'"
            ),
        )

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
        service_slug=payload.service_slug,
        battery_file=str(battery_file),
        artifact_path=str(artifact_path),
        run=artifact,
        persisted_probe_ids=persisted_probe_ids,
        persisted_probe_types=persisted_probe_types,
    )
