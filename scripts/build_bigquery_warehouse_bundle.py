#!/usr/bin/env python3
"""Build and validate a RHUMB_WAREHOUSE_<REF> env bundle for AUD-18 BigQuery dogfood.

Inputs can come from explicit CLI flags and, optionally, from a 1Password item
via `sop item get --format json`. CLI flags always win over item-derived values.

Prints either:
- raw JSON bundle
- a compact env-safe JSON value
- a shell export command
- the exact `railway variables --set ...` command

The bundle is validated against the same runtime parser Rhumb uses in-product.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "packages" / "api"
VENV_PYTHON = API_DIR / ".venv" / "bin" / "python"
DEFAULT_VAULT = "OpenClaw Agents"


def _ensure_runtime() -> None:
    if sys.version_info >= (3, 10):
        return
    if not VENV_PYTHON.exists():
        raise SystemExit(
            f"Python 3.10+ required and virtualenv interpreter missing at {VENV_PYTHON}"
        )
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__, *sys.argv[1:]])


_ensure_runtime()

sys.path.insert(0, str(API_DIR))

from services.warehouse_connection_registry import resolve_warehouse_bundle  # noqa: E402


def _normalize_key(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _parse_json_object(value: object, *, label: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        raise ValueError(f"{label} is required")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} is required")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must decode to a JSON object")
    return parsed


def _parse_string_list(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return _dedupe([str(item).strip() for item in value if str(item).strip()])
    if isinstance(value, tuple):
        return _dedupe([str(item).strip() for item in value if str(item).strip()])
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return _dedupe([str(item).strip() for item in parsed if str(item).strip()])
    return _dedupe([part.strip() for part in re.split(r"[\s,]+", text) if part.strip()])


def _parse_optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(str(value).strip())


def _first_value(values: dict[str, object], aliases: tuple[str, ...]) -> object | None:
    for alias in aliases:
        key = _normalize_key(alias)
        if key in values:
            return values[key]
    return None


def _first_string(values: dict[str, object], aliases: tuple[str, ...]) -> str | None:
    value = _first_value(values, aliases)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _field_value_map(item: dict[str, Any]) -> dict[str, object]:
    mapped: dict[str, object] = {}
    for field in item.get("fields") or []:
        if not isinstance(field, dict):
            continue
        value = field.get("value")
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        for key_name in ("id", "label", "name", "purpose"):
            key = _normalize_key(field.get(key_name))
            if key and key not in mapped:
                mapped[key] = value
    return mapped


def _extract_embedded_bundle(item: dict[str, Any], values: dict[str, object]) -> dict[str, Any]:
    candidates: list[object] = []
    notes = item.get("notesPlain")
    if isinstance(notes, str) and notes.strip():
        candidates.append(notes)
    direct = _first_value(
        values,
        (
            "warehouse_bundle_json",
            "warehouse_bundle",
            "bundle_json",
            "bundle",
        ),
    )
    if direct is not None:
        candidates.append(direct)

    for candidate in candidates:
        try:
            parsed = _parse_json_object(candidate, label="warehouse bundle")
        except ValueError:
            continue
        if str(parsed.get("provider") or "").strip().lower() == "bigquery":
            return parsed
    return {}


def _extract_service_account_json(
    item: dict[str, Any],
    values: dict[str, object],
    embedded_bundle: dict[str, Any],
) -> dict[str, Any] | None:
    for candidate in (
        _first_value(
            values,
            (
                "service_account_json",
                "google_service_account_json",
                "service_account_key_json",
                "gcp_service_account_json",
                "credentials_json",
                "keyfile_json",
            ),
        ),
        embedded_bundle.get("service_account_json"),
        item.get("notesPlain"),
    ):
        if candidate is None:
            continue
        try:
            parsed = _parse_json_object(candidate, label="service account JSON")
        except ValueError:
            continue
        if str(parsed.get("type") or "").strip().lower() == "service_account":
            return parsed
    return None


def _extract_authorized_user_json(
    item: dict[str, Any],
    values: dict[str, object],
    embedded_bundle: dict[str, Any],
) -> dict[str, Any] | None:
    for candidate in (
        _first_value(
            values,
            (
                "authorized_user_json",
                "google_authorized_user_json",
                "oauth_authorized_user_json",
                "oauth_credentials_json",
            ),
        ),
        embedded_bundle.get("authorized_user_json"),
        item.get("notesPlain"),
    ):
        if candidate is None:
            continue
        try:
            parsed = _parse_json_object(candidate, label="authorized user JSON")
        except ValueError:
            continue
        if str(parsed.get("type") or "").strip().lower() == "authorized_user":
            return parsed

    client_id = _first_string(values, ("client_id",))
    client_secret = _first_string(values, ("client_secret",))
    refresh_token = _first_string(
        values,
        (
            "refresh_token",
            "oauth_refresh_token",
            "google_refresh_token",
            "credential",
        ),
    )
    if not client_id or not client_secret or not refresh_token:
        return None

    synthesized: dict[str, Any] = {
        "type": "authorized_user",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    token_uri = _first_string(values, ("token_uri",)) or str(embedded_bundle.get("token_uri") or "").strip() or None
    quota_project_id = _first_string(
        values,
        ("quota_project_id", "billing_project_id", "project_id", "gcp_project_id", "bigquery_project_id"),
    ) or str(
        embedded_bundle.get("quota_project_id")
        or embedded_bundle.get("billing_project_id")
        or embedded_bundle.get("project_id")
        or ""
    ).strip() or None
    if token_uri:
        synthesized["token_uri"] = token_uri
    if quota_project_id:
        synthesized["quota_project_id"] = quota_project_id
    return synthesized


def _extract_sop_defaults(item: dict[str, Any]) -> dict[str, Any]:
    values = _field_value_map(item)
    embedded_bundle = _extract_embedded_bundle(item, values)
    explicit_auth_mode = (
        _first_string(values, ("auth_mode", "authentication_mode"))
        or str(embedded_bundle.get("auth_mode") or "").strip()
        or None
    )

    service_account_json = _extract_service_account_json(item, values, embedded_bundle)
    authorized_user_json = _extract_authorized_user_json(item, values, embedded_bundle)

    defaults: dict[str, Any] = {}
    auth_mode = explicit_auth_mode
    if not auth_mode:
        if authorized_user_json and (
            _first_string(
                values,
                (
                    "service_account_email",
                    "impersonated_service_account_email",
                    "target_service_account_email",
                ),
            )
            or str(embedded_bundle.get("service_account_email") or "").strip()
        ):
            auth_mode = "service_account_impersonation"
        elif service_account_json:
            auth_mode = "service_account_json"
    if auth_mode:
        defaults["auth_mode"] = auth_mode
    if service_account_json:
        defaults["service_account_json"] = service_account_json
    if authorized_user_json:
        defaults["authorized_user_json"] = authorized_user_json

    service_account_email = (
        _first_string(
            values,
            (
                "service_account_email",
                "impersonated_service_account_email",
                "target_service_account_email",
            ),
        )
        or str(embedded_bundle.get("service_account_email") or "").strip()
        or None
    )
    if service_account_email:
        defaults["service_account_email"] = service_account_email

    billing_project_id = (
        _first_string(values, ("billing_project_id", "project_id", "gcp_project_id", "bigquery_project_id"))
        or str(embedded_bundle.get("billing_project_id") or embedded_bundle.get("project_id") or "").strip()
        or None
    )
    location = (
        _first_string(values, ("location", "bigquery_location", "region"))
        or str(embedded_bundle.get("location") or "").strip()
        or None
    )
    allowed_dataset_refs = _parse_string_list(
        _first_value(values, ("allowed_dataset_refs", "allowed_dataset_ref", "dataset_refs", "dataset_ref"))
        or embedded_bundle.get("allowed_dataset_refs")
    )
    allowed_table_refs = _parse_string_list(
        _first_value(values, ("allowed_table_refs", "allowed_table_ref", "table_refs", "table_ref"))
        or embedded_bundle.get("allowed_table_refs")
    )
    require_partition_filter_for_table_refs = _parse_string_list(
        _first_value(
            values,
            (
                "require_partition_filter_for_table_refs",
                "require_partition_filter_for_table_ref",
                "partition_filter_table_refs",
            ),
        )
        or embedded_bundle.get("require_partition_filter_for_table_refs")
    )

    if billing_project_id:
        defaults["billing_project_id"] = billing_project_id
    if location:
        defaults["location"] = location
    if allowed_dataset_refs:
        defaults["allowed_dataset_refs"] = allowed_dataset_refs
    if allowed_table_refs:
        defaults["allowed_table_refs"] = allowed_table_refs
    if require_partition_filter_for_table_refs:
        defaults["require_partition_filter_for_table_refs"] = require_partition_filter_for_table_refs

    for field_name in (
        "max_bytes_billed",
        "max_rows_returned",
        "max_result_bytes",
        "statement_timeout_ms",
        "schema_dataset_limit",
        "schema_table_limit",
        "schema_column_limit",
    ):
        value = _parse_optional_int(
            _first_value(values, (field_name,))
            if _first_value(values, (field_name,)) is not None
            else embedded_bundle.get(field_name)
        )
        if value is not None:
            defaults[field_name] = value

    return defaults


def _load_sop_item(item_name: str, *, vault: str) -> dict[str, Any]:
    result = subprocess.run(
        ["sop", "item", "get", item_name, "--vault", vault, "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "sop item get failed").strip()
        raise ValueError(f"Unable to load 1Password item {item_name!r} from vault {vault!r}: {error}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"1Password item {item_name!r} did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"1Password item {item_name!r} returned an unexpected payload")
    return payload


def _service_account_json_from_args(args: argparse.Namespace, sourced: dict[str, Any]) -> dict[str, Any]:
    if args.service_account_json_file:
        try:
            return _parse_json_object(
                Path(args.service_account_json_file).read_text(),
                label="--service-account-json-file",
            )
        except OSError as exc:
            raise ValueError(f"Unable to read --service-account-json-file: {exc}") from exc
    if args.service_account_json:
        return _parse_json_object(args.service_account_json, label="--service-account-json")
    sourced_value = sourced.get("service_account_json")
    if sourced_value is not None:
        return _parse_json_object(sourced_value, label="service account JSON")
    raise ValueError(
        "--service-account-json or --service-account-json-file is required unless it can be inferred from --from-sop-item"
    )


def _authorized_user_json_from_args(args: argparse.Namespace, sourced: dict[str, Any]) -> dict[str, Any]:
    if args.authorized_user_json_file:
        try:
            return _parse_json_object(
                Path(args.authorized_user_json_file).read_text(),
                label="--authorized-user-json-file",
            )
        except OSError as exc:
            raise ValueError(f"Unable to read --authorized-user-json-file: {exc}") from exc
    if args.authorized_user_json:
        return _parse_json_object(args.authorized_user_json, label="--authorized-user-json")
    sourced_value = sourced.get("authorized_user_json")
    if sourced_value is not None:
        return _parse_json_object(sourced_value, label="authorized user JSON")
    raise ValueError(
        "--authorized-user-json or --authorized-user-json-file is required unless it can be inferred from --from-sop-item"
    )


def _service_account_email_from_args(args: argparse.Namespace, sourced: dict[str, Any]) -> str:
    value = str(args.service_account_email or sourced.get("service_account_email") or "").strip()
    if not value:
        raise ValueError(
            "--service-account-email is required for auth_mode service_account_impersonation unless it can be inferred from --from-sop-item"
        )
    return value


def _resolve_auth_mode(args: argparse.Namespace, sourced: dict[str, Any]) -> str:
    explicit = str(args.auth_mode or sourced.get("auth_mode") or "").strip().lower()
    if explicit:
        return explicit
    if (
        args.authorized_user_json
        or args.authorized_user_json_file
        or args.service_account_email
        or sourced.get("authorized_user_json") is not None
        or sourced.get("service_account_email") is not None
    ):
        return "service_account_impersonation"
    return "service_account_json"


def _build_bundle(args: argparse.Namespace, *, sourced: dict[str, Any] | None = None) -> dict[str, Any]:
    sourced = sourced or {}
    auth_mode = _resolve_auth_mode(args, sourced)

    billing_project_id = str(args.billing_project_id or sourced.get("billing_project_id") or "").strip()
    if not billing_project_id:
        raise ValueError(
            "--billing-project-id is required unless it can be inferred from --from-sop-item"
        )

    location = str(args.location or sourced.get("location") or "").strip()
    if not location:
        raise ValueError("--location is required unless it can be inferred from --from-sop-item")

    allowed_dataset_refs = (
        _dedupe([item.strip() for item in args.allowed_dataset_ref if item.strip()])
        if args.allowed_dataset_ref
        else list(sourced.get("allowed_dataset_refs") or [])
    )
    if not allowed_dataset_refs:
        raise ValueError(
            "At least one --allowed-dataset-ref is required unless it can be inferred from --from-sop-item"
        )

    allowed_table_refs = (
        _dedupe([item.strip() for item in args.allowed_table_ref if item.strip()])
        if args.allowed_table_ref
        else list(sourced.get("allowed_table_refs") or [])
    )
    if not allowed_table_refs:
        raise ValueError(
            "At least one --allowed-table-ref is required unless it can be inferred from --from-sop-item"
        )

    require_partition_filter_for_table_refs = (
        _dedupe([item.strip() for item in args.require_partition_filter_for_table_ref if item.strip()])
        if args.require_partition_filter_for_table_ref
        else list(sourced.get("require_partition_filter_for_table_refs") or [])
    )

    bundle: dict[str, Any] = {
        "provider": "bigquery",
        "auth_mode": auth_mode,
        "billing_project_id": billing_project_id,
        "location": location,
        "allowed_dataset_refs": allowed_dataset_refs,
        "allowed_table_refs": allowed_table_refs,
    }
    if auth_mode == "service_account_json":
        bundle["service_account_json"] = _service_account_json_from_args(args, sourced)
    elif auth_mode == "service_account_impersonation":
        bundle["authorized_user_json"] = _authorized_user_json_from_args(args, sourced)
        bundle["service_account_email"] = _service_account_email_from_args(args, sourced)
    else:
        raise ValueError(f"Unsupported auth mode: {auth_mode}")
    if require_partition_filter_for_table_refs:
        bundle["require_partition_filter_for_table_refs"] = require_partition_filter_for_table_refs

    for field_name, arg_value in (
        ("max_bytes_billed", args.max_bytes_billed),
        ("max_rows_returned", args.max_rows_returned),
        ("max_result_bytes", args.max_result_bytes),
        ("statement_timeout_ms", args.statement_timeout_ms),
        ("schema_dataset_limit", args.schema_dataset_limit),
        ("schema_table_limit", args.schema_table_limit),
        ("schema_column_limit", args.schema_column_limit),
    ):
        value = arg_value if arg_value is not None else sourced.get(field_name)
        if value is not None:
            bundle[field_name] = int(value)

    return bundle


def _validate_bundle(ref: str, bundle: dict[str, Any]) -> dict[str, Any]:
    env_key = f"RHUMB_WAREHOUSE_{ref.upper()}"
    original = os.environ.get(env_key)
    os.environ[env_key] = json.dumps(bundle, separators=(",", ":"), sort_keys=True)
    try:
        resolved = resolve_warehouse_bundle(ref)
    finally:
        if original is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = original
    return {
        "warehouse_ref": resolved.warehouse_ref,
        "provider": resolved.provider,
        "auth_mode": resolved.auth_mode,
        "billing_project_id": resolved.billing_project_id,
        "location": resolved.location,
        "allowed_dataset_refs": list(resolved.allowed_dataset_refs),
        "allowed_table_refs": list(resolved.allowed_table_refs),
        "require_partition_filter_for_table_refs": list(resolved.require_partition_filter_for_table_refs),
        "max_bytes_billed": resolved.max_bytes_billed,
        "max_rows_returned": resolved.max_rows_returned,
        "max_result_bytes": resolved.max_result_bytes,
        "statement_timeout_ms": resolved.statement_timeout_ms,
        "schema_dataset_limit": resolved.schema_dataset_limit,
        "schema_table_limit": resolved.schema_table_limit,
        "schema_column_limit": resolved.schema_column_limit,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse-ref", required=True)
    parser.add_argument("--auth-mode", choices=["service_account_json", "service_account_impersonation"])
    parser.add_argument("--billing-project-id")
    parser.add_argument("--location")
    parser.add_argument("--service-account-json")
    parser.add_argument("--service-account-json-file")
    parser.add_argument("--authorized-user-json")
    parser.add_argument("--authorized-user-json-file")
    parser.add_argument("--service-account-email")
    parser.add_argument("--from-sop-item")
    parser.add_argument("--vault", default=DEFAULT_VAULT)
    parser.add_argument("--allowed-dataset-ref", action="append")
    parser.add_argument("--allowed-table-ref", action="append")
    parser.add_argument("--require-partition-filter-for-table-ref", action="append")
    parser.add_argument("--max-bytes-billed", type=int)
    parser.add_argument("--max-rows-returned", type=int)
    parser.add_argument("--max-result-bytes", type=int)
    parser.add_argument("--statement-timeout-ms", type=int)
    parser.add_argument("--schema-dataset-limit", type=int)
    parser.add_argument("--schema-table-limit", type=int)
    parser.add_argument("--schema-column-limit", type=int)
    parser.add_argument("--format", choices=["json", "env-value", "export", "railway"], default="json")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    sourced: dict[str, Any] = {}
    if args.from_sop_item:
        try:
            sourced = _extract_sop_defaults(_load_sop_item(args.from_sop_item, vault=args.vault))
        except ValueError as exc:
            parser.error(str(exc))

    try:
        bundle = _build_bundle(args, sourced=sourced)
        _validate_bundle(args.warehouse_ref, bundle)
    except ValueError as exc:
        parser.error(str(exc))

    env_key = f"RHUMB_WAREHOUSE_{args.warehouse_ref.upper()}"
    raw = json.dumps(bundle, separators=(",", ":"), sort_keys=True)
    if args.format == "json":
        print(json.dumps(bundle, indent=2, sort_keys=True))
    elif args.format == "env-value":
        print(raw)
    elif args.format == "export":
        print(f"export {env_key}={shlex.quote(raw)}")
    else:
        print(f"railway variables --set {env_key}={shlex.quote(raw)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
