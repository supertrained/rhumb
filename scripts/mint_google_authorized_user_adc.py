#!/usr/bin/env python3
"""Mint or refresh Google ADC authorized-user material for bounded Rhumb operator flows.

Primary use case: acquire a refresh-capable authorized_user JSON for the Rhumb
Google OAuth client, then feed that ADC file into the AUD-18 BigQuery
service-account-impersonation bundle builder.

This helper intentionally avoids printing secret values. It can:
- source client_id/client_secret from a 1Password item via `sop`
- build a temporary `--client-id-file` payload for gcloud
- back up the current ADC file before login
- run `gcloud auth application-default login` with the requested scopes
- verify that the resulting ADC file is `type=authorized_user` and matches the
  requested OAuth client
- print a ready follow-on `build_bigquery_warehouse_bundle.py` command when
  warehouse bundle flags are supplied
- print a one-shot hosted proof command that rebuilds the bounded warehouse env
  from the refreshed ADC and runs `bigquery_warehouse_read_dogfood.py`

By default this command is interactive and expects a human-attended browser
login. Use `--dry-run --json` when you only want the generated plan/command.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_VAULT = "OpenClaw Agents"
DEFAULT_SOP_ITEM = "Rhumb - Google OAuth"
DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/bigquery",
)
DEFAULT_ADC_PATH = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
DEFAULT_GCLOUD_FALLBACK = Path.home() / "google-cloud-sdk" / "bin" / "gcloud"
DEFAULT_CLIENT_TYPE = "installed"
DEFAULT_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
DEFAULT_PROOF_BASE_URL = "https://api.rhumb.dev"
DEFAULT_PROOF_LIMIT = 5
ROOT = Path(__file__).resolve().parents[1]


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _normalize_key(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _normalize_scopes(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in str(raw or "").split(","):
            scope = part.strip()
            if not scope or scope in seen:
                continue
            seen.add(scope)
            output.append(scope)
    return output or list(DEFAULT_SCOPES)


def _field_value_map(item: dict[str, Any]) -> dict[str, object]:
    mapped: dict[str, object] = {}
    for field in item.get("fields") or []:
        if not isinstance(field, dict):
            continue
        value = field.get("value")
        for key_name in ("label", "id", "name", "purpose"):
            key = _normalize_key(field.get(key_name))
            if key and key not in mapped:
                mapped[key] = value
    return mapped


def _load_sop_item(item_name: str, *, vault: str) -> dict[str, Any]:
    result = subprocess.run(
        ["sop", "item", "get", item_name, "--vault", vault, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "sop item get failed").strip()
        raise RuntimeError(error)
    return json.loads(result.stdout)


def _extract_sop_client_metadata(item: dict[str, Any]) -> dict[str, str | None]:
    values = _field_value_map(item)

    def first(*aliases: str) -> str | None:
        for alias in aliases:
            value = values.get(_normalize_key(alias))
            text = str(value or "").strip()
            if text:
                return text
        return None

    return {
        "client_id": first("client_id"),
        "client_secret": first("client_secret"),
        "project_id": first("project_id", "gcp_project_id", "billing_project_id"),
        "account": first("account", "username", "email"),
    }


def _build_client_id_file_payload(
    client_id: str,
    client_secret: str,
    *,
    client_type: str = DEFAULT_CLIENT_TYPE,
) -> dict[str, Any]:
    payload = {
        client_type: {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": DEFAULT_AUTH_URI,
            "token_uri": DEFAULT_TOKEN_URI,
        }
    }
    if client_type == "web":
        payload[client_type]["redirect_uris"] = ["http://localhost"]
    return payload


def _resolve_gcloud_path(explicit_path: str | None = None) -> Path:
    if explicit_path:
        path = Path(explicit_path).expanduser()
        if path.exists():
            return path
        raise FileNotFoundError(f"gcloud not found at {path}")

    discovered = shutil.which("gcloud")
    if discovered:
        return Path(discovered)
    if DEFAULT_GCLOUD_FALLBACK.exists():
        return DEFAULT_GCLOUD_FALLBACK
    raise FileNotFoundError(
        "Unable to find gcloud. Set --gcloud-path or install the Google Cloud CLI."
    )


def _write_client_id_file(payload: dict[str, Any], output_path: Path | None) -> Path:
    if output_path is None:
        output_path = Path(tempfile.gettempdir()) / "rhumb-google-oauth-client.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path


def _build_login_command(
    *,
    gcloud_path: Path,
    client_id_file: Path,
    scopes: list[str],
    disable_quota_project: bool,
    no_browser: bool,
) -> list[str]:
    command = [
        str(gcloud_path),
        "auth",
        "application-default",
        "login",
        f"--client-id-file={client_id_file}",
        f"--scopes={','.join(scopes)}",
    ]
    if disable_quota_project:
        command.append("--disable-quota-project")
    if no_browser:
        command.append("--no-browser")
    return command


def _backup_adc_file(adc_path: Path, backup_dir: Path | None = None) -> Path | None:
    if not adc_path.exists():
        return None
    backup_root = backup_dir or adc_path.parent / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    destination = backup_root / f"application_default_credentials-{_now_slug()}.json"
    shutil.copy2(adc_path, destination)
    return destination


def _summarize_adc_file(adc_path: Path, *, expected_client_id: str) -> dict[str, Any]:
    if not adc_path.exists():
        raise FileNotFoundError(f"ADC file not found at {adc_path}")
    payload = json.loads(adc_path.read_text(encoding="utf-8"))
    refresh_token = str(payload.get("refresh_token") or "")
    client_id = str(payload.get("client_id") or "")
    return {
        "path": str(adc_path),
        "type": payload.get("type"),
        "client_id_matches": client_id == expected_client_id,
        "client_id_length": len(client_id),
        "refresh_token_present": bool(refresh_token),
        "refresh_token_length": len(refresh_token),
        "quota_project_id": payload.get("quota_project_id"),
    }


def _build_bundle_command_hint(args: argparse.Namespace, adc_path: Path) -> str | None:
    if not (
        args.warehouse_ref
        and args.service_account_email
        and args.billing_project_id
        and args.location
        and args.allowed_dataset_ref
        and args.allowed_table_ref
    ):
        return None

    command = [
        sys.executable,
        str(ROOT / "scripts" / "build_bigquery_warehouse_bundle.py"),
        "--warehouse-ref",
        args.warehouse_ref,
        "--auth-mode",
        "service_account_impersonation",
        "--authorized-user-json-file",
        str(adc_path),
        "--service-account-email",
        args.service_account_email,
        "--billing-project-id",
        args.billing_project_id,
        "--location",
        args.location,
    ]
    for dataset_ref in args.allowed_dataset_ref:
        command.extend(["--allowed-dataset-ref", dataset_ref])
    for table_ref in args.allowed_table_ref:
        command.extend(["--allowed-table-ref", table_ref])
    return shlex.join(command)


def _default_proof_query(table_ref: str) -> str:
    return f"SELECT * FROM `{table_ref}` LIMIT {DEFAULT_PROOF_LIMIT}"


def _build_proof_command_hint(args: argparse.Namespace, adc_path: Path) -> str | None:
    if not (
        args.warehouse_ref
        and args.service_account_email
        and args.billing_project_id
        and args.location
        and args.allowed_dataset_ref
        and args.allowed_table_ref
    ):
        return None

    env_key = f"RHUMB_WAREHOUSE_{args.warehouse_ref.upper()}"
    build_command = [
        sys.executable,
        str(ROOT / "scripts" / "build_bigquery_warehouse_bundle.py"),
        "--warehouse-ref",
        args.warehouse_ref,
        "--auth-mode",
        "service_account_impersonation",
        "--authorized-user-json-file",
        str(adc_path),
        "--service-account-email",
        args.service_account_email,
        "--billing-project-id",
        args.billing_project_id,
        "--location",
        args.location,
    ]
    for dataset_ref in args.allowed_dataset_ref:
        build_command.extend(["--allowed-dataset-ref", dataset_ref])
    for table_ref in args.allowed_table_ref:
        build_command.extend(["--allowed-table-ref", table_ref])
    build_command.extend(["--format", "env-value"])

    proof_command = [
        sys.executable,
        str(ROOT / "scripts" / "bigquery_warehouse_read_dogfood.py"),
        "--base-url",
        args.proof_base_url,
        "--warehouse-ref",
        args.warehouse_ref,
        "--query",
        args.proof_query or _default_proof_query(args.allowed_table_ref[0]),
        "--json-out",
        str(ROOT / "artifacts" / f"aud18-bigquery-hosted-proof-{_now_slug()}.json"),
    ]

    return (
        f'export {env_key}="$({shlex.join(build_command)})" '
        f"&& {shlex.join(proof_command)}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mint or refresh a Google ADC authorized-user JSON for bounded Rhumb operator flows."
    )
    parser.add_argument("--from-sop-item", default=DEFAULT_SOP_ITEM)
    parser.add_argument("--vault", default=DEFAULT_VAULT)
    parser.add_argument("--client-id")
    parser.add_argument("--client-secret")
    parser.add_argument("--client-type", choices=("installed", "web"), default=DEFAULT_CLIENT_TYPE)
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument("--gcloud-path")
    parser.add_argument("--adc-path", default=str(DEFAULT_ADC_PATH))
    parser.add_argument("--backup-dir")
    parser.add_argument("--client-id-file-output")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--allow-quota-project", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-out")
    parser.add_argument("--proof-base-url", default=DEFAULT_PROOF_BASE_URL)
    parser.add_argument("--proof-query")

    # Optional bounded follow-on hints for AUD-18 BigQuery.
    parser.add_argument("--warehouse-ref")
    parser.add_argument("--service-account-email")
    parser.add_argument("--billing-project-id")
    parser.add_argument("--location")
    parser.add_argument("--allowed-dataset-ref", action="append", default=[])
    parser.add_argument("--allowed-table-ref", action="append", default=[])
    return parser


def _build_plan(args: argparse.Namespace) -> dict[str, Any]:
    sourced: dict[str, str | None] = {}
    if args.from_sop_item:
        sourced = _extract_sop_client_metadata(_load_sop_item(args.from_sop_item, vault=args.vault))

    client_id = str(args.client_id or sourced.get("client_id") or "").strip()
    client_secret = str(args.client_secret or sourced.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise ValueError(
            "client_id and client_secret are required, either explicitly or via --from-sop-item"
        )

    scopes = _normalize_scopes(args.scope)
    gcloud_path = _resolve_gcloud_path(args.gcloud_path)
    adc_path = Path(args.adc_path).expanduser()
    backup_dir = Path(args.backup_dir).expanduser() if args.backup_dir else None
    client_id_file = _write_client_id_file(
        _build_client_id_file_payload(client_id, client_secret, client_type=args.client_type),
        Path(args.client_id_file_output).expanduser() if args.client_id_file_output else None,
    )
    login_command = _build_login_command(
        gcloud_path=gcloud_path,
        client_id_file=client_id_file,
        scopes=scopes,
        disable_quota_project=not args.allow_quota_project,
        no_browser=args.no_browser,
    )
    bundle_command = _build_bundle_command_hint(args, adc_path)
    proof_command = _build_proof_command_hint(args, adc_path)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "dry_run" if args.dry_run else "interactive_login",
        "oauth_client": {
            "source_item": args.from_sop_item,
            "vault": args.vault,
            "client_type": args.client_type,
            "client_id_length": len(client_id),
            "client_secret_length": len(client_secret),
            "account": sourced.get("account"),
            "project_id": sourced.get("project_id"),
        },
        "gcloud": {
            "path": str(gcloud_path),
            "adc_path": str(adc_path),
            "client_id_file": str(client_id_file),
            "scopes": scopes,
            "disable_quota_project": not args.allow_quota_project,
            "no_browser": args.no_browser,
            "command": shlex.join(login_command),
            "env": {"CLOUDSDK_PYTHON": sys.executable},
        },
        "adc_backup": {
            "would_backup": adc_path.exists(),
            "backup_dir": str(backup_dir or (adc_path.parent / 'backups')),
        },
        "bundle_command": bundle_command,
        "proof_command": proof_command,
    }


def _emit_summary(summary: dict[str, Any], *, as_json: bool, json_out: str | None) -> None:
    if json_out:
        Path(json_out).expanduser().write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if as_json:
        print(json.dumps(summary, indent=2))
        return

    mode = summary.get("mode")
    gcloud = summary.get("gcloud") or {}
    oauth_client = summary.get("oauth_client") or {}
    print(f"Google ADC helper ({mode})")
    print(f"- gcloud: {gcloud.get('path')}")
    print(f"- adc_path: {gcloud.get('adc_path')}")
    print(f"- scopes: {', '.join(gcloud.get('scopes') or [])}")
    print(f"- client source: {oauth_client.get('source_item')}")
    print(f"- command: {gcloud.get('command')}")
    bundle_command = summary.get("bundle_command")
    if bundle_command:
        print(f"- follow-on bundle command: {bundle_command}")
    proof_command = summary.get("proof_command")
    if proof_command:
        print(f"- follow-on proof command: {proof_command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    summary = _build_plan(args)
    adc_path = Path((summary.get("gcloud") or {}).get("adc_path") or args.adc_path).expanduser()

    if args.dry_run:
        _emit_summary(summary, as_json=args.json, json_out=args.json_out)
        return 0

    backup_path = _backup_adc_file(
        adc_path,
        Path(args.backup_dir).expanduser() if args.backup_dir else None,
    )
    summary["adc_backup"]["backup_path"] = str(backup_path) if backup_path else None

    command = shlex.split(str(summary["gcloud"]["command"]))
    env = os.environ.copy()
    env["CLOUDSDK_PYTHON"] = sys.executable
    completed = subprocess.run(command, env=env, check=False)
    summary["gcloud"]["returncode"] = completed.returncode
    if completed.returncode != 0:
        _emit_summary(summary, as_json=args.json, json_out=args.json_out)
        return completed.returncode

    client_id_length = int((summary.get("oauth_client") or {}).get("client_id_length") or 0)
    if client_id_length <= 0:
        raise RuntimeError("missing expected client metadata after login")

    expected_client_id = json.loads(Path(summary["gcloud"]["client_id_file"]).read_text(encoding="utf-8"))[args.client_type]["client_id"]
    adc_summary = _summarize_adc_file(adc_path, expected_client_id=expected_client_id)
    summary["adc"] = adc_summary
    if adc_summary.get("type") != "authorized_user":
        raise RuntimeError("ADC login completed but the resulting file is not type=authorized_user")
    if adc_summary.get("client_id_matches") is not True:
        raise RuntimeError("ADC login completed but the resulting file does not match the requested OAuth client")
    if adc_summary.get("refresh_token_present") is not True:
        raise RuntimeError("ADC login completed but no refresh_token was written")

    _emit_summary(summary, as_json=args.json, json_out=args.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
