"""PostgreSQL direct read executor for AUD-18 Wave 1 capabilities."""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

import psycopg
from psycopg.rows import dict_row

from schemas.db_capabilities import (
    DB_QUERY_DEFAULT_TIMEOUT_MS,
    DB_RESULT_MAX_BYTES,
    DbColumnSchema,
    DbQueryBounds,
    DbQueryReadRequest,
    DbQueryReadResponse,
    DbQuerySummary,
    DbRelationshipSchema,
    DbRowGetBounds,
    DbRowGetRequest,
    DbRowGetResponse,
    DbSchemaBounds,
    DbSchemaDescribeRequest,
    DbSchemaDescribeResponse,
    DbTableRef,
    DbTableSchema,
)
from services.db_sql_classifier import QueryClassification, classify_read_only_query

ConnectionFactory = Callable[[], Any]
Classifier = Callable[[str], QueryClassification]


@dataclass(slots=True)
class DbExecutorError(RuntimeError):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@asynccontextmanager
async def _open_connection(
    *,
    connection_factory: ConnectionFactory | None = None,
    dsn: str | None = None,
) -> AsyncIterator[Any]:
    if connection_factory is not None:
        async with connection_factory() as connection:
            yield connection
        return

    if not dsn:
        raise ValueError("dsn or connection_factory is required")

    connection = await psycopg.AsyncConnection.connect(dsn)
    try:
        yield connection
    finally:
        await connection.close()


async def execute_read_query(
    request: DbQueryReadRequest,
    *,
    credential_mode: str,
    connection_factory: ConnectionFactory | None = None,
    dsn: str | None = None,
    classifier: Classifier = classify_read_only_query,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> DbQueryReadResponse:
    classification = classifier(request.query)
    _raise_if_query_denied(classification)

    start = time.perf_counter()
    try:
        async with _open_connection(connection_factory=connection_factory, dsn=dsn) as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await _configure_read_only_session(cursor, timeout_ms=request.timeout_ms)
                await _execute_statement(cursor, request.query, request.params)
                rows = await _fetch_limited_rows(cursor, request.max_rows)
                columns = _extract_columns(cursor)
    except DbExecutorError:
        raise
    except Exception as exc:  # pragma: no cover - exercised through unit mapping tests
        raise _map_db_exception(exc) from exc

    truncated = len(rows) > request.max_rows
    rows = rows[: request.max_rows]
    _enforce_result_size(rows)

    return DbQueryReadResponse(
        provider_used="postgresql",
        credential_mode=credential_mode,
        capability_id="db.query.read",
        receipt_id=receipt_id,
        execution_id=execution_id,
        bounded_by=DbQueryBounds(
            row_limit_applied=request.max_rows,
            timeout_ms_applied=request.timeout_ms,
            result_bytes_limit_applied=DB_RESULT_MAX_BYTES,
        ),
        query_summary=DbQuerySummary(
            statement_type=classification.statement_type,
            tables_referenced=classification.tables_referenced,
            read_only_classification="allow",
            truncated=truncated,
        ),
        columns=columns,
        rows=rows,
        row_count_returned=len(rows),
        duration_ms=_duration_ms(start),
    )


async def describe_schema(
    request: DbSchemaDescribeRequest,
    *,
    credential_mode: str,
    connection_factory: ConnectionFactory | None = None,
    dsn: str | None = None,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> DbSchemaDescribeResponse:
    schemas = request.schemas or ["public"]
    start = time.perf_counter()
    relationships: list[DbRelationshipSchema] = []

    columns_sql = (
        "SELECT c.table_schema, c.table_name, "
        "CASE WHEN t.table_type = 'VIEW' THEN 'view' ELSE 'table' END AS kind, "
        "c.column_name, c.udt_name AS type_name, "
        "(c.is_nullable = 'YES') AS nullable, c.column_default "
        "FROM information_schema.columns c "
        "JOIN information_schema.tables t "
        "ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
        "WHERE c.table_schema = ANY(%s) "
        "AND (%s::text[] IS NULL OR c.table_name = ANY(%s)) "
        "ORDER BY c.table_schema, c.table_name, c.ordinal_position"
    )
    table_filter = request.tables if request.tables else None

    try:
        async with _open_connection(connection_factory=connection_factory, dsn=dsn) as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await _configure_read_only_session(cursor, timeout_ms=DB_QUERY_DEFAULT_TIMEOUT_MS)
                await cursor.execute(columns_sql, (schemas, table_filter, table_filter))
                column_rows = await cursor.fetchall()

                if request.include_relationships:
                    relationships_sql = (
                        "SELECT tc.table_name AS from_table, kcu.column_name AS from_column, "
                        "ccu.table_name AS to_table, ccu.column_name AS to_column "
                        "FROM information_schema.table_constraints tc "
                        "JOIN information_schema.key_column_usage kcu "
                        "ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
                        "JOIN information_schema.constraint_column_usage ccu "
                        "ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema "
                        "WHERE tc.constraint_type = 'FOREIGN KEY' "
                        "AND tc.table_schema = ANY(%s) "
                        "AND (%s::text[] IS NULL OR tc.table_name = ANY(%s)) "
                        "ORDER BY tc.table_name, kcu.column_name"
                    )
                    await cursor.execute(relationships_sql, (schemas, table_filter, table_filter))
                    relationship_rows = await cursor.fetchall()
                    relationships = [
                        DbRelationshipSchema(**row) for row in relationship_rows
                    ]
    except Exception as exc:  # pragma: no cover - exercised through unit mapping tests
        raise _map_db_exception(exc) from exc

    truncated = len(column_rows) > 500
    if truncated:
        column_rows = column_rows[:500]

    table_map: dict[tuple[str, str], DbTableSchema] = {}
    for row in column_rows:
        key = (row["table_schema"], row["table_name"])
        table = table_map.get(key)
        if table is None:
            table = DbTableSchema(
                schema=row["table_schema"],
                name=row["table_name"],
                kind=row["kind"],
                columns=[],
            )
            table_map[key] = table
        table.columns.append(
            DbColumnSchema(
                name=row["column_name"],
                type=row["type_name"],
                nullable=row["nullable"],
            )
        )

    return DbSchemaDescribeResponse(
        provider_used="postgresql",
        credential_mode=credential_mode,
        capability_id="db.schema.describe",
        receipt_id=receipt_id,
        execution_id=execution_id,
        bounded_by=DbSchemaBounds(
            schema_limit_applied=len(schemas),
            table_limit_applied=50,
            column_limit_applied=500,
        ),
        schemas=schemas,
        tables=list(table_map.values()),
        relationships=relationships,
        truncated=truncated,
        duration_ms=_duration_ms(start),
    )


async def get_rows(
    request: DbRowGetRequest,
    *,
    credential_mode: str,
    connection_factory: ConnectionFactory | None = None,
    dsn: str | None = None,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> DbRowGetResponse:
    selected_columns = request.columns or ["*"]
    select_sql = "*" if selected_columns == ["*"] else ", ".join(_quote_identifier(column) for column in selected_columns)

    params: list[Any] = []
    where_clauses: list[str] = []
    for key, value in (request.filters or {}).items():
        where_clauses.append(f"{_quote_identifier(key)} = %s")
        params.append(value)

    order_sql = ""
    if request.order_by:
        order_sql = " ORDER BY " + ", ".join(
            f"{_quote_identifier(item.column)} {item.direction.upper()}" for item in request.order_by
        )

    query = (
        f"SELECT {select_sql} FROM {_quote_identifier(request.schema_name)}.{_quote_identifier(request.table)}"
        f"{' WHERE ' + ' AND '.join(where_clauses) if where_clauses else ''}"
        f"{order_sql} LIMIT %s"
    )
    params.append(request.limit + 1)

    start = time.perf_counter()
    try:
        async with _open_connection(connection_factory=connection_factory, dsn=dsn) as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await _configure_read_only_session(cursor, timeout_ms=DB_QUERY_DEFAULT_TIMEOUT_MS)
                await cursor.execute(query, params)
                rows = await cursor.fetchall()
                columns = [column.name for column in cursor.description or []]
    except Exception as exc:  # pragma: no cover - exercised through unit mapping tests
        raise _map_db_exception(exc) from exc

    truncated = len(rows) > request.limit
    rows = rows[: request.limit]
    _enforce_result_size(rows)

    columns_returned = request.columns or columns

    return DbRowGetResponse(
        provider_used="postgresql",
        credential_mode=credential_mode,
        capability_id="db.row.get",
        receipt_id=receipt_id,
        execution_id=execution_id,
        bounded_by=DbRowGetBounds(
            row_limit_applied=request.limit,
            column_limit_applied=len(columns_returned),
        ),
        table=DbTableRef(schema=request.schema_name, name=request.table),
        columns_returned=columns_returned,
        rows=rows,
        row_count_returned=len(rows),
        truncated=truncated,
        duration_ms=_duration_ms(start),
    )


async def _configure_read_only_session(cursor: Any, *, timeout_ms: int) -> None:
    await cursor.execute("BEGIN READ ONLY")
    await cursor.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")


async def _execute_statement(cursor: Any, query: str, params: list[Any] | dict[str, Any] | None) -> None:
    if params is None:
        await cursor.execute(query)
    else:
        await cursor.execute(query, params)


async def _fetch_limited_rows(cursor: Any, max_rows: int) -> list[dict[str, Any]]:
    if hasattr(cursor, "fetchmany"):
        rows = await cursor.fetchmany(max_rows + 1)
    else:  # pragma: no cover
        rows = await cursor.fetchall()
    return list(rows)


def _extract_columns(cursor: Any) -> list[DbColumnSchema]:
    columns: list[DbColumnSchema] = []
    for description in cursor.description or []:
        type_name = getattr(description, "type_code", None)
        columns.append(
            DbColumnSchema(
                name=description.name,
                type=str(type_name) if type_name is not None else "unknown",
            )
        )
    return columns


def _enforce_result_size(rows: list[dict[str, Any]]) -> None:
    serialized = json.dumps(rows, default=str, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > DB_RESULT_MAX_BYTES:
        raise DbExecutorError(
            code="db_query_result_too_large",
            message="Result payload exceeded the Wave 1 byte limit",
        )


def _raise_if_query_denied(classification: QueryClassification) -> None:
    if classification.read_only:
        return

    if classification.reason == "parse_error":
        raise DbExecutorError("db_query_invalid", "SQL could not be parsed")
    if classification.reason in {"multi_statement", "multi_statement_denied"}:
        raise DbExecutorError("db_query_multi_statement_denied", "Multi-statement SQL is not allowed")

    raise DbExecutorError("db_query_not_read_only", "Query is outside the read-only Wave 1 envelope")


def _map_db_exception(exc: Exception) -> DbExecutorError:
    message = str(exc)
    lower_message = message.lower()
    # Avoid echoing raw DSNs or internal config strings in error envelopes.
    if isinstance(exc, ValueError):
        return DbExecutorError("db_query_invalid", "Invalid database connection settings")
    if "statement timeout" in lower_message or exc.__class__.__name__ == "QueryCanceled":
        return DbExecutorError("db_query_timeout", "Query exceeded the configured timeout")
    if isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError)):
        return DbExecutorError("db_provider_unavailable", "Database provider unavailable")
    return DbExecutorError("db_query_invalid", message or "Database query failed")


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _duration_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
