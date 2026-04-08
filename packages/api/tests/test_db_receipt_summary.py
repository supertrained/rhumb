"""Tests for DB-read receipt summaries."""

from __future__ import annotations

from services.db_receipt_summary import (
    summarize_db_execution,
    summarize_query_read,
    summarize_row_get,
    summarize_schema_describe,
)


def test_summarize_query_read_basic() -> None:
    response = {
        "row_count_returned": 5,
        "query_summary": {
            "tables_referenced": ["users", "orders"],
            "truncated": False,
        },
        "duration_ms": 42,
    }
    result = summarize_query_read(response)
    assert result == "Read 5 row(s) from [users, orders] in 42ms"


def test_summarize_query_read_truncated() -> None:
    response = {
        "row_count_returned": 100,
        "query_summary": {
            "tables_referenced": ["events"],
            "truncated": True,
        },
        "duration_ms": 150,
    }
    result = summarize_query_read(response)
    assert "(truncated)" in result


def test_summarize_query_read_includes_connection_ref() -> None:
    response = {
        "connection_ref": "conn_reader",
        "row_count_returned": 2,
        "query_summary": {
            "tables_referenced": ["users"],
            "truncated": False,
        },
        "duration_ms": 12,
    }
    result = summarize_query_read(response)
    assert result == "Read 2 row(s) from [users] via conn_reader in 12ms"


def test_summarize_query_read_no_tables() -> None:
    response = {
        "row_count_returned": 1,
        "query_summary": {
            "tables_referenced": [],
            "truncated": False,
        },
        "duration_ms": 1,
    }
    result = summarize_query_read(response)
    assert "unknown" in result


def test_summarize_schema_describe() -> None:
    response = {
        "tables": [{"name": "users"}, {"name": "orders"}, {"name": "products"}],
        "schemas": ["public"],
        "duration_ms": 30,
        "truncated": False,
    }
    result = summarize_schema_describe(response)
    assert result == "Described 3 table(s) in schema [public] in 30ms"


def test_summarize_schema_describe_includes_connection_ref() -> None:
    response = {
        "connection_ref": "conn_reader",
        "tables": [{"name": "users"}],
        "schemas": ["public"],
        "duration_ms": 30,
        "truncated": False,
    }
    result = summarize_schema_describe(response)
    assert result == "Described 1 table(s) in schema [public] via conn_reader in 30ms"


def test_summarize_row_get() -> None:
    response = {
        "row_count_returned": 1,
        "table": {"schema": "public", "name": "users"},
        "duration_ms": 5,
        "truncated": False,
    }
    result = summarize_row_get(response)
    assert result == "Got 1 row(s) from public.users in 5ms"


def test_summarize_row_get_includes_connection_ref() -> None:
    response = {
        "connection_ref": "conn_reader",
        "row_count_returned": 1,
        "table": {"schema": "public", "name": "users"},
        "duration_ms": 5,
        "truncated": False,
    }
    result = summarize_row_get(response)
    assert result == "Got 1 row(s) from public.users via conn_reader in 5ms"


def test_summarize_row_get_truncated() -> None:
    response = {
        "row_count_returned": 25,
        "table": {"schema": "analytics", "name": "events"},
        "duration_ms": 80,
        "truncated": True,
    }
    result = summarize_row_get(response)
    assert "(truncated)" in result
    assert "analytics.events" in result


def test_summarize_db_execution_dispatches() -> None:
    query_resp = {
        "row_count_returned": 3,
        "query_summary": {"tables_referenced": ["t"], "truncated": False},
        "duration_ms": 10,
    }
    assert summarize_db_execution("db.query.read", query_resp).startswith("Read 3")

    schema_resp = {
        "tables": [{"name": "a"}],
        "schemas": ["public"],
        "duration_ms": 5,
        "truncated": False,
    }
    assert summarize_db_execution("db.schema.describe", schema_resp).startswith("Described 1")

    row_resp = {
        "row_count_returned": 1,
        "table": {"schema": "public", "name": "x"},
        "duration_ms": 2,
        "truncated": False,
    }
    assert summarize_db_execution("db.row.get", row_resp).startswith("Got 1")

    assert summarize_db_execution("db.unknown", {}).startswith("DB execution completed")
