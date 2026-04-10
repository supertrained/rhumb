"""Tests for warehouse capability schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.warehouse_capabilities import (
    WarehouseQueryReadRequest,
    WarehouseSchemaDescribeRequest,
)


def test_query_request_normalizes_query_and_ref() -> None:
    request = WarehouseQueryReadRequest(
        warehouse_ref="bq_main",
        query="  SELECT user_id FROM proj.analytics.events  ",
        params={"user_id": "u_1"},
    )

    assert request.warehouse_ref == "bq_main"
    assert request.query == "SELECT user_id FROM proj.analytics.events"
    assert request.params == {"user_id": "u_1"}


def test_query_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        WarehouseQueryReadRequest(
            warehouse_ref="bq_main",
            query="SELECT user_id FROM proj.analytics.events",
            provider="bigquery",
        )


def test_query_request_rejects_too_many_params() -> None:
    with pytest.raises(ValidationError, match="params supports at most"):
        WarehouseQueryReadRequest(
            warehouse_ref="bq_main",
            query="SELECT user_id FROM proj.analytics.events WHERE user_id IN UNNEST(@user_ids)",
            params={f"p{i}": i for i in range(51)},
        )


def test_schema_request_normalizes_refs() -> None:
    request = WarehouseSchemaDescribeRequest(
        warehouse_ref="bq_main",
        dataset_refs=["Proj.Analytics"],
        table_refs=["Proj.Analytics.Events"],
    )

    assert request.dataset_refs == ["proj.analytics"]
    assert request.table_refs == ["proj.analytics.events"]


def test_schema_request_rejects_invalid_dataset_ref() -> None:
    with pytest.raises(ValidationError, match="dataset_ref must be in part.part form"):
        WarehouseSchemaDescribeRequest(
            warehouse_ref="bq_main",
            dataset_refs=["analytics"],
        )
