#!/usr/bin/env python3
"""Build and validate a RHUMB_STORAGE_<REF> env bundle for AUD-18 S3 dogfood.

Usage:
  python3 scripts/build_s3_storage_bundle.py \
    --storage-ref st_docs \
    --bucket docs-bucket \
    --prefix docs-bucket=reports/ \
    --key-env AWS_ACCESS_KEY_ID \
    --secret-env AWS_SECRET_ACCESS_KEY \
    --region us-west-2 \
    --railway

The script reads credentials from explicit flags first, then standard AWS env vars.
It validates the generated bundle against the product runtime parser before printing:
- JSON only (default)
- exact `railway variables --set ...` command (`--railway`)
- shell export form (`--shell`)

For bounded public AWS proof targets, `--anonymous` builds an allowlisted bundle without
access keys and tells the runtime to use unsigned reads.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "packages" / "api"
API_VENV_PYTHON = REPO_ROOT / "packages" / "api" / ".venv" / "bin" / "python"

if sys.version_info < (3, 10) and API_VENV_PYTHON.exists():
    os.execv(str(API_VENV_PYTHON), [str(API_VENV_PYTHON), __file__, *sys.argv[1:]])

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services.storage_connection_registry import resolve_storage_bundle  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-ref", required=True, help="storage_ref handle, for example st_docs")
    parser.add_argument(
        "--bucket",
        action="append",
        dest="buckets",
        required=True,
        help="Allowlisted bucket. Repeat for multiple buckets.",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help="Allowed prefix in the form bucket=prefix/. Repeat as needed.",
    )
    parser.add_argument("--region", help="AWS region. Falls back to AWS_REGION or AWS_DEFAULT_REGION.")
    parser.add_argument(
        "--anonymous",
        action="store_true",
        help="Use unsigned anonymous reads for a bounded public AWS bucket",
    )
    parser.add_argument("--access-key-id", help="AWS access key id. Falls back to env vars.")
    parser.add_argument("--secret-access-key", help="AWS secret access key. Falls back to env vars.")
    parser.add_argument("--session-token", help="Optional AWS session token. Falls back to AWS_SESSION_TOKEN.")
    parser.add_argument("--endpoint-url", help="Optional endpoint URL for explicit non-default routing.")
    parser.add_argument("--key-env", default="AWS_ACCESS_KEY_ID", help="Env var name for access key id fallback")
    parser.add_argument(
        "--secret-env",
        default="AWS_SECRET_ACCESS_KEY",
        help="Env var name for secret access key fallback",
    )
    parser.add_argument(
        "--session-token-env",
        default="AWS_SESSION_TOKEN",
        help="Env var name for session token fallback",
    )
    parser.add_argument("--railway", action="store_true", help="Print exact railway variables --set command")
    parser.add_argument("--shell", action="store_true", help="Print shell export form")
    return parser.parse_args()


def _env_value(name: str | None) -> str | None:
    if not name:
        return None
    value = os.environ.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _required(value: str | None, label: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise SystemExit(f"Missing required {label}")


def _parse_prefix_specs(specs: list[str], buckets: list[str]) -> dict[str, list[str]]:
    allowed_bucket_set = set(buckets)
    parsed: dict[str, list[str]] = {}
    for spec in specs:
        if "=" not in spec:
            raise SystemExit(f"Invalid --prefix {spec!r}; expected bucket=prefix/")
        bucket, prefix = spec.split("=", 1)
        bucket = bucket.strip()
        prefix = prefix.strip()
        if bucket not in allowed_bucket_set:
            raise SystemExit(f"Prefix bucket {bucket!r} is not present in --bucket")
        if not prefix:
            raise SystemExit(f"Invalid empty prefix for bucket {bucket!r}")
        parsed.setdefault(bucket, []).append(prefix)
    return parsed


def _build_payload(args: argparse.Namespace) -> dict[str, object]:
    region = args.region or _env_value("AWS_REGION") or _env_value("AWS_DEFAULT_REGION")
    access_key_id = args.access_key_id or _env_value(args.key_env)
    secret_access_key = args.secret_access_key or _env_value(args.secret_env)
    session_token = args.session_token or _env_value(args.session_token_env)

    payload: dict[str, object] = {
        "provider": "aws-s3",
        "region": _required(region, "AWS region"),
        "allowed_buckets": args.buckets,
    }
    if args.anonymous:
        payload["auth_mode"] = "anonymous"
    else:
        payload["aws_access_key_id"] = _required(access_key_id, "AWS access key id")
        payload["aws_secret_access_key"] = _required(secret_access_key, "AWS secret access key")
    allowed_prefixes = _parse_prefix_specs(args.prefix, args.buckets)
    if allowed_prefixes:
        payload["allowed_prefixes"] = allowed_prefixes
    if session_token and not args.anonymous:
        payload["aws_session_token"] = session_token
    if args.endpoint_url:
        payload["endpoint_url"] = args.endpoint_url.strip()
    return payload


def _validate_bundle(storage_ref: str, payload: dict[str, object]) -> None:
    env_key = f"RHUMB_STORAGE_{storage_ref.upper()}"
    previous = os.environ.get(env_key)
    try:
        os.environ[env_key] = json.dumps(payload)
        resolve_storage_bundle(storage_ref)
    finally:
        if previous is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = previous


def main() -> int:
    args = parse_args()
    payload = _build_payload(args)
    _validate_bundle(args.storage_ref, payload)

    env_key = f"RHUMB_STORAGE_{args.storage_ref.upper()}"
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    if args.railway:
        print(f"railway variables --set {shlex.quote(f'{env_key}={encoded}')}")
        return 0
    if args.shell:
        print(f"export {env_key}={shlex.quote(encoded)}")
        return 0

    print(json.dumps({"env_key": env_key, "bundle": payload}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
