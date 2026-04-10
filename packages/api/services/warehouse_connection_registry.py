"""warehouse_ref registry helpers for the AUD-18 BigQuery read-first wedge."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from schemas.warehouse_capabilities import (
    WAREHOUSE_QUERY_DEFAULT_MAX_BYTES_BILLED,
    WAREHOUSE_QUERY_DEFAULT_ROWS,
    WAREHOUSE_QUERY_DEFAULT_TIMEOUT_MS,
    WAREHOUSE_QUERY_MAX_MAX_BYTES_BILLED,
    WAREHOUSE_QUERY_MAX_ROWS,
    WAREHOUSE_QUERY_MAX_TIMEOUT_MS,
    WAREHOUSE_REF_PATTERN,
    WAREHOUSE_RESULT_MAX_BYTES,
    WAREHOUSE_SCHEMA_MAX_COLUMNS,
    WAREHOUSE_SCHEMA_MAX_DATASETS,
    WAREHOUSE_SCHEMA_MAX_TABLES,
    dataset_ref_for_table,
    normalize_dataset_ref,
    normalize_table_ref,
)

_WAREHOUSE_REF_RE = re.compile(WAREHOUSE_REF_PATTERN)


class WarehouseRefError(ValueError):
    """Raised when a warehouse_ref cannot be resolved or used safely."""


@dataclass(frozen=True, slots=True)
class BigQueryWarehouseBundle:
    warehouse_ref: str
    provider: str
    auth_mode: str
    service_account_info: dict[str, Any] = field(repr=False)
    billing_project_id: str | None = None
    location: str | None = None
    allowed_dataset_refs: tuple[str, ...] = ()
    allowed_table_refs: tuple[str, ...] = ()
    max_bytes_billed: int = WAREHOUSE_QUERY_DEFAULT_MAX_BYTES_BILLED
    max_rows_returned: int = WAREHOUSE_QUERY_MAX_ROWS
    max_result_bytes: int = WAREHOUSE_RESULT_MAX_BYTES
    statement_timeout_ms: int = WAREHOUSE_QUERY_DEFAULT_TIMEOUT_MS
    require_partition_filter_for_table_refs: tuple[str, ...] = ()
    schema_dataset_limit: int = WAREHOUSE_SCHEMA_MAX_DATASETS
    schema_table_limit: int = WAREHOUSE_SCHEMA_MAX_TABLES
    schema_column_limit: int = WAREHOUSE_SCHEMA_MAX_COLUMNS

    @property
    def project_id(self) -> str | None:
        return self.billing_project_id

    @property
    def default_max_bytes_billed(self) -> int:
        return self.max_bytes_billed

    @property
    def max_bytes_billed_cap(self) -> int:
        return self.max_bytes_billed

    @property
    def default_max_rows(self) -> int:
        return self.max_rows_returned

    @property
    def max_rows_cap(self) -> int:
        return self.max_rows_returned

    @property
    def default_timeout_ms(self) -> int:
        return self.statement_timeout_ms

    @property
    def result_bytes_cap(self) -> int:
        return self.max_result_bytes

    @property
    def max_timeout_ms(self) -> int:
        return self.statement_timeout_ms


def validate_warehouse_ref(warehouse_ref: str) -> None:
    if not _WAREHOUSE_REF_RE.fullmatch(warehouse_ref):
        raise WarehouseRefError(
            f"Invalid warehouse_ref '{warehouse_ref}': must be lowercase alphanumeric with underscores, 1-64 chars"
        )


def has_any_warehouse_bundle_configured(provider: str | None = None) -> bool:
    provider_filter = str(provider or "").strip().lower() or None
    for env_key in os.environ:
        if not env_key.startswith("RHUMB_WAREHOUSE_"):
            continue
        warehouse_ref = env_key.removeprefix("RHUMB_WAREHOUSE_").lower()
        try:
            bundle = resolve_warehouse_bundle(warehouse_ref)
        except WarehouseRefError:
            continue
        if provider_filter and bundle.provider != provider_filter:
            continue
        return True
    return False


def resolve_warehouse_bundle(warehouse_ref: str) -> BigQueryWarehouseBundle:
    validate_warehouse_ref(warehouse_ref)
    env_key = f"RHUMB_WAREHOUSE_{warehouse_ref.upper()}"
    raw_bundle = os.environ.get(env_key)
    if not raw_bundle:
        raise WarehouseRefError(
            f"No warehouse bundle configured for warehouse_ref '{warehouse_ref}' (expected env var {env_key})"
        )

    try:
        payload = json.loads(raw_bundle)
    except Exception as exc:
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but is not valid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but is not a JSON object"
        )

    provider = str(payload.get("provider") or "").strip().lower()
    if provider != "bigquery":
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but provider must be 'bigquery'"
        )

    auth_mode = str(payload.get("auth_mode") or "").strip().lower()
    if auth_mode != "service_account_json":
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but auth_mode must be 'service_account_json'"
        )

    service_account_info = _service_account_info(
        payload.get("service_account_json"),
        warehouse_ref=warehouse_ref,
        env_key=env_key,
    )
    billing_project_id = _optional_string(
        payload.get("billing_project_id")
        or payload.get("project_id")
        or service_account_info.get("project_id")
    )
    if not billing_project_id:
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but must declare billing_project_id"
        )

    location = _optional_string(payload.get("location"))
    if not location:
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but must declare location"
        )

    allowed_dataset_refs = _dataset_ref_tuple(
        payload.get("allowed_dataset_refs"),
        field_name="allowed_dataset_refs",
    )
    allowed_table_refs = _table_ref_tuple(
        payload.get("allowed_table_refs"),
        field_name="allowed_table_refs",
    )
    if not allowed_dataset_refs:
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but must declare at least one allowed_dataset_refs entry"
        )
    if not allowed_table_refs:
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but must declare at least one allowed_table_refs entry"
        )
    disallowed_table_refs = [
        table_ref
        for table_ref in allowed_table_refs
        if dataset_ref_for_table(table_ref) not in allowed_dataset_refs
    ]
    if disallowed_table_refs:
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but every allowed_table_refs entry must belong to an allowed_dataset_refs entry"
        )

    max_bytes_billed = _bounded_int(
        payload.get("max_bytes_billed") or payload.get("default_max_bytes_billed") or payload.get("max_bytes_billed_cap"),
        default=WAREHOUSE_QUERY_DEFAULT_MAX_BYTES_BILLED,
        minimum=1,
        maximum=WAREHOUSE_QUERY_MAX_MAX_BYTES_BILLED,
        field_name="max_bytes_billed",
    )
    max_rows_returned = _bounded_int(
        payload.get("max_rows_returned") or payload.get("default_max_rows") or payload.get("max_rows_cap"),
        default=WAREHOUSE_QUERY_DEFAULT_ROWS,
        minimum=1,
        maximum=WAREHOUSE_QUERY_MAX_ROWS,
        field_name="max_rows_returned",
    )
    statement_timeout_ms = _bounded_int(
        payload.get("statement_timeout_ms") or payload.get("default_timeout_ms") or payload.get("max_timeout_ms"),
        default=WAREHOUSE_QUERY_DEFAULT_TIMEOUT_MS,
        minimum=1,
        maximum=WAREHOUSE_QUERY_MAX_TIMEOUT_MS,
        field_name="statement_timeout_ms",
    )
    max_result_bytes = _bounded_int(
        payload.get("max_result_bytes") or payload.get("result_bytes_cap"),
        default=WAREHOUSE_RESULT_MAX_BYTES,
        minimum=1024,
        maximum=WAREHOUSE_RESULT_MAX_BYTES,
        field_name="max_result_bytes",
    )
    require_partition_filter_for_table_refs = _table_ref_tuple(
        payload.get("require_partition_filter_for_table_refs"),
        field_name="require_partition_filter_for_table_refs",
    )
    missing_partition_scope = [
        table_ref
        for table_ref in require_partition_filter_for_table_refs
        if table_ref not in allowed_table_refs
    ]
    if missing_partition_scope:
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but require_partition_filter_for_table_refs entries must also appear in allowed_table_refs"
        )
    schema_dataset_limit = _bounded_int(
        payload.get("schema_dataset_limit"),
        default=min(len(allowed_dataset_refs) or 1, WAREHOUSE_SCHEMA_MAX_DATASETS),
        minimum=1,
        maximum=WAREHOUSE_SCHEMA_MAX_DATASETS,
        field_name="schema_dataset_limit",
    )
    schema_table_limit = _bounded_int(
        payload.get("schema_table_limit"),
        default=min(len(allowed_table_refs) or WAREHOUSE_SCHEMA_MAX_TABLES, WAREHOUSE_SCHEMA_MAX_TABLES),
        minimum=1,
        maximum=WAREHOUSE_SCHEMA_MAX_TABLES,
        field_name="schema_table_limit",
    )
    schema_column_limit = _bounded_int(
        payload.get("schema_column_limit"),
        default=WAREHOUSE_SCHEMA_MAX_COLUMNS,
        minimum=1,
        maximum=WAREHOUSE_SCHEMA_MAX_COLUMNS,
        field_name="schema_column_limit",
    )

    return BigQueryWarehouseBundle(
        warehouse_ref=warehouse_ref,
        provider=provider,
        auth_mode=auth_mode,
        service_account_info=service_account_info,
        billing_project_id=billing_project_id,
        location=location,
        allowed_dataset_refs=allowed_dataset_refs,
        allowed_table_refs=allowed_table_refs,
        max_bytes_billed=max_bytes_billed,
        max_rows_returned=max_rows_returned,
        max_result_bytes=max_result_bytes,
        statement_timeout_ms=statement_timeout_ms,
        require_partition_filter_for_table_refs=require_partition_filter_for_table_refs,
        schema_dataset_limit=schema_dataset_limit,
        schema_table_limit=schema_table_limit,
        schema_column_limit=schema_column_limit,
    )


def dataset_is_allowed(bundle: BigQueryWarehouseBundle, dataset_ref: str | None) -> bool:
    if dataset_ref is None:
        return False
    normalized = normalize_dataset_ref(dataset_ref)
    return normalized in bundle.allowed_dataset_refs


def table_is_allowed(bundle: BigQueryWarehouseBundle, table_ref: str | None) -> bool:
    if table_ref is None:
        return False
    normalized = normalize_table_ref(table_ref)
    return normalized in bundle.allowed_table_refs


def ensure_dataset_allowed(bundle: BigQueryWarehouseBundle, dataset_ref: str | None) -> str:
    if dataset_ref is None:
        raise WarehouseRefError(
            f"warehouse_ref '{bundle.warehouse_ref}' requires an explicit dataset_ref in project.dataset form"
        )
    normalized = normalize_dataset_ref(dataset_ref)
    if normalized in bundle.allowed_dataset_refs:
        return normalized
    raise WarehouseRefError(
        f"warehouse_ref '{bundle.warehouse_ref}' is not allowed to access dataset '{normalized}'"
    )


def ensure_table_allowed(bundle: BigQueryWarehouseBundle, table_ref: str | None) -> str:
    if table_ref is None:
        raise WarehouseRefError(
            f"warehouse_ref '{bundle.warehouse_ref}' requires an explicit table_ref in project.dataset.table form"
        )
    normalized = normalize_table_ref(table_ref)
    if table_is_allowed(bundle, normalized):
        return normalized
    raise WarehouseRefError(
        f"warehouse_ref '{bundle.warehouse_ref}' is not allowed to access table '{normalized}'"
    )


def allowed_dataset_refs(bundle: BigQueryWarehouseBundle) -> tuple[str, ...]:
    return bundle.allowed_dataset_refs


def allowed_table_refs(bundle: BigQueryWarehouseBundle) -> tuple[str, ...]:
    return bundle.allowed_table_refs


def _service_account_info(
    value: object,
    *,
    warehouse_ref: str,
    env_key: str,
) -> dict[str, Any]:
    payload: object = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            payload = None
        else:
            try:
                payload = json.loads(text)
            except Exception as exc:
                raise WarehouseRefError(
                    f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but field 'service_account_json' is not valid JSON"
                ) from exc

    if not isinstance(payload, dict):
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but field 'service_account_json' must be a JSON object"
        )

    sa_type = str(payload.get("type") or "").strip().lower()
    if sa_type != "service_account":
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but field 'service_account_json.type' must be 'service_account'"
        )
    if not _optional_string(payload.get("client_email")):
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but field 'service_account_json.client_email' is missing"
        )
    if not _optional_string(payload.get("private_key")):
        raise WarehouseRefError(
            f"warehouse_ref '{warehouse_ref}' is configured via env '{env_key}' but field 'service_account_json.private_key' is missing"
        )
    return dict(payload)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dataset_ref_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise WarehouseRefError(f"{field_name} must be an array of project.dataset strings")
    items: list[str] = []
    for item in value:
        text = _optional_string(item)
        if text is None:
            raise WarehouseRefError(f"{field_name} entries must be non-empty strings")
        items.append(normalize_dataset_ref(text))
    return tuple(dict.fromkeys(items))


def _table_ref_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise WarehouseRefError(f"{field_name} must be an array of project.dataset.table strings")
    items: list[str] = []
    for item in value:
        text = _optional_string(item)
        if text is None:
            raise WarehouseRefError(f"{field_name} entries must be non-empty strings")
        items.append(normalize_table_ref(text))
    return tuple(dict.fromkeys(items))


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
    field_name: str,
) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise WarehouseRefError(f"{field_name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise WarehouseRefError(
            f"{field_name} must be between {minimum} and {maximum}"
        )
    return parsed
