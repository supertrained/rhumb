"""Human-readable receipt summaries for DB-read capability executions."""

from __future__ import annotations

from typing import Any


def summarize_query_read(response: dict[str, Any]) -> str:
    """One-line summary for a db.query.read execution."""
    row_count = response.get("row_count_returned", 0)
    summary = response.get("query_summary", {})
    tables = summary.get("tables_referenced", [])
    duration = response.get("duration_ms", 0)
    truncated = summary.get("truncated", False)

    table_str = ", ".join(tables[:3]) if tables else "unknown"
    suffix = " (truncated)" if truncated else ""
    return f"Read {row_count} row(s) from [{table_str}] in {duration}ms{suffix}"


def summarize_schema_describe(response: dict[str, Any]) -> str:
    """One-line summary for a db.schema.describe execution."""
    table_count = len(response.get("tables", []))
    schemas = response.get("schemas", [])
    duration = response.get("duration_ms", 0)
    truncated = response.get("truncated", False)

    schema_str = ", ".join(schemas[:3]) if schemas else "public"
    suffix = " (truncated)" if truncated else ""
    return f"Described {table_count} table(s) in schema [{schema_str}] in {duration}ms{suffix}"


def summarize_row_get(response: dict[str, Any]) -> str:
    """One-line summary for a db.row.get execution."""
    row_count = response.get("row_count_returned", 0)
    table = response.get("table", {})
    table_name = f"{table.get('schema', 'public')}.{table.get('name', '?')}"
    duration = response.get("duration_ms", 0)
    truncated = response.get("truncated", False)

    suffix = " (truncated)" if truncated else ""
    return f"Got {row_count} row(s) from {table_name} in {duration}ms{suffix}"


def summarize_db_execution(capability_id: str, response: dict[str, Any]) -> str:
    """Dispatch to the correct summarizer based on capability_id."""
    if capability_id == "db.query.read":
        return summarize_query_read(response)
    if capability_id == "db.schema.describe":
        return summarize_schema_describe(response)
    if capability_id == "db.row.get":
        return summarize_row_get(response)
    return f"DB execution completed ({capability_id})"
