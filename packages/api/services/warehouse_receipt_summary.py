"""Human-readable receipt summaries for warehouse capability executions."""

from __future__ import annotations

from typing import Any


def summarize_query_read(response: dict[str, Any]) -> str:
    row_count = response.get("row_count_returned", 0)
    summary = response.get("query_summary", {})
    tables = summary.get("tables_referenced", [])
    duration = response.get("duration_ms", 0)
    truncated = bool(response.get("truncated", summary.get("truncated", False)))
    via = f" via {response['warehouse_ref']}" if response.get("warehouse_ref") else ""

    table_str = ", ".join(tables[:3]) if tables else "unknown"
    suffix = " (truncated)" if truncated else ""
    return f"Read {row_count} warehouse row(s) from [{table_str}]{via} in {duration}ms{suffix}"


def summarize_schema_describe(response: dict[str, Any]) -> str:
    table_count = response.get("table_count_returned", 0)
    datasets = response.get("datasets", [])
    duration = response.get("duration_ms", 0)
    truncated = response.get("truncated", False)
    via = f" via {response['warehouse_ref']}" if response.get("warehouse_ref") else ""

    labels: list[str] = []
    for dataset in datasets[:3]:
        if isinstance(dataset, dict):
            project_id = dataset.get("project_id")
            dataset_id = dataset.get("dataset_id")
            if project_id and dataset_id:
                labels.append(f"{project_id}.{dataset_id}")
                continue
        labels.append(str(dataset))
    dataset_str = ", ".join(labels) if labels else "unknown"
    suffix = " (truncated)" if truncated else ""
    return f"Described {table_count} warehouse table(s) in [{dataset_str}]{via} in {duration}ms{suffix}"


def summarize_warehouse_execution(capability_id: str, response: dict[str, Any]) -> str:
    if capability_id == "warehouse.query.read":
        return summarize_query_read(response)
    if capability_id == "warehouse.schema.describe":
        return summarize_schema_describe(response)
    return f"Warehouse execution completed ({capability_id})"
