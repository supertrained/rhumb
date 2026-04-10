"""Warehouse capability request/response schemas for the AUD-18 BigQuery wedge."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WAREHOUSE_REF_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
WAREHOUSE_QUERY_MAX_SQL_CHARS = 8000
WAREHOUSE_QUERY_DEFAULT_ROWS = 50
WAREHOUSE_QUERY_MAX_ROWS = 100
WAREHOUSE_QUERY_DEFAULT_TIMEOUT_MS = 10000
WAREHOUSE_QUERY_MAX_TIMEOUT_MS = 30000
WAREHOUSE_QUERY_DEFAULT_MAX_BYTES_BILLED = 50_000_000
WAREHOUSE_QUERY_MAX_MAX_BYTES_BILLED = 1_000_000_000
WAREHOUSE_QUERY_MAX_PARAMS = 50
WAREHOUSE_RESULT_MAX_BYTES = 262144
WAREHOUSE_SCHEMA_MAX_DATASETS = 5
WAREHOUSE_SCHEMA_MAX_TABLES = 20
WAREHOUSE_SCHEMA_MAX_COLUMNS = 500
WAREHOUSE_REASON_MAX_CHARS = 300

_REF_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")

CredentialMode = Literal["byok"]
ProviderUsed = Literal["bigquery"]
StatementType = Literal["select"]
WarehouseObjectKind = Literal["table", "view", "materialized_view", "external", "snapshot", "unknown"]


class WarehouseBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _strip_wrapping_backticks(value: str) -> str:
    text = value.strip()
    if text.startswith("`") and text.endswith("`") and len(text) >= 2:
        return text[1:-1].strip()
    return text


def _normalize_ref_parts(value: str, *, expected_parts: int, field_name: str) -> tuple[str, ...]:
    normalized = _strip_wrapping_backticks(value)
    parts = [part.strip() for part in normalized.split(".")]
    if len(parts) != expected_parts or any(not part for part in parts):
        raise ValueError(f"{field_name} must be in {'.'.join(['part'] * expected_parts)} form")
    lowered = tuple(part.lower() for part in parts)
    for part in lowered:
        if not _REF_SEGMENT_RE.fullmatch(part):
            raise ValueError(f"{field_name} contains an invalid identifier segment")
    return lowered


def normalize_dataset_ref(value: str) -> str:
    project_id, dataset_id = _normalize_ref_parts(
        value,
        expected_parts=2,
        field_name="dataset_ref",
    )
    return f"{project_id}.{dataset_id}"


def normalize_table_ref(value: str) -> str:
    project_id, dataset_id, table_id = _normalize_ref_parts(
        value,
        expected_parts=3,
        field_name="table_ref",
    )
    return f"{project_id}.{dataset_id}.{table_id}"


def dataset_ref_for_table(table_ref: str) -> str:
    project_id, dataset_id, _table_id = _normalize_ref_parts(
        table_ref,
        expected_parts=3,
        field_name="table_ref",
    )
    return f"{project_id}.{dataset_id}"


def split_dataset_ref(dataset_ref: str) -> tuple[str, str]:
    project_id, dataset_id = _normalize_ref_parts(
        dataset_ref,
        expected_parts=2,
        field_name="dataset_ref",
    )
    return project_id, dataset_id


def split_table_ref(table_ref: str) -> tuple[str, str, str]:
    project_id, dataset_id, table_id = _normalize_ref_parts(
        table_ref,
        expected_parts=3,
        field_name="table_ref",
    )
    return project_id, dataset_id, table_id


class WarehouseColumnSchema(WarehouseBaseModel):
    name: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    nullable: bool | None = None
    mode: str | None = None
    description: str | None = None


class WarehouseDatasetSchema(WarehouseBaseModel):
    project_id: str = Field(..., min_length=1)
    dataset_id: str = Field(..., min_length=1)


class WarehousePartitioningSchema(WarehouseBaseModel):
    type: str | None = None
    field: str | None = None


class WarehouseTableSchema(WarehouseBaseModel):
    table_ref: str
    table_type: WarehouseObjectKind = "unknown"
    description: str | None = None
    partitioning: WarehousePartitioningSchema | None = None
    clustering: list[str] | None = None
    columns: list[WarehouseColumnSchema] | None = None

    @field_validator("table_ref")
    @classmethod
    def _validate_table_ref(cls, value: str) -> str:
        return normalize_table_ref(value)


class WarehouseQueryBounds(WarehouseBaseModel):
    row_limit_applied: int = Field(..., ge=1, le=WAREHOUSE_QUERY_MAX_ROWS)
    timeout_ms_applied: int = Field(..., ge=1, le=WAREHOUSE_QUERY_MAX_TIMEOUT_MS)
    max_bytes_billed_applied: int = Field(..., ge=1, le=WAREHOUSE_QUERY_MAX_MAX_BYTES_BILLED)
    result_bytes_limit_applied: int = Field(..., ge=1, le=WAREHOUSE_RESULT_MAX_BYTES)


class WarehouseSchemaBounds(WarehouseBaseModel):
    dataset_limit_applied: int = Field(..., ge=1, le=WAREHOUSE_SCHEMA_MAX_DATASETS)
    table_limit_applied: int = Field(..., ge=1, le=WAREHOUSE_SCHEMA_MAX_TABLES)
    column_limit_applied: int = Field(..., ge=1, le=WAREHOUSE_SCHEMA_MAX_COLUMNS)


class WarehouseQuerySummary(WarehouseBaseModel):
    statement_type: StatementType
    tables_referenced: list[str] = Field(default_factory=list)
    dry_run_performed: bool
    dry_run_bytes_processed: int = Field(..., ge=0)
    truncated: bool = False

    @field_validator("tables_referenced")
    @classmethod
    def _validate_tables_referenced(cls, value: list[str]) -> list[str]:
        return [normalize_table_ref(item) for item in value]


class WarehouseQueryReadRequest(WarehouseBaseModel):
    warehouse_ref: str = Field(..., pattern=WAREHOUSE_REF_PATTERN)
    query: str = Field(..., min_length=1, max_length=WAREHOUSE_QUERY_MAX_SQL_CHARS)
    params: list[Any] | dict[str, Any] | None = None
    max_rows: int = Field(
        default=WAREHOUSE_QUERY_DEFAULT_ROWS,
        ge=1,
        le=WAREHOUSE_QUERY_MAX_ROWS,
    )
    timeout_ms: int = Field(
        default=WAREHOUSE_QUERY_DEFAULT_TIMEOUT_MS,
        ge=1,
        le=WAREHOUSE_QUERY_MAX_TIMEOUT_MS,
    )
    max_bytes_billed: int | None = Field(
        default=None,
        ge=1,
        le=WAREHOUSE_QUERY_MAX_MAX_BYTES_BILLED,
    )
    reason: str | None = Field(default=None, max_length=WAREHOUSE_REASON_MAX_CHARS)

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be empty")
        return normalized

    @field_validator("params")
    @classmethod
    def _validate_params(cls, value: list[Any] | dict[str, Any] | None) -> list[Any] | dict[str, Any] | None:
        if value is None:
            return value
        if len(value) > WAREHOUSE_QUERY_MAX_PARAMS:
            raise ValueError(f"params supports at most {WAREHOUSE_QUERY_MAX_PARAMS} bound values")
        return value


class WarehouseQueryReadResponse(WarehouseBaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["warehouse.query.read"]
    receipt_id: str
    execution_id: str
    warehouse_ref: str
    billing_project_id: str | None = None
    location: str | None = None
    bounded_by: WarehouseQueryBounds
    query_summary: WarehouseQuerySummary
    columns: list[WarehouseColumnSchema] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count_returned: int = Field(..., ge=0)
    truncated: bool = False
    dry_run_bytes_estimate: int = Field(..., ge=0)
    actual_bytes_billed: int | None = Field(default=None, ge=0)
    duration_ms: int = Field(..., ge=0)


class WarehouseSchemaDescribeRequest(WarehouseBaseModel):
    warehouse_ref: str = Field(..., pattern=WAREHOUSE_REF_PATTERN)
    dataset_refs: list[str] | None = None
    table_refs: list[str] | None = None
    include_columns: bool = True
    reason: str | None = Field(default=None, max_length=WAREHOUSE_REASON_MAX_CHARS)

    @field_validator("dataset_refs")
    @classmethod
    def _validate_dataset_refs(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) > WAREHOUSE_SCHEMA_MAX_DATASETS:
            raise ValueError(
                f"dataset_refs supports at most {WAREHOUSE_SCHEMA_MAX_DATASETS} dataset references"
            )
        return [normalize_dataset_ref(item) for item in value]

    @field_validator("table_refs")
    @classmethod
    def _validate_table_refs(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) > WAREHOUSE_SCHEMA_MAX_TABLES:
            raise ValueError(
                f"table_refs supports at most {WAREHOUSE_SCHEMA_MAX_TABLES} table references"
            )
        return [normalize_table_ref(item) for item in value]

    @model_validator(mode="after")
    def _validate_scope(self) -> "WarehouseSchemaDescribeRequest":
        if self.dataset_refs is not None and len(self.dataset_refs) == 0:
            raise ValueError("dataset_refs must not be empty when provided")
        if self.table_refs is not None and len(self.table_refs) == 0:
            raise ValueError("table_refs must not be empty when provided")
        return self


class WarehouseSchemaDescribeResponse(WarehouseBaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["warehouse.schema.describe"]
    receipt_id: str
    execution_id: str
    warehouse_ref: str
    billing_project_id: str | None = None
    location: str | None = None
    bounded_by: WarehouseSchemaBounds
    datasets: list[WarehouseDatasetSchema] = Field(default_factory=list)
    tables: list[WarehouseTableSchema] = Field(default_factory=list)
    table_count_returned: int = Field(..., ge=0)
    truncated: bool = False
    duration_ms: int = Field(..., ge=0)


SUPPORTED_WAREHOUSE_CAPABILITY_IDS = frozenset({
    "warehouse.query.read",
    "warehouse.schema.describe",
})
