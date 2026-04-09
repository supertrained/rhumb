"""support_ref registry helpers for AUD-18 Zendesk ticket read-first execution."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

_SUPPORT_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class SupportRefError(ValueError):
    """Raised when a support_ref cannot be resolved or used safely."""


@dataclass(frozen=True, slots=True)
class ZendeskSupportBundle:
    support_ref: str
    provider: str
    subdomain: str
    auth_mode: str
    allowed_group_ids: tuple[int, ...]
    allowed_brand_ids: tuple[int, ...]
    allow_internal_comments: bool
    email: str | None = None
    api_token: str | None = None
    bearer_token: str | None = None


def validate_support_ref(support_ref: str) -> None:
    if not _SUPPORT_REF_RE.fullmatch(support_ref):
        raise SupportRefError(
            f"Invalid support_ref '{support_ref}': must be lowercase alphanumeric with underscores, 1-64 chars"
        )


def has_any_support_bundle_configured() -> bool:
    for env_key in os.environ:
        if not env_key.startswith("RHUMB_SUPPORT_"):
            continue
        support_ref = env_key.removeprefix("RHUMB_SUPPORT_").lower()
        try:
            resolve_support_bundle(support_ref)
        except SupportRefError:
            continue
        return True
    return False


def resolve_support_bundle(support_ref: str) -> ZendeskSupportBundle:
    validate_support_ref(support_ref)
    env_key = f"RHUMB_SUPPORT_{support_ref.upper()}"
    raw_bundle = os.environ.get(env_key)
    if not raw_bundle:
        raise SupportRefError(
            f"No support bundle configured for support_ref '{support_ref}' (expected env var {env_key})"
        )

    try:
        payload = json.loads(raw_bundle)
    except Exception as exc:
        raise SupportRefError(
            f"support_ref '{support_ref}' is configured via env '{env_key}' but is not valid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise SupportRefError(
            f"support_ref '{support_ref}' is configured via env '{env_key}' but is not a JSON object"
        )

    provider = str(payload.get("provider") or "").strip()
    if provider != "zendesk":
        raise SupportRefError(
            f"support_ref '{support_ref}' is configured via env '{env_key}' but provider is not zendesk"
        )

    subdomain = str(payload.get("subdomain") or "").strip().lower()
    if not _SUBDOMAIN_RE.fullmatch(subdomain):
        raise SupportRefError(
            f"support_ref '{support_ref}' is configured via env '{env_key}' but subdomain is invalid"
        )

    auth_mode = str(payload.get("auth_mode") or "").strip()
    if auth_mode not in {"api_token", "bearer_token"}:
        raise SupportRefError(
            f"support_ref '{support_ref}' is configured via env '{env_key}' but auth_mode must be 'api_token' or 'bearer_token'"
        )

    email: str | None = None
    api_token: str | None = None
    bearer_token: str | None = None
    if auth_mode == "api_token":
        email = _required_string(payload, "email", support_ref, env_key)
        api_token = _required_string(payload, "api_token", support_ref, env_key)
    else:
        bearer_token = _required_string(payload, "bearer_token", support_ref, env_key)

    allowed_group_ids = _normalize_id_list(
        payload.get("allowed_group_ids"),
        support_ref=support_ref,
        env_key=env_key,
        field_name="allowed_group_ids",
    )
    allowed_brand_ids = _normalize_id_list(
        payload.get("allowed_brand_ids"),
        support_ref=support_ref,
        env_key=env_key,
        field_name="allowed_brand_ids",
    )
    if not allowed_group_ids and not allowed_brand_ids:
        raise SupportRefError(
            f"support_ref '{support_ref}' is configured via env '{env_key}' but must declare at least one scope constraint via allowed_group_ids or allowed_brand_ids"
        )

    allow_internal_comments = payload.get("allow_internal_comments", False)
    if not isinstance(allow_internal_comments, bool):
        raise SupportRefError(
            f"support_ref '{support_ref}' allow_internal_comments must be a boolean when provided"
        )

    return ZendeskSupportBundle(
        support_ref=support_ref,
        provider=provider,
        subdomain=subdomain,
        auth_mode=auth_mode,
        allowed_group_ids=allowed_group_ids,
        allowed_brand_ids=allowed_brand_ids,
        allow_internal_comments=allow_internal_comments,
        email=email,
        api_token=api_token,
        bearer_token=bearer_token,
    )


def ticket_in_scope(bundle: ZendeskSupportBundle, ticket: dict[str, Any]) -> bool:
    return ticket_is_allowed(
        bundle,
        group_id=_ticket_id(ticket.get("group_id")),
        brand_id=_ticket_id(ticket.get("brand_id")),
    )


def ticket_is_allowed(
    bundle: ZendeskSupportBundle,
    *,
    group_id: int | None,
    brand_id: int | None,
) -> bool:
    if bundle.allowed_group_ids and group_id not in bundle.allowed_group_ids:
        return False
    if bundle.allowed_brand_ids and brand_id not in bundle.allowed_brand_ids:
        return False
    return True


def ensure_ticket_access(
    bundle: ZendeskSupportBundle,
    ticket: dict[str, Any] | None = None,
    *,
    ticket_id: int | None = None,
    group_id: int | None = None,
    brand_id: int | None = None,
) -> None:
    resolved_group_id = group_id
    resolved_brand_id = brand_id
    if ticket is not None:
        resolved_group_id = _ticket_id(ticket.get("group_id")) if resolved_group_id is None else resolved_group_id
        resolved_brand_id = _ticket_id(ticket.get("brand_id")) if resolved_brand_id is None else resolved_brand_id
        if ticket_id is None:
            ticket_id = _ticket_id(ticket.get("id"))

    if ticket_is_allowed(bundle, group_id=resolved_group_id, brand_id=resolved_brand_id):
        return

    if ticket_id is not None:
        raise SupportRefError(
            f"support_ref '{bundle.support_ref}' is not allowed to access ticket '{ticket_id}'"
        )
    raise SupportRefError(
        f"support_ref '{bundle.support_ref}' is not allowed to access the requested ticket"
    )


def ensure_internal_comments_allowed(
    bundle: ZendeskSupportBundle,
    *,
    include_internal: bool,
) -> None:
    if include_internal and not bundle.allow_internal_comments:
        raise SupportRefError(
            f"support_ref '{bundle.support_ref}' is not allowed to access internal Zendesk comments"
        )


def _required_string(
    payload: dict[str, object],
    key: str,
    support_ref: str,
    env_key: str,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SupportRefError(
            f"support_ref '{support_ref}' is configured via env '{env_key}' but field '{key}' is missing"
        )
    return value.strip()


def _normalize_id_list(
    values: object,
    *,
    support_ref: str,
    env_key: str,
    field_name: str,
) -> tuple[int, ...]:
    if values is None:
        return ()
    if not isinstance(values, list):
        raise SupportRefError(
            f"support_ref '{support_ref}' is configured via env '{env_key}' but field '{field_name}' must be a list"
        )

    normalized: list[int] = []
    for value in values:
        number = _ticket_id(value)
        if number is None or number <= 0:
            raise SupportRefError(
                f"support_ref '{support_ref}' is configured via env '{env_key}' but field '{field_name}' contains an invalid id"
            )
        normalized.append(number)
    return tuple(normalized)


def _ticket_id(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None
