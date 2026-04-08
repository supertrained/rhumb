"""Tests for the storage_ref registry."""

from __future__ import annotations

import json

import pytest

from services.storage_connection_registry import (
    StorageRefError,
    ensure_storage_access,
    resolve_storage_bundle,
)


def test_resolve_storage_bundle_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_STORAGE_ST_DOCS",
        json.dumps(
            {
                "provider": "aws-s3",
                "region": "us-west-1",
                "aws_access_key_id": "AKIA...",
                "aws_secret_access_key": "secret",
                "allowed_buckets": ["docs-bucket"],
                "allowed_prefixes": {"docs-bucket": ["reports/"]},
            }
        ),
    )

    bundle = resolve_storage_bundle("st_docs")
    assert bundle.storage_ref == "st_docs"
    assert bundle.provider == "aws-s3"
    assert bundle.auth_mode == "access_key"
    assert bundle.allowed_buckets == ("docs-bucket",)
    assert bundle.allowed_prefixes["docs-bucket"] == ("reports/",)


def test_resolve_storage_bundle_allows_anonymous_public_aws_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_STORAGE_ST_DOCS",
        json.dumps(
            {
                "provider": "aws-s3",
                "auth_mode": "anonymous",
                "region": "us-east-1",
                "allowed_buckets": ["public-bucket"],
                "allowed_prefixes": {"public-bucket": ["docs/"]},
            }
        ),
    )

    bundle = resolve_storage_bundle("st_docs")
    assert bundle.auth_mode == "anonymous"
    assert bundle.aws_access_key_id is None
    assert bundle.aws_secret_access_key is None
    assert bundle.allowed_buckets == ("public-bucket",)


def test_resolve_storage_bundle_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RHUMB_STORAGE_ST_DOCS", raising=False)
    with pytest.raises(StorageRefError, match="No storage bundle configured"):
        resolve_storage_bundle("st_docs")


def test_resolve_storage_bundle_requires_keys_for_access_key_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_STORAGE_ST_DOCS",
        json.dumps(
            {
                "provider": "aws-s3",
                "region": "us-west-1",
                "allowed_buckets": ["docs-bucket"],
            }
        ),
    )

    with pytest.raises(StorageRefError, match="field 'aws_access_key_id' is missing"):
        resolve_storage_bundle("st_docs")


def test_ensure_storage_access_rejects_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_STORAGE_ST_DOCS",
        json.dumps(
            {
                "provider": "aws-s3",
                "region": "us-west-1",
                "aws_access_key_id": "AKIA...",
                "aws_secret_access_key": "secret",
                "allowed_buckets": ["docs-bucket"],
            }
        ),
    )
    bundle = resolve_storage_bundle("st_docs")

    with pytest.raises(StorageRefError, match="not allowed to access bucket"):
        ensure_storage_access(bundle, bucket="private-bucket", prefix_or_key="reports/daily.json")


def test_ensure_storage_access_rejects_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_STORAGE_ST_DOCS",
        json.dumps(
            {
                "provider": "aws-s3",
                "region": "us-west-1",
                "aws_access_key_id": "AKIA...",
                "aws_secret_access_key": "secret",
                "allowed_buckets": ["docs-bucket"],
                "allowed_prefixes": {"docs-bucket": ["reports/"]},
            }
        ),
    )
    bundle = resolve_storage_bundle("st_docs")

    with pytest.raises(StorageRefError, match="not allowed to access"):
        ensure_storage_access(bundle, bucket="docs-bucket", prefix_or_key="secrets/raw.csv")
