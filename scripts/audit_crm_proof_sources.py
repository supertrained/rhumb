#!/usr/bin/env python3
"""Audit local proof-source signals for CRM rails like HubSpot.

This is an operator helper for AUD-18. It turns the repeated manual discovery pass into
an evidence-backed artifact by scanning:
- 1Password item metadata via `sop`
- the rhumb browser profile History DB
- Gmail metadata via `gog`
- hosted Rhumb capability/resolve/credential-mode surfaces

It is intentionally conservative: browser/mail traces can prove account history or recovery
paths, but only vault-backed scoped bundle material counts as proof-material-ready.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "artifacts"
DEFAULT_HISTORY_DB = Path("/Volumes/tomme 4TB/.openclaw/browser/rhumb/user-data/Default/History")
DEFAULT_VAULT = "OpenClaw Agents"
DEFAULT_GMAIL_ACCOUNTS = [
    "tommeredith@supertrained.ai",
    "tmeredith@simplaphi.com",
    "tom.d.meredith@gmail.com",
]
DEFAULT_API_BASE = "https://api.rhumb.dev"


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    vault_tokens: tuple[str, ...]
    gmail_query: str
    gmail_sender_patterns: tuple[re.Pattern[str], ...]
    browser_like_terms: tuple[str, ...]
    generic_public_hosts: tuple[str, ...]
    hosted_capability_id: str | None = None


PROVIDERS: dict[str, ProviderConfig] = {
    "hubspot": ProviderConfig(
        name="hubspot",
        vault_tokens=("hubspot",),
        gmail_query='hubspot OR from:(noreply@notifications.transactional.hubspot.com) OR subject:("Reset your HubSpot Password")',
        gmail_sender_patterns=(
            re.compile(r"@([a-z0-9-]+)\.hubspot\.com", re.I),
            re.compile(r"@([a-z0-9-]+)\.transactional\.hubspot\.com", re.I),
        ),
        browser_like_terms=("hubspot",),
        generic_public_hosts=("app.hubspot.com", "developers.hubspot.com", "www.hubspot.com", "legal.hubspot.com", "accounts.google.com"),
        hosted_capability_id="crm.record.search",
    ),
}


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _run_json(cmd: list[str]) -> tuple[Any | None, str | None]:
    code, stdout, stderr = _run(cmd)
    if code != 0:
        return None, (stderr or stdout or f"command failed with exit code {code}").strip()
    try:
        return json.loads(stdout or "null"), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON output: {exc}"


def _fetch_json_url(url: str) -> tuple[int | None, Any | None, str | None]:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return None, None, str(exc)

    try:
        payload = json.loads(body or "null")
    except json.JSONDecodeError as exc:
        return status, None, f"invalid JSON response from {url}: {exc}"
    return status, payload, None


def _host_from_url(url: str) -> str | None:
    match = re.match(r"https?://([^/]+)", url, re.I)
    if not match:
        return None
    return match.group(1).lower()


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _normalize_key(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _normalize_object_type(value: object) -> str:
    return str(value or "").strip().lower()


def _normalize_property_name(value: object) -> str:
    return str(value or "").strip().lower()


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


def _parse_string_list(value: object, *, normalize) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return _dedupe_strings([normalize(item) for item in value if normalize(item)])
    if isinstance(value, tuple):
        return _dedupe_strings([normalize(item) for item in value if normalize(item)])
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
                return _dedupe_strings([normalize(item) for item in parsed if normalize(item)])
        return _dedupe_strings([normalize(part) for part in re.split(r"[\s,]+", text) if normalize(part)])
    normalized = normalize(value)
    return [normalized] if normalized else []


def _parse_object_map_value(value: object, *, value_normalizer) -> dict[str, list[str]]:
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return {}
    if not isinstance(value, dict):
        return {}

    scoped: dict[str, list[str]] = {}
    for raw_object_type, raw_values in value.items():
        object_type = _normalize_object_type(raw_object_type)
        if not object_type:
            continue
        values = _parse_string_list(raw_values, normalize=value_normalizer)
        if values:
            scoped[object_type] = values
    return scoped


def _collect_prefixed_scoped_fields(
    values: dict[str, object],
    *,
    prefixes: tuple[str, ...],
    value_normalizer,
) -> dict[str, list[str]]:
    scoped: dict[str, list[str]] = {}
    for key, raw_value in values.items():
        for prefix in prefixes:
            normalized_prefix = _normalize_key(prefix)
            if not key.startswith(normalized_prefix):
                continue
            object_type = _normalize_object_type(key.removeprefix(normalized_prefix).strip("_"))
            if not object_type:
                continue
            parsed_values = _parse_string_list(raw_value, normalize=value_normalizer)
            if parsed_values:
                scoped[object_type] = parsed_values
    return scoped


def _merge_scoped_maps(*maps: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for current in maps:
        for object_type, values in current.items():
            bucket = merged.setdefault(object_type, [])
            for value in values:
                if value not in bucket:
                    bucket.append(value)
    return merged


def _load_vault_item(item_id: str, vault: str) -> tuple[dict[str, Any] | None, str | None]:
    payload, error = _run_json(["sop", "item", "get", item_id, "--vault", vault, "--format", "json"])
    if error:
        return None, error
    if not isinstance(payload, dict):
        return None, "unexpected item payload"
    return payload, None


def _hubspot_bundle_material(item: dict[str, Any]) -> tuple[bool, list[str]]:
    values = _field_value_map(item)
    missing: list[str] = []

    if not _first_string(
        values,
        ("private_app_token", "access_token", "token", "credential", "secret", "password"),
    ):
        missing.append("private_app_token")

    allowed_object_types = _parse_string_list(
        _first_value(values, ("allowed_object_types", "object_types", "object_type")),
        normalize=_normalize_object_type,
    )
    if not allowed_object_types:
        missing.append("allowed_object_types")

    allowed_properties_by_object = _merge_scoped_maps(
        _parse_object_map_value(
            _first_value(values, ("allowed_properties_by_object",)),
            value_normalizer=_normalize_property_name,
        ),
        _collect_prefixed_scoped_fields(
            values,
            prefixes=("allowed_properties_",),
            value_normalizer=_normalize_property_name,
        ),
    )
    if not allowed_properties_by_object:
        missing.append("allowed_properties_by_object")
    elif allowed_object_types:
        missing_objects = [
            object_type for object_type in allowed_object_types if object_type not in allowed_properties_by_object
        ]
        if missing_objects:
            missing.append("allowed_properties_by_object_for_all_allowed_object_types")

    return not missing, missing


def audit_vault(provider: ProviderConfig, vault: str, max_hits: int) -> dict[str, Any]:
    payload, error = _run_json(["sop", "item", "list", "--vault", vault, "--format", "json"])
    if error:
        return {"ok": False, "error": error, "hits": []}

    hits: list[dict[str, Any]] = []
    bundle_ready_hit_count = 0
    for item in payload or []:
        blob = json.dumps(item).lower()
        if not any(token in blob for token in provider.vault_tokens):
            continue
        item_id = str(item.get("id") or "").strip()
        item_detail = None
        item_error = None
        bundle_material_ready = False
        missing_bundle_fields: list[str] = []
        if item_id:
            item_detail, item_error = _load_vault_item(item_id, vault)
        if item_detail is not None:
            bundle_material_ready, missing_bundle_fields = _hubspot_bundle_material(item_detail)
        if bundle_material_ready:
            bundle_ready_hit_count += 1
        hits.append(
            {
                "id": item_id,
                "title": item.get("title"),
                "category": item.get("category"),
                "urls": item.get("urls") or [],
                "tags": item.get("tags") or [],
                "bundle_material_ready": bundle_material_ready,
                "missing_bundle_fields": missing_bundle_fields,
                "item_error": item_error,
            }
        )
        if len(hits) >= max_hits:
            break

    return {
        "ok": True,
        "hits": hits,
        "hit_count": len(hits),
        "bundle_ready_hit_count": bundle_ready_hit_count,
    }


def audit_browser_history(provider: ProviderConfig, history_db: Path, max_hits: int) -> dict[str, Any]:
    if not history_db.exists():
        return {"ok": False, "error": f"history DB not found at {history_db}", "hits": []}

    with tempfile.TemporaryDirectory(prefix="crm-proof-history-") as tmpdir:
        copy_path = Path(tmpdir) / "History.sqlite"
        shutil.copy2(history_db, copy_path)
        conn = sqlite3.connect(copy_path)
        try:
            where = " OR ".join(["lower(url) LIKE ?", "lower(title) LIKE ?"] * len(provider.browser_like_terms))
            params: list[str] = []
            for term in provider.browser_like_terms:
                like = f"%{term.lower()}%"
                params.extend([like, like])
            rows = conn.execute(
                f"SELECT url, title, last_visit_time FROM urls WHERE {where} ORDER BY last_visit_time DESC LIMIT ?",
                [*params, max_hits],
            ).fetchall()
        finally:
            conn.close()

    hits: list[dict[str, Any]] = []
    hosts: list[str] = []
    workspace_hosts: list[str] = []
    portal_ids: list[str] = []

    for url, title, last_visit_time in rows:
        host = _host_from_url(url or "")
        if host:
            hosts.append(host)
            if host not in provider.generic_public_hosts:
                workspace_hosts.append(host)
        if url:
            portal_ids.extend(
                re.findall(r"(?:loginPortalId|portalId|portal)(?:=|%22:|:)([0-9]{4,})", url, flags=re.I)
            )
        hits.append(
            {
                "url": url,
                "title": title,
                "host": host,
                "last_visit_time": last_visit_time,
            }
        )

    return {
        "ok": True,
        "hits": hits,
        "hit_count": len(hits),
        "hosts": _dedupe_strings(hosts),
        "workspace_hosts": _dedupe_strings(workspace_hosts),
        "portal_ids": _dedupe_strings(portal_ids),
    }


def _extract_sender_instances(provider: ProviderConfig, sender: str) -> list[str]:
    values: list[str] = []
    for pattern in provider.gmail_sender_patterns:
        for match in pattern.finditer(sender):
            value = match.group(1).lower()
            if value not in {provider.name, "www", "app", "support", "service", "operator", "no-reply", "noreply", "notifications", "transactional"}:
                values.append(value)
    return _dedupe_strings(values)


def audit_gmail(provider: ProviderConfig, accounts: list[str], max_hits: int) -> dict[str, Any]:
    account_results: list[dict[str, Any]] = []
    all_hits: list[dict[str, Any]] = []
    instances: list[str] = []
    password_reset_hits: list[dict[str, Any]] = []

    for account in accounts:
        payload, error = _run_json(
            [
                "gog",
                "gmail",
                "messages",
                "search",
                provider.gmail_query,
                "--max",
                str(max_hits),
                "--json",
                "--no-input",
                "--account",
                account,
            ]
        )
        if error:
            account_results.append({"account": account, "ok": False, "error": error, "hits": []})
            continue

        messages = payload.get("messages") or []
        filtered_hits: list[dict[str, Any]] = []
        for message in messages:
            sender = str(message.get("from") or "")
            subject = str(message.get("subject") or "")
            joined = f"{sender} {subject}".lower()
            if provider.name not in joined and "hubspot" not in joined:
                continue
            hit = {
                "account": account,
                "id": message.get("id"),
                "date": message.get("date"),
                "from": sender,
                "subject": subject,
                "labels": message.get("labels") or [],
                "instances": _extract_sender_instances(provider, sender),
                "is_password_reset": subject.strip().lower() == "reset your hubspot password",
            }
            instances.extend(hit["instances"])
            filtered_hits.append(hit)
            all_hits.append(hit)
            if hit["is_password_reset"]:
                password_reset_hits.append(hit)

        account_results.append(
            {
                "account": account,
                "ok": True,
                "hit_count": len(filtered_hits),
                "hits": filtered_hits,
            }
        )

    return {
        "ok": all(result.get("ok") for result in account_results) if account_results else True,
        "accounts": account_results,
        "hit_count": len(all_hits),
        "hits": all_hits,
        "instances": _dedupe_strings(instances),
        "password_reset_hit_count": len(password_reset_hits),
        "password_reset_hits": password_reset_hits,
    }


def audit_hosted_surface(provider: ProviderConfig, api_base: str) -> dict[str, Any]:
    if not provider.hosted_capability_id:
        return {
            "ok": True,
            "supported": False,
            "reason": "provider has no direct hosted CRM rail to audit yet",
        }

    capability_id = provider.hosted_capability_id
    get_status, get_payload, get_error = _fetch_json_url(f"{api_base}/v1/capabilities/{capability_id}")
    resolve_status, resolve_payload, resolve_error = _fetch_json_url(
        f"{api_base}/v1/capabilities/{capability_id}/resolve"
    )
    modes_status, modes_payload, modes_error = _fetch_json_url(
        f"{api_base}/v1/capabilities/{capability_id}/credential-modes"
    )

    resolve_provider = None
    if isinstance(resolve_payload, dict):
        providers = ((resolve_payload.get("data") or {}).get("providers") or [])
        resolve_provider = next(
            (item for item in providers if item.get("service_slug") == provider.name),
            providers[0] if providers else None,
        )

    mode_provider = None
    byok_mode = None
    if isinstance(modes_payload, dict):
        providers = ((modes_payload.get("data") or {}).get("providers") or [])
        mode_provider = next(
            (item for item in providers if item.get("service_slug") == provider.name),
            providers[0] if providers else None,
        )
        modes = ((mode_provider or {}).get("modes") or []) if isinstance(mode_provider, dict) else []
        byok_mode = next((item for item in modes if item.get("mode") == "byok"), None)

    return {
        "ok": all(error is None for error in (get_error, resolve_error, modes_error)),
        "supported": True,
        "capability_id": capability_id,
        "get_status": get_status,
        "resolve_status": resolve_status,
        "credential_modes_status": modes_status,
        "live": get_status == 200 and resolve_status == 200 and modes_status == 200,
        "resolve_configured": bool((resolve_provider or {}).get("configured")),
        "credential_modes_configured": bool((byok_mode or {}).get("configured")) or bool((mode_provider or {}).get("any_configured")),
        "errors": {
            "get": get_error,
            "resolve": resolve_error,
            "credential_modes": modes_error,
        },
    }


def summarize_provider(
    provider: ProviderConfig,
    vault: dict[str, Any],
    browser: dict[str, Any],
    gmail: dict[str, Any],
    hosted_surface: dict[str, Any],
) -> dict[str, Any]:
    vault_hit_count = int(vault.get("hit_count") or 0)
    vault_bundle_ready_hit_count = int(vault.get("bundle_ready_hit_count") or 0)
    browser_workspace_hosts = browser.get("workspace_hosts") or []
    gmail_instances = gmail.get("instances") or []
    password_reset_hit_count = int(gmail.get("password_reset_hit_count") or 0)
    proof_material_ready = vault_bundle_ready_hit_count > 0
    likely_blocked = not proof_material_ready
    hosted_surface_live = bool(hosted_surface.get("live"))
    hosted_configured = bool(
        hosted_surface.get("resolve_configured") or hosted_surface.get("credential_modes_configured")
    )

    if not hosted_surface.get("supported"):
        blocker = "No hosted direct CRM rail is published yet for this provider."
    elif not hosted_surface_live:
        blocker = "Hosted CRM surface is not fully live yet, so deploy truth still needs verification before credentials matter."
    elif likely_blocked and password_reset_hit_count > 0:
        blocker = (
            "Hosted CRM surface is live, and password-reset mail is reaching the known mailbox, but no vault-backed scoped HubSpot bundle was detected yet. "
            "Account recovery path is real; the remaining blocker is converting that access into a bounded private-app token bundle without relying on stale or absent saved credentials."
        )
    elif likely_blocked:
        blocker = (
            "Hosted CRM surface is live, but no vault-backed scoped HubSpot bundle was detected. Browser and Gmail may show account history or recovery paths, "
            "but they do not constitute operator-ready proof material."
        )
    else:
        blocker = "Vault inspection found at least one HubSpot item with the scoped bundle fields required for hosted proof."

    return {
        "provider": provider.name,
        "vault_hit_count": vault_hit_count,
        "vault_bundle_ready_hit_count": vault_bundle_ready_hit_count,
        "browser_workspace_host_count": len(browser_workspace_hosts),
        "browser_workspace_hosts": browser_workspace_hosts,
        "browser_portal_ids": browser.get("portal_ids") or [],
        "gmail_hit_count": int(gmail.get("hit_count") or 0),
        "gmail_candidate_instances": gmail_instances,
        "password_reset_hit_count": password_reset_hit_count,
        "hosted_surface_live": hosted_surface_live,
        "hosted_surface_configured": hosted_configured,
        "proof_material_ready": proof_material_ready,
        "likely_blocked_on_credentials": likely_blocked,
        "assessment": blocker,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit local CRM proof-source signals")
    parser.add_argument("--provider", choices=["hubspot", "all"], default="all")
    parser.add_argument("--vault", default=DEFAULT_VAULT)
    parser.add_argument("--browser-history", type=Path, default=DEFAULT_HISTORY_DB)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--gmail-account", action="append", default=[])
    parser.add_argument("--max-hits", type=int, default=25)
    parser.add_argument("--json-out")
    parser.add_argument("--summary-only", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    providers = [args.provider] if args.provider != "all" else list(PROVIDERS.keys())
    accounts = args.gmail_account or DEFAULT_GMAIL_ACCOUNTS

    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vault": args.vault,
        "browser_history": str(args.browser_history),
        "api_base": args.api_base,
        "gmail_accounts": accounts,
        "providers": {},
        "summary": [],
    }

    for provider_name in providers:
        provider = PROVIDERS[provider_name]
        vault = audit_vault(provider, args.vault, args.max_hits)
        browser = audit_browser_history(provider, args.browser_history, args.max_hits)
        gmail = audit_gmail(provider, accounts, args.max_hits)
        hosted_surface = audit_hosted_surface(provider, args.api_base)
        summary = summarize_provider(provider, vault, browser, gmail, hosted_surface)
        result["providers"][provider_name] = {
            "vault": vault,
            "browser": browser,
            "gmail": gmail,
            "hosted_surface": hosted_surface,
            "summary": summary,
        }
        result["summary"].append(summary)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = Path(args.json_out) if args.json_out else ARTIFACTS_DIR / f"crm-proof-source-audit-{_now_slug()}.json"
    artifact_path.write_text(json.dumps(result, indent=2))

    print(str(artifact_path))
    if args.summary_only:
        for summary in result["summary"]:
            print(
                f"{summary['provider']}: vault_hits={summary['vault_hit_count']} "
                f"bundle_ready={summary['vault_bundle_ready_hit_count']} "
                f"browser_workspace_hosts={summary['browser_workspace_host_count']} "
                f"portal_ids={','.join(summary['browser_portal_ids']) or '-'} "
                f"gmail_hits={summary['gmail_hit_count']} "
                f"reset_hits={summary['password_reset_hit_count']} "
                f"hosted_live={summary['hosted_surface_live']} "
                f"hosted_configured={summary['hosted_surface_configured']} "
                f"proof_ready={summary['proof_material_ready']}"
            )
    else:
        print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
