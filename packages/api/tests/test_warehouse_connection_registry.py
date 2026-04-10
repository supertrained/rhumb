"""Tests for the warehouse_ref registry."""

from __future__ import annotations

import json

import pytest

from services.warehouse_connection_registry import (
    WarehouseRefError,
    ensure_table_allowed,
    has_any_warehouse_bundle_configured,
    resolve_warehouse_bundle,
)


def _bundle_payload(**overrides):
    payload = {
        "provider": "bigquery",
        "auth_mode": "service_account_json",
        "service_account_json": {
            "type": "service_account",
            "project_id": "proj",
            "client_email": "rhumb@example.iam.gserviceaccount.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
        },
        "billing_project_id": "proj",
        "location": "US",
        "allowed_dataset_refs": ["proj.analytics"],
        "allowed_table_refs": ["proj.analytics.events"],
        "max_rows_returned": 100,
    }
    payload.update(overrides)
    return payload


def test_resolve_warehouse_bundle_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_WAREHOUSE_BQ_MAIN",
        json.dumps(
            _bundle_payload(
                max_bytes_billed=60_000_000,
                max_rows_returned=80,
                max_result_bytes=131072,
                statement_timeout_ms=15000,
                require_partition_filter_for_table_refs=["proj.analytics.events"],
            )
        ),
    )

    bundle = resolve_warehouse_bundle("bq_main")

    assert bundle.provider == "bigquery"
    assert bundle.auth_mode == "service_account_json"
    assert bundle.billing_project_id == "proj"
    assert bundle.allowed_dataset_refs == ("proj.analytics",)
    assert bundle.allowed_table_refs == ("proj.analytics.events",)
    assert bundle.max_bytes_billed == 60_000_000
    assert bundle.max_rows_returned == 80
    assert bundle.max_result_bytes == 131072
    assert bundle.statement_timeout_ms == 15000
    assert bundle.require_partition_filter_for_table_refs == ("proj.analytics.events",)


def test_resolve_warehouse_bundle_accepts_legacy_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_WAREHOUSE_BQ_MAIN",
        json.dumps(
            _bundle_payload(
                billing_project_id=None,
                project_id="legacy-proj",
                max_rows_returned=None,
                default_max_bytes_billed=70_000_000,
                default_max_rows=75,
                result_bytes_cap=120000,
                default_timeout_ms=12000,
            )
        ),
    )

    bundle = resolve_warehouse_bundle("bq_main")

    assert bundle.billing_project_id == "legacy-proj"
    assert bundle.max_bytes_billed == 70_000_000
    assert bundle.max_rows_returned == 75
    assert bundle.max_result_bytes == 120000
    assert bundle.statement_timeout_ms == 12000


def test_resolve_warehouse_bundle_requires_location(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_WAREHOUSE_BQ_MAIN",
        json.dumps(_bundle_payload(location=None)),
    )

    with pytest.raises(WarehouseRefError, match="must declare location"):
        resolve_warehouse_bundle("bq_main")


def test_resolve_warehouse_bundle_requires_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_WAREHOUSE_BQ_MAIN",
        json.dumps(
            _bundle_payload(
                allowed_dataset_refs=[],
                allowed_table_refs=[],
            )
        ),
    )

    with pytest.raises(WarehouseRefError, match="must declare at least one allowed_dataset_refs"):
        resolve_warehouse_bundle("bq_main")


def test_resolve_warehouse_bundle_requires_table_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_WAREHOUSE_BQ_MAIN",
        json.dumps(
            _bundle_payload(
                allowed_dataset_refs=["proj.analytics"],
                allowed_table_refs=[],
            )
        ),
    )

    with pytest.raises(WarehouseRefError, match="must declare at least one allowed_table_refs"):
        resolve_warehouse_bundle("bq_main")


def test_ensure_table_allowed_requires_explicit_table_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_WAREHOUSE_BQ_MAIN",
        json.dumps(_bundle_payload()),
    )

    bundle = resolve_warehouse_bundle("bq_main")

    assert ensure_table_allowed(bundle, "proj.analytics.events") == "proj.analytics.events"
    with pytest.raises(WarehouseRefError, match="is not allowed to access table"):
        ensure_table_allowed(bundle, "proj.analytics.secret_events")
    assert has_any_warehouse_bundle_configured("bigquery") is True
