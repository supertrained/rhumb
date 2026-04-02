"""Tests for database capability request/response schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.db_capabilities import (
    DB_QUERY_DEFAULT_ROWS,
    DB_QUERY_DEFAULT_TIMEOUT_MS,
    DB_QUERY_MAX_PARAMS,
    DB_ROW_GET_DEFAULT_LIMIT,
    DB_ROW_GET_MAX_COLUMNS,
    DB_ROW_GET_MAX_FILTERS,
    DB_SCHEMA_MAX_SCHEMAS,
    DbQueryReadRequest,
    DbRowGetRequest,
    DbSchemaDescribeRequest,
)


def test_db_query_read_request_applies_defaults() -> None:
    request = DbQueryReadRequest(
        connection_ref="conn_reader",
        query="SELECT id FROM users WHERE org_id = $1",
        params=["org_123"],
    )

    assert request.max_rows == DB_QUERY_DEFAULT_ROWS
    assert request.timeout_ms == DB_QUERY_DEFAULT_TIMEOUT_MS
    assert request.params == ["org_123"]


@pytest.mark.parametrize(
    "params",
    [
        list(range(DB_QUERY_MAX_PARAMS + 1)),
        {f"k{index}": index for index in range(DB_QUERY_MAX_PARAMS + 1)},
    ],
)
def test_db_query_read_request_rejects_too_many_params(params: object) -> None:
    with pytest.raises(ValidationError):
        DbQueryReadRequest(
            connection_ref="conn_reader",
            query="SELECT 1",
            params=params,
        )


def test_db_schema_describe_defaults_to_public() -> None:
    request = DbSchemaDescribeRequest(connection_ref="conn_reader")

    assert request.schemas == ["public"]
    assert request.tables is None
    assert request.include_relationships is False


def test_db_schema_describe_rejects_too_many_schemas() -> None:
    with pytest.raises(ValidationError):
        DbSchemaDescribeRequest(
            connection_ref="conn_reader",
            schemas=[f"schema_{index}" for index in range(DB_SCHEMA_MAX_SCHEMAS + 1)],
        )


def test_db_row_get_request_rejects_invalid_identifier() -> None:
    with pytest.raises(ValidationError):
        DbRowGetRequest(
            connection_ref="conn_reader",
            table="users;drop",
        )


def test_db_row_get_request_requires_filters_for_limit_above_one() -> None:
    with pytest.raises(ValidationError):
        DbRowGetRequest(
            connection_ref="conn_reader",
            table="users",
            limit=DB_ROW_GET_DEFAULT_LIMIT + 1,
        )


def test_db_row_get_request_accepts_default_limit_without_filters() -> None:
    request = DbRowGetRequest(
        connection_ref="conn_reader",
        table="users",
    )

    assert request.limit == DB_ROW_GET_DEFAULT_LIMIT
    assert request.filters is None


def test_db_row_get_request_rejects_too_many_filters() -> None:
    with pytest.raises(ValidationError):
        DbRowGetRequest(
            connection_ref="conn_reader",
            table="users",
            filters={f"field_{index}": index for index in range(DB_ROW_GET_MAX_FILTERS + 1)},
        )


def test_db_row_get_request_rejects_too_many_columns() -> None:
    with pytest.raises(ValidationError):
        DbRowGetRequest(
            connection_ref="conn_reader",
            table="users",
            columns=[f"column_{index}" for index in range(DB_ROW_GET_MAX_COLUMNS + 1)],
        )
