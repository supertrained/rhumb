#!/usr/bin/env python3
"""Build and validate a RHUMB_SUPPORT_<REF> env bundle for AUD-18 Intercom dogfood."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

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

from services.support_connection_registry import resolve_intercom_support_bundle  # noqa: E402


def _parse_id_list(values: list[str] | None) -> list[int]:
    parsed: list[int] = []
    for value in values or []:
        normalized = value.strip()
        if not normalized:
            continue
        parsed.append(int(normalized))
    return parsed


def _build_bundle(args: argparse.Namespace) -> dict[str, object]:
    bundle = {
        "provider": "intercom",
        "region": args.region,
        "auth_mode": "bearer_token",
        "bearer_token": args.bearer_token,
        "allowed_team_ids": _parse_id_list(args.allowed_team_id),
        "allowed_admin_ids": _parse_id_list(args.allowed_admin_id),
        "allow_internal_notes": bool(args.allow_internal_notes),
    }
    if not bundle["allowed_team_ids"] and not bundle["allowed_admin_ids"]:
        raise ValueError("At least one --allowed-team-id or --allowed-admin-id is required")
    return bundle


def _validate_bundle(ref: str, bundle: dict[str, object]) -> dict[str, object]:
    env_key = f"RHUMB_SUPPORT_{ref.upper()}"
    original = os.environ.get(env_key)
    os.environ[env_key] = json.dumps(bundle)
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--support-ref", required=True)
    parser.add_argument("--region", required=True, choices=["us", "eu", "au"])
    parser.add_argument("--bearer-token", required=True)
    parser.add_argument("--allowed-team-id", action="append")
    parser.add_argument("--allowed-admin-id", action="append")
    parser.add_argument("--allow-internal-notes", action="store_true")
    parser.add_argument("--format", choices=["json", "export", "railway"], default="json")
    args = parser.parse_args()

    bundle = _build_bundle(args)
    _validate_bundle(args.support_ref, bundle)

    env_key = f"RHUMB_SUPPORT_{args.support_ref.upper()}"
    raw = json.dumps(bundle, separators=(",", ":"))
    if args.format == "json":
        print(json.dumps(bundle, indent=2))
    elif args.format == "export":
        print(f"export {env_key}={shlex.quote(raw)}")
    else:
        print(f"railway variables --set {env_key}={shlex.quote(raw)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
