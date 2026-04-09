#!/usr/bin/env python3
"""Build and validate a RHUMB_SUPPORT_<REF> env bundle for AUD-18 Zendesk dogfood.

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
_ZENDESK_HOST_RE = re.compile(r"^https?://([a-z0-9-]+)\.zendesk\.com(?:/|$)", re.I)


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

from services.support_connection_registry import resolve_support_bundle  # noqa: E402


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


def _subdomain_from_item_urls(item: dict[str, Any]) -> str | None:
    for raw_url in item.get("urls") or []:
        if isinstance(raw_url, str):
            href = raw_url.strip()
        elif isinstance(raw_url, dict):
            href = str(raw_url.get("href") or raw_url.get("url") or "").strip()
        else:
            continue
        if not href:
            continue
        match = _ZENDESK_HOST_RE.match(href)
        if match:
            return match.group(1).lower()
    return None


def _infer_auth_mode(
    *,
    explicit_auth_mode: str | None,
    email: str | None,
    api_token: str | None,
    bearer_token: str | None,
    generic_secret: str | None,
) -> str | None:
    if explicit_auth_mode in {"api_token", "bearer_token"}:
        return explicit_auth_mode
    if api_token or (email and generic_secret):
        return "api_token"
    if bearer_token or generic_secret:
        return "bearer_token"
    return None


def _extract_sop_defaults(item: dict[str, Any]) -> dict[str, Any]:
    values = _field_value_map(item)
    explicit_auth_mode = _first_string(values, ("auth_mode", "authentication_mode"))
    subdomain = _first_string(
        values,
        ("subdomain", "zendesk_subdomain", "workspace_subdomain", "zendesk_workspace"),
    ) or _subdomain_from_item_urls(item)
    email = _first_string(values, ("email", "username", "login", "account_email"))
    explicit_api_token = _first_string(values, ("api_token", "api_key", "password"))
    explicit_bearer_token = _first_string(values, ("bearer_token", "access_token"))
    generic_secret = _first_string(values, ("credential", "token", "secret"))

    auth_mode = _infer_auth_mode(
        explicit_auth_mode=explicit_auth_mode,
        email=email,
        api_token=explicit_api_token,
        bearer_token=explicit_bearer_token,
        generic_secret=generic_secret,
    )

    defaults: dict[str, Any] = {}
    if subdomain:
        defaults["subdomain"] = subdomain
    if auth_mode:
        defaults["auth_mode"] = auth_mode
    if email:
        defaults["email"] = email

    if auth_mode == "api_token":
        api_token = explicit_api_token or generic_secret
        if api_token:
            defaults["api_token"] = api_token
    elif auth_mode == "bearer_token":
        bearer_token = explicit_bearer_token or generic_secret
        if bearer_token:
            defaults["bearer_token"] = bearer_token

    allowed_group_ids = _parse_id_value(
        _first_value(values, ("allowed_group_ids", "allowed_group_id", "group_ids", "group_id"))
    )
    allowed_brand_ids = _parse_id_value(
        _first_value(values, ("allowed_brand_ids", "allowed_brand_id", "brand_ids", "brand_id"))
    )
    allow_internal_comments = _parse_bool(
        _first_value(
            values,
            (
                "allow_internal_comments",
                "internal_comments_allowed",
                "include_internal_comments",
            ),
        )
    )

    if allowed_group_ids:
        defaults["allowed_group_ids"] = allowed_group_ids
    if allowed_brand_ids:
        defaults["allowed_brand_ids"] = allowed_brand_ids
    if allow_internal_comments is not None:
        defaults["allow_internal_comments"] = allow_internal_comments
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


def _cli_auth_mode_guess(args: argparse.Namespace) -> str | None:
    if args.bearer_token and not (args.email or args.api_token):
        return "bearer_token"
    return None


def _build_bundle(args: argparse.Namespace, *, sourced: dict[str, Any] | None = None) -> dict[str, Any]:
    sourced = sourced or {}
    auth_mode = args.auth_mode or sourced.get("auth_mode") or _cli_auth_mode_guess(args) or "api_token"
    subdomain = str(args.subdomain or sourced.get("subdomain") or "").strip()
    if not subdomain:
        raise ValueError("--subdomain is required unless it can be inferred from --from-sop-item")

    allowed_group_ids = _parse_id_list(args.allowed_group_id) if args.allowed_group_id else list(
        sourced.get("allowed_group_ids") or []
    )
    allowed_brand_ids = _parse_id_list(args.allowed_brand_id) if args.allowed_brand_id else list(
        sourced.get("allowed_brand_ids") or []
    )

    allow_internal_comments = bool(args.allow_internal_comments)
    if not args.allow_internal_comments and sourced.get("allow_internal_comments") is True:
        allow_internal_comments = True

    bundle: dict[str, Any] = {
        "provider": "zendesk",
        "subdomain": subdomain,
        "auth_mode": auth_mode,
        "allowed_group_ids": allowed_group_ids,
        "allowed_brand_ids": allowed_brand_ids,
        "allow_internal_comments": allow_internal_comments,
    }
    if auth_mode == "api_token":
        email = str(args.email or sourced.get("email") or "").strip()
        api_token = str(args.api_token or sourced.get("api_token") or "").strip()
        if not email or not api_token:
            raise ValueError(
                "--email and --api-token are required for auth_mode api_token, unless they can be inferred from --from-sop-item"
            )
        bundle["email"] = email
        bundle["api_token"] = api_token
    elif auth_mode == "bearer_token":
        bearer_token = str(args.bearer_token or sourced.get("bearer_token") or "").strip()
        if not bearer_token:
            raise ValueError(
                "--bearer-token is required for auth_mode bearer_token, unless it can be inferred from --from-sop-item"
            )
        bundle["bearer_token"] = bearer_token
    else:
        raise ValueError(f"Unsupported auth mode: {auth_mode}")
    return bundle


def _validate_bundle(bundle: dict[str, Any], *, support_ref: str) -> None:
    env_key = f"RHUMB_SUPPORT_{support_ref.upper()}"
    previous = os.environ.get(env_key)
    os.environ[env_key] = json.dumps(bundle, separators=(",", ":"), sort_keys=True)
    try:
        resolve_support_bundle(support_ref)
    finally:
        if previous is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = previous


def _render(bundle: dict[str, Any], *, support_ref: str, mode: str) -> str:
    env_key = f"RHUMB_SUPPORT_{support_ref.upper()}"
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
        description="Build and validate a RHUMB_SUPPORT_<REF> Zendesk support bundle"
    )
    parser.add_argument("--support-ref", default="st_zd")
    parser.add_argument("--subdomain")
    parser.add_argument("--from-sop-item")
    parser.add_argument("--vault", default=DEFAULT_VAULT)
    parser.add_argument(
        "--auth-mode",
        choices=["api_token", "bearer_token"],
    )
    parser.add_argument("--email")
    parser.add_argument("--api-token")
    parser.add_argument("--bearer-token")
    parser.add_argument("--allowed-group-id", action="append", default=[])
    parser.add_argument("--allowed-brand-id", action="append", default=[])
    parser.add_argument("--allow-internal-comments", action="store_true")

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

    _validate_bundle(bundle, support_ref=args.support_ref)

    mode = "railway" if args.railway else "shell" if args.shell else "json"
    print(_render(bundle, support_ref=args.support_ref, mode=mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
