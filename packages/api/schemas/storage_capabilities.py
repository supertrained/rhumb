"""Object-storage capability request/response schemas for AUD-18 AWS S3 Wave 1."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

OBJECT_STORAGE_DEFAULT_MAX_KEYS = 50
OBJECT_STORAGE_MAX_KEYS = 100
OBJECT_STORAGE_DEFAULT_MAX_BYTES = 262144
OBJECT_STORAGE_MAX_BYTES = 1048576
OBJECT_STORAGE_REASON_MAX_CHARS = 300

_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")

CredentialMode = Literal["byok"]
ProviderUsed = Literal["aws-s3"]
DecodeMode = Literal["auto", "text", "base64"]


def _validate_bucket(value: str) -> str:
    normalized = value.strip()
    if not _BUCKET_RE.fullmatch(normalized):
        raise ValueError("bucket must be a valid S3 bucket name")
    return normalized


def _validate_keyish(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if normalized.startswith("/"):
        raise ValueError(f"{field_name} must not start with '/'")
    return normalized


class S3ObjectRef(BaseModel):
    bucket: str
    key: str

    @field_validator("bucket")
    @classmethod
    def _validate_bucket_field(cls, value: str) -> str:
        return _validate_bucket(value)

    @field_validator("key")
    @classmethod
    def _validate_key_field(cls, value: str) -> str:
        return _validate_keyish(value, "key")


class S3ObjectSummary(BaseModel):
    key: str
    size: int = Field(..., ge=0)
    etag: str | None = None
    last_modified: str | None = None
    storage_class: str | None = None


class S3ListBounds(BaseModel):
    max_keys_applied: int = Field(..., ge=1, le=OBJECT_STORAGE_MAX_KEYS)


class S3GetBounds(BaseModel):
    max_bytes_applied: int = Field(..., ge=1, le=OBJECT_STORAGE_MAX_BYTES)


class S3ObjectListRequest(BaseModel):
    storage_ref: str = Field(..., min_length=1)
    bucket: str
    prefix: str | None = None
    continuation_token: str | None = None
    max_keys: int = Field(OBJECT_STORAGE_DEFAULT_MAX_KEYS, ge=1, le=OBJECT_STORAGE_MAX_KEYS)
    reason: str | None = Field(default=None, max_length=OBJECT_STORAGE_REASON_MAX_CHARS)

    @field_validator("bucket")
    @classmethod
    def _validate_bucket_field(cls, value: str) -> str:
        return _validate_bucket(value)

    @field_validator("prefix")
    @classmethod
    def _validate_prefix(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_keyish(value, "prefix")


class S3ObjectListResponse(BaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["object.list"]
    receipt_id: str
    execution_id: str
    storage_ref: str
    bucket: str
    prefix: str | None = None
    bounded_by: S3ListBounds
    objects: list[S3ObjectSummary] = Field(default_factory=list)
    object_count_returned: int = Field(..., ge=0)
    is_truncated: bool = False
    next_continuation_token: str | None = None
    duration_ms: int = Field(..., ge=0)


class S3ObjectHeadRequest(S3ObjectRef):
    storage_ref: str = Field(..., min_length=1)


class S3ObjectHeadResponse(BaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["object.head"]
    receipt_id: str
    execution_id: str
    storage_ref: str
    bucket: str
    key: str
    size: int = Field(..., ge=0)
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    metadata_keys: list[str] = Field(default_factory=list)
    duration_ms: int = Field(..., ge=0)


class S3ObjectGetRequest(S3ObjectRef):
    storage_ref: str = Field(..., min_length=1)
    range_start: int | None = Field(default=None, ge=0)
    range_end: int | None = Field(default=None, ge=0)
    max_bytes: int = Field(OBJECT_STORAGE_DEFAULT_MAX_BYTES, ge=1, le=OBJECT_STORAGE_MAX_BYTES)
    decode_as: DecodeMode = "auto"

    @model_validator(mode="after")
    def _validate_range(self) -> "S3ObjectGetRequest":
        if self.range_end is not None and self.range_start is None:
            raise ValueError("range_start is required when range_end is provided")
        if self.range_start is not None and self.range_end is not None and self.range_end < self.range_start:
            raise ValueError("range_end must be greater than or equal to range_start")
        if self.range_start is not None and self.range_end is not None:
            requested_bytes = self.range_end - self.range_start + 1
            if requested_bytes > self.max_bytes:
                raise ValueError("requested range exceeds max_bytes")
        return self


class S3ObjectGetResponse(BaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["object.get"]
    receipt_id: str
    execution_id: str
    storage_ref: str
    bucket: str
    key: str
    bounded_by: S3GetBounds
    content_type: str | None = None
    bytes_returned: int = Field(..., ge=0)
    truncated: bool = False
    body_text: str | None = None
    body_base64: str | None = None
    duration_ms: int = Field(..., ge=0)
