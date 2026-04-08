"""Tests for the storage_ref registry helpers."""

from __future__ import annotations

import pytest

from services.storage_connection_registry import (
    StorageRefError,
    bucket_is_allowed,
    prefix_is_allowed,
    resolve_storage_bundle,
    validate_storage_ref,
)


VALID_BUNDLE = '{"provider":"aws-s3","aws_access_key_id":"AKIA_TEST","aws_secret_access_key":"secret","region":"us-west-2","allowed_buckets":["rhumb-bucket"],"allowed_prefixes":{"rhumb-bucket":["reports/","exports/"]}}'


def test_validate_storage_ref_accepts_simple_value() -> None:
    validate_storage_ref("st_reports")


def test_resolve_storage_bundle_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RHUMB_STORAGE_ST_REPORTS", VALID_BUNDLE)
    bundle = resolve_storage_bundle("st_reports")
    assert bundle.provider == "aws-s3"
    assert bundle.region == "us-west-2"
    assert bundle.allowed_buckets == ("rhumb-bucket",)
    assert bundle.allowed_prefixes["rhumb-bucket"] == ("reports/", "exports/")


def test_resolve_storage_bundle_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RHUMB_STORAGE_ST_REPORTS", raising=False)
    with pytest.raises(StorageRefError, match="No storage bundle configured"):
        resolve_storage_bundle("st_reports")


def test_resolve_storage_bundle_invalid_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RHUMB_STORAGE_ST_REPORTS", "{")
    with pytest.raises(StorageRefError, match="not valid JSON"):
        resolve_storage_bundle("st_reports")


def test_resolve_storage_bundle_rejects_wrong_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_STORAGE_ST_REPORTS",
        '{"provider":"cloudflare-r2","aws_access_key_id":"AKIA_TEST","aws_secret_access_key":"secret","region":"us-west-2","allowed_buckets":["rhumb-bucket"]}',
    )
    with pytest.raises(StorageRefError, match="provider is not aws-s3"):
        resolve_storage_bundle("st_reports")


def test_bucket_and_prefix_allowlist_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RHUMB_STORAGE_ST_REPORTS", VALID_BUNDLE)
    bundle = resolve_storage_bundle("st_reports")
    assert bucket_is_allowed(bundle, "rhumb-bucket") is True
    assert bucket_is_allowed(bundle, "other-bucket") is False
    assert prefix_is_allowed(bundle, "rhumb-bucket", "reports/daily.json") is True
    assert prefix_is_allowed(bundle, "rhumb-bucket", "private/secret.json") is False
