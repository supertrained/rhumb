from __future__ import annotations


def is_schema_ready(endpoint_pattern: object) -> bool:
    return bool(str(endpoint_pattern or "").strip())


def rail_honesty_fields(
    *,
    endpoint_pattern: object,
    configured: object,
    available_for_execute: object,
) -> dict[str, bool]:
    schema_ready = is_schema_ready(endpoint_pattern)
    tenant_configured = bool(configured)
    return {
        "schema_ready": schema_ready,
        "tenant_configured": tenant_configured,
        "callable": schema_ready and tenant_configured and bool(available_for_execute),
    }


def stamp_rail_honesty(item: dict[str, object]) -> dict[str, object]:
    item.update(
        rail_honesty_fields(
            endpoint_pattern=item.get("endpoint_pattern"),
            configured=item.get("configured"),
            available_for_execute=item.get("available_for_execute"),
        )
    )
    return item
