#!/usr/bin/env python3
"""Build and validate a RHUMB_SUPPORT_<REF> env bundle for AUD-18 Intercom dogfood.

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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "packages" / "api"
VENV_PYTHON = API_DIR / ".venv" / "bin" / "python"
DEFAULT_VAULT = "OpenClaw Agents"
_VALID_REGIONS = {"us", "eu", "au"}


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

from services.support_connection_registry import resolve_intercom_support_bundle  # noqa: E402


def _normalize_key(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _parse_id_list(values: list[str] | None) -> list[int]:
    parsed: list[int] = []
    for value in values or []:
        normalized = value.strip()
        if not normalized:
            continue
        parsed.append(int(normalized))
    return parsed


def _parse_id_value(value: object) -> list[int]:
    if value is None or value == "":
        return []
    if isinstance(value, (int, float)):
        return [int(value)]
    if isinstance(value, list):
        parsed: list[int] = []
        for item in value:
            parsed.extend(_parse_id_value(item))
        return parsed
    parts = re.split(r"[\s,]+", str(value).strip())
    return [int(part) for part in parts if part]


def _parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


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


def _extract_sop_defaults(item: dict[str, Any]) -> dict[str, Any]:
    values = _field_value_map(item)

    region = _first_string(values, ("region", "workspace_region", "intercom_region"))
    bearer_token = _first_string(
        values,
        ("bearer_token", "access_token", "token", "credential", "secret", "password"),
    )
    allowed_team_ids = _parse_id_value(
        _first_value(values, ("allowed_team_ids", "allowed_team_id", "team_ids", "team_id"))
    )
    allowed_admin_ids = _parse_id_value(
        _first_value(
            values,
            (
                "allowed_admin_ids",
                "allowed_admin_id",
                "admin_ids",
                "admin_id",
                "teammate_ids",
                "teammate_id",
            ),
        )
    )
    allow_internal_notes = _parse_bool(
        _first_value(
            values,
            ("allow_internal_notes", "internal_notes_allowed", "include_internal_notes"),
        )
    )

    defaults: dict[str, Any] = {}
    if region:
        defaults["region"] = region.lower()
    if bearer_token:
        defaults["bearer_token"] = bearer_token
    if allowed_team_ids:
        defaults["allowed_team_ids"] = allowed_team_ids
    if allowed_admin_ids:
        defaults["allowed_admin_ids"] = allowed_admin_ids
    if allow_internal_notes is not None:
        defaults["allow_internal_notes"] = allow_internal_notes
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


def _build_bundle(args: argparse.Namespace, *, sourced: dict[str, Any] | None = None) -> dict[str, object]:
    sourced = sourced or {}

    region = str(args.region or sourced.get("region") or "").strip().lower()
    if region not in _VALID_REGIONS:
        raise ValueError(
            "--region is required unless it can be inferred from --from-sop-item, and must be us, eu, or au"
        )

    bearer_token = str(args.bearer_token or sourced.get("bearer_token") or "").strip()
    if not bearer_token:
        raise ValueError(
            "--bearer-token is required unless it can be inferred from --from-sop-item"
        )

    allowed_team_ids = _parse_id_list(args.allowed_team_id) if args.allowed_team_id else list(
        sourced.get("allowed_team_ids") or []
    )
    allowed_admin_ids = _parse_id_list(args.allowed_admin_id) if args.allowed_admin_id else list(
        sourced.get("allowed_admin_ids") or []
    )
    if not allowed_team_ids and not allowed_admin_ids:
        raise ValueError("At least one --allowed-team-id or --allowed-admin-id is required")

    allow_internal_notes = bool(args.allow_internal_notes)
    if not args.allow_internal_notes and sourced.get("allow_internal_notes") is True:
        allow_internal_notes = True

    return {
        "provider": "intercom",
        "region": region,
        "auth_mode": "bearer_token",
        "bearer_token": bearer_token,
        "allowed_team_ids": allowed_team_ids,
        "allowed_admin_ids": allowed_admin_ids,
        "allow_internal_notes": allow_internal_notes,
    }


def _validate_bundle(ref: str, bundle: dict[str, object]) -> dict[str, object]:
    env_key = f"RHUMB_SUPPORT_{ref.upper()}"
    original = os.environ.get(env_key)
    os.environ[env_key] = json.dumps(bundle, separators=(",", ":"), sort_keys=True)
    try:
        resolved = resolve_intercom_support_bundle(ref)
    finally:
        if original is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = original
    return {
        "support_ref": resolved.support_ref,
        "provider": resolved.provider,
        "region": resolved.region,
        "allowed_team_ids": list(resolved.allowed_team_ids),
        "allowed_admin_ids": list(resolved.allowed_admin_ids),
        "allow_internal_notes": resolved.allow_internal_notes,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--support-ref", required=True)
    parser.add_argument("--region", choices=sorted(_VALID_REGIONS))
    parser.add_argument("--bearer-token")
    parser.add_argument("--from-sop-item")
    parser.add_argument("--vault", default=DEFAULT_VAULT)
    parser.add_argument("--allowed-team-id", action="append")
    parser.add_argument("--allowed-admin-id", action="append")
    parser.add_argument("--allow-internal-notes", action="store_true")
    parser.add_argument("--format", choices=["json", "export", "railway"], default="json")
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

    _validate_bundle(args.support_ref, bundle)

    env_key = f"RHUMB_SUPPORT_{args.support_ref.upper()}"
    raw = json.dumps(bundle, separators=(",", ":"), sort_keys=True)
    if args.format == "json":
        print(json.dumps(bundle, indent=2, sort_keys=True))
    elif args.format == "export":
        print(f"export {env_key}={shlex.quote(raw)}")
    else:
        print(f"railway variables --set {env_key}={shlex.quote(raw)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
