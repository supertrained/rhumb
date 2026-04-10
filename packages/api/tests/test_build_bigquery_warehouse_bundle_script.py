from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "build_bigquery_warehouse_bundle.py"

spec = importlib.util.spec_from_file_location("build_bigquery_warehouse_bundle", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
build_bigquery_warehouse_bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_bigquery_warehouse_bundle)


def test_extract_sop_defaults_accepts_embedded_bundle_note() -> None:
    defaults = build_bigquery_warehouse_bundle._extract_sop_defaults(
        {
            "notesPlain": """
            {
              "provider": "bigquery",
              "auth_mode": "service_account_json",
              "service_account_json": {
                "type": "service_account",
                "project_id": "proj",
                "client_email": "svc@proj.iam.gserviceaccount.com",
                "private_key": "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n"
              },
              "billing_project_id": "proj",
              "location": "US",
              "allowed_dataset_refs": ["proj.analytics"],
              "allowed_table_refs": ["proj.analytics.events"],
              "max_bytes_billed": 12345
            }
            """,
            "fields": [],
        }
    )

    assert defaults["billing_project_id"] == "proj"
    assert defaults["location"] == "US"
    assert defaults["allowed_dataset_refs"] == ["proj.analytics"]
    assert defaults["allowed_table_refs"] == ["proj.analytics.events"]
    assert defaults["max_bytes_billed"] == 12345
    assert defaults["service_account_json"]["client_email"] == "svc@proj.iam.gserviceaccount.com"


def test_build_bundle_prefers_cli_overrides_over_item_defaults() -> None:
    args = build_bigquery_warehouse_bundle.build_parser().parse_args(
        [
            "--warehouse-ref",
            "bq_main",
            "--billing-project-id",
            "proj_cli",
            "--location",
            "EU",
            "--service-account-json",
            '{"type":"service_account","project_id":"proj_cli","client_email":"cli@proj.iam.gserviceaccount.com","private_key":"-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n"}',
            "--allowed-dataset-ref",
            "proj_cli.analytics",
            "--allowed-table-ref",
            "proj_cli.analytics.events",
            "--require-partition-filter-for-table-ref",
            "proj_cli.analytics.events",
        ]
    )

    bundle = build_bigquery_warehouse_bundle._build_bundle(
        args,
        sourced={
            "billing_project_id": "proj_item",
            "location": "US",
            "allowed_dataset_refs": ["proj_item.analytics"],
            "allowed_table_refs": ["proj_item.analytics.orders"],
            "require_partition_filter_for_table_refs": ["proj_item.analytics.orders"],
            "service_account_json": {
                "type": "service_account",
                "project_id": "proj_item",
                "client_email": "item@proj.iam.gserviceaccount.com",
                "private_key": "-----BEGIN PRIVATE KEY-----\nxyz\n-----END PRIVATE KEY-----\n",
            },
        },
    )

    assert bundle["billing_project_id"] == "proj_cli"
    assert bundle["location"] == "EU"
    assert bundle["allowed_dataset_refs"] == ["proj_cli.analytics"]
    assert bundle["allowed_table_refs"] == ["proj_cli.analytics.events"]
    assert bundle["require_partition_filter_for_table_refs"] == ["proj_cli.analytics.events"]
    assert bundle["service_account_json"]["client_email"] == "cli@proj.iam.gserviceaccount.com"


def test_build_bundle_requires_dataset_and_table_scope() -> None:
    args = build_bigquery_warehouse_bundle.build_parser().parse_args(
        [
            "--warehouse-ref",
            "bq_main",
            "--billing-project-id",
            "proj",
            "--location",
            "US",
            "--service-account-json",
            '{"type":"service_account","project_id":"proj","client_email":"svc@proj.iam.gserviceaccount.com","private_key":"-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n"}',
        ]
    )

    with pytest.raises(ValueError, match="At least one --allowed-dataset-ref is required"):
        build_bigquery_warehouse_bundle._build_bundle(args, sourced={})
