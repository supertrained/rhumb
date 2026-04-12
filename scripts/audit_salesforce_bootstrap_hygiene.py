#!/usr/bin/env python3
"""Audit durable Salesforce bootstrap persistence and temporary secret residue.

This is a bounded AUD-18 operator helper for the post-proof Salesforce closeout pass.
It verifies that the live `sf_main` bootstrap material is durably stored in 1Password
without printing secret values, then scans temporary files for leftover secret-bearing
Salesforce residue. Optional cleanup moves high-risk temp files to Trash.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "artifacts"
DEFAULT_VAULT = "OpenClaw Agents"
DEFAULT_BUNDLE_ITEM = "Salesforce CRM Bundle - sf_main"
DEFAULT_LOGIN_ITEM = "Salesforce Developer Edition - AUD-18 sf_main"
DEFAULT_TEMP_ROOT = Path("/tmp")
DEFAULT_MAX_FILE_BYTES = 2_000_000

REQUIRED_BUNDLE_FIELDS = (
    "client_id",
    "client_secret",
    "refresh_token",
    "auth_base_url",
    "redirect_uri",
    "connected_app",
    "account",
    "instance_url",
    "allowed_object_types",
    "allowed_properties_by_object",
    "record_id",
)

SECRET_MARKERS = (
    "refresh_token",
    "client_secret",
    "access_token",
    "authorized_user_json",
    "rhumb_crm_sf_main",
)

SALESFORCE_MARKERS = (
    "salesforce",
    "sf_main",
    "force.com",
    "crm bundle - sf_main",
)


@dataclass(frozen=True)
class ResidueScan:
    path: Path
    size_bytes: int
    salesforce_markers: tuple[str, ...]
    secret_markers: tuple[str, ...]
    high_risk: bool


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_json(cmd: list[str]) -> tuple[Any | None, str | None]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or f"command failed with exit code {proc.returncode}").strip()
    try:
        return json.loads(proc.stdout or "null"), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON output: {exc}"


def _normalize_key(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _load_item(title: str, vault: str) -> tuple[dict[str, Any] | None, str | None]:
    payload, error = _run_json(["sop", "item", "get", title, "--vault", vault, "--format", "json"])
    if error:
        return None, error
    if not isinstance(payload, dict):
        return None, "unexpected item payload"
    return payload, None


def _field_presence(item: dict[str, Any]) -> dict[str, bool]:
    presence: dict[str, bool] = {}
    for field in item.get("fields") or []:
        if not isinstance(field, dict):
            continue
        key = _normalize_key(field.get("label") or field.get("name") or field.get("id") or field.get("purpose"))
        if not key:
            continue
        value = field.get("value")
        presence[key] = value is not None and (not isinstance(value, str) or bool(value.strip()))
    return presence


def audit_bundle_item(title: str, vault: str) -> dict[str, Any]:
    item, error = _load_item(title, vault)
    if error:
        return {
            "title": title,
            "vault": vault,
            "ok": False,
            "error": error,
            "exists": False,
        }

    presence = _field_presence(item)
    missing_required = [field for field in REQUIRED_BUNDLE_FIELDS if not presence.get(field, False)]
    return {
        "title": title,
        "vault": vault,
        "ok": True,
        "exists": True,
        "category": item.get("category"),
        "required_fields": {field: presence.get(field, False) for field in REQUIRED_BUNDLE_FIELDS},
        "missing_required_fields": missing_required,
        "bundle_material_ready": not missing_required,
    }


def audit_login_item(title: str, vault: str) -> dict[str, Any]:
    item, error = _load_item(title, vault)
    if error:
        return {
            "title": title,
            "vault": vault,
            "ok": False,
            "error": error,
            "exists": False,
        }

    presence = _field_presence(item)
    return {
        "title": title,
        "vault": vault,
        "ok": True,
        "exists": True,
        "category": item.get("category"),
        "has_username": presence.get("username", False),
        "has_password": presence.get("password", False),
        "has_security_answer": presence.get("security_answer", False),
        "urls": [url.get("label") for url in item.get("urls") or [] if isinstance(url, dict) and url.get("label")],
    }


def _marker_hits(text: str, markers: tuple[str, ...]) -> tuple[str, ...]:
    lowered = text.lower()
    return tuple(marker for marker in markers if marker in lowered)


def scan_temp_residue(temp_root: Path, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> list[ResidueScan]:
    scans: list[ResidueScan] = []
    if not temp_root.exists():
        return scans

    for path in sorted(temp_root.iterdir()):
        if not path.is_file():
            continue
        try:
            size_bytes = path.stat().st_size
        except OSError:
            continue
        if size_bytes > max_file_bytes:
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        combined = f"{path.name}\n{text}"
        salesforce_hits = _marker_hits(combined, SALESFORCE_MARKERS)
        secret_hits = _marker_hits(combined, SECRET_MARKERS)
        if not salesforce_hits and not secret_hits:
            continue
        high_risk = bool(secret_hits and salesforce_hits)
        scans.append(
            ResidueScan(
                path=path,
                size_bytes=size_bytes,
                salesforce_markers=salesforce_hits,
                secret_markers=secret_hits,
                high_risk=high_risk,
            )
        )
    return scans


def cleanup_residue(scans: list[ResidueScan]) -> dict[str, Any]:
    trash_bin = shutil.which("trash")
    if not trash_bin:
        return {
            "requested": True,
            "available": False,
            "cleaned_paths": [],
            "errors": ["trash command not available"],
        }

    cleaned_paths: list[str] = []
    errors: list[dict[str, str]] = []
    for scan in scans:
        if not scan.high_risk:
            continue
        proc = subprocess.run([trash_bin, str(scan.path)], capture_output=True, text=True)
        if proc.returncode == 0:
            cleaned_paths.append(str(scan.path))
        else:
            errors.append(
                {
                    "path": str(scan.path),
                    "error": (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip(),
                }
            )
    return {
        "requested": True,
        "available": True,
        "cleaned_paths": cleaned_paths,
        "errors": errors,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    bundle = audit_bundle_item(args.bundle_item_title, args.vault)
    login = audit_login_item(args.login_item_title, args.vault)
    residue_scans = scan_temp_residue(args.temp_root, max_file_bytes=args.max_file_bytes)

    cleanup: dict[str, Any] | None = None
    if args.trash_residue:
        cleanup = cleanup_residue(residue_scans)
        residue_scans = scan_temp_residue(args.temp_root, max_file_bytes=args.max_file_bytes)

    residue_payload = [
        {
            "path": str(scan.path),
            "size_bytes": scan.size_bytes,
            "salesforce_markers": list(scan.salesforce_markers),
            "secret_markers": list(scan.secret_markers),
            "high_risk": scan.high_risk,
        }
        for scan in residue_scans
    ]

    remaining_high_risk = [entry["path"] for entry in residue_payload if entry["high_risk"]]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault": args.vault,
        "bundle_item": bundle,
        "login_item": login,
        "temp_root": str(args.temp_root),
        "residue_scan": {
            "files_considered": len(residue_payload),
            "high_risk_paths": remaining_high_risk,
            "findings": residue_payload,
        },
        "cleanup": cleanup,
    }
    report["overall_ok"] = bool(
        bundle.get("bundle_material_ready")
        and login.get("exists")
        and not remaining_high_risk
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Salesforce bootstrap persistence and temporary secret residue")
    parser.add_argument("--vault", default=DEFAULT_VAULT)
    parser.add_argument("--bundle-item-title", default=DEFAULT_BUNDLE_ITEM)
    parser.add_argument("--login-item-title", default=DEFAULT_LOGIN_ITEM)
    parser.add_argument("--temp-root", type=Path, default=DEFAULT_TEMP_ROOT)
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--trash-residue", action="store_true")
    parser.add_argument("--json-out", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = build_report(args)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n")

    print(json.dumps(report, indent=2))
    return 0 if report.get("overall_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
