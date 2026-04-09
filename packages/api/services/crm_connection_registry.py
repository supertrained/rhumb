"""crm_ref registry helpers for AUD-18 HubSpot CRM read-first execution."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

_CRM_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_OBJECT_TYPE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_PROPERTY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_RECORD_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class CrmRefError(ValueError):
    """Raised when a crm_ref cannot be resolved or used safely."""


@dataclass(frozen=True, slots=True)
class HubSpotCrmBundle:
    crm_ref: str
    provider: str
    auth_mode: str
    private_app_token: str
    portal_id: str | None
    allowed_object_types: tuple[str, ...]
    allowed_properties_by_object: dict[str, tuple[str, ...]]
    default_properties_by_object: dict[str, tuple[str, ...]]
    searchable_properties_by_object: dict[str, tuple[str, ...]]
    sortable_properties_by_object: dict[str, tuple[str, ...]]
    allowed_record_ids_by_object: dict[str, tuple[str, ...]]


def validate_crm_ref(crm_ref: str) -> None:
    if not _CRM_REF_RE.fullmatch(crm_ref):
        raise CrmRefError(
            f"Invalid crm_ref '{crm_ref}': must be lowercase alphanumeric with underscores, 1-64 chars"
        )


def has_any_crm_bundle_configured(provider: str | None = None) -> bool:
    provider_filter = str(provider or "").strip().lower() or None
    for env_key in os.environ:
        if not env_key.startswith("RHUMB_CRM_"):
            continue
        crm_ref = env_key.removeprefix("RHUMB_CRM_").lower()
        try:
            bundle = resolve_crm_bundle(crm_ref)
        except CrmRefError:
            continue
        if provider_filter and bundle.provider != provider_filter:
            continue
        return True
    return False


def resolve_crm_bundle(crm_ref: str) -> HubSpotCrmBundle:
    validate_crm_ref(crm_ref)
    env_key = f"RHUMB_CRM_{crm_ref.upper()}"
    raw_bundle = os.environ.get(env_key)
    if not raw_bundle:
        raise CrmRefError(
            f"No crm bundle configured for crm_ref '{crm_ref}' (expected env var {env_key})"
        )

    try:
        payload = json.loads(raw_bundle)
    except Exception as exc:
        raise CrmRefError(
            f"crm_ref '{crm_ref}' is configured via env '{env_key}' but is not valid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise CrmRefError(
            f"crm_ref '{crm_ref}' is configured via env '{env_key}' but is not a JSON object"
        )

    provider = str(payload.get("provider") or "").strip().lower()
    if provider != "hubspot":
        raise CrmRefError(
            f"crm_ref '{crm_ref}' is configured via env '{env_key}' but provider must be 'hubspot'"
        )

    auth_mode = str(payload.get("auth_mode") or "").strip().lower()
    if auth_mode != "private_app_token":
        raise CrmRefError(
            f"crm_ref '{crm_ref}' is configured via env '{env_key}' but auth_mode must be 'private_app_token'"
        )

    private_app_token = _required_string(payload, "private_app_token", crm_ref=crm_ref, env_key=env_key)
    portal_id = _optional_string(payload.get("portal_id"))

    allowed_object_types = _object_type_tuple(
        payload.get("allowed_object_types"),
        field_name="allowed_object_types",
    )
    if not allowed_object_types:
        raise CrmRefError(
            f"crm_ref '{crm_ref}' is configured via env '{env_key}' but must declare at least one allowed_object_types entry"
        )

    allowed_properties_by_object = _properties_map(
        payload.get("allowed_properties_by_object"),
        field_name="allowed_properties_by_object",
    )
    missing_allowed_property_maps = [
        object_type
        for object_type in allowed_object_types
        if object_type not in allowed_properties_by_object
    ]
    if missing_allowed_property_maps:
        missing = ", ".join(missing_allowed_property_maps)
        raise CrmRefError(
            f"crm_ref '{crm_ref}' is configured via env '{env_key}' but allowed_properties_by_object is missing entries for: {missing}"
        )

    default_properties_by_object = _properties_map(
        payload.get("default_properties_by_object"),
        field_name="default_properties_by_object",
    )
    searchable_properties_by_object = _properties_map(
        payload.get("searchable_properties_by_object"),
        field_name="searchable_properties_by_object",
    )
    sortable_properties_by_object = _properties_map(
        payload.get("sortable_properties_by_object"),
        field_name="sortable_properties_by_object",
    )
    allowed_record_ids_by_object = _record_ids_map(
        payload.get("allowed_record_ids_by_object"),
        field_name="allowed_record_ids_by_object",
    )

    for field_name, scoped_map in (
        ("allowed_properties_by_object", allowed_properties_by_object),
        ("default_properties_by_object", default_properties_by_object),
        ("searchable_properties_by_object", searchable_properties_by_object),
        ("sortable_properties_by_object", sortable_properties_by_object),
        ("allowed_record_ids_by_object", allowed_record_ids_by_object),
    ):
        _ensure_map_keys_subset(
            scoped_map,
            allowed_object_types=allowed_object_types,
            field_name=field_name,
        )

    for field_name, scoped_map in (
        ("default_properties_by_object", default_properties_by_object),
        ("searchable_properties_by_object", searchable_properties_by_object),
        ("sortable_properties_by_object", sortable_properties_by_object),
    ):
        _ensure_map_values_subset(
            scoped_map,
            allowed_values_by_object=allowed_properties_by_object,
            field_name=field_name,
        )

    return HubSpotCrmBundle(
        crm_ref=crm_ref,
        provider=provider,
        auth_mode=auth_mode,
        private_app_token=private_app_token,
        portal_id=portal_id,
        allowed_object_types=allowed_object_types,
        allowed_properties_by_object=allowed_properties_by_object,
        default_properties_by_object=default_properties_by_object,
        searchable_properties_by_object=searchable_properties_by_object,
        sortable_properties_by_object=sortable_properties_by_object,
        allowed_record_ids_by_object=allowed_record_ids_by_object,
    )


def object_type_is_allowed(bundle: HubSpotCrmBundle, object_type: str | None) -> bool:
    normalized = _normalize_object_type(object_type)
    return normalized is not None and normalized in bundle.allowed_object_types


def ensure_object_type_allowed(bundle: HubSpotCrmBundle, object_type: str | None) -> str:
    normalized = _normalize_object_type(object_type)
    if normalized is None:
        raise CrmRefError(f"crm_ref '{bundle.crm_ref}' requires an explicit object_type")
    if normalized not in bundle.allowed_object_types:
        raise CrmRefError(
            f"crm_ref '{bundle.crm_ref}' is not allowed to access object_type '{normalized}'"
        )
    return normalized


def allowed_properties_for_object(bundle: HubSpotCrmBundle, object_type: str) -> tuple[str, ...]:
    normalized_object_type = ensure_object_type_allowed(bundle, object_type)
    return bundle.allowed_properties_by_object.get(normalized_object_type, ())


def default_properties_for_object(bundle: HubSpotCrmBundle, object_type: str) -> tuple[str, ...]:
    normalized_object_type = ensure_object_type_allowed(bundle, object_type)
    configured = bundle.default_properties_by_object.get(normalized_object_type)
    return configured if configured else allowed_properties_for_object(bundle, normalized_object_type)


def searchable_properties_for_object(bundle: HubSpotCrmBundle, object_type: str) -> tuple[str, ...]:
    normalized_object_type = ensure_object_type_allowed(bundle, object_type)
    configured = bundle.searchable_properties_by_object.get(normalized_object_type)
    return configured if configured else allowed_properties_for_object(bundle, normalized_object_type)


def sortable_properties_for_object(bundle: HubSpotCrmBundle, object_type: str) -> tuple[str, ...]:
    normalized_object_type = ensure_object_type_allowed(bundle, object_type)
    configured = bundle.sortable_properties_by_object.get(normalized_object_type)
    return configured if configured else allowed_properties_for_object(bundle, normalized_object_type)


def ensure_properties_allowed(
    bundle: HubSpotCrmBundle,
    object_type: str,
    properties: list[str] | tuple[str, ...],
) -> tuple[str, ...]:
    normalized_object_type = ensure_object_type_allowed(bundle, object_type)
    allowed = set(allowed_properties_for_object(bundle, normalized_object_type))
    normalized_properties: list[str] = []
    seen: set[str] = set()
    for property_name in properties:
        normalized_property = _normalize_property_name(property_name)
        if normalized_property is None:
            raise CrmRefError("property_names entries must be non-empty strings")
        if normalized_property not in allowed:
            raise CrmRefError(
                f"crm_ref '{bundle.crm_ref}' is not allowed to access property '{normalized_property}' for object_type '{normalized_object_type}'"
            )
        if normalized_property not in seen:
            seen.add(normalized_property)
            normalized_properties.append(normalized_property)
    return tuple(normalized_properties)


def effective_properties_for_object(
    bundle: HubSpotCrmBundle,
    object_type: str,
    property_names: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    normalized_object_type = ensure_object_type_allowed(bundle, object_type)
    if not property_names:
        return default_properties_for_object(bundle, normalized_object_type)
    return ensure_properties_allowed(bundle, normalized_object_type, property_names)


def ensure_search_filter_properties_allowed(
    bundle: HubSpotCrmBundle,
    object_type: str,
    property_names: list[str] | tuple[str, ...],
) -> tuple[str, ...]:
    normalized_object_type = ensure_object_type_allowed(bundle, object_type)
    allowed = set(searchable_properties_for_object(bundle, normalized_object_type))
    normalized_properties: list[str] = []
    for property_name in property_names:
        normalized_property = _normalize_property_name(property_name)
        if normalized_property is None:
            raise CrmRefError("filter property names must be non-empty strings")
        if normalized_property not in allowed:
            raise CrmRefError(
                f"crm_ref '{bundle.crm_ref}' is not allowed to search property '{normalized_property}' for object_type '{normalized_object_type}'"
            )
        normalized_properties.append(normalized_property)
    return tuple(normalized_properties)


def ensure_sort_properties_allowed(
    bundle: HubSpotCrmBundle,
    object_type: str,
    property_names: list[str] | tuple[str, ...],
) -> tuple[str, ...]:
    normalized_object_type = ensure_object_type_allowed(bundle, object_type)
    allowed = set(sortable_properties_for_object(bundle, normalized_object_type))
    normalized_properties: list[str] = []
    for property_name in property_names:
        normalized_property = _normalize_property_name(property_name)
        if normalized_property is None:
            raise CrmRefError("sort property names must be non-empty strings")
        if normalized_property not in allowed:
            raise CrmRefError(
                f"crm_ref '{bundle.crm_ref}' is not allowed to sort by property '{normalized_property}' for object_type '{normalized_object_type}'"
            )
        normalized_properties.append(normalized_property)
    return tuple(normalized_properties)


def record_id_is_allowed(bundle: HubSpotCrmBundle, object_type: str, record_id: str | None) -> bool:
    normalized_object_type = ensure_object_type_allowed(bundle, object_type)
    normalized_record_id = _normalize_record_id(record_id)
    if normalized_record_id is None:
        return False
    allowed_record_ids = bundle.allowed_record_ids_by_object.get(normalized_object_type)
    if not allowed_record_ids:
        return True
    return normalized_record_id in allowed_record_ids


def ensure_record_allowed(bundle: HubSpotCrmBundle, object_type: str, record_id: str | None) -> str:
    normalized_object_type = ensure_object_type_allowed(bundle, object_type)
    normalized_record_id = _normalize_record_id(record_id)
    if normalized_record_id is None:
        raise CrmRefError(f"crm_ref '{bundle.crm_ref}' requires an explicit record_id")
    if not record_id_is_allowed(bundle, normalized_object_type, normalized_record_id):
        raise CrmRefError(
            f"crm_ref '{bundle.crm_ref}' is not allowed to access record_id '{normalized_record_id}' for object_type '{normalized_object_type}'"
        )
    return normalized_record_id


def _required_string(payload: dict[str, object], field_name: str, *, crm_ref: str, env_key: str) -> str:
    value = _optional_string(payload.get(field_name))
    if value is None:
        raise CrmRefError(
            f"crm_ref '{crm_ref}' is configured via env '{env_key}' but field '{field_name}' is missing"
        )
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_object_type(value: object) -> str | None:
    text = _optional_string(value)
    if text is None:
        return None
    normalized = text.lower()
    if not _OBJECT_TYPE_RE.fullmatch(normalized):
        raise CrmRefError(f"object_type '{text}' is not valid")
    return normalized


def _normalize_property_name(value: object) -> str | None:
    text = _optional_string(value)
    if text is None:
        return None
    normalized = text.lower()
    if not _PROPERTY_RE.fullmatch(normalized):
        raise CrmRefError(f"property '{text}' is not valid")
    return normalized


def _normalize_record_id(value: object) -> str | None:
    text = _optional_string(value)
    if text is None:
        return None
    if not _RECORD_ID_RE.fullmatch(text):
        raise CrmRefError(f"record_id '{text}' is not valid")
    return text


def _object_type_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CrmRefError(f"{field_name} must be an array of object_type strings")
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _normalize_object_type(item)
        if normalized is None:
            raise CrmRefError(f"{field_name} entries must be non-empty object_type strings")
        if normalized not in seen:
            seen.add(normalized)
            items.append(normalized)
    return tuple(items)


def _properties_map(value: object, *, field_name: str) -> dict[str, tuple[str, ...]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CrmRefError(f"{field_name} must be an object keyed by object_type")
    normalized: dict[str, tuple[str, ...]] = {}
    for raw_object_type, raw_properties in value.items():
        object_type = _normalize_object_type(raw_object_type)
        if object_type is None:
            raise CrmRefError(f"{field_name} object_type keys must be non-empty strings")
        if not isinstance(raw_properties, list):
            raise CrmRefError(f"{field_name}.{object_type} must be an array of property names")
        properties: list[str] = []
        seen: set[str] = set()
        for raw_property in raw_properties:
            property_name = _normalize_property_name(raw_property)
            if property_name is None:
                raise CrmRefError(f"{field_name}.{object_type} entries must be non-empty property names")
            if property_name not in seen:
                seen.add(property_name)
                properties.append(property_name)
        if field_name == "allowed_properties_by_object" and not properties:
            raise CrmRefError(f"{field_name}.{object_type} must include at least one property")
        normalized[object_type] = tuple(properties)
    return normalized


def _record_ids_map(value: object, *, field_name: str) -> dict[str, tuple[str, ...]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CrmRefError(f"{field_name} must be an object keyed by object_type")
    normalized: dict[str, tuple[str, ...]] = {}
    for raw_object_type, raw_record_ids in value.items():
        object_type = _normalize_object_type(raw_object_type)
        if object_type is None:
            raise CrmRefError(f"{field_name} object_type keys must be non-empty strings")
        if not isinstance(raw_record_ids, list):
            raise CrmRefError(f"{field_name}.{object_type} must be an array of record ids")
        record_ids: list[str] = []
        seen: set[str] = set()
        for raw_record_id in raw_record_ids:
            record_id = _normalize_record_id(raw_record_id)
            if record_id is None:
                raise CrmRefError(f"{field_name}.{object_type} entries must be non-empty record ids")
            if record_id not in seen:
                seen.add(record_id)
                record_ids.append(record_id)
        normalized[object_type] = tuple(record_ids)
    return normalized


def _ensure_map_keys_subset(
    scoped_map: dict[str, tuple[str, ...]],
    *,
    allowed_object_types: tuple[str, ...],
    field_name: str,
) -> None:
    allowed = set(allowed_object_types)
    extras = sorted(key for key in scoped_map if key not in allowed)
    if extras:
        extra_list = ", ".join(extras)
        raise CrmRefError(f"{field_name} declares unsupported object_type entries: {extra_list}")


def _ensure_map_values_subset(
    scoped_map: dict[str, tuple[str, ...]],
    *,
    allowed_values_by_object: dict[str, tuple[str, ...]],
    field_name: str,
) -> None:
    for object_type, values in scoped_map.items():
        allowed_values = set(allowed_values_by_object.get(object_type, ()))
        extras = sorted(value for value in values if value not in allowed_values)
        if extras:
            extra_list = ", ".join(extras)
            raise CrmRefError(
                f"{field_name}.{object_type} contains properties outside allowed_properties_by_object: {extra_list}"
            )
