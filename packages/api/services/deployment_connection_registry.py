"""deployment_ref registry helpers for AUD-18 Vercel deployment read-first execution."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

_DEPLOYMENT_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class DeploymentRefError(ValueError):
    """Raised when a deployment_ref cannot be resolved or used safely."""


@dataclass(frozen=True, slots=True)
class VercelDeploymentBundle:
    deployment_ref: str
    provider: str
    auth_mode: str
    bearer_token: str
    allowed_project_ids: tuple[str, ...]
    allowed_targets: tuple[str, ...]
    team_id: str | None = None


def validate_deployment_ref(deployment_ref: str) -> None:
    if not _DEPLOYMENT_REF_RE.fullmatch(deployment_ref):
        raise DeploymentRefError(
            f"Invalid deployment_ref '{deployment_ref}': must be lowercase alphanumeric with underscores, 1-64 chars"
        )


def has_any_deployment_bundle_configured(provider: str | None = None) -> bool:
    provider_filter = str(provider or "").strip().lower() or None
    for env_key in os.environ:
        if not env_key.startswith("RHUMB_DEPLOYMENT_"):
            continue
        deployment_ref = env_key.removeprefix("RHUMB_DEPLOYMENT_").lower()
        try:
            bundle = resolve_deployment_bundle(deployment_ref)
        except DeploymentRefError:
            continue
        if provider_filter and bundle.provider != provider_filter:
            continue
        return True
    return False


def resolve_deployment_bundle(deployment_ref: str) -> VercelDeploymentBundle:
    validate_deployment_ref(deployment_ref)
    env_key = f"RHUMB_DEPLOYMENT_{deployment_ref.upper()}"
    raw_bundle = os.environ.get(env_key)
    if not raw_bundle:
        raise DeploymentRefError(
            f"No deployment bundle configured for deployment_ref '{deployment_ref}' (expected env var {env_key})"
        )

    try:
        payload = json.loads(raw_bundle)
    except Exception as exc:
        raise DeploymentRefError(
            f"deployment_ref '{deployment_ref}' is configured via env '{env_key}' but is not valid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise DeploymentRefError(
            f"deployment_ref '{deployment_ref}' is configured via env '{env_key}' but is not a JSON object"
        )

    provider = str(payload.get("provider") or "").strip().lower()
    if provider != "vercel":
        raise DeploymentRefError(
            f"deployment_ref '{deployment_ref}' is configured via env '{env_key}' but provider must be 'vercel'"
        )

    auth_mode = str(payload.get("auth_mode") or "").strip().lower()
    if auth_mode != "bearer_token":
        raise DeploymentRefError(
            f"deployment_ref '{deployment_ref}' is configured via env '{env_key}' but auth_mode must be 'bearer_token'"
        )

    bearer_token = _required_string(payload, "bearer_token", deployment_ref=deployment_ref, env_key=env_key)
    team_id = _optional_string(payload.get("team_id"))
    allowed_project_ids = _string_tuple(payload.get("allowed_project_ids"), field_name="allowed_project_ids")
    if not allowed_project_ids:
        raise DeploymentRefError(
            f"deployment_ref '{deployment_ref}' is configured via env '{env_key}' but must declare at least one allowed_project_ids entry"
        )

    allowed_targets = tuple(
        target for target in (_normalize_target(value) for value in _string_tuple(payload.get("allowed_targets"), field_name="allowed_targets")) if target
    )

    return VercelDeploymentBundle(
        deployment_ref=deployment_ref,
        provider=provider,
        auth_mode=auth_mode,
        bearer_token=bearer_token,
        allowed_project_ids=allowed_project_ids,
        allowed_targets=allowed_targets,
        team_id=team_id,
    )


def project_is_allowed(bundle: VercelDeploymentBundle, project_id: str | None) -> bool:
    normalized = _optional_string(project_id)
    if not normalized:
        return False
    return normalized in bundle.allowed_project_ids


def target_is_allowed(bundle: VercelDeploymentBundle, target: str | None) -> bool:
    normalized = _normalize_target(target)
    if not bundle.allowed_targets:
        return True
    return normalized in bundle.allowed_targets


def deployment_in_scope(bundle: VercelDeploymentBundle, deployment: dict[str, Any]) -> bool:
    project_id = _deployment_project_id(deployment)
    if not project_is_allowed(bundle, project_id):
        return False
    if not target_is_allowed(bundle, _deployment_target(deployment)):
        return False
    return True


def ensure_requested_project_allowed(bundle: VercelDeploymentBundle, project_id: str | None) -> None:
    normalized = _optional_string(project_id)
    if normalized is None:
        return
    if project_is_allowed(bundle, normalized):
        return
    raise DeploymentRefError(
        f"deployment_ref '{bundle.deployment_ref}' is not allowed to access project '{normalized}'"
    )


def ensure_target_allowed(bundle: VercelDeploymentBundle, target: str | None) -> None:
    normalized = _normalize_target(target)
    if normalized is None or target_is_allowed(bundle, normalized):
        return
    raise DeploymentRefError(
        f"deployment_ref '{bundle.deployment_ref}' is not allowed to access target '{normalized}'"
    )


def ensure_deployment_access(
    bundle: VercelDeploymentBundle,
    deployment: dict[str, Any] | None = None,
    *,
    deployment_id: str | None = None,
    project_id: str | None = None,
    target: str | None = None,
) -> None:
    resolved_project_id = project_id
    resolved_target = target
    if deployment is not None:
        resolved_project_id = _deployment_project_id(deployment) if resolved_project_id is None else resolved_project_id
        resolved_target = _deployment_target(deployment) if resolved_target is None else resolved_target
        if deployment_id is None:
            deployment_id = _deployment_id(deployment)

    if not project_is_allowed(bundle, resolved_project_id):
        if deployment_id:
            raise DeploymentRefError(
                f"deployment_ref '{bundle.deployment_ref}' is not allowed to access deployment '{deployment_id}'"
            )
        raise DeploymentRefError(
            f"deployment_ref '{bundle.deployment_ref}' is not allowed to access the requested deployment"
        )

    ensure_target_allowed(bundle, resolved_target)


def _deployment_id(deployment: dict[str, Any]) -> str | None:
    return _optional_string(deployment.get("uid") or deployment.get("id"))


def _deployment_project_id(deployment: dict[str, Any]) -> str | None:
    project = deployment.get("project")
    if isinstance(project, dict):
        nested = _optional_string(project.get("id"))
        if nested:
            return nested
    return _optional_string(deployment.get("projectId") or deployment.get("project_id"))


def _deployment_target(deployment: dict[str, Any]) -> str | None:
    return _normalize_target(deployment.get("target"))


def _required_string(payload: dict[str, object], field_name: str, *, deployment_ref: str, env_key: str) -> str:
    value = _optional_string(payload.get(field_name))
    if value is None:
        raise DeploymentRefError(
            f"deployment_ref '{deployment_ref}' is configured via env '{env_key}' but field '{field_name}' is missing"
        )
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise DeploymentRefError(f"{field_name} must be an array of strings")
    items: list[str] = []
    for item in value:
        text = _optional_string(item)
        if text is None:
            raise DeploymentRefError(f"{field_name} entries must be non-empty strings")
        items.append(text)
    return tuple(items)


def _normalize_target(value: object) -> str | None:
    text = _optional_string(value)
    if text is None:
        return None
    return text.lower()
