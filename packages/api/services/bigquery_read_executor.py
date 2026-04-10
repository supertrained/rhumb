"""BigQuery read-first executor for the AUD-18 warehouse wedge."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from schemas.warehouse_capabilities import (
    WAREHOUSE_RESULT_MAX_BYTES,
    WarehouseColumnSchema,
    WarehouseDatasetSchema,
    WarehousePartitioningSchema,
    WarehouseQueryBounds,
    WarehouseQueryReadRequest,
    WarehouseQueryReadResponse,
    WarehouseQuerySummary,
    WarehouseSchemaBounds,
    WarehouseSchemaDescribeRequest,
    WarehouseSchemaDescribeResponse,
    WarehouseTableSchema,
    dataset_ref_for_table,
    normalize_table_ref,
    split_dataset_ref,
)
from services.warehouse_connection_registry import (
    BigQueryWarehouseBundle,
    WarehouseRefError,
    allowed_dataset_refs,
    allowed_table_refs,
    ensure_dataset_allowed,
    ensure_table_allowed,
)

BigQueryClientFactory = Callable[[BigQueryWarehouseBundle], Any]

_COMMENT_RE = re.compile(r"--|/\*|\*/")
_SELECT_COUNT_RE = re.compile(r"\bselect\b", re.IGNORECASE)
_FROM_COUNT_RE = re.compile(r"\bfrom\b", re.IGNORECASE)
_FIRST_KEYWORD_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)")
_FROM_TABLE_RE = re.compile(
    r"\bfrom\s+(?P<table>`[^`]+`|[A-Za-z0-9_.-]+)"
    r"(?:\s+(?:as\s+)?(?!(?:where|group|having|order|limit|qualify)\b)[A-Za-z_][A-Za-z0-9_]*)?"
    r"(?P<rest>.*)\Z",
    re.IGNORECASE | re.DOTALL,
)
_MULTI_STATEMENT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r";"), "Only a single SELECT statement is allowed"),
    (re.compile(r"\bbegin\b", re.IGNORECASE), "Scripts are not allowed"),
    (re.compile(r"\bdeclare\b", re.IGNORECASE), "Scripts are not allowed"),
    (re.compile(r"\bset\b", re.IGNORECASE), "Scripts are not allowed"),
)
_NOT_READ_ONLY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\binsert\b", re.IGNORECASE), "INSERT is not allowed"),
    (re.compile(r"\bupdate\b", re.IGNORECASE), "UPDATE is not allowed"),
    (re.compile(r"\bdelete\b", re.IGNORECASE), "DELETE is not allowed"),
    (re.compile(r"\bmerge\b", re.IGNORECASE), "MERGE is not allowed"),
    (re.compile(r"\bcreate\b", re.IGNORECASE), "CREATE is not allowed"),
    (re.compile(r"\balter\b", re.IGNORECASE), "ALTER is not allowed"),
    (re.compile(r"\bdrop\b", re.IGNORECASE), "DROP is not allowed"),
    (re.compile(r"\btruncate\b", re.IGNORECASE), "TRUNCATE is not allowed"),
    (re.compile(r"\bgrant\b", re.IGNORECASE), "GRANT is not allowed"),
    (re.compile(r"\brevoke\b", re.IGNORECASE), "REVOKE is not allowed"),
)
_REQUEST_INVALID_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bjoin\b", re.IGNORECASE), "JOINs are not allowed"),
    (re.compile(r"\bunion\b", re.IGNORECASE), "UNION is not allowed"),
    (re.compile(r"\bintersect\b", re.IGNORECASE), "INTERSECT is not allowed"),
    (re.compile(r"\bexcept\b", re.IGNORECASE), "EXCEPT is not allowed"),
    (re.compile(r"\bwith\b", re.IGNORECASE), "CTEs are not allowed in the first slice"),
    (re.compile(r"\bunnest\s*\(", re.IGNORECASE), "UNNEST is not allowed"),
    (re.compile(r"\binto\b", re.IGNORECASE), "SELECT INTO is not allowed"),
    (re.compile(r"\bcall\b", re.IGNORECASE), "CALL is not allowed"),
    (re.compile(r"\bexecute\b", re.IGNORECASE), "EXECUTE is not allowed"),
    (re.compile(r"\bexport\s+data\b", re.IGNORECASE), "EXPORT DATA is not allowed"),
    (re.compile(r"\bload\s+data\b", re.IGNORECASE), "LOAD DATA is not allowed"),
    (re.compile(r"\bcopy\b", re.IGNORECASE), "COPY is not allowed"),
    (re.compile(r"\btemp\b", re.IGNORECASE), "Temporary objects are not allowed"),
    (re.compile(r"\bremote\b", re.IGNORECASE), "Remote functions are not allowed"),
    (re.compile(r"\bml\.", re.IGNORECASE), "BigQuery ML statements are not allowed"),
    (re.compile(r"\binformation_schema\b", re.IGNORECASE), "INFORMATION_SCHEMA is not allowed in warehouse.query.read"),
)
_PROJECTION_EXPR_RE = re.compile(
    r"""
    ^
    (
        [A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?
        |
        (?:count|sum|avg|min|max)\(
            \s*(?:\*|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s*
        \)
    )
    (?:\s+as\s+[A-Za-z_][A-Za-z0-9_]*)?
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)
_REST_FUNCTION_CALL_RE = re.compile(
    r"\b(?!in\b|and\b|or\b|not\b|null\b|true\b|false\b)[A-Za-z_][A-Za-z0-9_]*\s*\(",
    re.IGNORECASE,
)
_PARTITION_FILTER_RE = re.compile(
    r"""
    \b(?:[A-Za-z_][A-Za-z0-9_]*\.)?
    (?:_partitiondate|_partitiontime|[A-Za-z_][A-Za-z0-9_]*(?:partition|date|day)[A-Za-z0-9_]*)
    \b
    \s*(?:=|between\b|in\s*\()
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(slots=True)
class WarehouseExecutorError(RuntimeError):
    code: str
    message: str
    status_code: int = 422

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(frozen=True, slots=True)
class _ValidatedReadQuery:
    table_ref: str
    remainder_sql: str


@dataclass(frozen=True, slots=True)
class _DryRunResult:
    bytes_estimate: int


@dataclass(frozen=True, slots=True)
class _ExecuteResult:
    columns: list[WarehouseColumnSchema]
    rows: list[dict[str, Any]]
    bytes_billed: int | None


@dataclass(frozen=True, slots=True)
class _TableMetadata:
    table_type: str
    description: str | None
    partitioning: WarehousePartitioningSchema | None
    clustering: list[str] | None
    columns: list[WarehouseColumnSchema]


async def execute_read_query(
    request: WarehouseQueryReadRequest,
    *,
    bundle: BigQueryWarehouseBundle,
    client_factory: BigQueryClientFactory | None = None,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> WarehouseQueryReadResponse:
    validated = _validate_select_query(request.query)
    try:
        table_ref = ensure_table_allowed(bundle, validated.table_ref)
    except WarehouseRefError as exc:
        raise WarehouseExecutorError(
            code="warehouse_scope_denied",
            message=str(exc),
            status_code=403,
        ) from exc

    _enforce_partition_filter(bundle, validated)
    _ensure_supported_query_params(request.params)

    max_rows = min(request.max_rows, bundle.max_rows_returned)
    timeout_ms = min(request.timeout_ms, bundle.statement_timeout_ms)
    max_bytes_billed = min(
        request.max_bytes_billed or bundle.max_bytes_billed,
        bundle.max_bytes_billed,
    )
    result_bytes_limit = min(bundle.max_result_bytes, WAREHOUSE_RESULT_MAX_BYTES)
    client = _get_client(bundle, client_factory=client_factory)

    start = time.perf_counter()
    dry_run = _perform_dry_run(
        client,
        query=request.query,
        params=request.params,
        max_bytes_billed=max_bytes_billed,
        timeout_ms=timeout_ms,
    )
    if dry_run.bytes_estimate > max_bytes_billed:
        raise WarehouseExecutorError(
            code="warehouse_bytes_limit_exceeded",
            message="BigQuery dry run exceeded the configured bytes cap for this warehouse_ref",
            status_code=422,
        )

    execute_result = _perform_execute(
        client,
        query=request.query,
        params=request.params,
        max_bytes_billed=max_bytes_billed,
        timeout_ms=timeout_ms,
        max_results=max_rows + 1,
    )
    rows, truncated = _truncate_rows_by_bounds(
        execute_result.rows,
        row_limit=max_rows,
        result_bytes_limit=result_bytes_limit,
    )

    return WarehouseQueryReadResponse(
        provider_used="bigquery",
        credential_mode="byok",
        capability_id="warehouse.query.read",
        receipt_id=receipt_id,
        execution_id=execution_id,
        warehouse_ref=request.warehouse_ref,
        billing_project_id=bundle.billing_project_id,
        location=bundle.location,
        bounded_by=WarehouseQueryBounds(
            row_limit_applied=max_rows,
            timeout_ms_applied=timeout_ms,
            max_bytes_billed_applied=max_bytes_billed,
            result_bytes_limit_applied=result_bytes_limit,
        ),
        query_summary=WarehouseQuerySummary(
            statement_type="select",
            tables_referenced=[table_ref],
            dry_run_performed=True,
            dry_run_bytes_processed=dry_run.bytes_estimate,
            truncated=truncated,
        ),
        columns=execute_result.columns,
        rows=rows,
        row_count_returned=len(rows),
        truncated=truncated,
        dry_run_bytes_estimate=dry_run.bytes_estimate,
        actual_bytes_billed=execute_result.bytes_billed,
        duration_ms=_duration_ms(start),
    )


async def describe_schema(
    request: WarehouseSchemaDescribeRequest,
    *,
    bundle: BigQueryWarehouseBundle,
    client_factory: BigQueryClientFactory | None = None,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> WarehouseSchemaDescribeResponse:
    client = _get_client(bundle, client_factory=client_factory)
    start = time.perf_counter()

    datasets = _resolve_dataset_scope(bundle, request)
    table_refs, scope_truncated = _resolve_table_scope(bundle, request, datasets=datasets)

    dataset_objects = [_get_dataset_metadata(client, dataset_ref) for dataset_ref in datasets]

    tables: list[WarehouseTableSchema] = []
    column_limit = bundle.schema_column_limit
    table_limit = bundle.schema_table_limit
    truncated = scope_truncated
    for table_ref in table_refs[:table_limit]:
        metadata = _get_table_metadata(client, table_ref)
        columns: list[WarehouseColumnSchema] | None = None
        if request.include_columns:
            columns = metadata.columns[:column_limit]
            if len(metadata.columns) > column_limit:
                truncated = True
        tables.append(
            WarehouseTableSchema(
                table_ref=table_ref,
                table_type=metadata.table_type,
                description=metadata.description,
                partitioning=metadata.partitioning,
                clustering=metadata.clustering,
                columns=columns,
            )
        )

    if len(table_refs) > table_limit:
        truncated = True

    return WarehouseSchemaDescribeResponse(
        provider_used="bigquery",
        credential_mode="byok",
        capability_id="warehouse.schema.describe",
        receipt_id=receipt_id,
        execution_id=execution_id,
        warehouse_ref=request.warehouse_ref,
        billing_project_id=bundle.billing_project_id,
        location=bundle.location,
        bounded_by=WarehouseSchemaBounds(
            dataset_limit_applied=min(max(len(dataset_objects), 1), bundle.schema_dataset_limit),
            table_limit_applied=table_limit,
            column_limit_applied=column_limit,
        ),
        datasets=dataset_objects,
        tables=tables,
        table_count_returned=len(tables),
        truncated=truncated,
        duration_ms=_duration_ms(start),
    )


def _validate_select_query(query: str) -> _ValidatedReadQuery:
    if _COMMENT_RE.search(query):
        raise _request_invalid("SQL comments are not allowed")

    scrubbed = _scrub_string_literals(query)
    normalized = re.sub(r"\s+", " ", scrubbed.strip())
    lowered = normalized.lower()

    for pattern, reason in _MULTI_STATEMENT_PATTERNS:
        if pattern.search(lowered):
            raise _multi_statement_denied(reason)

    first_keyword = _first_keyword(lowered)
    if not lowered.startswith("select "):
        if first_keyword in {"insert", "update", "delete", "merge", "create", "alter", "drop", "truncate", "grant", "revoke"}:
            raise _not_read_only("Only read-only SELECT statements are allowed")
        raise _request_invalid("Only a single Standard SQL SELECT statement is allowed")

    if len(_SELECT_COUNT_RE.findall(lowered)) != 1 or len(_FROM_COUNT_RE.findall(lowered)) != 1:
        raise _request_invalid("Exactly one SELECT statement against exactly one table is required")

    for pattern, reason in _NOT_READ_ONLY_PATTERNS:
        if pattern.search(lowered):
            raise _not_read_only(reason)

    for pattern, reason in _REQUEST_INVALID_PATTERNS:
        if pattern.search(lowered):
            raise _request_invalid(reason)

    match = _FROM_TABLE_RE.search(query.strip())
    if match is None:
        raise _request_invalid("Query must use a direct FROM project.dataset.table shape")

    prefix = query.strip()[:match.start()]
    projection = re.sub(r"^\s*select\s+", "", prefix, flags=re.IGNORECASE | re.DOTALL)
    _validate_projection_list(projection.strip())

    try:
        table_ref = normalize_table_ref(match.group("table"))
    except ValueError as exc:
        raise _request_invalid("Query must use an explicit project.dataset.table reference") from exc
    if "*" in table_ref:
        raise _request_invalid("Wildcard table references are not allowed")
    if ".information_schema." in table_ref.lower():
        raise _request_invalid("INFORMATION_SCHEMA is not allowed in warehouse.query.read")

    rest = match.group("rest") or ""
    if re.search(r"^\s*,", rest):
        raise _request_invalid("Exactly one table reference is required")
    if _REST_FUNCTION_CALL_RE.search(_scrub_string_literals(rest)):
        raise _request_invalid("Function calls outside the select list are not allowed")

    return _ValidatedReadQuery(table_ref=table_ref, remainder_sql=rest)


def _validate_projection_list(projection: str) -> None:
    expressions = _split_projection_expressions(projection)
    if not expressions:
        raise _request_invalid("SELECT must project at least one explicit column or safe aggregate")
    for expression in expressions:
        normalized = re.sub(r"\s+", " ", expression.strip())
        if re.search(r"(^|[\s,(])(?:\*|[A-Za-z_][A-Za-z0-9_]*\.\*)([\s,),]|$)", normalized):
            if not re.fullmatch(
                r"count\(\s*\*\s*\)(?:\s+as\s+[A-Za-z_][A-Za-z0-9_]*)?",
                normalized,
                re.IGNORECASE,
            ):
                raise _request_invalid("SELECT * and wildcard projections are not allowed")
        if not _PROJECTION_EXPR_RE.fullmatch(normalized):
            raise _request_invalid("SELECT projections must use explicit columns or simple aggregates only")


def _split_projection_expressions(projection: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in projection:
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        elif char == "," and depth == 0:
            value = "".join(current).strip()
            if value:
                parts.append(value)
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _scrub_string_literals(value: str) -> str:
    return re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"", "''", value)


def _first_keyword(value: str) -> str | None:
    match = _FIRST_KEYWORD_RE.match(value)
    if match is None:
        return None
    return match.group(1).lower()


def _enforce_partition_filter(bundle: BigQueryWarehouseBundle, validated: _ValidatedReadQuery) -> None:
    if validated.table_ref not in bundle.require_partition_filter_for_table_refs:
        return
    scrubbed = re.sub(r"\s+", " ", _scrub_string_literals(validated.remainder_sql).lower())
    if not _PARTITION_FILTER_RE.search(scrubbed):
        raise WarehouseExecutorError(
            code="warehouse_bytes_limit_exceeded",
            message="A bounded partition/date filter is required for this allowlisted table",
            status_code=422,
        )


def _get_client(
    bundle: BigQueryWarehouseBundle,
    *,
    client_factory: BigQueryClientFactory | None,
) -> Any:
    if client_factory is not None:
        return client_factory(bundle)

    try:
        from google.cloud import bigquery
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise WarehouseExecutorError(
            code="warehouse_provider_unavailable",
            message="BigQuery client dependency is not installed",
            status_code=503,
        ) from exc

    try:
        from google.oauth2 import service_account
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise WarehouseExecutorError(
            code="warehouse_provider_unavailable",
            message="Google service-account dependency is not installed",
            status_code=503,
        ) from exc

    try:
        credentials = service_account.Credentials.from_service_account_info(
            bundle.service_account_info
        )
        project_id = bundle.billing_project_id or credentials.project_id
        if not project_id:
            raise WarehouseExecutorError(
                code="warehouse_ref_invalid",
                message="warehouse_ref bundle is missing a billing_project_id",
                status_code=400,
            )
        return _GoogleBigQueryAdapter(
            bigquery.Client(
                project=project_id,
                credentials=credentials,
                location=bundle.location,
            ),
            bigquery_module=bigquery,
        )
    except WarehouseExecutorError:
        raise
    except Exception as exc:  # pragma: no cover - environment dependent
        raise WarehouseExecutorError(
            code="warehouse_provider_unavailable",
            message="BigQuery client initialization failed",
            status_code=503,
        ) from exc


def _perform_dry_run(
    client: Any,
    *,
    query: str,
    params: list[Any] | dict[str, Any] | None,
    max_bytes_billed: int,
    timeout_ms: int,
) -> _DryRunResult:
    try:
        result = client.dry_run_query(
            query=query,
            params=params,
            max_bytes_billed=max_bytes_billed,
            timeout_ms=timeout_ms,
        )
    except WarehouseExecutorError:
        raise
    except Exception as exc:  # pragma: no cover - environment dependent
        raise _provider_error(
            exc,
            not_found_message="Referenced BigQuery object was not found during dry run",
            timeout_message="BigQuery dry run timed out",
            default_message="BigQuery dry run failed",
        ) from exc
    return _DryRunResult(bytes_estimate=int(getattr(result, "bytes_estimate", getattr(result, "bytes_processed", 0)) or 0))


def _perform_execute(
    client: Any,
    *,
    query: str,
    params: list[Any] | dict[str, Any] | None,
    max_bytes_billed: int,
    timeout_ms: int,
    max_results: int,
) -> _ExecuteResult:
    try:
        result = client.execute_query(
            query=query,
            params=params,
            max_bytes_billed=max_bytes_billed,
            timeout_ms=timeout_ms,
            max_results=max_results,
        )
    except WarehouseExecutorError:
        raise
    except Exception as exc:  # pragma: no cover - environment dependent
        raise _provider_error(
            exc,
            not_found_message="Referenced BigQuery object was not found",
            timeout_message="BigQuery query timed out",
            default_message="BigQuery query execution failed",
        ) from exc

    columns = [
        WarehouseColumnSchema(
            name=str(column.name),
            type=str(getattr(column, "type", getattr(column, "field_type", "UNKNOWN"))),
            nullable=_column_nullable(column),
            mode=_column_mode(column),
            description=getattr(column, "description", None),
        )
        for column in getattr(result, "columns", [])
    ]
    rows = [dict(row) for row in getattr(result, "rows", [])]
    return _ExecuteResult(
        columns=columns,
        rows=rows,
        bytes_billed=_optional_int(getattr(result, "bytes_billed", getattr(result, "bytes_processed", None))),
    )


def _truncate_rows_by_bounds(
    rows: list[dict[str, Any]],
    *,
    row_limit: int,
    result_bytes_limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    accepted: list[dict[str, Any]] = []
    bytes_used = 0
    truncated = len(rows) > row_limit
    for row in rows[: row_limit + 1]:
        if len(accepted) >= row_limit:
            truncated = True
            break
        encoded = json.dumps(row, default=str, separators=(",", ":")).encode("utf-8")
        if bytes_used + len(encoded) > result_bytes_limit:
            truncated = True
            break
        accepted.append(row)
        bytes_used += len(encoded)
    return accepted, truncated


def _resolve_dataset_scope(
    bundle: BigQueryWarehouseBundle,
    request: WarehouseSchemaDescribeRequest,
) -> list[str]:
    try:
        if request.dataset_refs:
            datasets = [ensure_dataset_allowed(bundle, dataset_ref) for dataset_ref in request.dataset_refs]
        else:
            datasets = list(allowed_dataset_refs(bundle))
    except WarehouseRefError as exc:
        raise WarehouseExecutorError(
            code="warehouse_scope_denied",
            message=str(exc),
            status_code=403,
        ) from exc
    return datasets[: bundle.schema_dataset_limit]


def _resolve_table_scope(
    bundle: BigQueryWarehouseBundle,
    request: WarehouseSchemaDescribeRequest,
    *,
    datasets: list[str],
) -> tuple[list[str], bool]:
    try:
        if request.table_refs:
            table_refs = [ensure_table_allowed(bundle, table_ref) for table_ref in request.table_refs]
        else:
            table_refs = list(allowed_table_refs(bundle))
    except WarehouseRefError as exc:
        raise WarehouseExecutorError(
            code="warehouse_scope_denied",
            message=str(exc),
            status_code=403,
        ) from exc

    if request.dataset_refs:
        dataset_filter = set(datasets)
        if request.table_refs:
            for table_ref in table_refs:
                if dataset_ref_for_table(table_ref) not in dataset_filter:
                    raise _request_invalid("Requested table_refs must belong to the requested dataset_refs scope")
        else:
            table_refs = [table_ref for table_ref in table_refs if dataset_ref_for_table(table_ref) in dataset_filter]

    truncated = len(table_refs) > bundle.schema_table_limit
    return table_refs[: bundle.schema_table_limit], truncated


def _get_dataset_metadata(client: Any, dataset_ref: str) -> WarehouseDatasetSchema:
    project_id, dataset_id = split_dataset_ref(dataset_ref)
    getter = getattr(client, "get_dataset", None)
    if getter is None:
        return WarehouseDatasetSchema(project_id=project_id, dataset_id=dataset_id)
    try:
        getter(dataset_ref)
    except Exception as exc:  # pragma: no cover - environment dependent
        raise _provider_error(
            exc,
            not_found_message=f"Allowlisted BigQuery dataset '{dataset_ref}' was not found",
            timeout_message="BigQuery dataset metadata fetch timed out",
            default_message="BigQuery dataset metadata fetch failed",
        ) from exc
    return WarehouseDatasetSchema(project_id=project_id, dataset_id=dataset_id)


def _get_table_metadata(client: Any, table_ref: str) -> _TableMetadata:
    try:
        table = client.get_table(table_ref)
    except Exception as exc:  # pragma: no cover - environment dependent
        raise _provider_error(
            exc,
            not_found_message=f"Allowlisted BigQuery table '{table_ref}' was not found",
            timeout_message="BigQuery table metadata fetch timed out",
            default_message="BigQuery table metadata fetch failed",
        ) from exc

    raw_columns = getattr(table, "schema", None) or []
    columns = [
        WarehouseColumnSchema(
            name=str(field.name),
            type=str(getattr(field, "field_type", getattr(field, "type", "UNKNOWN"))),
            nullable=_column_nullable(field),
            mode=_column_mode(field),
            description=getattr(field, "description", None),
        )
        for field in raw_columns
    ]
    return _TableMetadata(
        table_type=_normalize_table_kind(getattr(table, "table_type", None)),
        description=_clean_text(getattr(table, "description", None)),
        partitioning=_partitioning_metadata(table),
        clustering=_clustering_metadata(table),
        columns=columns,
    )


def _column_mode(field: object) -> str | None:
    mode = getattr(field, "mode", None)
    if mode is None:
        return None
    return str(mode)


def _column_nullable(field: object) -> bool | None:
    mode = _column_mode(field)
    if mode is None:
        return None
    return mode.upper() != "REQUIRED"


def _partitioning_metadata(table: object) -> WarehousePartitioningSchema | None:
    partitioning_type = _clean_text(
        getattr(table, "partitioning_type", None) or getattr(table, "time_partitioning_type", None)
    )
    partitioning_field = _clean_text(
        getattr(table, "partitioning_field", None)
        or getattr(getattr(table, "time_partitioning", None), "field", None)
        or getattr(getattr(table, "range_partitioning", None), "field", None)
    )
    if partitioning_type is None and partitioning_field is None:
        return None
    return WarehousePartitioningSchema(type=partitioning_type, field=partitioning_field)


def _clustering_metadata(table: object) -> list[str] | None:
    fields = getattr(table, "clustering_fields", None)
    if not fields:
        return None
    return [str(field) for field in fields if str(field).strip()]


def _normalize_table_kind(value: object) -> str:
    normalized = str(value or "").strip().upper()
    mapping = {
        "TABLE": "table",
        "VIEW": "view",
        "MATERIALIZED_VIEW": "materialized_view",
        "EXTERNAL": "external",
        "SNAPSHOT": "snapshot",
    }
    return mapping.get(normalized, "unknown")


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _provider_error(
    exc: Exception,
    *,
    not_found_message: str,
    timeout_message: str,
    default_message: str,
) -> WarehouseExecutorError:
    if _is_timeout_error(exc):
        return WarehouseExecutorError(
            code="warehouse_timeout",
            message=timeout_message,
            status_code=504,
        )
    if _is_not_found_error(exc):
        return WarehouseExecutorError(
            code="warehouse_object_not_found",
            message=not_found_message,
            status_code=404,
        )
    return WarehouseExecutorError(
        code="warehouse_provider_unavailable",
        message=default_message,
        status_code=503,
    )


def _is_timeout_error(exc: Exception) -> bool:
    name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    return isinstance(exc, TimeoutError) or "deadline" in name or "timeout" in name or "timed out" in message


def _is_not_found_error(exc: Exception) -> bool:
    name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    return "notfound" in name or "not found" in message or "404" in message


def _request_invalid(message: str) -> WarehouseExecutorError:
    return WarehouseExecutorError(
        code="warehouse_request_invalid",
        message=message,
        status_code=400,
    )


def _not_read_only(message: str) -> WarehouseExecutorError:
    return WarehouseExecutorError(
        code="warehouse_query_not_read_only",
        message=message,
        status_code=422,
    )


def _multi_statement_denied(message: str) -> WarehouseExecutorError:
    return WarehouseExecutorError(
        code="warehouse_query_multi_statement_denied",
        message=message,
        status_code=422,
    )


def _duration_ms(start: float) -> int:
    return max(0, round((time.perf_counter() - start) * 1000))


class _GoogleBigQueryAdapter:
    def __init__(self, client: Any, *, bigquery_module: Any):
        self._client = client
        self._bigquery = bigquery_module

    def dry_run_query(
        self,
        *,
        query: str,
        params: list[Any] | dict[str, Any] | None,
        max_bytes_billed: int,
        timeout_ms: int,
    ) -> _DryRunResult:
        query_parameters = _build_query_parameters(params, bigquery_module=self._bigquery)
        config = self._bigquery.QueryJobConfig(
            dry_run=True,
            use_legacy_sql=False,
            use_query_cache=False,
            maximum_bytes_billed=max_bytes_billed,
            job_timeout_ms=timeout_ms,
            query_parameters=query_parameters or None,
        )
        job = self._client.query(query, job_config=config)
        return _DryRunResult(bytes_estimate=int(getattr(job, "total_bytes_processed", 0) or 0))

    def execute_query(
        self,
        *,
        query: str,
        params: list[Any] | dict[str, Any] | None,
        max_bytes_billed: int,
        timeout_ms: int,
        max_results: int,
    ) -> _ExecuteResult:
        query_parameters = _build_query_parameters(params, bigquery_module=self._bigquery)
        config = self._bigquery.QueryJobConfig(
            dry_run=False,
            use_legacy_sql=False,
            use_query_cache=False,
            maximum_bytes_billed=max_bytes_billed,
            job_timeout_ms=timeout_ms,
            query_parameters=query_parameters or None,
        )
        job = self._client.query(query, job_config=config)
        iterator = job.result(max_results=max_results, timeout=max(timeout_ms / 1000.0, 1.0))
        rows = [dict(row.items()) for row in iterator]
        columns = list(getattr(job, "schema", None) or getattr(iterator, "schema", None) or [])
        return _ExecuteResult(
            columns=[
                WarehouseColumnSchema(
                    name=str(column.name),
                    type=str(getattr(column, "field_type", getattr(column, "type", "UNKNOWN"))),
                    nullable=_column_nullable(column),
                    mode=_column_mode(column),
                    description=getattr(column, "description", None),
                )
                for column in columns
            ],
            rows=rows,
            bytes_billed=_optional_int(getattr(job, "total_bytes_billed", None)),
        )

    def get_dataset(self, dataset_ref: str) -> Any:
        return self._client.get_dataset(dataset_ref)

    def list_tables(self, dataset_ref: str, max_results: int) -> Iterable[Any]:
        return self._client.list_tables(dataset_ref, max_results=max_results)

    def get_table(self, table_ref: str) -> Any:
        return self._client.get_table(table_ref)


def _build_query_parameters(
    params: list[Any] | dict[str, Any] | None,
    *,
    bigquery_module: Any,
) -> list[Any]:
    if params is None:
        return []
    _ensure_supported_query_params(params)
    if isinstance(params, list):
        return [
            _build_query_parameter(None, value, bigquery_module=bigquery_module)
            for value in params
        ]
    if isinstance(params, dict):
        built: list[Any] = []
        for name, value in params.items():
            _validate_named_query_parameter_name(name)
            built.append(_build_query_parameter(str(name), value, bigquery_module=bigquery_module))
        return built
    raise _request_invalid("params must be either a positional list or named object")


def _build_query_parameter(name: str | None, value: Any, *, bigquery_module: Any) -> Any:
    if isinstance(value, bool):
        return bigquery_module.ScalarQueryParameter(name, "BOOL", value)
    if isinstance(value, int) and not isinstance(value, bool):
        return bigquery_module.ScalarQueryParameter(name, "INT64", value)
    if isinstance(value, float):
        return bigquery_module.ScalarQueryParameter(name, "FLOAT64", value)
    if isinstance(value, str):
        return bigquery_module.ScalarQueryParameter(name, "STRING", value)
    if isinstance(value, list):
        if not value:
            raise _request_invalid("Array query parameters must not be empty")
        element_type = _bigquery_scalar_type(value[0])
        normalized_values: list[Any] = []
        for item in value:
            if _bigquery_scalar_type(item) != element_type:
                raise _request_invalid("Array query parameters must contain values of one scalar type")
            normalized_values.append(item)
        return bigquery_module.ArrayQueryParameter(name, element_type, normalized_values)
    raise _request_invalid("Unsupported query parameter type; use strings, numbers, booleans, or arrays of one scalar type")


def _ensure_supported_query_params(params: list[Any] | dict[str, Any] | None) -> None:
    if params is None:
        return
    if isinstance(params, list):
        for value in params:
            _validate_query_param_value(value)
        return
    if isinstance(params, dict):
        for name, value in params.items():
            _validate_named_query_parameter_name(name)
            _validate_query_param_value(value)
        return
    raise _request_invalid("params must be either a positional list or named object")


def _validate_named_query_parameter_name(name: object) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(name)):
        raise _request_invalid("Named query parameters must use simple identifiers")


def _validate_query_param_value(value: Any) -> None:
    if isinstance(value, list):
        if not value:
            raise _request_invalid("Array query parameters must not be empty")
        element_type = _bigquery_scalar_type(value[0])
        for item in value:
            if _bigquery_scalar_type(item) != element_type:
                raise _request_invalid("Array query parameters must contain values of one scalar type")
        return
    _bigquery_scalar_type(value)


def _bigquery_scalar_type(value: Any) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int) and not isinstance(value, bool):
        return "INT64"
    if isinstance(value, float):
        return "FLOAT64"
    if isinstance(value, str):
        return "STRING"
    raise _request_invalid("Unsupported query parameter type; use strings, numbers, booleans, or arrays of one scalar type")
