"""Focused tests for S3 client construction."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from services.s3_read_executor import get_s3_client
from services.storage_connection_registry import AwsS3StorageBundle


def _bundle(**overrides: object) -> AwsS3StorageBundle:
    payload: dict[str, object] = {
        "storage_ref": "st_docs",
        "provider": "aws-s3",
        "aws_access_key_id": "AKIA_TEST",
        "aws_secret_access_key": "secret-test",
        "region": "us-west-2",
        "allowed_buckets": ("docs-bucket",),
        "allowed_prefixes": {"docs-bucket": ("reports/",)},
        "aws_session_token": None,
        "endpoint_url": None,
    }
    payload.update(overrides)
    return AwsS3StorageBundle(**payload)


def test_get_s3_client_uses_default_aws_endpoint(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def _client(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=_client))

    result = get_s3_client(_bundle())

    assert result == {"ok": True}
    assert calls == [
        {
            "service_name": "s3",
            "region_name": "us-west-2",
            "aws_access_key_id": "AKIA_TEST",
            "aws_secret_access_key": "secret-test",
        }
    ]


def test_get_s3_client_passes_session_token_and_endpoint_override(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def _client(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=_client))

    result = get_s3_client(
        _bundle(
            aws_session_token="session-test",
            endpoint_url="https://example-bounded-s3.test",
        )
    )

    assert result == {"ok": True}
    assert calls == [
        {
            "service_name": "s3",
            "region_name": "us-west-2",
            "aws_access_key_id": "AKIA_TEST",
            "aws_secret_access_key": "secret-test",
            "aws_session_token": "session-test",
            "endpoint_url": "https://example-bounded-s3.test",
        }
    ]
