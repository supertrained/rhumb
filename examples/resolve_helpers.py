"""Helpers for consuming /resolve execute and recovery hints honestly."""

from __future__ import annotations

from typing import Any


def _slug_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _append_slug(target: list[str], slug: Any) -> None:
    if isinstance(slug, str) and slug and slug not in target:
        target.append(slug)


def execute_ready_provider_slugs(
    resolve_data: dict[str, Any],
    *,
    limit: int | None = None,
) -> list[str]:
    """Return the honest execute-ready provider order from /resolve."""

    ordered: list[str] = []

    execute_hint = resolve_data.get("execute_hint")
    if isinstance(execute_hint, dict):
        _append_slug(ordered, execute_hint.get("preferred_provider"))
        for slug in _slug_list(execute_hint.get("fallback_providers")):
            _append_slug(ordered, slug)

    for slug in _slug_list(resolve_data.get("fallback_chain")):
        _append_slug(ordered, slug)

    if ordered:
        return ordered[:limit] if limit is not None else ordered

    providers = resolve_data.get("providers")
    if not isinstance(providers, list):
        return []

    for provider in providers:
        if not isinstance(provider, dict):
            continue
        slug = provider.get("service_slug")
        if not isinstance(slug, str) or not slug:
            continue
        if provider.get("available_for_execute") is False:
            continue
        if "endpoint_pattern" in provider and not provider.get("endpoint_pattern"):
            continue
        _append_slug(ordered, slug)

    return ordered[:limit] if limit is not None else ordered


def preferred_execute_provider(resolve_data: dict[str, Any]) -> str | None:
    providers = execute_ready_provider_slugs(resolve_data, limit=1)
    return providers[0] if providers else None


def preferred_recovery_handoff(resolve_data: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    recovery_hint = resolve_data.get("recovery_hint")
    if not isinstance(recovery_hint, dict):
        return None

    alternate_execute_hint = recovery_hint.get("alternate_execute_hint")
    if isinstance(alternate_execute_hint, dict):
        return "alternate_execute", alternate_execute_hint

    setup_handoff = recovery_hint.get("setup_handoff")
    if isinstance(setup_handoff, dict):
        return "setup_handoff", setup_handoff

    return None


def _handoff_summary(prefix: str, handoff: Any) -> list[str]:
    if not isinstance(handoff, dict):
        return []

    provider = handoff.get("preferred_provider")
    mode = handoff.get("preferred_credential_mode")
    if isinstance(provider, str) and provider:
        summary = provider
        if isinstance(mode, str) and mode:
            summary = f"{summary}({mode})"
        parts = [f"{prefix}={summary}"]
    elif isinstance(mode, str) and mode:
        parts = [f"{prefix}=({mode})"]
    else:
        parts = [prefix]

    endpoint_pattern = handoff.get("endpoint_pattern")
    if isinstance(endpoint_pattern, str) and endpoint_pattern:
        parts.append(f"{prefix}_endpoint={endpoint_pattern}")

    setup_url = handoff.get("setup_url")
    if isinstance(setup_url, str) and setup_url:
        parts.append(f"{prefix}_setup_url={setup_url}")
    else:
        setup_hint = handoff.get("setup_hint")
        if isinstance(setup_hint, str) and setup_hint:
            parts.append(f"{prefix}_setup_hint={setup_hint}")

    return parts


def describe_recovery_hint(resolve_data: dict[str, Any]) -> str | None:
    recovery_hint = resolve_data.get("recovery_hint")
    if not isinstance(recovery_hint, dict):
        return None

    reason = recovery_hint.get("reason")
    parts = [reason if isinstance(reason, str) and reason else "unknown_recovery_state"]

    unavailable = _slug_list(recovery_hint.get("unavailable_provider_slugs"))
    if unavailable:
        parts.append(f"unavailable={','.join(unavailable)}")

    not_ready = _slug_list(recovery_hint.get("not_execute_ready_provider_slugs"))
    if not_ready:
        parts.append(f"not_execute_ready={','.join(not_ready)}")

    supported = _slug_list(recovery_hint.get("supported_provider_slugs"))
    if supported:
        parts.append(f"supported={','.join(supported)}")

    parts.extend(_handoff_summary("alternate_execute", recovery_hint.get("alternate_execute_hint")))
    parts.extend(_handoff_summary("setup_handoff", recovery_hint.get("setup_handoff")))

    return "; ".join(parts)
