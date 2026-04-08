"""storage_ref registry helpers for AUD-18 AWS S3 read-first execution."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

_STORAGE_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


class StorageRefError(ValueError):
    """Raised when a storage_ref cannot be resolved."""


@dataclass(frozen=True, slots=True)
class AwsS3StorageBundle:
    storage_ref: str
    provider: str
    auth_mode: str
    aws_access_key_id: str | None
    aws_secret_access_key: str | None
    region: str
    allowed_buckets: tuple[str, ...]
    allowed_prefixes: dict[str, tuple[str, ...]]
    aws_session_token: str | None = None
    endpoint_url: str | None = None


def validate_storage_ref(storage_ref: str) -> None:
    if not _STORAGE_REF_RE.fullmatch(storage_ref):
        raise StorageRefError(
            f"Invalid storage_ref '{storage_ref}': must be lowercase alphanumeric with underscores, 1-64 chars"
        )


def resolve_storage_bundle(storage_ref: str) -> AwsS3StorageBundle:
    validate_storage_ref(storage_ref)
    env_key = f"RHUMB_STORAGE_{storage_ref.upper()}"
    raw_bundle = os.environ.get(env_key)
    if not raw_bundle:
        raise StorageRefError(
            f"No storage bundle configured for storage_ref '{storage_ref}' (expected env var {env_key})"
        )

    try:
        payload = json.loads(raw_bundle)
    except Exception as exc:
        raise StorageRefError(
            f"storage_ref '{storage_ref}' is configured via env '{env_key}' but is not valid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise StorageRefError(
            f"storage_ref '{storage_ref}' is configured via env '{env_key}' but is not a JSON object"
        )

    provider = str(payload.get("provider") or "").strip()
    if provider != "aws-s3":
        raise StorageRefError(
            f"storage_ref '{storage_ref}' is configured via env '{env_key}' but provider is not aws-s3"
        )

    auth_mode = str(payload.get("auth_mode") or "access_key").strip()
    if auth_mode not in {"access_key", "anonymous"}:
        raise StorageRefError(
            f"storage_ref '{storage_ref}' is configured via env '{env_key}' but auth_mode must be 'access_key' or 'anonymous'"
        )

    access_key_id: str | None = None
    secret_access_key: str | None = None
    if auth_mode == "access_key":
        access_key_id = _required_string(payload, "aws_access_key_id", storage_ref, env_key)
        secret_access_key = _required_string(payload, "aws_secret_access_key", storage_ref, env_key)
    region = _required_string(payload, "region", storage_ref, env_key)

    allowed_buckets_raw = payload.get("allowed_buckets")
    if not isinstance(allowed_buckets_raw, list) or not allowed_buckets_raw:
        raise StorageRefError(
            f"storage_ref '{storage_ref}' is configured via env '{env_key}' but allowed_buckets is missing or empty"
        )

    allowed_buckets: list[str] = []
    for bucket in allowed_buckets_raw:
        if not isinstance(bucket, str) or not _BUCKET_RE.fullmatch(bucket.strip()):
            raise StorageRefError(
                f"storage_ref '{storage_ref}' has an invalid allowed_buckets entry"
            )
        allowed_buckets.append(bucket.strip())

    allowed_prefixes_raw = payload.get("allowed_prefixes") or {}
    if not isinstance(allowed_prefixes_raw, dict):
        raise StorageRefError(
            f"storage_ref '{storage_ref}' is configured via env '{env_key}' but allowed_prefixes is not an object"
        )

    allowed_bucket_set = set(allowed_buckets)
    allowed_prefixes: dict[str, tuple[str, ...]] = {}
    for bucket, prefixes in allowed_prefixes_raw.items():
        if bucket not in allowed_bucket_set:
            raise StorageRefError(
                f"storage_ref '{storage_ref}' allowed_prefixes references unknown bucket '{bucket}'"
            )
        if not isinstance(prefixes, list):
            raise StorageRefError(
                f"storage_ref '{storage_ref}' allowed_prefixes for bucket '{bucket}' must be a list"
            )
        normalized_prefixes: list[str] = []
        for prefix in prefixes:
            if not isinstance(prefix, str):
                raise StorageRefError(
                    f"storage_ref '{storage_ref}' allowed_prefixes for bucket '{bucket}' must be strings"
                )
            normalized = prefix.strip()
            if not normalized or normalized.startswith("/"):
                raise StorageRefError(
                    f"storage_ref '{storage_ref}' has an invalid allowed prefix for bucket '{bucket}'"
                )
            normalized_prefixes.append(normalized)
        allowed_prefixes[bucket] = tuple(normalized_prefixes)

    session_token = payload.get("aws_session_token")
    endpoint_url = payload.get("endpoint_url")
    if session_token is not None and not isinstance(session_token, str):
        raise StorageRefError(
            f"storage_ref '{storage_ref}' aws_session_token must be a string when provided"
        )
    if endpoint_url is not None and not isinstance(endpoint_url, str):
        raise StorageRefError(
            f"storage_ref '{storage_ref}' endpoint_url must be a string when provided"
        )

    return AwsS3StorageBundle(
        storage_ref=storage_ref,
        provider=provider,
        auth_mode=auth_mode,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region=region,
        allowed_buckets=tuple(allowed_buckets),
        allowed_prefixes=allowed_prefixes,
        aws_session_token=session_token.strip() if isinstance(session_token, str) and session_token.strip() else None,
        endpoint_url=endpoint_url.strip() if isinstance(endpoint_url, str) and endpoint_url.strip() else None,
    )


def bucket_is_allowed(bundle: AwsS3StorageBundle, bucket: str) -> bool:
    return bucket in bundle.allowed_buckets


def prefix_is_allowed(bundle: AwsS3StorageBundle, bucket: str, value: str | None) -> bool:
    bucket_prefixes = bundle.allowed_prefixes.get(bucket)
    if bucket_prefixes is None:
        return True
    if value is None:
        return False
    return any(value.startswith(prefix) for prefix in bucket_prefixes)


def ensure_storage_access(
    bundle: AwsS3StorageBundle,
    *,
    bucket: str,
    prefix_or_key: str | None = None,
) -> None:
    if not bucket_is_allowed(bundle, bucket):
        raise StorageRefError(
            f"storage_ref '{bundle.storage_ref}' is not allowed to access bucket '{bucket}'"
        )
    if not prefix_is_allowed(bundle, bucket, prefix_or_key):
        detail = (prefix_or_key or "").strip() or "(missing prefix)"
        raise StorageRefError(
            f"storage_ref '{bundle.storage_ref}' is not allowed to access '{detail}' in bucket '{bucket}'"
        )


def _required_string(payload: dict[str, object], key: str, storage_ref: str, env_key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise StorageRefError(
            f"storage_ref '{storage_ref}' is configured via env '{env_key}' but field '{key}' is missing"
        )
    return value.strip()
