"""actions_ref registry helpers for AUD-18 GitHub Actions workflow-run execution."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

_ACTIONS_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REPOSITORY_RE = re.compile(r"^[a-z0-9_.-]+/[a-z0-9_.-]+$")


class ActionsRefError(ValueError):
    """Raised when an actions_ref cannot be resolved or used safely."""


@dataclass(frozen=True, slots=True)
class GitHubActionsBundle:
    actions_ref: str
    provider: str
    auth_mode: str
    bearer_token: str
    allowed_repositories: tuple[str, ...]


def validate_actions_ref(actions_ref: str) -> None:
    if not _ACTIONS_REF_RE.fullmatch(actions_ref):
        raise ActionsRefError(
            f"Invalid actions_ref '{actions_ref}': must be lowercase alphanumeric with underscores, 1-64 chars"
        )


def has_any_actions_bundle_configured(provider: str | None = None) -> bool:
    provider_filter = str(provider or "").strip().lower() or None
    for env_key in os.environ:
        if not env_key.startswith("RHUMB_ACTIONS_"):
            continue
        actions_ref = env_key.removeprefix("RHUMB_ACTIONS_").lower()
        try:
            bundle = resolve_actions_bundle(actions_ref)
        except ActionsRefError:
            continue
        if provider_filter and bundle.provider != provider_filter:
            continue
        return True
    return False


def resolve_actions_bundle(actions_ref: str) -> GitHubActionsBundle:
    validate_actions_ref(actions_ref)
    env_key = f"RHUMB_ACTIONS_{actions_ref.upper()}"
    raw_bundle = os.environ.get(env_key)
    if not raw_bundle:
        raise ActionsRefError(
            f"No actions bundle configured for actions_ref '{actions_ref}' (expected env var {env_key})"
        )

    try:
        payload = json.loads(raw_bundle)
    except Exception as exc:
        raise ActionsRefError(
            f"actions_ref '{actions_ref}' is configured via env '{env_key}' but is not valid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise ActionsRefError(
            f"actions_ref '{actions_ref}' is configured via env '{env_key}' but is not a JSON object"
        )

    provider = str(payload.get("provider") or "").strip().lower()
    if provider != "github":
        raise ActionsRefError(
            f"actions_ref '{actions_ref}' is configured via env '{env_key}' but provider must be 'github'"
        )

    auth_mode = str(payload.get("auth_mode") or "").strip().lower()
    if auth_mode != "bearer_token":
        raise ActionsRefError(
            f"actions_ref '{actions_ref}' is configured via env '{env_key}' but auth_mode must be 'bearer_token'"
        )

    bearer_token = _required_string(payload, "bearer_token", actions_ref=actions_ref, env_key=env_key)
    allowed_repositories = _repository_tuple(payload.get("allowed_repositories"), field_name="allowed_repositories")
    if not allowed_repositories:
        raise ActionsRefError(
            f"actions_ref '{actions_ref}' is configured via env '{env_key}' but must declare at least one allowed_repositories entry"
        )

    return GitHubActionsBundle(
        actions_ref=actions_ref,
        provider=provider,
        auth_mode=auth_mode,
        bearer_token=bearer_token,
        allowed_repositories=allowed_repositories,
    )


def repository_is_allowed(bundle: GitHubActionsBundle, repository: str | None) -> bool:
    normalized = _normalize_repository(repository)
    if not normalized:
        return False
    return normalized in bundle.allowed_repositories


def ensure_repository_allowed(bundle: GitHubActionsBundle, repository: str | None) -> str:
    normalized = _normalize_repository(repository)
    if not normalized:
        raise ActionsRefError(
            f"actions_ref '{bundle.actions_ref}' requires an explicit repository in owner/repo form"
        )
    if normalized in bundle.allowed_repositories:
        return normalized
    raise ActionsRefError(
        f"actions_ref '{bundle.actions_ref}' is not allowed to access repository '{normalized}'"
    )


def split_repository(repository: str) -> tuple[str, str]:
    normalized = _normalize_repository(repository)
    if normalized is None:
        raise ActionsRefError("repository must be provided in owner/repo form")
    owner, repo = normalized.split("/", 1)
    return owner, repo


def _required_string(payload: dict[str, object], field_name: str, *, actions_ref: str, env_key: str) -> str:
    value = _optional_string(payload.get(field_name))
    if value is None:
        raise ActionsRefError(
            f"actions_ref '{actions_ref}' is configured via env '{env_key}' but field '{field_name}' is missing"
        )
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_repository(value: object) -> str | None:
    text = _optional_string(value)
    if text is None:
        return None
    normalized = text.lower()
    if not _REPOSITORY_RE.fullmatch(normalized):
        raise ActionsRefError(f"repository '{text}' must be in owner/repo form")
    return normalized


def _repository_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ActionsRefError(f"{field_name} must be an array of owner/repo strings")
    items: list[str] = []
    for item in value:
        normalized = _normalize_repository(item)
        if normalized is None:
            raise ActionsRefError(f"{field_name} entries must be non-empty owner/repo strings")
        items.append(normalized)
    return tuple(items)
