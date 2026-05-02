"""Tester fleet execution routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException

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


def _validated_profile(profile: str | None) -> str:
    normalized = str(profile or "").strip().lower()
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'profile' field.",
        detail="Provide a non-empty tester-fleet profile value.",
    )


def _validated_trigger_source(trigger_source: str | None) -> str:
    normalized = str(trigger_source or "").strip()
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'trigger_source' field.",
        detail="Provide a non-empty trigger_source value.",
    )


def _validated_tester_fleet_text_field(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise RhumbError(
            "INVALID_PARAMETERS",
            message=f"Invalid '{field_name}' field.",
            detail=f"Provide {field_name} as a string.",
        )

    normalized = value.strip()
    if normalized:
        return normalized

    if field_name == "profile":
        return _validated_profile(value)
    if field_name == "trigger_source":
        return _validated_trigger_source(value)

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field_name}' field.",
        detail=f"Provide a non-empty {field_name} value.",
    )


def _validated_tester_fleet_bool_field(value: Any, *, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field_name}' field.",
        detail=f"Provide {field_name} as a boolean value.",
    )


def _validated_tester_fleet_payload(payload: Any) -> BatteryRunRequestSchema:
    if not isinstance(payload, dict):
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid tester-fleet payload.",
            detail="Provide a JSON object payload.",
        )

    service_slug = _validated_tester_fleet_text_field(
        payload.get("service_slug"),
        field_name="service_slug",
    )
    profile = _validated_tester_fleet_text_field(
        payload.get("profile", "default"),
        field_name="profile",
    )
    trigger_source = _validated_tester_fleet_text_field(
        payload.get("trigger_source", "tester_fleet_cli"),
        field_name="trigger_source",
    )

    return BatteryRunRequestSchema(
        service_slug=service_slug,
        profile=profile,
        persist_probes=_validated_tester_fleet_bool_field(
            payload.get("persist_probes"),
            field_name="persist_probes",
            default=True,
        ),
        trigger_source=trigger_source,
    )


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
async def run_tester_fleet_battery(payload: Any = Body(default=None)) -> BatteryRunResponseSchema:
    """Run a seeded tester-fleet battery for one service and persist evidence."""
    payload = _validated_tester_fleet_payload(payload)
    normalized_service_slug = _normalize_service_slug(payload.service_slug)
    if normalized_service_slug is None:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'service_slug' field.",
            detail="Provide a non-empty service_slug value.",
        )
    normalized_profile = _validated_profile(payload.profile)
    trigger_source = _validated_trigger_source(payload.trigger_source)

    battery_file = _resolve_battery_file(normalized_service_slug, normalized_profile)
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
                trigger_source=trigger_source,
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
