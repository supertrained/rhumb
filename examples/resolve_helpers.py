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

    return "; ".join(parts)
