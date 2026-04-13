"""Storage capability request/response schemas for the AWS S3 read-first wedge."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

STORAGE_LIST_DEFAULT_KEYS = 50
STORAGE_LIST_MAX_KEYS = 100
STORAGE_GET_DEFAULT_MAX_BYTES = 262144
STORAGE_GET_MAX_BYTES = 1048576
STORAGE_REASON_MAX_CHARS = 300

_STORAGE_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")

CredentialMode = Literal["byok"]
ProviderUsed = Literal["aws-s3"]
DecodeAs = Literal["auto", "text", "base64"]


def _validate_storage_ref(value: str) -> str:
    if not _STORAGE_REF_RE.fullmatch(value):
        raise ValueError("storage_ref must be lowercase alphanumeric with underscores, 1-64 chars")
    return value


def _validate_bucket(value: str) -> str:
    if not _BUCKET_RE.fullmatch(value):
        raise ValueError("bucket must look like a valid S3 bucket name")
    return value


def _validate_object_path(value: str, *, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} is required")
    if value.startswith("/"):
        raise ValueError(f"{field_name} must not start with '/'")
    if len(value) > 1024:
        raise ValueError(f"{field_name} is too long")
    return value


class StorageObjectSummary(BaseModel):
    key: str
    size: int = Field(..., ge=0)
    etag: str | None = None
    last_modified: str | None = None
    storage_class: str | None = None


class ObjectListRequest(BaseModel):
    storage_ref: str = Field(..., min_length=1)
    bucket: str = Field(..., min_length=3)
    prefix: str | None = None
    continuation_token: str | None = None
    max_keys: int = Field(STORAGE_LIST_DEFAULT_KEYS, ge=1, le=STORAGE_LIST_MAX_KEYS)
    reason: str | None = Field(default=None, max_length=STORAGE_REASON_MAX_CHARS)

    @field_validator("storage_ref")
    @classmethod
    def _validate_storage_ref_field(cls, value: str) -> str:
        return _validate_storage_ref(value)

    @field_validator("bucket")
    @classmethod
    def _validate_bucket_field(cls, value: str) -> str:
        return _validate_bucket(value)

    @field_validator("prefix")
    @classmethod
    def _validate_prefix(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_object_path(value, field_name="prefix")


class ObjectListResponse(BaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["object.list"]
    receipt_id: str
    execution_id: str
    storage_ref: str
    bucket: str
    prefix: str | None = None
    objects: list[StorageObjectSummary] = Field(default_factory=list)
    object_count_returned: int = Field(..., ge=0)
    is_truncated: bool = False
    next_continuation_token: str | None = None


class ObjectHeadRequest(BaseModel):
    storage_ref: str = Field(..., min_length=1)
    bucket: str = Field(..., min_length=3)
    key: str = Field(..., min_length=1)
    reason: str | None = Field(default=None, max_length=STORAGE_REASON_MAX_CHARS)

    @field_validator("storage_ref")
    @classmethod
    def _validate_storage_ref_field(cls, value: str) -> str:
        return _validate_storage_ref(value)

    @field_validator("bucket")
    @classmethod
    def _validate_bucket_field(cls, value: str) -> str:
        return _validate_bucket(value)

    @field_validator("key")
    @classmethod
    def _validate_key_field(cls, value: str) -> str:
        return _validate_object_path(value, field_name="key")


class ObjectHeadResponse(BaseModel):
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
    storage_class: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class ObjectGetRequest(BaseModel):
    storage_ref: str = Field(..., min_length=1)
    bucket: str = Field(..., min_length=3)
    key: str = Field(..., min_length=1)
    range_start: int | None = Field(default=None, ge=0)
    range_end: int | None = Field(default=None, ge=0)
    max_bytes: int = Field(STORAGE_GET_DEFAULT_MAX_BYTES, ge=1, le=STORAGE_GET_MAX_BYTES)
    decode_as: DecodeAs = "auto"
    reason: str | None = Field(default=None, max_length=STORAGE_REASON_MAX_CHARS)

    @field_validator("storage_ref")
    @classmethod
    def _validate_storage_ref_field(cls, value: str) -> str:
        return _validate_storage_ref(value)

    @field_validator("bucket")
    @classmethod
    def _validate_bucket_field(cls, value: str) -> str:
        return _validate_bucket(value)

    @field_validator("key")
    @classmethod
    def _validate_key_field(cls, value: str) -> str:
        return _validate_object_path(value, field_name="key")

    @model_validator(mode="after")
    def _validate_range(self) -> "ObjectGetRequest":
        if self.range_end is not None and self.range_start is None:
            raise ValueError("range_start is required when range_end is provided")
        if (
            self.range_start is not None
            and self.range_end is not None
            and self.range_end < self.range_start
        ):
            raise ValueError("range_end must be greater than or equal to range_start")
        if (
            self.range_start is not None
            and self.range_end is not None
            and (self.range_end - self.range_start + 1) > self.max_bytes
        ):
            raise ValueError("requested range exceeds max_bytes")
        return self


class ObjectGetResponse(BaseModel):
    provider_used: ProviderUsed
    credential_mode: CredentialMode
    capability_id: Literal["object.get"]
    receipt_id: str
    execution_id: str
    storage_ref: str
    bucket: str
    key: str
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    bytes_returned: int = Field(..., ge=0)
    truncated: bool = False
    body_text: str | None = None
    body_base64: str | None = None


# Backward-compatible aliases for older AUD-18 S3-specific imports.
S3ObjectListRequest = ObjectListRequest
S3ObjectListResponse = ObjectListResponse
S3ObjectHeadRequest = ObjectHeadRequest
S3ObjectHeadResponse = ObjectHeadResponse
S3ObjectGetRequest = ObjectGetRequest
S3ObjectGetResponse = ObjectGetResponse
