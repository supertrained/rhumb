#!/usr/bin/env python3
"""Build and validate a RHUMB_SUPPORT_<REF> env bundle for AUD-18 Zendesk dogfood.

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
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "packages" / "api"
VENV_PYTHON = API_DIR / ".venv" / "bin" / "python"


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


def _parse_id_list(values: list[str] | None) -> list[int]:
    parsed: list[int] = []
    for value in values or []:
        normalized = value.strip()
        if not normalized:
            continue
        parsed.append(int(normalized))
    return parsed


def _build_bundle(args: argparse.Namespace) -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "provider": "zendesk",
        "subdomain": args.subdomain.strip(),
        "auth_mode": args.auth_mode,
        "allowed_group_ids": _parse_id_list(args.allowed_group_id),
        "allowed_brand_ids": _parse_id_list(args.allowed_brand_id),
        "allow_internal_comments": bool(args.allow_internal_comments),
    }
    if args.auth_mode == "api_token":
        bundle["email"] = args.email.strip()
        bundle["api_token"] = args.api_token.strip()
    else:
        bundle["bearer_token"] = args.bearer_token.strip()
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
    parser.add_argument("--subdomain", required=True)
    parser.add_argument(
        "--auth-mode",
        choices=["api_token", "bearer_token"],
        default="api_token",
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

    if args.auth_mode == "api_token":
        if not args.email or not args.api_token:
            parser.error("--email and --api-token are required for --auth-mode api_token")
    else:
        if not args.bearer_token:
            parser.error("--bearer-token is required for --auth-mode bearer_token")

    bundle = _build_bundle(args)
    _validate_bundle(bundle, support_ref=args.support_ref)

    mode = "railway" if args.railway else "shell" if args.shell else "json"
    print(_render(bundle, support_ref=args.support_ref, mode=mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
