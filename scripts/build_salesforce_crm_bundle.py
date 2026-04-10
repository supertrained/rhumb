#!/usr/bin/env python3
"""Build and validate a RHUMB_CRM_<REF> env bundle for AUD-18 Salesforce CRM dogfood.

Inputs can come from explicit CLI flags and, optionally, from a 1Password item
via `sop item get --format json`. CLI flags always win over item-derived values.

Prints either:
- raw JSON bundle
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
from typing import Any, Callable


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

from services.crm_connection_registry import resolve_crm_bundle  # noqa: E402


def _normalize_key(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _normalize_object_type(value: object) -> str:
    return str(value or "").strip()


def _normalize_property_name(value: object) -> str:
    return str(value or "").strip()


def _normalize_record_id(value: object) -> str:
    return str(value or "").strip()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _parse_string_list(value: object, *, normalize: Callable[[object], str]) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return _dedupe([normalize(item) for item in value if normalize(item)])
    if isinstance(value, tuple):
        return _dedupe([normalize(item) for item in value if normalize(item)])
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return _dedupe([normalize(item) for item in parsed if normalize(item)])
        parts = re.split(r"[\s,]+", text)
        return _dedupe([normalize(part) for part in parts if normalize(part)])
    normalized = normalize(value)
    return [normalized] if normalized else []


def _parse_scoped_cli_values(
    values: list[str] | None,
    *,
    value_normalizer: Callable[[object], str],
) -> dict[str, list[str]]:
    scoped: dict[str, list[str]] = {}
    for raw in values or []:
        text = str(raw or "").strip()
        if not text:
            continue
        object_type, sep, raw_value = text.partition(":")
        if not sep:
            raise ValueError(f"Scoped value must look like object_type:value, got {raw!r}")
        normalized_object = _normalize_object_type(object_type)
        normalized_value = value_normalizer(raw_value)
        if not normalized_object or not normalized_value:
            raise ValueError(f"Scoped value must include both object_type and value, got {raw!r}")
        scoped.setdefault(normalized_object, [])
        if normalized_value not in scoped[normalized_object]:
            scoped[normalized_object].append(normalized_value)
    return scoped


def _parse_object_map_value(
    value: object,
    *,
    value_normalizer: Callable[[object], str],
) -> dict[str, list[str]]:
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Expected a JSON object for scoped CRM map fields") from exc
    if not isinstance(value, dict):
        raise ValueError("Scoped CRM map fields must be JSON objects")

    scoped: dict[str, list[str]] = {}
    for raw_object_type, raw_values in value.items():
        object_type = _normalize_object_type(raw_object_type)
        if not object_type:
            continue
        scoped[object_type] = _parse_string_list(raw_values, normalize=value_normalizer)
    return {key: values for key, values in scoped.items() if values}


def _merge_scoped_maps(*maps: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for current in maps:
        for object_type, values in current.items():
            bucket = merged.setdefault(object_type, [])
            for value in values:
                if value not in bucket:
                    bucket.append(value)
    return merged


def _filter_scoped_map(
    scoped: dict[str, list[str]],
    *,
    allowed_object_types: list[str],
) -> dict[str, list[str]]:
    allowed = set(allowed_object_types)
    return {
        object_type: values
        for object_type, values in scoped.items()
        if object_type in allowed and values
    }


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


def _raw_field_keys(field: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for key_name in ("id", "label", "name", "purpose"):
        value = field.get(key_name)
        if not isinstance(value, str):
            continue
        text = value.strip()
        if text and text not in keys:
            keys.append(text)
    return keys


def _collect_prefixed_scoped_fields(
    item: dict[str, Any],
    *,
    prefixes: tuple[str, ...],
    value_normalizer: Callable[[object], str],
) -> dict[str, list[str]]:
    scoped: dict[str, list[str]] = {}
    for field in item.get("fields") or []:
        if not isinstance(field, dict):
            continue
        raw_value = field.get("value")
        if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
            continue
        matched_object_type: str | None = None
        for raw_key in _raw_field_keys(field):
            for prefix in prefixes:
                if raw_key.lower().startswith(prefix.lower()):
                    matched_object_type = _normalize_object_type(raw_key[len(prefix) :].lstrip("_"))
                    break
            if matched_object_type:
                break
        if not matched_object_type or matched_object_type.lower() == "by_object":
            continue
        parsed_values = _parse_string_list(raw_value, normalize=value_normalizer)
        if not parsed_values:
            continue
        bucket = scoped.setdefault(matched_object_type, [])
        for value in parsed_values:
            if value not in bucket:
                bucket.append(value)
    return scoped


def _extract_sop_defaults(item: dict[str, Any]) -> dict[str, Any]:
    values = _field_value_map(item)
    defaults: dict[str, Any] = {}

    client_id = _first_string(values, ("client_id", "consumer_key", "connected_app_client_id"))
    client_secret = _first_string(
        values,
        ("client_secret", "consumer_secret", "connected_app_client_secret", "secret"),
    )
    refresh_token = _first_string(values, ("refresh_token", "token"))
    auth_base_url = _first_string(values, ("auth_base_url", "login_url", "base_url"))
    api_version = _first_string(values, ("api_version", "version"))
    allowed_object_types = _parse_string_list(
        _first_value(values, ("allowed_object_types", "object_types", "object_type")),
        normalize=_normalize_object_type,
    )

    allowed_properties_by_object = _merge_scoped_maps(
        _parse_object_map_value(
            _first_value(values, ("allowed_properties_by_object",)),
            value_normalizer=_normalize_property_name,
        ),
        _collect_prefixed_scoped_fields(
            item,
            prefixes=("allowed_properties_",),
            value_normalizer=_normalize_property_name,
        ),
    )
    default_properties_by_object = _merge_scoped_maps(
        _parse_object_map_value(
            _first_value(values, ("default_properties_by_object",)),
            value_normalizer=_normalize_property_name,
        ),
        _collect_prefixed_scoped_fields(
            item,
            prefixes=("default_properties_",),
            value_normalizer=_normalize_property_name,
        ),
    )
    searchable_properties_by_object = _merge_scoped_maps(
        _parse_object_map_value(
            _first_value(values, ("searchable_properties_by_object",)),
            value_normalizer=_normalize_property_name,
        ),
        _collect_prefixed_scoped_fields(
            item,
            prefixes=("searchable_properties_",),
            value_normalizer=_normalize_property_name,
        ),
    )
    sortable_properties_by_object = _merge_scoped_maps(
        _parse_object_map_value(
            _first_value(values, ("sortable_properties_by_object",)),
            value_normalizer=_normalize_property_name,
        ),
        _collect_prefixed_scoped_fields(
            item,
            prefixes=("sortable_properties_",),
            value_normalizer=_normalize_property_name,
        ),
    )
    allowed_record_ids_by_object = _merge_scoped_maps(
        _parse_object_map_value(
            _first_value(values, ("allowed_record_ids_by_object",)),
            value_normalizer=_normalize_record_id,
        ),
        _collect_prefixed_scoped_fields(
            item,
            prefixes=("allowed_record_ids_",),
            value_normalizer=_normalize_record_id,
        ),
    )

    if client_id:
        defaults["client_id"] = client_id
    if client_secret:
        defaults["client_secret"] = client_secret
    if refresh_token:
        defaults["refresh_token"] = refresh_token
    if auth_base_url:
        defaults["auth_base_url"] = auth_base_url
    if api_version:
        defaults["api_version"] = api_version
    if allowed_object_types:
        defaults["allowed_object_types"] = allowed_object_types
    if allowed_properties_by_object:
        defaults["allowed_properties_by_object"] = allowed_properties_by_object
    if default_properties_by_object:
        defaults["default_properties_by_object"] = default_properties_by_object
    if searchable_properties_by_object:
        defaults["searchable_properties_by_object"] = searchable_properties_by_object
    if sortable_properties_by_object:
        defaults["sortable_properties_by_object"] = sortable_properties_by_object
    if allowed_record_ids_by_object:
        defaults["allowed_record_ids_by_object"] = allowed_record_ids_by_object
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


def _build_bundle(args: argparse.Namespace, *, sourced: dict[str, Any] | None = None) -> dict[str, Any]:
    sourced = sourced or {}

    client_id = str(args.client_id or sourced.get("client_id") or "").strip()
    client_secret = str(args.client_secret or sourced.get("client_secret") or "").strip()
    refresh_token = str(args.refresh_token or sourced.get("refresh_token") or "").strip()
    auth_base_url = str(args.auth_base_url or sourced.get("auth_base_url") or "").strip() or None
    api_version = str(args.api_version or sourced.get("api_version") or "").strip() or None

    if not client_id:
        raise ValueError("--client-id is required unless it can be inferred from --from-sop-item")
    if not client_secret:
        raise ValueError(
            "--client-secret is required unless it can be inferred from --from-sop-item"
        )
    if not refresh_token:
        raise ValueError(
            "--refresh-token is required unless it can be inferred from --from-sop-item"
        )

    sourced_allowed_object_types = list(sourced.get("allowed_object_types") or [])
    cli_allowed_object_types = _parse_string_list(args.allow_object, normalize=_normalize_object_type)

    sourced_allowed_properties = dict(sourced.get("allowed_properties_by_object") or {})
    sourced_default_properties = dict(sourced.get("default_properties_by_object") or {})
    sourced_searchable_properties = dict(sourced.get("searchable_properties_by_object") or {})
    sourced_sortable_properties = dict(sourced.get("sortable_properties_by_object") or {})
    sourced_allowed_record_ids = dict(sourced.get("allowed_record_ids_by_object") or {})

    cli_allowed_properties = _parse_scoped_cli_values(
        args.allow_property,
        value_normalizer=_normalize_property_name,
    )
    cli_default_properties = _parse_scoped_cli_values(
        args.default_property,
        value_normalizer=_normalize_property_name,
    )
    cli_searchable_properties = _parse_scoped_cli_values(
        args.searchable_property,
        value_normalizer=_normalize_property_name,
    )
    cli_sortable_properties = _parse_scoped_cli_values(
        args.sortable_property,
        value_normalizer=_normalize_property_name,
    )
    cli_allowed_record_ids = _parse_scoped_cli_values(
        args.allowed_record_id,
        value_normalizer=_normalize_record_id,
    )

    sourced_map_keys = set().union(
        sourced_allowed_properties,
        sourced_default_properties,
        sourced_searchable_properties,
        sourced_sortable_properties,
        sourced_allowed_record_ids,
    )
    cli_map_keys = set().union(
        cli_allowed_properties,
        cli_default_properties,
        cli_searchable_properties,
        cli_sortable_properties,
        cli_allowed_record_ids,
    )

    if cli_allowed_object_types:
        allowed_object_types = _dedupe(cli_allowed_object_types + sorted(cli_map_keys))
    else:
        allowed_object_types = _dedupe(sourced_allowed_object_types + sorted(sourced_map_keys | cli_map_keys))

    if not allowed_object_types:
        raise ValueError(
            "At least one --allow-object or scoped property/record flag is required, unless it can be inferred from --from-sop-item"
        )

    allowed_properties_by_object = _filter_scoped_map(
        _merge_scoped_maps(sourced_allowed_properties, cli_allowed_properties),
        allowed_object_types=allowed_object_types,
    )
    default_properties_by_object = _filter_scoped_map(
        _merge_scoped_maps(sourced_default_properties, cli_default_properties),
        allowed_object_types=allowed_object_types,
    )
    searchable_properties_by_object = _filter_scoped_map(
        _merge_scoped_maps(sourced_searchable_properties, cli_searchable_properties),
        allowed_object_types=allowed_object_types,
    )
    sortable_properties_by_object = _filter_scoped_map(
        _merge_scoped_maps(sourced_sortable_properties, cli_sortable_properties),
        allowed_object_types=allowed_object_types,
    )
    allowed_record_ids_by_object = _filter_scoped_map(
        _merge_scoped_maps(sourced_allowed_record_ids, cli_allowed_record_ids),
        allowed_object_types=allowed_object_types,
    )

    missing_property_maps = [
        object_type for object_type in allowed_object_types if object_type not in allowed_properties_by_object
    ]
    if missing_property_maps:
        missing = ", ".join(missing_property_maps)
        raise ValueError(
            f"Every allowlisted object_type needs allowed properties; missing allowed properties for: {missing}"
        )

    bundle: dict[str, Any] = {
        "provider": "salesforce",
        "auth_mode": "connected_app_refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "allowed_object_types": allowed_object_types,
        "allowed_properties_by_object": allowed_properties_by_object,
    }
    if auth_base_url:
        bundle["auth_base_url"] = auth_base_url
    if api_version:
        bundle["api_version"] = api_version
    if default_properties_by_object:
        bundle["default_properties_by_object"] = default_properties_by_object
    if searchable_properties_by_object:
        bundle["searchable_properties_by_object"] = searchable_properties_by_object
    if sortable_properties_by_object:
        bundle["sortable_properties_by_object"] = sortable_properties_by_object
    if allowed_record_ids_by_object:
        bundle["allowed_record_ids_by_object"] = allowed_record_ids_by_object
    return bundle


def _validate_bundle(bundle: dict[str, Any], *, crm_ref: str) -> None:
    env_key = f"RHUMB_CRM_{crm_ref.upper()}"
    previous = os.environ.get(env_key)
    os.environ[env_key] = json.dumps(bundle, separators=(",", ":"), sort_keys=True)
    try:
        resolve_crm_bundle(crm_ref)
    finally:
        if previous is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = previous


def _render(bundle: dict[str, Any], *, crm_ref: str, mode: str) -> str:
    env_key = f"RHUMB_CRM_{crm_ref.upper()}"
    payload = json.dumps(bundle, separators=(",", ":"), sort_keys=True)
    if mode == "json":
        return json.dumps(bundle, indent=2, sort_keys=True)
    if mode == "shell":
        return f"export {env_key}={shlex.quote(payload)}"
    if mode == "railway":
        return f"railway variables --set {env_key}={shlex.quote(payload)}"
    raise ValueError(f"Unsupported output mode: {mode}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and validate a RHUMB_CRM_<REF> Salesforce CRM bundle"
    )
    parser.add_argument("--crm-ref", default="sf_main")
    parser.add_argument("--client-id")
    parser.add_argument("--client-secret")
    parser.add_argument("--refresh-token")
    parser.add_argument("--auth-base-url")
    parser.add_argument("--api-version")
    parser.add_argument("--from-sop-item")
    parser.add_argument("--vault", default=DEFAULT_VAULT)
    parser.add_argument("--allow-object", action="append", default=[])
    parser.add_argument("--allow-property", action="append", default=[])
    parser.add_argument("--default-property", action="append", default=[])
    parser.add_argument("--searchable-property", action="append", default=[])
    parser.add_argument("--sortable-property", action="append", default=[])
    parser.add_argument("--allowed-record-id", action="append", default=[])

    output = parser.add_mutually_exclusive_group()
    output.add_argument("--shell", action="store_true")
    output.add_argument("--railway", action="store_true")
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
    except ValueError as exc:
        parser.error(str(exc))

    _validate_bundle(bundle, crm_ref=args.crm_ref)

    mode = "railway" if args.railway else "shell" if args.shell else "json"
    print(_render(bundle, crm_ref=args.crm_ref, mode=mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
