"""Database capability request/response schemas for the read-first Wave 1 wedge."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DB_QUERY_MAX_SQL_CHARS = 8000
DB_QUERY_MAX_PARAMS = 50
DB_QUERY_DEFAULT_ROWS = 100
DB_QUERY_MAX_ROWS = 500
DB_QUERY_DEFAULT_TIMEOUT_MS = 5000
DB_QUERY_MAX_TIMEOUT_MS = 10000
DB_RESULT_MAX_BYTES = 262144
DB_SCHEMA_MAX_SCHEMAS = 10
DB_SCHEMA_MAX_TABLES = 50
DB_SCHEMA_MAX_COLUMNS = 500
DB_ROW_GET_DEFAULT_LIMIT = 1
DB_ROW_GET_MAX_LIMIT = 25
DB_ROW_GET_MAX_FILTERS = 10
DB_ROW_GET_MAX_COLUMNS = 50
DB_ORDER_BY_MAX_COLUMNS = 3
DB_REASON_MAX_CHARS = 300
DB_AGENT_VAULT_TOKEN_DEFAULT_TTL_SECONDS = 300
DB_AGENT_VAULT_TOKEN_MAX_TTL_SECONDS = 3600

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CredentialMode = Literal["byok", "agent_vault"]
ProviderUsed = Literal["postgresql", "supabase"]


def _validate_identifier(value: str, field_name: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a simple SQL identifier")
    return value


def _validate_identifier_list(
    values: list[str] | None,
    *,
    field_name: str,
    max_items: int,
) -> list[str] | None:
    if values is None:
        return None
    if len(values) > max_items:
        raise ValueError(f"{field_name} supports at most {max_items} items")
    return [_validate_identifier(value, field_name) for value in values]


class DbColumnSchema(BaseModel):
    name: str
    type: str
    nullable: bool | None = None


class DbRelationshipSchema(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str

    @field_validator("from_table", "from_column", "to_table", "to_column")
    @classmethod
    def _validate_identifier_fields(cls, value: str) -> str:
        return _validate_identifier(value, "relationship identifier")


class DbTableRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema", serialization_alias="schema")
    name: str

    @field_validator("schema_name")
    @classmethod
    def _validate_schema(cls, value: str) -> str:
        return _validate_identifier(value, "schema")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _validate_identifier(value, "table")


class DbTableSchema(DbTableRef):
    kind: Literal["table", "view", "materialized_view", "foreign_table"]
    columns: list[DbColumnSchema] = Field(default_factory=list)


class DbQueryBounds(BaseModel):
    row_limit_applied: int = Field(..., ge=1, le=DB_QUERY_MAX_ROWS)
    timeout_ms_applied: int = Field(..., ge=1, le=DB_QUERY_MAX_TIMEOUT_MS)
    result_bytes_limit_applied: int = Field(..., ge=1, le=DB_RESULT_MAX_BYTES)


class DbSchemaBounds(BaseModel):
    schema_limit_applied: int = Field(..., ge=1, le=DB_SCHEMA_MAX_SCHEMAS)
    table_limit_applied: int = Field(..., ge=1, le=DB_SCHEMA_MAX_TABLES)
    column_limit_applied: int = Field(..., ge=1, le=DB_SCHEMA_MAX_COLUMNS)


class DbRowGetBounds(BaseModel):
    row_limit_applied: int = Field(..., ge=1, le=DB_ROW_GET_MAX_LIMIT)
    column_limit_applied: int = Field(..., ge=1, le=DB_ROW_GET_MAX_COLUMNS)


class DbQuerySummary(BaseModel):
    statement_type: str
    tables_referenced: list[str] = Field(default_factory=list)
    read_only_classification: Literal["allow", "deny"]
    truncated: bool = False


class DbRowOrderBy(BaseModel):
    column: str
    direction: Literal["asc", "desc"] = "asc"

    @field_validator("column")
    @classmethod
    def _validate_column(cls, value: str) -> str:
        return _validate_identifier(value, "order_by column")


class DbQueryReadRequest(BaseModel):
    connection_ref: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1, max_length=DB_QUERY_MAX_SQL_CHARS)
    params: list[Any] | dict[str, Any] | None = None
    max_rows: int = Field(DB_QUERY_DEFAULT_ROWS, ge=1, le=DB_QUERY_MAX_ROWS)
    timeout_ms: int = Field(DB_QUERY_DEFAULT_TIMEOUT_MS, ge=1, le=DB_QUERY_MAX_TIMEOUT_MS)
    reason: str | None = Field(default=None, max_length=DB_REASON_MAX_CHARS)

    @field_validator("params")
    @classmethod
    def _validate_params(cls, value: list[Any] | dict[str, Any] | None) -> list[Any] | dict[str, Any] | None:
        if value is None:
            return value
        if len(value) > DB_QUERY_MAX_PARAMS:
            raise ValueError(f"params supports at most {DB_QUERY_MAX_PARAMS} bound values")
        return value


class DbAgentVaultTokenizeRequest(BaseModel):
    connection_ref: str = Field(..., min_length=1)
    dsn: str = Field(..., min_length=1, max_length=4096)
    ttl_seconds: int = Field(
        DB_AGENT_VAULT_TOKEN_DEFAULT_TTL_SECONDS,
        ge=1,
        le=DB_AGENT_VAULT_TOKEN_MAX_TTL_SECONDS,
    )


class DbAgentVaultTokenizeResponse(BaseModel):
    token: str
    token_format: Literal["rhdbv1"]
    connection_ref: str
    ttl_seconds: int = Field(..., ge=1, le=DB_AGENT_VAULT_TOKEN_MAX_TTL_SECONDS)
    expires_at: int = Field(..., ge=1)


class DbQueryReadResponse(BaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["db.query.read"]
    receipt_id: str
    execution_id: str
    connection_ref: str
    bounded_by: DbQueryBounds
    query_summary: DbQuerySummary
    columns: list[DbColumnSchema] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count_returned: int = Field(..., ge=0)
    duration_ms: int = Field(..., ge=0)


class DbSchemaDescribeRequest(BaseModel):
    connection_ref: str = Field(..., min_length=1)
    schemas: list[str] = Field(default_factory=lambda: ["public"])
    tables: list[str] | None = None
    include_relationships: bool = False

    @field_validator("schemas")
    @classmethod
    def _validate_schemas(cls, value: list[str]) -> list[str]:
        validated = _validate_identifier_list(
            value,
            field_name="schemas",
            max_items=DB_SCHEMA_MAX_SCHEMAS,
        )
        return validated or ["public"]

    @field_validator("tables")
    @classmethod
    def _validate_tables(cls, value: list[str] | None) -> list[str] | None:
        return _validate_identifier_list(
            value,
            field_name="tables",
            max_items=DB_SCHEMA_MAX_TABLES,
        )


class DbSchemaDescribeResponse(BaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["db.schema.describe"]
    receipt_id: str
    execution_id: str
    connection_ref: str
    bounded_by: DbSchemaBounds
    schemas: list[str] = Field(default_factory=list)
    tables: list[DbTableSchema] = Field(default_factory=list)
    relationships: list[DbRelationshipSchema] = Field(default_factory=list)
    truncated: bool = False
    duration_ms: int = Field(..., ge=0)


class DbRowGetRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    connection_ref: str = Field(..., min_length=1)
    schema_name: str = Field(default="public", alias="schema", serialization_alias="schema")
    table: str
    filters: dict[str, Any] | None = None
    columns: list[str] | None = None
    limit: int = Field(DB_ROW_GET_DEFAULT_LIMIT, ge=1, le=DB_ROW_GET_MAX_LIMIT)
    order_by: list[DbRowOrderBy] | None = None

    @field_validator("schema_name")
    @classmethod
    def _validate_schema(cls, value: str) -> str:
        return _validate_identifier(value, "schema")

    @field_validator("table")
    @classmethod
    def _validate_table(cls, value: str) -> str:
        return _validate_identifier(value, "table")

    @field_validator("filters")
    @classmethod
    def _validate_filters(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value
        if len(value) > DB_ROW_GET_MAX_FILTERS:
            raise ValueError(f"filters supports at most {DB_ROW_GET_MAX_FILTERS} keys")
        return {
            _validate_identifier(key, "filter key"): filter_value
            for key, filter_value in value.items()
        }

    @field_validator("columns")
    @classmethod
    def _validate_columns(cls, value: list[str] | None) -> list[str] | None:
        return _validate_identifier_list(
            value,
            field_name="columns",
            max_items=DB_ROW_GET_MAX_COLUMNS,
        )

    @field_validator("order_by")
    @classmethod
    def _validate_order_by(cls, value: list[DbRowOrderBy] | None) -> list[DbRowOrderBy] | None:
        if value is None:
            return value
        if len(value) > DB_ORDER_BY_MAX_COLUMNS:
            raise ValueError(f"order_by supports at most {DB_ORDER_BY_MAX_COLUMNS} entries")
        return value

    @model_validator(mode="after")
    def _validate_scope(self) -> "DbRowGetRequest":
        if not self.filters and self.limit > DB_ROW_GET_DEFAULT_LIMIT:
            raise ValueError("filters are required when limit exceeds 1")
        return self


class DbRowGetResponse(BaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["db.row.get"]
    receipt_id: str
    execution_id: str
    connection_ref: str
    bounded_by: DbRowGetBounds
    table: DbTableRef
    columns_returned: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count_returned: int = Field(..., ge=0)
    truncated: bool = False
    duration_ms: int = Field(..., ge=0)

    @field_validator("columns_returned")
    @classmethod
    def _validate_columns_returned(cls, value: list[str]) -> list[str]:
        return _validate_identifier_list(
            value,
            field_name="columns_returned",
            max_items=DB_ROW_GET_MAX_COLUMNS,
        ) or []
