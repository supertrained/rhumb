#!/usr/bin/env python3
"""Slack current-depth runtime review pass — 2026-04-03.

Slack remains the sole weakest callable provider in the live public audit at depth 9.
This pass re-verifies the safe, non-mutating auth identity read (`POST /api/auth.test`)
through the Rhumb proxy and compares it directly against Slack.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages/api"))

from db.client import get_supabase_client  # noqa: E402
from schemas.agent_identity import AgentIdentityStore  # noqa: E402
from services.billing_bootstrap import ensure_org_billing_bootstrap  # noqa: E402

BASE_URL = "https://api.rhumb.dev/v1"
PROVIDER = "slack"
PUBLIC_SERVICE_SLUG = "slack"
METHOD = "POST"
PATH = "/api/auth.test"
DIRECT_URL = "https://slack.com/api/auth.test"
SLACK_ENV_VAR = "RHUMB_CREDENTIAL_SLACK_BOT_TOKEN"
SLACK_1PASSWORD_ITEM = "Slack - TeamSuper Bot Token"
POST_GRANT_PROPAGATION_DELAY_SECONDS = 5
EXECUTE_AUTH_RETRY_ATTEMPTS = 4
EXECUTE_AUTH_RETRY_DELAY_SECONDS = 5
RUNTIME_BACKED_TRUST_LABELS = {"🟢 Runtime-verified", "🧪 Tester-generated"}


@dataclass
class HttpResult:
    status_code: int
    body: Any


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _looks_like_invalid_key(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    detail = str(body.get("detail") or "").lower()
    error = str(body.get("error") or "").lower()
    return "invalid or expired rhumb api key" in detail or "invalid or expired rhumb api key" in error


async def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    content: bytes | None = None,
    timeout: float = 120.0,
) -> HttpResult:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            content=content,
        )
    try:
        body: Any = response.json()
    except Exception:
        body = response.text
    return HttpResult(status_code=response.status_code, body=body)


def _extract_review_stats(body: Any) -> dict[str, int | None]:
    reviews = []
    if isinstance(body, dict):
        maybe_reviews = body.get("reviews")
        if isinstance(maybe_reviews, list):
            reviews = maybe_reviews
        else:
            data = body.get("data")
            if isinstance(data, dict) and isinstance(data.get("reviews"), list):
                reviews = data.get("reviews") or []
    runtime_backed = 0
    published = 0
    for review in reviews:
        if not isinstance(review, dict):
            continue
        if review.get("status") == "published" or review.get("review_status") == "published":
            published += 1
        source_type = review.get("source_type") or review.get("sourceType")
        trust_label = review.get("trust_label") or review.get("trustLabel")
        if source_type == "runtime_verified" or trust_label in RUNTIME_BACKED_TRUST_LABELS:
            runtime_backed += 1
    return {
        "published_reviews": published or (len(reviews) if isinstance(reviews, list) else None),
        "runtime_backed_reviews": runtime_backed,
    }


async def _fetch_public_review_stats(service_slug: str) -> dict[str, int | None]:
    result = await _request_json("GET", f"{BASE_URL}/services/{service_slug}/reviews", timeout=60.0)
    if result.status_code != 200:
        return {"published_reviews": None, "runtime_backed_reviews": None}
    return _extract_review_stats(result.body)


def _run_publish(args: list[str], output_path: Path) -> dict[str, Any]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT / "packages/api") + (f":{existing}" if existing else "")
    proc = subprocess.run(
        [str(REPO_ROOT / "packages/api/.venv/bin/python"), str(REPO_ROOT / "scripts/publish_runtime_review_pair.py"), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"publish_runtime_review_pair.py failed ({proc.returncode})\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    payload = json.loads(proc.stdout)
    _json_dump(output_path, payload)
    return payload


def _require_slack_token() -> tuple[str, str]:
    env_value = os.environ.get(SLACK_ENV_VAR, "").strip()
    if env_value:
        return env_value, "environment"

    proc = subprocess.run(
        [
            "sop",
            "item",
            "get",
            SLACK_1PASSWORD_ITEM,
            "--vault",
            "OpenClaw Agents",
            "--fields",
            "credential",
            "--reveal",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip(), "1password"

    raise RuntimeError(
        f"Slack credential unavailable via {SLACK_ENV_VAR} or 1Password item {SLACK_1PASSWORD_ITEM!r}"
    )


def _pick_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "ok": payload.get("ok"),
        "url": payload.get("url"),
        "team": payload.get("team"),
        "team_id": payload.get("team_id"),
        "user": payload.get("user"),
        "user_id": payload.get("user_id"),
        "bot_id": payload.get("bot_id"),
        "is_enterprise_install": payload.get("is_enterprise_install"),
    }


async def main() -> None:
    started_at = datetime.now(tz=UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-slack-depth10.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-04-03-slack-depth10.json"
    org_id = f"org_runtime_review_slack_{stamp.lower()}"

    payload: dict[str, Any] = {
        "provider": PROVIDER,
        "method": METHOD,
        "path": PATH,
        "review_kind": "current_depth10",
        "organization_id": org_id,
        "artifact_path": str(artifact_path),
    }
    _json_dump(artifact_path, payload)

    slack_token, token_source = _require_slack_token()
    payload["direct_credential_source"] = token_source
    _json_dump(artifact_path, payload)

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-slack-{stamp}",
        starter_credits_cents=5000,
    )
    payload["bootstrap"] = bootstrap

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-slack-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for Slack depth-10 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", "slack"],
    )
    payload["review_agent"] = {"agent_id": agent_id, "organization_id": org_id}

    access_id = await store.grant_service_access(agent_id, PROVIDER)
    payload["grant_access"] = {"status": "success", "access_id": access_id}
    payload["post_grant_delay_seconds"] = POST_GRANT_PROPAGATION_DELAY_SECONDS
    _json_dump(artifact_path, payload)

    await asyncio.sleep(POST_GRANT_PROPAGATION_DELAY_SECONDS)

    try:
        counts_before = await _fetch_public_review_stats(PUBLIC_SERVICE_SLUG)
        current_depth = int(counts_before.get("runtime_backed_reviews") or 0)
        target_depth = current_depth + 1

        execute_attempts = 0
        execute = HttpResult(status_code=0, body=None)
        while execute_attempts < EXECUTE_AUTH_RETRY_ATTEMPTS:
            execute_attempts += 1
            execute = await _request_json(
                "POST",
                f"{BASE_URL}/proxy/",
                headers={"X-Rhumb-Key": api_key},
                json_body={
                    "service": PROVIDER,
                    "method": METHOD,
                    "path": PATH,
                },
                timeout=120.0,
            )
            if not (
                execute.status_code == 401
                and _looks_like_invalid_key(execute.body)
                and execute_attempts < EXECUTE_AUTH_RETRY_ATTEMPTS
            ):
                break
            await asyncio.sleep(EXECUTE_AUTH_RETRY_DELAY_SECONDS)

        direct = await _request_json(
            "POST",
            DIRECT_URL,
            headers={
                "Authorization": f"Bearer {slack_token}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "rhumb-runtime-review/1.0",
            },
            content=b"",
            timeout=60.0,
        )

        execute_payload = execute.body if isinstance(execute.body, dict) else {}
        rhumb_body = execute_payload.get("body") if isinstance(execute_payload.get("body"), dict) else {}
        rhumb_fields = _pick_fields(rhumb_body)
        direct_fields = _pick_fields(direct.body if isinstance(direct.body, dict) else {})

        observed_at = _iso_now()
        reviewed_at_dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        fresh_until = (reviewed_at_dt + timedelta(days=30)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        comparison = {
            "rhumb_fields": rhumb_fields,
            "direct_fields": direct_fields,
            "parity": rhumb_fields == direct_fields,
        }

        verdict = "pass" if (
            execute.status_code == 200
            and direct.status_code == 200
            and comparison["parity"]
        ) else "fail"

        payload.update(
            {
                "observed_at": observed_at,
                "fresh_until": fresh_until,
                "counts_before": counts_before,
                "target_depth": target_depth,
                "execute_attempts": execute_attempts,
                "rhumb": {"status": execute.status_code, "data": execute.body},
                "direct": {"status": direct.status_code, "data": direct.body},
                "comparison": comparison,
                "verdict": verdict,
            }
        )
        _json_dump(artifact_path, payload)

        if verdict != "pass":
            raise RuntimeError("Slack depth-10 runtime pass failed; inspect artifact for parity details")

        execution_id = execute_payload.get("execution_id") or ""
        publication = _run_publish(
            [
                "--service", PROVIDER,
                "--headline", f"Slack: depth-{target_depth} rerun confirms auth.test parity through Rhumb Resolve",
                "--summary", f"Fresh depth-{target_depth} runtime rerun passed for Slack auth.test through Rhumb Resolve. The safe proxy auth identity read matched direct Slack control on workspace URL/name, workspace id, bot user identity, bot id, and enterprise-install flag.",
                "--evidence-title", f"Slack depth-{target_depth} runtime rerun parity check via Rhumb Resolve",
                "--evidence-summary", f"Fresh depth-{target_depth} runtime rerun passed for Slack auth.test through Rhumb Resolve. The safe proxy auth identity read matched direct Slack control on normalized workspace and bot identity fields.",
                "--source-ref", f"runtime-review:slack:{stamp}",
                "--source-batch-id", f"runtime-review:slack:{stamp}",
                "--reviewed-at", observed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", execution_id,
                "--tag", "runtime_review",
                "--tag", "slack",
                "--tag", "auth.test",
                "--tag", "current_pass",
                "--tag", "phase3",
                "--raw-payload-file", str(artifact_path.relative_to(REPO_ROOT)),
            ],
            publication_path,
        )
        payload["published"] = {
            "service_slug": PROVIDER,
            "evidence_id": (publication.get("evidence") or {}).get("id"),
            "review_id": (publication.get("review") or {}).get("id"),
            "execution_id": execution_id,
        }
        payload["counts_after"] = await _fetch_public_review_stats(PUBLIC_SERVICE_SLUG)
        _json_dump(artifact_path, payload)
    finally:
        disabled = await store.disable_agent(agent_id)
        payload["agent_disabled"] = bool(disabled)
        _json_dump(artifact_path, payload)


if __name__ == "__main__":
    asyncio.run(main())
