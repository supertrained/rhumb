"""Focused tests for the PostgreSQL direct read executor."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from schemas.db_capabilities import DbQueryReadRequest, DbRowGetRequest, DbSchemaDescribeRequest
from services.postgres_read_executor import (
    DbExecutorError,
    describe_schema,
    execute_read_query,
    get_rows,
)


class FakeCursor:
    def __init__(self, *, executions=None, rows=None, fetchmany_rows=None, description=None):
        self.executions = executions if executions is not None else []
        self.rows = rows if rows is not None else []
        self.fetchmany_rows = fetchmany_rows if fetchmany_rows is not None else list(self.rows)
        self.description = description or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, sql, params=None):
        self.executions.append((sql, params))

    async def fetchmany(self, count):
        return list(self.fetchmany_rows[:count])

    async def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def cursor(self, row_factory=None):
        return self._cursor


@asynccontextmanager
async def fake_connection_factory(cursor: FakeCursor):
    yield FakeConnection(cursor)


@pytest.mark.asyncio
async def test_execute_read_query_sets_read_only_session_and_truncates() -> None:
    cursor = FakeCursor(
        fetchmany_rows=[
            {"id": 1, "email": "a@example.com"},
            {"id": 2, "email": "b@example.com"},
            {"id": 3, "email": "c@example.com"},
        ],
        description=[
            SimpleNamespace(name="id", type_code="uuid"),
            SimpleNamespace(name="email", type_code="text"),
        ],
    )

    response = await execute_read_query(
        DbQueryReadRequest(
            connection_ref="conn_123",
            query="SELECT id, email FROM public.users",
            max_rows=2,
        ),
        credential_mode="byok",
        provider_used="supabase",
        connection_factory=lambda: fake_connection_factory(cursor),
        receipt_id="rcpt_123",
        execution_id="exec_123",
    )

    assert cursor.executions[0][0] == "BEGIN READ ONLY"
    assert cursor.executions[1][0] == "SET LOCAL statement_timeout = 5000"
    assert cursor.executions[2][0] == "SELECT id, email FROM public.users"
    assert response.query_summary.truncated is True
    assert response.provider_used == "supabase"
    assert response.connection_ref == "conn_123"
    assert response.row_count_returned == 2
    assert response.rows == [
        {"id": 1, "email": "a@example.com"},
        {"id": 2, "email": "b@example.com"},
    ]
    assert [column.name for column in response.columns] == ["id", "email"]


@pytest.mark.asyncio
async def test_execute_read_query_rejects_non_read_only_sql_before_db_access() -> None:
    cursor = FakeCursor()

    with pytest.raises(DbExecutorError, match="db_query_not_read_only"):
        await execute_read_query(
            DbQueryReadRequest(
                connection_ref="conn_123",
                query="DELETE FROM public.users",
            ),
            credential_mode="byok",
            connection_factory=lambda: fake_connection_factory(cursor),
        )

    assert cursor.executions == []


@pytest.mark.asyncio
async def test_execute_read_query_enforces_result_size_cap() -> None:
    cursor = FakeCursor(
        fetchmany_rows=[{"payload": "x" * 300000}],
        description=[SimpleNamespace(name="payload", type_code="text")],
    )

    with pytest.raises(DbExecutorError, match="db_query_result_too_large"):
        await execute_read_query(
            DbQueryReadRequest(
                connection_ref="conn_123",
                query="SELECT payload FROM public.big_rows",
            ),
            credential_mode="byok",
            connection_factory=lambda: fake_connection_factory(cursor),
        )


@pytest.mark.asyncio
async def test_describe_schema_groups_columns_into_tables() -> None:
    cursor = FakeCursor(
        rows=[
            {
                "table_schema": "public",
                "table_name": "users",
                "kind": "table",
                "column_name": "id",
                "type_name": "uuid",
                "nullable": False,
                "column_default": None,
            },
            {
                "table_schema": "public",
                "table_name": "users",
                "kind": "table",
                "column_name": "email",
                "type_name": "text",
                "nullable": False,
                "column_default": None,
            },
        ]
    )

    response = await describe_schema(
        DbSchemaDescribeRequest(connection_ref="conn_123", schemas=["public"]),
        credential_mode="agent_vault",
        connection_factory=lambda: fake_connection_factory(cursor),
        receipt_id="rcpt_123",
        execution_id="exec_123",
    )

    assert len(response.tables) == 1
    assert response.connection_ref == "conn_123"
    assert response.tables[0].schema_name == "public"
    assert response.tables[0].name == "users"
    assert [column.name for column in response.tables[0].columns] == ["id", "email"]


@pytest.mark.asyncio
async def test_get_rows_builds_safe_sql_and_truncates() -> None:
    cursor = FakeCursor(
        rows=[
            {"id": "user_1", "email": "a@example.com"},
            {"id": "user_2", "email": "b@example.com"},
        ],
        description=[
            SimpleNamespace(name="id", type_code="uuid"),
            SimpleNamespace(name="email", type_code="text"),
        ],
    )

    response = await get_rows(
        DbRowGetRequest(
            connection_ref="conn_123",
            schema="public",
            table="users",
            filters={"id": "user_1"},
            columns=["id", "email"],
            limit=1,
        ),
        credential_mode="byok",
        connection_factory=lambda: fake_connection_factory(cursor),
        receipt_id="rcpt_123",
        execution_id="exec_123",
    )

    select_sql, params = cursor.executions[2]
    assert select_sql == 'SELECT "id", "email" FROM "public"."users" WHERE "id" = %s LIMIT %s'
    assert params == ["user_1", 2]
    assert response.connection_ref == "conn_123"
    assert response.truncated is True
    assert response.row_count_returned == 1
    assert response.columns_returned == ["id", "email"]
    assert response.rows == [{"id": "user_1", "email": "a@example.com"}]
