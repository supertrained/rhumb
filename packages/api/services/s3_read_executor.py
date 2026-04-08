"""AWS S3 read-first executor for AUD-18."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from typing import Any, Callable

from schemas.storage_capabilities import (
    ObjectGetRequest,
    ObjectGetResponse,
    ObjectHeadRequest,
    ObjectHeadResponse,
    ObjectListRequest,
    ObjectListResponse,
    StorageObjectSummary,
)
from services.storage_connection_registry import AwsS3StorageBundle, ensure_storage_access

S3ClientFactory = Callable[[AwsS3StorageBundle], Any]


@dataclass(slots=True)
class S3ExecutorError(RuntimeError):
    code: str
    message: str
    status_code: int = 422

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def get_s3_client(bundle: AwsS3StorageBundle) -> Any:
    try:
        import boto3
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise S3ExecutorError(
            code="s3_provider_unavailable",
            message="boto3 is required for AWS S3 execution",
            status_code=503,
        ) from exc

    kwargs: dict[str, Any] = {
        "service_name": "s3",
        "region_name": bundle.region,
        "aws_access_key_id": bundle.aws_access_key_id,
        "aws_secret_access_key": bundle.aws_secret_access_key,
    }
    if bundle.aws_session_token:
        kwargs["aws_session_token"] = bundle.aws_session_token
    if bundle.endpoint_url:
        kwargs["endpoint_url"] = bundle.endpoint_url
    return boto3.client(**kwargs)


async def list_objects(
    request: ObjectListRequest,
    *,
    bundle: AwsS3StorageBundle,
    client_factory: S3ClientFactory = get_s3_client,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> ObjectListResponse:
    ensure_storage_access(bundle, bucket=request.bucket, prefix_or_key=request.prefix)
    client = client_factory(bundle)

    params: dict[str, Any] = {
        "Bucket": request.bucket,
        "MaxKeys": request.max_keys,
    }
    if request.prefix:
        params["Prefix"] = request.prefix
    if request.continuation_token:
        params["ContinuationToken"] = request.continuation_token

    try:
        response = await asyncio.to_thread(lambda: client.list_objects_v2(**params))
    except Exception as exc:  # pragma: no cover - mapped in dedicated tests
        raise _map_s3_exception(exc) from exc

    objects = [
        StorageObjectSummary(
            key=item.get("Key", ""),
            size=int(item.get("Size") or 0),
            etag=item.get("ETag"),
            last_modified=_to_iso(item.get("LastModified")),
            storage_class=item.get("StorageClass"),
        )
        for item in response.get("Contents") or []
    ]

    return ObjectListResponse(
        provider_used="aws-s3",
        credential_mode="byok",
        capability_id="object.list",
        receipt_id=receipt_id,
        execution_id=execution_id,
        storage_ref=bundle.storage_ref,
        bucket=request.bucket,
        prefix=request.prefix,
        objects=objects,
        object_count_returned=len(objects),
        is_truncated=bool(response.get("IsTruncated")),
        next_continuation_token=response.get("NextContinuationToken"),
    )


async def head_object(
    request: ObjectHeadRequest,
    *,
    bundle: AwsS3StorageBundle,
    client_factory: S3ClientFactory = get_s3_client,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> ObjectHeadResponse:
    ensure_storage_access(bundle, bucket=request.bucket, prefix_or_key=request.key)
    client = client_factory(bundle)

    try:
        response = await asyncio.to_thread(
            lambda: client.head_object(Bucket=request.bucket, Key=request.key)
        )
    except Exception as exc:  # pragma: no cover
        raise _map_s3_exception(exc) from exc

    return ObjectHeadResponse(
        provider_used="aws-s3",
        credential_mode="byok",
        capability_id="object.head",
        receipt_id=receipt_id,
        execution_id=execution_id,
        storage_ref=bundle.storage_ref,
        bucket=request.bucket,
        key=request.key,
        size=int(response.get("ContentLength") or 0),
        content_type=response.get("ContentType"),
        etag=response.get("ETag"),
        last_modified=_to_iso(response.get("LastModified")),
        storage_class=response.get("StorageClass"),
        metadata={str(key): str(value) for key, value in (response.get("Metadata") or {}).items()},
    )


async def get_object(
    request: ObjectGetRequest,
    *,
    bundle: AwsS3StorageBundle,
    client_factory: S3ClientFactory = get_s3_client,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> ObjectGetResponse:
    ensure_storage_access(bundle, bucket=request.bucket, prefix_or_key=request.key)
    client = client_factory(bundle)

    try:
        head = await asyncio.to_thread(
            lambda: client.head_object(Bucket=request.bucket, Key=request.key)
        )
    except Exception as exc:  # pragma: no cover
        raise _map_s3_exception(exc) from exc

    content_length = int(head.get("ContentLength") or 0)
    range_header = _build_range_header(
        content_length=content_length,
        range_start=request.range_start,
        range_end=request.range_end,
        max_bytes=request.max_bytes,
    )
    if range_header is None and content_length > request.max_bytes:
        raise S3ExecutorError(
            code="s3_object_too_large",
            message=(
                f"Object size {content_length} bytes exceeds max_bytes {request.max_bytes}. "
                "Use a bounded byte range."
            ),
            status_code=422,
        )

    params: dict[str, Any] = {"Bucket": request.bucket, "Key": request.key}
    if range_header:
        params["Range"] = range_header

    try:
        response = await asyncio.to_thread(lambda: client.get_object(**params))
        body = await asyncio.to_thread(lambda: response["Body"].read())
    except Exception as exc:  # pragma: no cover
        raise _map_s3_exception(exc) from exc

    body_text: str | None = None
    body_base64: str | None = None
    content_type = response.get("ContentType") or head.get("ContentType")

    if request.decode_as == "base64":
        body_base64 = base64.b64encode(body).decode("ascii")
    elif request.decode_as == "text" or _should_decode_text(content_type, body):
        body_text = body.decode("utf-8", errors="replace")
    else:
        body_base64 = base64.b64encode(body).decode("ascii")

    return ObjectGetResponse(
        provider_used="aws-s3",
        credential_mode="byok",
        capability_id="object.get",
        receipt_id=receipt_id,
        execution_id=execution_id,
        storage_ref=bundle.storage_ref,
        bucket=request.bucket,
        key=request.key,
        content_type=content_type,
        etag=response.get("ETag") or head.get("ETag"),
        last_modified=_to_iso(response.get("LastModified") or head.get("LastModified")),
        bytes_returned=len(body),
        truncated=range_header is not None or len(body) < content_length,
        body_text=body_text,
        body_base64=body_base64,
    )


def _build_range_header(
    *,
    content_length: int,
    range_start: int | None,
    range_end: int | None,
    max_bytes: int,
) -> str | None:
    if range_start is None:
        return None

    end = range_end if range_end is not None else min(content_length - 1, range_start + max_bytes - 1)
    if end < range_start:
        raise S3ExecutorError(
            code="s3_range_invalid",
            message="range_end must be greater than or equal to range_start",
            status_code=422,
        )
    if end - range_start + 1 > max_bytes:
        raise S3ExecutorError(
            code="s3_range_too_large",
            message=f"Requested range exceeds max_bytes {max_bytes}",
            status_code=422,
        )
    return f"bytes={range_start}-{end}"


def _should_decode_text(content_type: str | None, body: bytes) -> bool:
    if content_type:
        lowered = content_type.lower()
        if lowered.startswith("text/") or lowered in {
            "application/json",
            "application/xml",
            "application/javascript",
            "application/x-ndjson",
        }:
            return True
    try:
        body.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _map_s3_exception(exc: Exception) -> S3ExecutorError:
    response = getattr(exc, "response", None) or {}
    error = response.get("Error") or {}
    error_code = str(error.get("Code") or "")
    http_status = int((response.get("ResponseMetadata") or {}).get("HTTPStatusCode") or 422)

    if error_code in {"NoSuchBucket"} or http_status == 404:
        return S3ExecutorError("s3_not_found", "Requested S3 bucket or object was not found", 404)
    if error_code in {"NoSuchKey", "NotFound"}:
        return S3ExecutorError("s3_not_found", "Requested S3 bucket or object was not found", 404)
    if error_code in {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"} or http_status == 403:
        return S3ExecutorError("s3_access_denied", "Access denied by AWS S3", 403)
    return S3ExecutorError(
        "s3_provider_unavailable",
        str(exc) or "AWS S3 request failed",
        503 if http_status >= 500 else http_status,
    )
