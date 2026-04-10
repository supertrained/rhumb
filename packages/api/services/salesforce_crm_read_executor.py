"""Salesforce CRM read-first executor for AUD-18."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote, urlparse

import httpx

from schemas.crm_capabilities import (
    CRM_TEXT_MAX_CHARS,
    SUPPORTED_FILTER_OPERATORS,
    CrmObjectDescribeRequest,
    CrmObjectDescribeResponse,
    CrmPropertyDescriptor,
    CrmRecordGetRequest,
    CrmRecordGetResponse,
    CrmRecordSearchFilter,
    CrmRecordSearchRequest,
    CrmRecordSearchResponse,
    CrmRecordSort,
    CrmRecordSummary,
    ScalarValue,
)
from services.crm_connection_registry import (
    CrmRefError,
    SalesforceCrmBundle,
    allowed_properties_for_object,
    effective_properties_for_object,
    ensure_object_type_allowed,
    ensure_record_allowed,
    ensure_search_filter_properties_allowed,
    ensure_sort_properties_allowed,
    record_id_is_allowed,
    searchable_properties_for_object,
)

SalesforceClientFactory = Callable[..., Any]

_MAX_ERROR_TEXT_CHARS = 500
_DEFAULT_TIMEOUT = 30.0
_SALESFORCE_QUERY_CURSOR_PREFIX = "/services/data/"
_PRIMARY_DISPLAY_FIELD_CANDIDATES = ("Name", "Subject")
_CREATED_AT_FIELD = "CreatedDate"
_UPDATED_AT_FIELDS = ("LastModifiedDate", "SystemModstamp")


@dataclass(slots=True)
class SalesforceCrmExecutorError(RuntimeError):
    code: str
    message: str
    status_code: int = 422

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(frozen=True, slots=True)
class SalesforceAccessToken:
    access_token: str
    instance_url: str


async def describe_object(
    request: CrmObjectDescribeRequest,
    *,
    bundle: SalesforceCrmBundle,
    client_factory: SalesforceClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> CrmObjectDescribeResponse:
    try:
        object_type = ensure_object_type_allowed(bundle, request.object_type)
    except CrmRefError as exc:
        raise SalesforceCrmExecutorError(
            code="crm_object_scope_denied",
            message=str(exc),
            status_code=403,
        ) from exc

    token = await _refresh_access_token(bundle=bundle, client_factory=client_factory)
    payload = await _salesforce_request_json(
        "GET",
        f"/services/data/{bundle.api_version}/sobjects/{quote(object_type, safe='')}/describe",
        bundle=bundle,
        token=token,
        params=None,
        json_body=None,
        client_factory=client_factory,
        not_found_code="crm_object_not_found",
        not_found_message=f"Salesforce CRM object_type '{object_type}' not found",
        not_found_status=404,
    )

    if not isinstance(payload, dict):
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message="Salesforce CRM schema response was not a JSON object",
            status_code=503,
        )

    allowed_properties = allowed_properties_for_object(bundle, object_type)
    searchable = set(searchable_properties_for_object(bundle, object_type))
    sortable = set(bundle.sortable_properties_by_object.get(object_type) or allowed_properties)
    descriptors_by_name: dict[str, CrmPropertyDescriptor] = {}
    for item in _describe_fields(payload):
        field_name = _field_name(item)
        if field_name is None or field_name not in allowed_properties:
            continue
        descriptors_by_name[field_name] = CrmPropertyDescriptor(
            name=field_name,
            label=_clean_text(item.get("label")),
            type=_clean_text(item.get("type")),
            field_type=_clean_text(item.get("soapType") or item.get("soapTypeInfo")),
            searchable=field_name in searchable and bool(item.get("filterable") is True),
            sortable=field_name in sortable and bool(item.get("sortable") is True),
            read_only=bool(
                item.get("updateable") is False
                or item.get("calculated") is True
                or item.get("autoNumber") is True
            ),
            archived=False,
        )

    descriptors = [
        descriptors_by_name[property_name]
        for property_name in allowed_properties
        if property_name in descriptors_by_name
    ]
    required_properties = [
        descriptor.name
        for descriptor in descriptors
        if _is_required_field(payload_by_name=descriptors_by_name, raw_fields=_describe_fields(payload), name=descriptor.name)
    ]

    return CrmObjectDescribeResponse(
        provider_used="salesforce",
        credential_mode="byok",
        capability_id="crm.object.describe",
        receipt_id=receipt_id,
        execution_id=execution_id,
        crm_ref=bundle.crm_ref,
        object_type=object_type,
        portal_id=None,
        label=_clean_text(payload.get("label")),
        plural_label=_clean_text(payload.get("labelPlural") or payload.get("label_plural")),
        primary_display_property=_primary_display_property(descriptors=descriptors, raw_fields=_describe_fields(payload)),
        required_properties=required_properties,
        properties=descriptors,
        property_count_returned=len(descriptors),
    )


async def search_records(
    request: CrmRecordSearchRequest,
    *,
    bundle: SalesforceCrmBundle,
    client_factory: SalesforceClientFactory = httpx.AsyncClient,
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

    token = await _refresh_access_token(bundle=bundle, client_factory=client_factory)
    if request.after:
        if request.query or request.filters or request.sorts or request.property_names is not None:
            raise SalesforceCrmExecutorError(
                code="crm_request_invalid",
                message="Salesforce pagination cursors must be replayed without query, filters, sorts, or property_names",
                status_code=400,
            )
        path = _validated_next_records_path(bundle, request.after)
        payload = await _salesforce_request_json(
            "GET",
            path,
            bundle=bundle,
            token=token,
            params=None,
            json_body=None,
            client_factory=client_factory,
            not_found_code="crm_object_not_found",
            not_found_message=f"Salesforce CRM object_type '{object_type}' not found",
            not_found_status=404,
        )
    else:
        payload = await _salesforce_request_json(
            "GET",
            f"/services/data/{bundle.api_version}/query",
            bundle=bundle,
            token=token,
            params={"q": _build_search_soql(request=request, bundle=bundle, object_type=object_type, property_names=property_names)},
            json_body=None,
            client_factory=client_factory,
            not_found_code="crm_object_not_found",
            not_found_message=f"Salesforce CRM object_type '{object_type}' not found",
            not_found_status=404,
        )

    if not isinstance(payload, dict):
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message="Salesforce CRM search response was not a JSON object",
            status_code=503,
        )

    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message="Salesforce CRM search response was missing records",
            status_code=503,
        )

    records: list[CrmRecordSummary] = []
    for item in raw_records:
        if not isinstance(item, dict):
            continue
        record_id = _record_id(item)
        if record_id is None or not record_id_is_allowed(bundle, object_type, record_id):
            continue
        records.append(_build_record_summary(item, property_names=property_names))

    return CrmRecordSearchResponse(
        provider_used="salesforce",
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
    bundle: SalesforceCrmBundle,
    client_factory: SalesforceClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> CrmRecordGetResponse:
    try:
        object_type = ensure_object_type_allowed(bundle, request.object_type)
        property_names = effective_properties_for_object(bundle, object_type, request.property_names)
        record_id = ensure_record_allowed(bundle, object_type, request.record_id)
    except CrmRefError as exc:
        raise _scope_error(exc) from exc

    token = await _refresh_access_token(bundle=bundle, client_factory=client_factory)
    payload = await _salesforce_request_json(
        "GET",
        f"/services/data/{bundle.api_version}/query",
        bundle=bundle,
        token=token,
        params={"q": _build_get_soql(bundle=bundle, object_type=object_type, record_id=record_id, property_names=property_names)},
        json_body=None,
        client_factory=client_factory,
        not_found_code="crm_object_not_found",
        not_found_message=f"Salesforce CRM object_type '{object_type}' not found",
        not_found_status=404,
    )

    if not isinstance(payload, dict):
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message="Salesforce CRM record response was not a JSON object",
            status_code=503,
        )
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message="Salesforce CRM record response was missing records",
            status_code=503,
        )
    if not raw_records:
        raise SalesforceCrmExecutorError(
            code="crm_record_not_found",
            message=f"Salesforce CRM record '{record_id}' not found",
            status_code=404,
        )

    summary = _build_record_summary(raw_records[0], property_names=property_names)
    if not record_id_is_allowed(bundle, object_type, summary.record_id):
        raise SalesforceCrmExecutorError(
            code="crm_record_scope_denied",
            message=(
                f"crm_ref '{bundle.crm_ref}' is not allowed to access record_id "
                f"'{summary.record_id}' for object_type '{object_type}'"
            ),
            status_code=403,
        )
    return CrmRecordGetResponse(
        provider_used="salesforce",
        credential_mode="byok",
        capability_id="crm.record.get",
        receipt_id=receipt_id,
        execution_id=execution_id,
        crm_ref=bundle.crm_ref,
        object_type=object_type,
        record_id=summary.record_id,
        archived=False,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        properties=summary.properties,
    )


async def _refresh_access_token(
    *,
    bundle: SalesforceCrmBundle,
    client_factory: SalesforceClientFactory,
) -> SalesforceAccessToken:
    try:
        async with client_factory(base_url=bundle.auth_base_url, timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.request(
                "POST",
                "/services/oauth2/token",
                headers={"Accept": "application/json"},
                data={
                    "grant_type": "refresh_token",
                    "client_id": bundle.client_id,
                    "client_secret": bundle.client_secret,
                    "refresh_token": bundle.refresh_token,
                },
            )
    except httpx.HTTPError as exc:
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message=str(exc) or "Salesforce token refresh failed",
            status_code=503,
        ) from exc

    payload = _safe_json(response)
    if response.status_code in {400, 401, 403}:
        raise SalesforceCrmExecutorError(
            code="crm_access_denied",
            message="Salesforce denied access with the provided crm_ref credentials",
            status_code=403,
        )
    if response.status_code >= 500:
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message="Salesforce token endpoint returned an upstream error",
            status_code=503,
        )
    if response.status_code >= 400:
        message = f"Salesforce token refresh failed with status {response.status_code}"
        error_text = _provider_error_text(response, payload)
        if error_text:
            message = f"{message}: {error_text}"
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message=message[:_MAX_ERROR_TEXT_CHARS],
            status_code=502,
        )
    if not isinstance(payload, dict):
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message="Salesforce token response was not a JSON object",
            status_code=503,
        )

    access_token = _clean_text(payload.get("access_token"))
    instance_url = _clean_text(payload.get("instance_url"))
    if not access_token or not instance_url:
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message="Salesforce token response was missing access_token or instance_url",
            status_code=503,
        )
    return SalesforceAccessToken(access_token=access_token, instance_url=instance_url.rstrip("/"))


async def _salesforce_request_json(
    method: str,
    path: str,
    *,
    bundle: SalesforceCrmBundle,
    token: SalesforceAccessToken,
    params: dict[str, Any] | None,
    json_body: dict[str, Any] | None,
    client_factory: SalesforceClientFactory,
    not_found_code: str,
    not_found_message: str,
    not_found_status: int,
) -> Any:
    try:
        async with client_factory(
            base_url=token.instance_url,
            headers=_build_headers(token),
            timeout=_DEFAULT_TIMEOUT,
        ) as client:
            response = await client.request(method, path, params=params, json=json_body)
    except httpx.HTTPError as exc:
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message=str(exc) or "Salesforce request failed",
            status_code=503,
        ) from exc

    payload = _safe_json(response)
    error_text = _provider_error_text(response, payload)
    error_code = _provider_error_code(payload)

    if response.status_code == 404 or error_code == "INVALID_TYPE":
        raise SalesforceCrmExecutorError(not_found_code, not_found_message, not_found_status)
    if response.status_code == 429 or error_code == "REQUEST_LIMIT_EXCEEDED":
        raise SalesforceCrmExecutorError(
            code="crm_rate_limited",
            message="Salesforce rate limited the request",
            status_code=429,
        )
    if response.status_code in {401, 403}:
        raise SalesforceCrmExecutorError(
            code="crm_access_denied",
            message="Salesforce denied access with the provided crm_ref credentials",
            status_code=response.status_code,
        )
    if error_code == "INVALID_QUERY_LOCATOR":
        raise SalesforceCrmExecutorError(
            code="crm_request_invalid",
            message="Salesforce pagination cursor is invalid or expired",
            status_code=400,
        )
    if response.status_code >= 500:
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message="Salesforce upstream error",
            status_code=503,
        )
    if response.status_code >= 400:
        message = f"Salesforce request failed with status {response.status_code}"
        if error_text:
            message = f"{message}: {error_text}"
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message=message[:_MAX_ERROR_TEXT_CHARS],
            status_code=502,
        )

    return payload


def _build_headers(token: SalesforceAccessToken) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token.access_token}",
        "Content-Type": "application/json",
    }


def _build_search_soql(
    *,
    request: CrmRecordSearchRequest,
    bundle: SalesforceCrmBundle,
    object_type: str,
    property_names: tuple[str, ...],
) -> str:
    selected_fields = _selected_fields(bundle=bundle, object_type=object_type, property_names=property_names)
    clauses = _search_where_clauses(request=request, bundle=bundle, object_type=object_type)
    order_by = _order_by_clause(request.sorts)
    soql = f"SELECT {', '.join(selected_fields)} FROM {object_type}"
    if clauses:
        soql += " WHERE " + " AND ".join(clauses)
    if order_by:
        soql += f" ORDER BY {order_by}"
    soql += f" LIMIT {min(max(request.limit, 1), 25)}"
    return soql


def _build_get_soql(
    *,
    bundle: SalesforceCrmBundle,
    object_type: str,
    record_id: str,
    property_names: tuple[str, ...],
) -> str:
    selected_fields = _selected_fields(bundle=bundle, object_type=object_type, property_names=property_names)
    return (
        f"SELECT {', '.join(selected_fields)} FROM {object_type} "
        f"WHERE Id = {_soql_literal(record_id)} LIMIT 1"
    )


def _selected_fields(
    *,
    bundle: SalesforceCrmBundle,
    object_type: str,
    property_names: tuple[str, ...],
) -> tuple[str, ...]:
    selected: list[str] = ["Id"]
    for field_name in property_names:
        if field_name not in selected:
            selected.append(field_name)
    for metadata_field in (_CREATED_AT_FIELD, *_UPDATED_AT_FIELDS):
        if metadata_field in bundle.allowed_properties_by_object.get(object_type, ()) and metadata_field not in selected:
            selected.append(metadata_field)
    return tuple(selected)


def _search_where_clauses(
    *,
    request: CrmRecordSearchRequest,
    bundle: SalesforceCrmBundle,
    object_type: str,
) -> list[str]:
    clauses: list[str] = []
    if request.query:
        searchable_fields = searchable_properties_for_object(bundle, object_type)
        if not searchable_fields:
            raise SalesforceCrmExecutorError(
                code="crm_request_invalid",
                message=f"crm_ref '{bundle.crm_ref}' does not declare searchable properties for object_type '{object_type}'",
                status_code=400,
            )
        like_value = _escape_like_literal(request.query)
        clauses.append(
            "(" + " OR ".join(
                f"{field_name} LIKE {_soql_literal(f'%{like_value}%')}"
                for field_name in searchable_fields
            ) + ")"
        )
    for filter_ in request.filters:
        clauses.append(_filter_clause(filter_))
    allowed_record_ids = bundle.allowed_record_ids_by_object.get(object_type)
    if allowed_record_ids:
        record_ids = ", ".join(_soql_literal(record_id) for record_id in allowed_record_ids)
        clauses.append(f"Id IN ({record_ids})")
    return clauses


def _filter_clause(filter_: CrmRecordSearchFilter) -> str:
    if filter_.operator not in SUPPORTED_FILTER_OPERATORS:
        raise SalesforceCrmExecutorError(
            code="crm_request_invalid",
            message=f"Unsupported filter operator '{filter_.operator}'",
            status_code=400,
        )
    if filter_.operator == "EQ":
        return f"{filter_.property} = {_soql_literal(filter_.value)}"
    if filter_.operator == "NEQ":
        return f"{filter_.property} != {_soql_literal(filter_.value)}"
    if filter_.operator == "LT":
        return f"{filter_.property} < {_soql_literal(filter_.value)}"
    if filter_.operator == "LTE":
        return f"{filter_.property} <= {_soql_literal(filter_.value)}"
    if filter_.operator == "GT":
        return f"{filter_.property} > {_soql_literal(filter_.value)}"
    if filter_.operator == "GTE":
        return f"{filter_.property} >= {_soql_literal(filter_.value)}"
    if filter_.operator == "CONTAINS_TOKEN":
        return f"{filter_.property} LIKE {_soql_literal(f'%{_escape_like_literal(filter_.value)}%')}"
    if filter_.operator == "HAS_PROPERTY":
        return f"{filter_.property} != null"
    if filter_.operator == "NOT_HAS_PROPERTY":
        return f"{filter_.property} = null"
    raise SalesforceCrmExecutorError(
        code="crm_request_invalid",
        message=f"Unsupported filter operator '{filter_.operator}'",
        status_code=400,
    )


def _order_by_clause(sorts: list[CrmRecordSort]) -> str | None:
    if not sorts:
        return None
    items: list[str] = []
    for sort in sorts:
        if sort.direction not in {"asc", "desc"}:
            raise SalesforceCrmExecutorError(
                code="crm_request_invalid",
                message=f"Unsupported sort direction '{sort.direction}'",
                status_code=400,
            )
        items.append(f"{sort.property} {sort.direction.upper()}")
    return ", ".join(items)


def _soql_literal(value: ScalarValue) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SalesforceCrmExecutorError(
                code="crm_request_invalid",
                message="Numeric filter values must be finite",
                status_code=400,
            )
        return format(value, "g")
    text = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"


def _escape_like_literal(value: ScalarValue) -> str:
    return str(value or "").replace("%", "\\%").replace("_", "\\_")


def _describe_fields(payload: dict[str, Any]) -> list[dict[str, Any]]:
    fields = payload.get("fields")
    if not isinstance(fields, list):
        raise SalesforceCrmExecutorError(
            code="crm_provider_unavailable",
            message="Salesforce CRM schema response was missing fields",
            status_code=503,
        )
    return [item for item in fields if isinstance(item, dict)]


def _is_required_field(
    *,
    payload_by_name: dict[str, CrmPropertyDescriptor],
    raw_fields: list[dict[str, Any]],
    name: str,
) -> bool:
    if name not in payload_by_name:
        return False
    for field in raw_fields:
        if _field_name(field) != name:
            continue
        return bool(field.get("nillable") is False and field.get("defaultedOnCreate") is False)
    return False


def _primary_display_property(
    *,
    descriptors: list[CrmPropertyDescriptor],
    raw_fields: list[dict[str, Any]],
) -> str | None:
    for field in raw_fields:
        field_name = _field_name(field)
        if field_name and field.get("nameField") is True:
            return field_name
    allowed = {descriptor.name for descriptor in descriptors}
    for candidate in _PRIMARY_DISPLAY_FIELD_CANDIDATES:
        if candidate in allowed:
            return candidate
    return descriptors[0].name if descriptors else None


def _build_record_summary(item: dict[str, Any], *, property_names: tuple[str, ...]) -> CrmRecordSummary:
    properties: dict[str, ScalarValue] = {}
    for property_name in property_names:
        if property_name not in item:
            continue
        properties[property_name] = _clean_scalar(item.get(property_name))

    created_at = _clean_text(item.get(_CREATED_AT_FIELD))
    updated_at = None
    for field_name in _UPDATED_AT_FIELDS:
        updated_at = _clean_text(item.get(field_name))
        if updated_at:
            break
    return CrmRecordSummary(
        record_id=_record_id(item) or "unknown",
        archived=False,
        created_at=created_at,
        updated_at=updated_at,
        properties=properties,
    )


def _field_name(item: dict[str, Any]) -> str | None:
    value = item.get("name")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _record_id(item: dict[str, Any]) -> str | None:
    value = item.get("Id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _next_after(payload: dict[str, Any]) -> str | None:
    next_path = payload.get("nextRecordsUrl")
    if not isinstance(next_path, str):
        return None
    normalized = next_path.strip()
    return normalized or None


def _validated_next_records_path(bundle: SalesforceCrmBundle, value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise SalesforceCrmExecutorError(
            code="crm_request_invalid",
            message="Salesforce pagination cursor must be a relative nextRecordsUrl path",
            status_code=400,
        )
    path = parsed.path or ""
    required_prefix = f"{_SALESFORCE_QUERY_CURSOR_PREFIX}{bundle.api_version}/query/"
    if not path.startswith(required_prefix):
        raise SalesforceCrmExecutorError(
            code="crm_request_invalid",
            message="Salesforce pagination cursor must target the current api_version query path",
            status_code=400,
        )
    return path


def _provider_error_code(payload: Any) -> str | None:
    first_error = _first_error(payload)
    if not isinstance(first_error, dict):
        return None
    code = first_error.get("errorCode") or first_error.get("error")
    return _clean_text(code)


def _provider_error_text(response: Any, payload: Any) -> str | None:
    first_error = _first_error(payload)
    if isinstance(first_error, dict):
        message = _clean_text(first_error.get("message") or first_error.get("error_description"))
        if message:
            return message
    text = _clean_text(getattr(response, "text", None))
    return text[:_MAX_ERROR_TEXT_CHARS] if text else None


def _first_error(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    if isinstance(payload, dict):
        return payload
    return None


def _safe_json(response: Any) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:CRM_TEXT_MAX_CHARS]


def _clean_scalar(value: Any) -> ScalarValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return _clean_text(value)


def _scope_error(exc: CrmRefError) -> SalesforceCrmExecutorError:
    message = str(exc)
    if "record_id" in message:
        return SalesforceCrmExecutorError(
            code="crm_record_scope_denied",
            message=message,
            status_code=403,
        )
    if "search property" in message or "sort by property" in message or "property '" in message:
        return SalesforceCrmExecutorError(
            code="crm_property_scope_denied",
            message=message,
            status_code=403,
        )
    return SalesforceCrmExecutorError(
        code="crm_object_scope_denied",
        message=message,
        status_code=403,
    )
