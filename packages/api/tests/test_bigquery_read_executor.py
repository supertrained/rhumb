"""Tests for the BigQuery warehouse read-first executor."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from schemas.warehouse_capabilities import WarehouseQueryReadRequest, WarehouseSchemaDescribeRequest
from services.bigquery_read_executor import WarehouseExecutorError, describe_schema, execute_read_query
from services.warehouse_connection_registry import BigQueryWarehouseBundle


class NotFoundError(Exception):
    pass


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.dataset_refs = {"proj.analytics"}
        self.table_refs = {"proj.analytics.events"}

    def dry_run_query(self, *, query: str, params, max_bytes_billed: int, timeout_ms: int):
        self.calls.append(f"dry:{params}:{max_bytes_billed}:{timeout_ms}")
        return SimpleNamespace(bytes_estimate=1200)

    def execute_query(self, *, query: str, params, max_bytes_billed: int, timeout_ms: int, max_results: int):
        self.calls.append(f"run:{params}:{max_results}")
        return SimpleNamespace(
            columns=[
                SimpleNamespace(name="user_id", field_type="STRING", mode="NULLABLE"),
                SimpleNamespace(name="total", field_type="INTEGER", mode="NULLABLE"),
            ],
            rows=[
                {"user_id": "u_1", "total": 10},
                {"user_id": "u_2", "total": 20},
                {"user_id": "u_3", "total": 30},
            ],
            bytes_billed=900,
        )

    def get_dataset(self, dataset_ref: str):
        self.calls.append(f"dataset:{dataset_ref}")
        if dataset_ref not in self.dataset_refs:
            raise NotFoundError(f"dataset not found: {dataset_ref}")
        return SimpleNamespace(project="proj", dataset_id="analytics")

    def get_table(self, table_ref: str):
        self.calls.append(f"table:{table_ref}")
        if table_ref not in self.table_refs:
            raise NotFoundError(f"table not found: {table_ref}")
        return SimpleNamespace(
            table_type="TABLE",
            description="Daily events table",
            partitioning_type="DAY",
            partitioning_field="event_date",
            clustering_fields=["user_id"],
            schema=[
                SimpleNamespace(name="user_id", field_type="STRING", mode="NULLABLE"),
                SimpleNamespace(name="event_date", field_type="DATE", mode="REQUIRED"),
                SimpleNamespace(name="event_count", field_type="INTEGER", mode="NULLABLE"),
            ],
        )


def _bundle(**overrides) -> BigQueryWarehouseBundle:
    data = {
        "warehouse_ref": "bq_main",
        "provider": "bigquery",
        "auth_mode": "service_account_json",
        "service_account_info": {
            "type": "service_account",
            "project_id": "proj",
            "client_email": "rhumb@example.iam.gserviceaccount.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
        },
        "billing_project_id": "proj",
        "location": "US",
        "allowed_dataset_refs": ("proj.analytics",),
        "allowed_table_refs": ("proj.analytics.events",),
        "max_bytes_billed": 50_000_000,
        "max_rows_returned": 2,
        "max_result_bytes": 262144,
        "statement_timeout_ms": 5000,
        "require_partition_filter_for_table_refs": (),
        "schema_dataset_limit": 5,
        "schema_table_limit": 5,
        "schema_column_limit": 2,
    }
    data.update(overrides)
    return BigQueryWarehouseBundle(**data)


@pytest.mark.asyncio
async def test_execute_read_query_enforces_dry_run_and_contract_response() -> None:
    client = FakeClient()
    request = WarehouseQueryReadRequest(
        warehouse_ref="bq_main",
        query=(
            "SELECT user_id, COUNT(*) AS total "
            "FROM proj.analytics.events "
            "WHERE event_date = @event_date "
            "GROUP BY user_id ORDER BY user_id"
        ),
        params={"event_date": "2026-04-08"},
        max_rows=10,
        timeout_ms=9999,
    )

    response = await execute_read_query(
        request,
        bundle=_bundle(require_partition_filter_for_table_refs=("proj.analytics.events",)),
        client_factory=lambda _bundle: client,
    )

    assert client.calls == [
        "dry:{'event_date': '2026-04-08'}:50000000:5000",
        "run:{'event_date': '2026-04-08'}:3",
    ]
    assert response.billing_project_id == "proj"
    assert response.location == "US"
    assert response.row_count_returned == 2
    assert response.truncated is True
    assert response.dry_run_bytes_estimate == 1200
    assert response.actual_bytes_billed == 900
    assert response.query_summary.tables_referenced == ["proj.analytics.events"]
    assert response.bounded_by.row_limit_applied == 2
    assert response.bounded_by.timeout_ms_applied == 5000


@pytest.mark.asyncio
async def test_execute_read_query_rejects_select_star_as_request_invalid() -> None:
    request = WarehouseQueryReadRequest(
        warehouse_ref="bq_main",
        query="SELECT * FROM proj.analytics.events",
    )

    with pytest.raises(WarehouseExecutorError) as exc:
        await execute_read_query(
            request,
            bundle=_bundle(),
            client_factory=lambda _bundle: FakeClient(),
        )

    assert exc.value.code == "warehouse_request_invalid"
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_execute_read_query_rejects_unsupported_param_shapes() -> None:
    request = WarehouseQueryReadRequest(
        warehouse_ref="bq_main",
        query="SELECT user_id FROM proj.analytics.events WHERE user_id = @user_id",
        params={"user_id": {"nested": "nope"}},
    )

    with pytest.raises(WarehouseExecutorError) as exc:
        await execute_read_query(
            request,
            bundle=_bundle(),
            client_factory=lambda _bundle: FakeClient(),
        )

    assert exc.value.code == "warehouse_request_invalid"
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_execute_read_query_rejects_multi_statement_scripts() -> None:
    request = WarehouseQueryReadRequest(
        warehouse_ref="bq_main",
        query="SELECT user_id FROM proj.analytics.events;",
    )

    with pytest.raises(WarehouseExecutorError) as exc:
        await execute_read_query(
            request,
            bundle=_bundle(),
            client_factory=lambda _bundle: FakeClient(),
        )

    assert exc.value.code == "warehouse_query_multi_statement_denied"
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_execute_read_query_rejects_non_read_only_statement() -> None:
    request = WarehouseQueryReadRequest(
        warehouse_ref="bq_main",
        query="DELETE FROM proj.analytics.events",
    )

    with pytest.raises(WarehouseExecutorError) as exc:
        await execute_read_query(
            request,
            bundle=_bundle(),
            client_factory=lambda _bundle: FakeClient(),
        )

    assert exc.value.code == "warehouse_query_not_read_only"
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_execute_read_query_requires_allowlisted_table() -> None:
    request = WarehouseQueryReadRequest(
        warehouse_ref="bq_main",
        query="SELECT user_id FROM proj.analytics.secret_events",
    )

    with pytest.raises(WarehouseExecutorError) as exc:
        await execute_read_query(
            request,
            bundle=_bundle(allowed_table_refs=("proj.analytics.events",)),
            client_factory=lambda _bundle: FakeClient(),
        )

    assert exc.value.code == "warehouse_scope_denied"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_execute_read_query_requires_partition_filter_when_configured() -> None:
    request = WarehouseQueryReadRequest(
        warehouse_ref="bq_main",
        query="SELECT user_id FROM proj.analytics.events WHERE user_id = 'u_1'",
    )

    with pytest.raises(WarehouseExecutorError) as exc:
        await execute_read_query(
            request,
            bundle=_bundle(require_partition_filter_for_table_refs=("proj.analytics.events",)),
            client_factory=lambda _bundle: FakeClient(),
        )

    assert exc.value.code == "warehouse_bytes_limit_exceeded"
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_describe_schema_returns_bounded_contract_metadata() -> None:
    client = FakeClient()
    request = WarehouseSchemaDescribeRequest(warehouse_ref="bq_main")

    response = await describe_schema(
        request,
        bundle=_bundle(),
        client_factory=lambda _bundle: client,
    )

    assert response.billing_project_id == "proj"
    assert response.datasets[0].project_id == "proj"
    assert response.datasets[0].dataset_id == "analytics"
    assert response.table_count_returned == 1
    assert response.tables[0].table_ref == "proj.analytics.events"
    assert response.tables[0].table_type == "table"
    assert response.tables[0].description == "Daily events table"
    assert response.tables[0].partitioning is not None
    assert response.tables[0].partitioning.field == "event_date"
    assert response.tables[0].clustering == ["user_id"]
    assert [column.name for column in response.tables[0].columns or []] == ["user_id", "event_date"]
    assert response.truncated is True
    assert client.calls == ["dataset:proj.analytics", "table:proj.analytics.events"]


@pytest.mark.asyncio
async def test_describe_schema_omits_columns_when_not_requested() -> None:
    response = await describe_schema(
        WarehouseSchemaDescribeRequest(warehouse_ref="bq_main", include_columns=False),
        bundle=_bundle(),
        client_factory=lambda _bundle: FakeClient(),
    )

    assert response.tables[0].columns is None


@pytest.mark.asyncio
async def test_describe_schema_maps_missing_objects_to_404() -> None:
    client = FakeClient()
    client.table_refs.clear()

    with pytest.raises(WarehouseExecutorError) as exc:
        await describe_schema(
            WarehouseSchemaDescribeRequest(warehouse_ref="bq_main", table_refs=["proj.analytics.events"]),
            bundle=_bundle(),
            client_factory=lambda _bundle: client,
        )

    assert exc.value.code == "warehouse_object_not_found"
    assert exc.value.status_code == 404
