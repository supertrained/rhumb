#!/usr/bin/env python3
"""Audit local proof-source signals for support rails like Zendesk and Intercom.

This is an operator helper for AUD-18. It turns the repeated manual discovery pass into
an evidence-backed artifact by scanning:
- 1Password item metadata via `sop`
- the rhumb browser profile History DB
- Gmail metadata via `gog`

It is intentionally conservative: mailbox/browser traces can suggest provider usage or
candidate workspace instances, but only vault-backed credential material should be
considered proof-material-ready.
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
    "zendesk": ProviderConfig(
        name="zendesk",
        vault_tokens=("zendesk", "helpdesk", "support", "ticket"),
        gmail_query='zendesk.com OR from:(no-reply@zendesk.com) OR from:(support@zendesk.com) OR subject:("welcome to zendesk")',
        gmail_sender_patterns=(
            re.compile(r"@([a-z0-9-]+)\.zendesk\.com", re.I),
            re.compile(r"([a-z0-9-]+)\.zendesk\.com", re.I),
        ),
        browser_like_terms=("zendesk",),
        generic_public_hosts=("www.zendesk.com", "zendesk.com"),
        hosted_capability_id="ticket.search",
    ),
    "intercom": ProviderConfig(
        name="intercom",
        vault_tokens=("intercom", "customer support", "support"),
        gmail_query='intercom-mail.com OR intercom.com OR from:(intercom-mail.com)',
        gmail_sender_patterns=(
            re.compile(r"@([a-z0-9-]+)\.intercom-mail\.com", re.I),
            re.compile(r"([a-z0-9-]+)\.intercom-mail\.com", re.I),
            re.compile(r"@([a-z0-9-]+)\.intercom\.com", re.I),
        ),
        browser_like_terms=("intercom",),
        generic_public_hosts=("app.intercom.com", "www.intercom.com", "intercom.com"),
        hosted_capability_id="conversation.list",
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


def _extract_data(payload: dict[str, Any] | None) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def _resolve_handoff(payload: Any) -> dict[str, Any] | None:
    data = _extract_data(payload)
    if not isinstance(data, dict):
        return None
    recovery_hint = data.get("recovery_hint")
    raw_recovery = recovery_hint if isinstance(recovery_hint, dict) else {}
    candidates = (
        ("execute_hint", data.get("execute_hint")),
        ("alternate_execute_hint", raw_recovery.get("alternate_execute_hint")),
        ("setup_handoff", raw_recovery.get("setup_handoff")),
    )
    for source, candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        handoff = {
            "source": source,
            "reason": raw_recovery.get("reason") if isinstance(raw_recovery.get("reason"), str) else None,
            "resolve_url": raw_recovery.get("resolve_url") if isinstance(raw_recovery.get("resolve_url"), str) else None,
            "preferred_provider": candidate.get("preferred_provider") if isinstance(candidate.get("preferred_provider"), str) else None,
            "preferred_credential_mode": (
                candidate.get("preferred_credential_mode")
                if isinstance(candidate.get("preferred_credential_mode"), str)
                else None
            ),
            "selection_reason": candidate.get("selection_reason") if isinstance(candidate.get("selection_reason"), str) else None,
            "setup_hint": candidate.get("setup_hint") if isinstance(candidate.get("setup_hint"), str) else None,
            "setup_url": candidate.get("setup_url") if isinstance(candidate.get("setup_url"), str) else None,
            "credential_modes_url": (
                candidate.get("credential_modes_url")
                if isinstance(candidate.get("credential_modes_url"), str)
                else raw_recovery.get("credential_modes_url")
                if isinstance(raw_recovery.get("credential_modes_url"), str)
                else None
            ),
            "endpoint_pattern": candidate.get("endpoint_pattern") if isinstance(candidate.get("endpoint_pattern"), str) else None,
            "configured": candidate.get("configured") if isinstance(candidate.get("configured"), bool) else None,
        }
        return {key: value for key, value in handoff.items() if value is not None}
    return None


def _resolve_handoff_summary(handoff: dict[str, Any] | None) -> str | None:
    if not isinstance(handoff, dict) or not handoff:
        return None
    parts: list[str] = []
    if isinstance(handoff.get("source"), str):
        parts.append(f"source={handoff['source']}")
    if isinstance(handoff.get("preferred_provider"), str):
        parts.append(f"provider={handoff['preferred_provider']}")
    if isinstance(handoff.get("preferred_credential_mode"), str):
        parts.append(f"mode={handoff['preferred_credential_mode']}")
    if isinstance(handoff.get("endpoint_pattern"), str):
        parts.append(f"endpoint={handoff['endpoint_pattern']}")
    next_url = handoff.get("setup_url") or handoff.get("resolve_url") or handoff.get("credential_modes_url")
    if isinstance(next_url, str):
        parts.append(f"next_url={next_url}")
    if not parts:
        return None
    return "Resolve next step: " + ", ".join(parts)


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
    parsed: list[int] = []
    for part in parts:
        if not part:
            continue
        try:
            parsed.append(int(part))
        except ValueError:
            continue
    return parsed


def _load_vault_item(item_id: str, vault: str) -> tuple[dict[str, Any] | None, str | None]:
    payload, error = _run_json(["sop", "item", "get", item_id, "--vault", vault, "--format", "json"])
    if error:
        return None, error
    if not isinstance(payload, dict):
        return None, "unexpected item payload"
    return payload, None


def _intercom_bundle_material(item: dict[str, Any]) -> tuple[bool, list[str]]:
    values = _field_value_map(item)
    missing: list[str] = []
    if not _first_string(values, ("region", "workspace_region", "intercom_region")):
        missing.append("region")
    if not _first_string(
        values,
        ("bearer_token", "access_token", "token", "credential", "secret", "password"),
    ):
        missing.append("bearer_token")
    team_ids = _parse_id_value(
        _first_value(values, ("allowed_team_ids", "allowed_team_id", "team_ids", "team_id"))
    )
    admin_ids = _parse_id_value(
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
    if not team_ids and not admin_ids:
        missing.append("allowed_team_ids_or_allowed_admin_ids")
    return not missing, missing


def _zendesk_bundle_material(item: dict[str, Any]) -> tuple[bool, list[str]]:
    values = _field_value_map(item)
    missing: list[str] = []
    if not _first_string(values, ("subdomain", "zendesk_subdomain", "workspace_subdomain", "zendesk_workspace")):
        missing.append("subdomain")
    if not _first_string(values, ("email", "username", "login", "account_email")):
        missing.append("email")
    if not _first_string(
        values,
        ("api_token", "api_key", "password", "bearer_token", "access_token", "credential", "token", "secret"),
    ):
        missing.append("api_token_or_bearer_token")
    group_ids = _parse_id_value(
        _first_value(values, ("allowed_group_ids", "allowed_group_id", "group_ids", "group_id"))
    )
    brand_ids = _parse_id_value(
        _first_value(values, ("allowed_brand_ids", "allowed_brand_id", "brand_ids", "brand_id"))
    )
    if not group_ids and not brand_ids:
        missing.append("allowed_group_ids_or_allowed_brand_ids")
    return not missing, missing


def _bundle_material_status(provider: ProviderConfig, item: dict[str, Any]) -> tuple[bool, list[str]]:
    if provider.name == "intercom":
        return _intercom_bundle_material(item)
    if provider.name == "zendesk":
        return _zendesk_bundle_material(item)
    return False, ["unsupported_provider"]


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
            bundle_material_ready, missing_bundle_fields = _bundle_material_status(provider, item_detail)
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

    with tempfile.TemporaryDirectory(prefix="support-proof-history-") as tmpdir:
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
    for url, title, last_visit_time in rows:
        host = _host_from_url(url or "")
        if host:
            hosts.append(host)
            if host not in provider.generic_public_hosts:
                workspace_hosts.append(host)
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
    }


def _extract_sender_instances(provider: ProviderConfig, sender: str) -> list[str]:
    values: list[str] = []
    for pattern in provider.gmail_sender_patterns:
        for match in pattern.finditer(sender):
            value = match.group(1).lower()
            if value not in {provider.name, "www", "app", "support", "service", "operator", "no-reply"}:
                values.append(value)
    return _dedupe_strings(values)


def audit_gmail(provider: ProviderConfig, accounts: list[str], max_hits: int) -> dict[str, Any]:
    account_results: list[dict[str, Any]] = []
    all_hits: list[dict[str, Any]] = []
    instances: list[str] = []

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
            sender_match = any(token in joined for token in provider.browser_like_terms)
            if provider.name == "intercom":
                sender_match = sender_match or "intercom-mail.com" in joined
            if not sender_match:
                continue
            hit = {
                "account": account,
                "id": message.get("id"),
                "date": message.get("date"),
                "from": sender,
                "subject": subject,
                "labels": message.get("labels") or [],
                "instances": _extract_sender_instances(provider, sender),
            }
            instances.extend(hit["instances"])
            filtered_hits.append(hit)
            all_hits.append(hit)
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
    }


def audit_hosted_surface(provider: ProviderConfig, api_base: str) -> dict[str, Any]:
    if not provider.hosted_capability_id:
        return {
            "ok": True,
            "supported": False,
            "reason": "provider has no direct hosted support rail to audit yet",
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
    resolve_provider_present = False
    if isinstance(resolve_payload, dict):
        providers = ((resolve_payload.get("data") or {}).get("providers") or [])
        resolve_provider = next(
            (item for item in providers if item.get("service_slug") == provider.name),
            None,
        )
        resolve_provider_present = isinstance(resolve_provider, dict)
    resolve_handoff = _resolve_handoff(resolve_payload)

    mode_provider = None
    credential_modes_provider_present = False
    if isinstance(modes_payload, dict):
        providers = ((modes_payload.get("data") or {}).get("providers") or [])
        mode_provider = next(
            (item for item in providers if item.get("service_slug") == provider.name),
            None,
        )
        credential_modes_provider_present = isinstance(mode_provider, dict)

    return {
        "ok": all(error is None for error in (get_error, resolve_error, modes_error)),
        "supported": True,
        "capability_id": capability_id,
        "get_status": get_status,
        "resolve_status": resolve_status,
        "credential_modes_status": modes_status,
        "live": (
            get_status == 200
            and resolve_status == 200
            and modes_status == 200
            and resolve_provider_present
            and credential_modes_provider_present
        ),
        "resolve_provider_present": resolve_provider_present,
        "credential_modes_provider_present": credential_modes_provider_present,
        "resolve_configured": bool((resolve_provider or {}).get("configured")),
        "credential_modes_configured": bool((mode_provider or {}).get("any_configured")),
        "resolve_handoff": resolve_handoff,
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
    proof_material_ready = vault_bundle_ready_hit_count > 0
    likely_blocked = not proof_material_ready
    hosted_surface_live = bool(hosted_surface.get("live"))
    hosted_configured = bool(
        hosted_surface.get("resolve_configured") or hosted_surface.get("credential_modes_configured")
    )
    resolve_handoff = hosted_surface.get("resolve_handoff")
    resolve_step = _resolve_handoff_summary(resolve_handoff)

    if not hosted_surface.get("supported"):
        blocker = "No hosted direct support rail is published yet for this provider."
    elif not hosted_surface_live:
        blocker = "Hosted support surface is not fully live yet, so deploy truth still needs verification before credentials matter."
    elif likely_blocked:
        if vault_hit_count > 0:
            blocker = (
                "Hosted support surface is live, and candidate vault items now exist, but none currently contain the scoped credential-bundle fields required for hosted proof. "
                "Browser and Gmail may show provider traces or third-party instances, but they do not constitute operator-ready proof material."
            )
        else:
            blocker = (
                "Hosted support surface is live, but no vault-backed support credential bundle was detected. Browser and Gmail may show provider traces or third-party instances, "
                "but they do not constitute operator-ready proof material."
            )
    else:
        blocker = "Vault inspection found at least one support item with the scoped bundle fields required for hosted proof."
    if resolve_step and (likely_blocked or not hosted_surface_live or not hosted_configured):
        blocker += f" {resolve_step}."

    return {
        "provider": provider.name,
        "vault_hit_count": vault_hit_count,
        "vault_bundle_ready_hit_count": vault_bundle_ready_hit_count,
        "browser_workspace_host_count": len(browser_workspace_hosts),
        "browser_workspace_hosts": browser_workspace_hosts,
        "gmail_hit_count": int(gmail.get("hit_count") or 0),
        "gmail_candidate_instances": gmail_instances,
        "hosted_surface_live": hosted_surface_live,
        "hosted_surface_configured": hosted_configured,
        "resolve_handoff": resolve_handoff,
        "resolve_step": resolve_step,
        "resolve_handoff_summary": resolve_step,
        "proof_material_ready": proof_material_ready,
        "likely_blocked_on_credentials": likely_blocked,
        "assessment": blocker,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit local support proof-source signals")
    parser.add_argument("--provider", choices=["zendesk", "intercom", "all"], default="all")
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
    artifact_path = Path(args.json_out) if args.json_out else ARTIFACTS_DIR / f"support-proof-source-audit-{_now_slug()}.json"
    artifact_path.write_text(json.dumps(result, indent=2))

    print(str(artifact_path))
    if args.summary_only:
        for summary in result["summary"]:
            print(
                f"{summary['provider']}: vault_hits={summary['vault_hit_count']} "
                f"browser_workspace_hosts={summary['browser_workspace_host_count']} "
                f"gmail_hits={summary['gmail_hit_count']} "
                f"gmail_instances={','.join(summary['gmail_candidate_instances']) or '-'} "
                f"hosted_live={summary['hosted_surface_live']} "
                f"hosted_configured={summary['hosted_surface_configured']} "
                f"resolve_step={summary['resolve_step'] or '-'} "
                f"proof_ready={summary['proof_material_ready']}"
            )
    else:
        print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
