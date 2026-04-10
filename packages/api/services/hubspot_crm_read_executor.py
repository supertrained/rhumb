"""HubSpot CRM read-first executor for AUD-18."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote

import httpx

from schemas.crm_capabilities import (
    CRM_PROPERTY_NAME_MAX_CHARS,
    CRM_TEXT_MAX_CHARS,
    SUPPORTED_FILTER_OPERATORS,
    CrmObjectDescribeRequest,
    CrmObjectDescribeResponse,
    CrmRecordGetRequest,
    CrmRecordGetResponse,
    CrmRecordSearchFilter,
    CrmRecordSearchRequest,
    CrmRecordSearchResponse,
    CrmRecordSort,
    HubSpotCrmPropertyDescriptor,
    HubSpotCrmRecordSummary,
    ScalarValue,
)
from services.crm_connection_registry import (
    CrmRefError,
    HubSpotCrmBundle,
    allowed_properties_for_object,
    effective_properties_for_object,
    ensure_object_type_allowed,
    ensure_record_allowed,
    ensure_search_filter_properties_allowed,
    ensure_sort_properties_allowed,
    record_id_is_allowed,
    searchable_properties_for_object,
    sortable_properties_for_object,
)

HubSpotClientFactory = Callable[..., Any]

_HUBSPOT_BASE_URL = "https://api.hubapi.com"
_MAX_ERROR_TEXT_CHARS = 500
_OBJECT_METADATA_FALLBACKS: dict[str, dict[str, str]] = {
    "contacts": {
        "label": "Contact",
        "plural_label": "Contacts",
        "primary_display_property": "email",
    },
    "companies": {
        "label": "Company",
        "plural_label": "Companies",
        "primary_display_property": "name",
    },
    "deals": {
        "label": "Deal",
        "plural_label": "Deals",
        "primary_display_property": "dealname",
    },
    "tickets": {
        "label": "Ticket",
        "plural_label": "Tickets",
        "primary_display_property": "subject",
    },
}


@dataclass(slots=True)
class HubSpotCrmExecutorError(RuntimeError):
    code: str
    message: str
    status_code: int = 422

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


async def describe_object(
    request: CrmObjectDescribeRequest,
    *,
    bundle: HubSpotCrmBundle,
    client_factory: HubSpotClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> CrmObjectDescribeResponse:
    try:
        object_type = ensure_object_type_allowed(bundle, request.object_type)
    except CrmRefError as exc:
        raise HubSpotCrmExecutorError(
            code="crm_object_scope_denied",
            message=str(exc),
            status_code=403,
        ) from exc

    payload = await _hubspot_request_json(
        "GET",
        f"/crm/v3/properties/{quote(object_type, safe='')}",
        bundle=bundle,
        params=None,
        json_body=None,
        client_factory=client_factory,
        not_found_code="crm_object_not_found",
        not_found_message=f"HubSpot CRM object_type '{object_type}' not found",
        not_found_status=404,
    )

    if not isinstance(payload, dict):
        raise HubSpotCrmExecutorError(
            code="crm_provider_unavailable",
            message="HubSpot CRM schema response was not a JSON object",
            status_code=503,
        )

    allowed_properties = allowed_properties_for_object(bundle, object_type)
    searchable = set(searchable_properties_for_object(bundle, object_type))
    sortable = set(sortable_properties_for_object(bundle, object_type))
    descriptors_by_name: dict[str, HubSpotCrmPropertyDescriptor] = {}
    for item in _schema_properties(payload):
        property_name = _property_name(item)
        if property_name is None or property_name not in allowed_properties:
            continue
        descriptors_by_name[property_name] = HubSpotCrmPropertyDescriptor(
            name=property_name,
            label=_clean_text(item.get("label")),
            type=_clean_text(item.get("type")),
            field_type=_clean_text(item.get("fieldType") or item.get("field_type")),
            searchable=property_name in searchable,
            sortable=property_name in sortable,
            read_only=_read_only(item),
            archived=bool(item.get("archived") is True),
        )

    descriptors = [
        descriptors_by_name[property_name]
        for property_name in allowed_properties
        if property_name in descriptors_by_name
    ]

    singular_label, plural_label = _schema_labels(payload, object_type=object_type)
    primary_display_property = _primary_display_property(
        payload,
        object_type=object_type,
        allowed_properties=allowed_properties,
        descriptors=descriptors,
    )
    return CrmObjectDescribeResponse(
        provider_used="hubspot",
        credential_mode="byok",
        capability_id="crm.object.describe",
        receipt_id=receipt_id,
        execution_id=execution_id,
        crm_ref=bundle.crm_ref,
        object_type=object_type,
        portal_id=bundle.portal_id,
        label=singular_label,
        plural_label=plural_label,
        primary_display_property=primary_display_property,
        required_properties=_property_name_list(
            payload.get("requiredProperties") or payload.get("required_properties")
        ),
        properties=descriptors,
        property_count_returned=len(descriptors),
    )


async def search_records(
    request: CrmRecordSearchRequest,
    *,
    bundle: HubSpotCrmBundle,
    client_factory: HubSpotClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> CrmRecordSearchResponse:
    try:
        object_type = ensure_object_type_allowed(bundle, request.object_type)
        property_names = effective_properties_for_object(bundle, object_type, request.property_names)
        ensure_search_filter_properties_allowed(
            bundle,
            object_type,
            [flt.property for flt in request.filters],
        )
        ensure_sort_properties_allowed(
            bundle,
            object_type,
            [sort.property for sort in request.sorts],
        )
    except CrmRefError as exc:
        raise _scope_error(exc) from exc

    payload = await _hubspot_request_json(
        "POST",
        f"/crm/v3/objects/{quote(object_type, safe='')}/search",
        bundle=bundle,
        params=None,
        json_body=_build_search_body(request=request, property_names=property_names),
        client_factory=client_factory,
        not_found_code="crm_object_not_found",
        not_found_message=f"HubSpot CRM object_type '{object_type}' not found",
        not_found_status=404,
    )

    if not isinstance(payload, dict):
        raise HubSpotCrmExecutorError(
            code="crm_provider_unavailable",
            message="HubSpot CRM search response was not a JSON object",
            status_code=503,
        )

    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise HubSpotCrmExecutorError(
            code="crm_provider_unavailable",
            message="HubSpot CRM search response was missing results",
            status_code=503,
        )

    records: list[HubSpotCrmRecordSummary] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        record_id = _record_id(item)
        if record_id is None:
            continue
        if not record_id_is_allowed(bundle, object_type, record_id):
            continue
        records.append(_build_record_summary(item, property_names=property_names))

    return CrmRecordSearchResponse(
        provider_used="hubspot",
        credential_mode="byok",
        capability_id="crm.record.search",
        receipt_id=receipt_id,
        execution_id=execution_id,
        crm_ref=bundle.crm_ref,
        object_type=object_type,
        records=records,
        record_count_returned=len(records),
        next_after=_next_after(payload),
    )


async def get_record(
    request: CrmRecordGetRequest,
    *,
    bundle: HubSpotCrmBundle,
    client_factory: HubSpotClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> CrmRecordGetResponse:
    try:
        object_type = ensure_object_type_allowed(bundle, request.object_type)
        property_names = effective_properties_for_object(bundle, object_type, request.property_names)
        record_id = ensure_record_allowed(bundle, object_type, request.record_id)
    except CrmRefError as exc:
        raise _scope_error(exc) from exc

    payload = await _hubspot_request_json(
        "GET",
        f"/crm/v3/objects/{quote(object_type, safe='')}/{quote(record_id, safe='')}",
        bundle=bundle,
        params={"properties": ",".join(property_names)} if property_names else None,
        json_body=None,
        client_factory=client_factory,
        not_found_code="crm_record_not_found",
        not_found_message=f"HubSpot CRM record '{record_id}' not found",
        not_found_status=404,
    )

    if not isinstance(payload, dict) or _record_id(payload) is None:
        raise HubSpotCrmExecutorError(
            code="crm_provider_unavailable",
            message="HubSpot CRM record response was missing record payload",
            status_code=503,
        )

    returned_record_id = _record_id(payload) or record_id
    if not record_id_is_allowed(bundle, object_type, returned_record_id):
        raise HubSpotCrmExecutorError(
            code="crm_record_scope_denied",
            message=(
                f"crm_ref '{bundle.crm_ref}' is not allowed to access record_id "
                f"'{returned_record_id}' for object_type '{object_type}'"
            ),
            status_code=403,
        )

    summary = _build_record_summary(payload, property_names=property_names)
    return CrmRecordGetResponse(
        provider_used="hubspot",
        credential_mode="byok",
        capability_id="crm.record.get",
        receipt_id=receipt_id,
        execution_id=execution_id,
        crm_ref=bundle.crm_ref,
        object_type=object_type,
        record_id=summary.record_id,
        archived=summary.archived,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        properties=summary.properties,
    )


async def _hubspot_request_json(
    method: str,
    path: str,
    *,
    bundle: HubSpotCrmBundle,
    params: dict[str, Any] | None,
    json_body: dict[str, Any] | None,
    client_factory: HubSpotClientFactory,
    not_found_code: str,
    not_found_message: str,
    not_found_status: int,
) -> Any:
    headers = _build_headers(bundle)
    try:
        async with client_factory(base_url=_HUBSPOT_BASE_URL, headers=headers, timeout=30.0) as client:
            response = await client.request(method, path, params=params, json=json_body)
    except httpx.HTTPError as exc:
        raise HubSpotCrmExecutorError(
            code="crm_provider_unavailable",
            message=str(exc) or "HubSpot request failed",
            status_code=503,
        ) from exc

    error_text = _response_error_text(response)
    if response.status_code == 404:
        raise HubSpotCrmExecutorError(not_found_code, not_found_message, not_found_status)
    if response.status_code == 429:
        raise HubSpotCrmExecutorError(
            code="crm_rate_limited",
            message="HubSpot rate limited the request",
            status_code=429,
        )
    if response.status_code in {401, 403}:
        raise HubSpotCrmExecutorError(
            code="crm_access_denied",
            message="HubSpot denied access with the provided crm_ref credentials",
            status_code=response.status_code,
        )
    if response.status_code >= 500:
        raise HubSpotCrmExecutorError(
            code="crm_provider_unavailable",
            message="HubSpot upstream error",
            status_code=503,
        )
    if response.status_code >= 400:
        message = f"HubSpot request failed with status {response.status_code}"
        if error_text:
            message = f"{message}: {error_text}"
        raise HubSpotCrmExecutorError(
            code="crm_provider_unavailable",
            message=message[:_MAX_ERROR_TEXT_CHARS],
            status_code=502,
        )

    try:
        return response.json()
    except ValueError as exc:
        raise HubSpotCrmExecutorError(
            code="crm_provider_unavailable",
            message="HubSpot returned invalid JSON",
            status_code=503,
        ) from exc


def _build_headers(bundle: HubSpotCrmBundle) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {bundle.private_app_token}",
        "Content-Type": "application/json",
    }


def _build_search_body(*, request: CrmRecordSearchRequest, property_names: tuple[str, ...]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "limit": min(max(request.limit, 1), 25),
        "properties": list(property_names),
    }
    if request.after:
        body["after"] = request.after
    if request.query:
        body["query"] = request.query
    if request.filters:
        body["filterGroups"] = [{"filters": [_serialize_filter(filter_) for filter_ in request.filters]}]
    if request.sorts:
        body["sorts"] = [_serialize_sort(sort) for sort in request.sorts]
    return body


def _serialize_filter(filter_: CrmRecordSearchFilter) -> dict[str, Any]:
    if filter_.operator not in SUPPORTED_FILTER_OPERATORS:
        raise HubSpotCrmExecutorError(
            code="crm_request_invalid",
            message=f"Unsupported filter operator '{filter_.operator}'",
            status_code=400,
        )
    payload: dict[str, Any] = {
        "propertyName": filter_.property,
        "operator": filter_.operator,
    }
    if filter_.value is not None:
        payload["value"] = filter_.value
    return payload


def _serialize_sort(sort: CrmRecordSort) -> str:
    if sort.direction not in {"asc", "desc"}:
        raise HubSpotCrmExecutorError(
            code="crm_request_invalid",
            message=f"Unsupported sort direction '{sort.direction}'",
            status_code=400,
        )
    prefix = "-" if sort.direction == "desc" else ""
    return f"{prefix}{sort.property}"


def _schema_properties(payload: dict[str, Any]) -> list[dict[str, Any]]:
    properties = payload.get("properties")
    if not isinstance(properties, list):
        properties = payload.get("results")
    if not isinstance(properties, list):
        raise HubSpotCrmExecutorError(
            code="crm_provider_unavailable",
            message="HubSpot CRM schema response was missing properties",
            status_code=503,
        )
    return [item for item in properties if isinstance(item, dict)]


def _schema_labels(payload: dict[str, Any], *, object_type: str) -> tuple[str | None, str | None]:
    labels = payload.get("labels")
    if isinstance(labels, dict):
        singular = _clean_text(labels.get("singular"))
        plural = _clean_text(labels.get("plural"))
        if singular or plural:
            return singular, plural
    singular = _clean_text(payload.get("label"))
    plural = _clean_text(payload.get("pluralLabel"))
    if singular or plural:
        return singular, plural
    fallback = _OBJECT_METADATA_FALLBACKS.get(object_type, {})
    return _clean_text(fallback.get("label")), _clean_text(fallback.get("plural_label"))


def _primary_display_property(
    payload: dict[str, Any],
    *,
    object_type: str,
    allowed_properties: tuple[str, ...],
    descriptors: list[HubSpotCrmPropertyDescriptor],
) -> str | None:
    explicit = _clean_property_name(payload.get("primaryDisplayProperty") or payload.get("primary_display_property"))
    if explicit:
        return explicit
    fallback = _clean_property_name(_OBJECT_METADATA_FALLBACKS.get(object_type, {}).get("primary_display_property"))
    if fallback and fallback in allowed_properties:
        return fallback
    if descriptors:
        return descriptors[0].name
    return allowed_properties[0] if allowed_properties else None


def _build_record_summary(item: dict[str, Any], *, property_names: tuple[str, ...]) -> HubSpotCrmRecordSummary:
    raw_properties = item.get("properties")
    property_payload = raw_properties if isinstance(raw_properties, dict) else {}
    cleaned_properties: dict[str, ScalarValue] = {}
    for property_name in property_names:
        if property_name not in property_payload:
            continue
        cleaned_properties[property_name] = _clean_scalar(property_payload.get(property_name))

    return HubSpotCrmRecordSummary(
        record_id=_record_id(item) or "unknown",
        archived=bool(item.get("archived") is True),
        created_at=_clean_text(item.get("createdAt") or item.get("created_at")),
        updated_at=_clean_text(item.get("updatedAt") or item.get("updated_at")),
        properties=cleaned_properties,
    )


def _property_name(item: dict[str, Any]) -> str | None:
    value = item.get("name")
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _record_id(item: dict[str, Any]) -> str | None:
    value = item.get("id")
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _next_after(payload: dict[str, Any]) -> str | None:
    paging = payload.get("paging")
    if not isinstance(paging, dict):
        return None
    next_page = paging.get("next")
    if not isinstance(next_page, dict):
        return None
    after = next_page.get("after")
    if after is None:
        return None
    normalized = str(after).strip()
    return normalized or None


def _scope_error(exc: CrmRefError) -> HubSpotCrmExecutorError:
    message = str(exc)
    if "record_id" in message:
        return HubSpotCrmExecutorError(
            code="crm_record_scope_denied",
            message=message,
            status_code=403,
        )
    if "search property" in message or "sort by property" in message or "property '" in message:
        return HubSpotCrmExecutorError(
            code="crm_property_scope_denied",
            message=message,
            status_code=403,
        )
    return HubSpotCrmExecutorError(
        code="crm_object_scope_denied",
        message=message,
        status_code=403,
    )


def _response_error_text(response: Any) -> str:
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message")
        if message:
            return str(message)[:_MAX_ERROR_TEXT_CHARS]
    text = getattr(response, "text", None)
    if not text:
        return ""
    return str(text).strip()[:_MAX_ERROR_TEXT_CHARS]


def _property_name_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _clean_property_name(item)
        if text and text not in seen:
            seen.add(text)
            cleaned.append(text)
    return cleaned


def _read_only(item: dict[str, Any]) -> bool:
    modification_metadata = item.get("modificationMetadata") or item.get("modification_metadata")
    return bool(
        item.get("readOnlyValue") is True
        or item.get("readOnlyDefinition") is True
        or item.get("calculated") is True
        or (
            isinstance(modification_metadata, dict)
            and (
                modification_metadata.get("readOnlyDefinition") is True
                or modification_metadata.get("readOnlyValue") is True
            )
        )
    )


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:CRM_TEXT_MAX_CHARS] if text else None


def _clean_property_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    return text[:CRM_PROPERTY_NAME_MAX_CHARS]


def _clean_scalar(value: Any) -> ScalarValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str):
            return value[:CRM_TEXT_MAX_CHARS]
        return value
    return str(value)[:CRM_TEXT_MAX_CHARS]
