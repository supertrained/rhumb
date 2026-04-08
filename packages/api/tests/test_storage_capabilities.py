"""Tests for AWS S3 read-first request/response schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.storage_capabilities import S3ObjectGetRequest, S3ObjectListRequest


def test_object_list_rejects_slash_prefixed_prefix() -> None:
    with pytest.raises(ValidationError, match="must not start with '/'"):
        S3ObjectListRequest(
            storage_ref="st_reports",
            bucket="rhumb-bucket",
            prefix="/reports/",
        )


def test_object_get_requires_range_start_when_range_end_present() -> None:
    with pytest.raises(ValidationError, match="range_start is required"):
        S3ObjectGetRequest(
            storage_ref="st_reports",
            bucket="rhumb-bucket",
            key="reports/daily.json",
            range_end=10,
        )


def test_object_get_rejects_range_larger_than_max_bytes() -> None:
    with pytest.raises(ValidationError, match="requested range exceeds max_bytes"):
        S3ObjectGetRequest(
            storage_ref="st_reports",
            bucket="rhumb-bucket",
            key="reports/daily.json",
            range_start=0,
            range_end=1024,
            max_bytes=512,
        )
