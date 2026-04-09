"""support_ref registry helpers for AUD-18 support read-first execution."""

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


@dataclass(frozen=True, slots=True)
class IntercomSupportBundle:
    support_ref: str
    provider: str
    region: str
    auth_mode: str
    bearer_token: str
    allowed_team_ids: tuple[int, ...]
    allowed_admin_ids: tuple[int, ...]
    allowed_conversation_ids: tuple[str, ...]
    allow_internal_notes: bool


SupportBundle = ZendeskSupportBundle | IntercomSupportBundle


def validate_support_ref(support_ref: str) -> None:
    if not _SUPPORT_REF_RE.fullmatch(support_ref):
        raise SupportRefError(
            f"Invalid support_ref '{support_ref}': must be lowercase alphanumeric with underscores, 1-64 chars"
        )


def has_any_support_bundle_configured(provider: str | None = None) -> bool:
    provider_filter = str(provider or "").strip().lower() or None
    for env_key in os.environ:
        if not env_key.startswith("RHUMB_SUPPORT_"):
            continue
        support_ref = env_key.removeprefix("RHUMB_SUPPORT_").lower()
        try:
            bundle = resolve_support_bundle(support_ref)
        except SupportRefError:
            continue
        if provider_filter and bundle.provider != provider_filter:
            continue
        return True
    return False


def resolve_support_bundle(support_ref: str) -> SupportBundle:
    validate_support_ref(support_ref)
    env_key, payload = _load_support_payload(support_ref)

    provider = str(payload.get("provider") or "").strip().lower()
    if provider == "zendesk":
        return _parse_zendesk_bundle(payload, support_ref=support_ref, env_key=env_key)
    if provider == "intercom":
        return _parse_intercom_bundle(payload, support_ref=support_ref, env_key=env_key)

    raise SupportRefError(
        f"support_ref '{support_ref}' is configured via env '{env_key}' but provider must be 'zendesk' or 'intercom'"
    )


def resolve_zendesk_support_bundle(support_ref: str) -> ZendeskSupportBundle:
    bundle = resolve_support_bundle(support_ref)
    if not isinstance(bundle, ZendeskSupportBundle):
        raise SupportRefError(
            f"support_ref '{support_ref}' does not resolve to a Zendesk bundle"
        )
    return bundle


def resolve_intercom_support_bundle(support_ref: str) -> IntercomSupportBundle:
    bundle = resolve_support_bundle(support_ref)
    if not isinstance(bundle, IntercomSupportBundle):
        raise SupportRefError(
            f"support_ref '{support_ref}' does not resolve to an Intercom bundle"
        )
    return bundle


def ticket_in_scope(bundle: ZendeskSupportBundle, ticket: dict[str, Any]) -> bool:
    return ticket_is_allowed(
        bundle,
        group_id=_id_value(ticket.get("group_id")),
        brand_id=_id_value(ticket.get("brand_id")),
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
        resolved_group_id = _id_value(ticket.get("group_id")) if resolved_group_id is None else resolved_group_id
        resolved_brand_id = _id_value(ticket.get("brand_id")) if resolved_brand_id is None else resolved_brand_id
        if ticket_id is None:
            ticket_id = _id_value(ticket.get("id"))

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


def conversation_in_scope(bundle: IntercomSupportBundle, conversation: dict[str, Any]) -> bool:
    return conversation_is_allowed(
        bundle,
        conversation_id=conversation.get("id"),
        team_assignee_id=_conversation_team_assignee_id(conversation),
        admin_assignee_id=_conversation_admin_assignee_id(conversation),
    )


def conversation_is_allowed(
    bundle: IntercomSupportBundle,
    *,
    conversation_id: str | int | None,
    team_assignee_id: int | None,
    admin_assignee_id: int | None,
) -> bool:
    normalized_conversation_id = _string_id_value(conversation_id)
    if bundle.allowed_conversation_ids and normalized_conversation_id not in bundle.allowed_conversation_ids:
        return False
    if bundle.allowed_team_ids and team_assignee_id not in bundle.allowed_team_ids:
        return False
    if bundle.allowed_admin_ids and admin_assignee_id not in bundle.allowed_admin_ids:
        return False
    return True


def ensure_conversation_access(
    bundle: IntercomSupportBundle,
    conversation: dict[str, Any] | None = None,
    *,
    conversation_id: str | int | None = None,
    team_assignee_id: int | None = None,
    admin_assignee_id: int | None = None,
) -> None:
    resolved_team_id = team_assignee_id
    resolved_admin_id = admin_assignee_id
    if conversation is not None:
        resolved_team_id = _conversation_team_assignee_id(conversation) if resolved_team_id is None else resolved_team_id
        resolved_admin_id = _conversation_admin_assignee_id(conversation) if resolved_admin_id is None else resolved_admin_id
        if conversation_id is None:
            conversation_id = conversation.get("id")

    if conversation_is_allowed(
        bundle,
        conversation_id=conversation_id,
        team_assignee_id=resolved_team_id,
        admin_assignee_id=resolved_admin_id,
    ):
        return

    if conversation_id is not None:
        raise SupportRefError(
            f"support_ref '{bundle.support_ref}' is not allowed to access conversation '{conversation_id}'"
        )
    raise SupportRefError(
        f"support_ref '{bundle.support_ref}' is not allowed to access the requested conversation"
    )


def ensure_internal_notes_allowed(
    bundle: IntercomSupportBundle,
    *,
    include_internal: bool,
) -> None:
    if include_internal and not bundle.allow_internal_notes:
        raise SupportRefError(
            f"support_ref '{bundle.support_ref}' is not allowed to access internal Intercom notes"
        )


def _load_support_payload(support_ref: str) -> tuple[str, dict[str, object]]:
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

    return env_key, payload


def _parse_zendesk_bundle(
    payload: dict[str, object],
    *,
    support_ref: str,
    env_key: str,
) -> ZendeskSupportBundle:
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
        provider="zendesk",
        subdomain=subdomain,
        auth_mode=auth_mode,
        allowed_group_ids=allowed_group_ids,
        allowed_brand_ids=allowed_brand_ids,
        allow_internal_comments=allow_internal_comments,
        email=email,
        api_token=api_token,
        bearer_token=bearer_token,
    )


def _parse_intercom_bundle(
    payload: dict[str, object],
    *,
    support_ref: str,
    env_key: str,
) -> IntercomSupportBundle:
    region = str(payload.get("region") or "").strip().lower()
    if region not in {"us", "eu", "au"}:
        raise SupportRefError(
            f"support_ref '{support_ref}' is configured via env '{env_key}' but region must be 'us', 'eu', or 'au'"
        )

    auth_mode = str(payload.get("auth_mode") or "").strip()
    if auth_mode != "bearer_token":
        raise SupportRefError(
            f"support_ref '{support_ref}' is configured via env '{env_key}' but auth_mode must be 'bearer_token' for Intercom"
        )

    bearer_token = _required_string(payload, "bearer_token", support_ref, env_key)

    allowed_team_ids = _normalize_id_list(
        payload.get("allowed_team_ids"),
        support_ref=support_ref,
        env_key=env_key,
        field_name="allowed_team_ids",
    )
    allowed_admin_ids = _normalize_id_list(
        payload.get("allowed_admin_ids"),
        support_ref=support_ref,
        env_key=env_key,
        field_name="allowed_admin_ids",
    )
    allowed_conversation_ids = _normalize_string_id_list(
        payload.get("allowed_conversation_ids"),
        support_ref=support_ref,
        env_key=env_key,
        field_name="allowed_conversation_ids",
    )
    if not allowed_team_ids and not allowed_admin_ids and not allowed_conversation_ids:
        raise SupportRefError(
            f"support_ref '{support_ref}' is configured via env '{env_key}' but must declare at least one scope constraint via allowed_team_ids, allowed_admin_ids, or allowed_conversation_ids"
        )

    allow_internal_notes = payload.get("allow_internal_notes", False)
    if not isinstance(allow_internal_notes, bool):
        raise SupportRefError(
            f"support_ref '{support_ref}' allow_internal_notes must be a boolean when provided"
        )

    return IntercomSupportBundle(
        support_ref=support_ref,
        provider="intercom",
        region=region,
        auth_mode=auth_mode,
        bearer_token=bearer_token,
        allowed_team_ids=allowed_team_ids,
        allowed_admin_ids=allowed_admin_ids,
        allowed_conversation_ids=allowed_conversation_ids,
        allow_internal_notes=allow_internal_notes,
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
        number = _id_value(value)
        if number is None or number <= 0:
            raise SupportRefError(
                f"support_ref '{support_ref}' is configured via env '{env_key}' but field '{field_name}' contains an invalid id"
            )
        normalized.append(number)
    return tuple(normalized)


def _normalize_string_id_list(
    values: object,
    *,
    support_ref: str,
    env_key: str,
    field_name: str,
) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, list):
        raise SupportRefError(
            f"support_ref '{support_ref}' is configured via env '{env_key}' but field '{field_name}' must be a list"
        )

    normalized: list[str] = []
    for value in values:
        string_id = _string_id_value(value)
        if string_id is None:
            raise SupportRefError(
                f"support_ref '{support_ref}' is configured via env '{env_key}' but field '{field_name}' contains an invalid id"
            )
        normalized.append(string_id)
    return tuple(normalized)


def _conversation_admin_assignee_id(conversation: dict[str, Any]) -> int | None:
    for key in ("admin_assignee_id", "assignee_id"):
        value = _id_value(conversation.get(key))
        if value is not None:
            return value
    for key in ("admin_assignee", "assignee"):
        value = _reference_id(conversation.get(key))
        if value is not None:
            return value
    return None


def _conversation_team_assignee_id(conversation: dict[str, Any]) -> int | None:
    for key in ("team_assignee_id",):
        value = _id_value(conversation.get(key))
        if value is not None:
            return value
    value = _reference_id(conversation.get("team_assignee"))
    if value is not None:
        return value
    return None


def _reference_id(value: object) -> int | None:
    if isinstance(value, dict):
        return _id_value(value.get("id"))
    return _id_value(value)


def _id_value(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _string_id_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
