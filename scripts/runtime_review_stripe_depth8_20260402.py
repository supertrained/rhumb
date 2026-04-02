#!/usr/bin/env python3
"""Stripe current-depth runtime review pass — 2026-04-02.

Mission 1 requires a real capability execute through Rhumb Resolve, not just a raw
proxy pass. This rail uses the existing BYO execute path for Stripe on a safe,
non-mutating wallet balance read.
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
PROVIDER = "stripe"
PUBLIC_SERVICE_SLUG = "stripe"
CAPABILITY_ID = "wallet.get_balance"
METHOD = "GET"
PATH = "/v1/balance"
DIRECT_URL = "https://api.stripe.com/v1/balance"
STRIPE_ENV_VAR = "RHUMB_CREDENTIAL_STRIPE_API_KEY"
STRIPE_1PASSWORD_ITEM = "Stripe Test Secret Key (Rhumb)"


@dataclass
class HttpResult:
    status_code: int
    body: Any


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    timeout: float = 120.0,
) -> HttpResult:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method, url, headers=headers, params=params, json=json_body)
    try:
        body: Any = response.json()
    except Exception:
        body = response.text
    return HttpResult(status_code=response.status_code, body=body)


RUNTIME_BACKED_TRUST_LABELS = {"🟢 Runtime-verified", "🧪 Tester-generated"}


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


def _require_stripe_key() -> tuple[str, str]:
    env_value = os.environ.get(STRIPE_ENV_VAR, "").strip()
    if env_value:
        return env_value, "environment"

    proc = subprocess.run(
        [
            "sop",
            "item",
            "get",
            STRIPE_1PASSWORD_ITEM,
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
        f"Stripe credential unavailable via {STRIPE_ENV_VAR} or 1Password item {STRIPE_1PASSWORD_ITEM!r}"
    )


def _find_currency_row(rows: Any, currency: str = "usd") -> dict[str, Any]:
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("currency") == currency:
                return row
        for row in rows:
            if isinstance(row, dict):
                return row
    return {}


def _pick_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    available = _find_currency_row(payload.get("available"))
    pending = _find_currency_row(payload.get("pending"))
    refund_prefunding = payload.get("refund_and_dispute_prefunding")
    if not isinstance(refund_prefunding, dict):
        refund_prefunding = {}
    refund_available = _find_currency_row(refund_prefunding.get("available"))
    refund_pending = _find_currency_row(refund_prefunding.get("pending"))
    return {
        "object": payload.get("object"),
        "livemode": payload.get("livemode"),
        "available": {
            "currency": available.get("currency"),
            "amount": available.get("amount"),
            "card_amount": ((available.get("source_types") or {}).get("card")) if isinstance(available.get("source_types"), dict) else None,
        },
        "pending": {
            "currency": pending.get("currency"),
            "amount": pending.get("amount"),
            "card_amount": ((pending.get("source_types") or {}).get("card")) if isinstance(pending.get("source_types"), dict) else None,
        },
        "refund_and_dispute_prefunding": {
            "available": {
                "currency": refund_available.get("currency"),
                "amount": refund_available.get("amount"),
            },
            "pending": {
                "currency": refund_pending.get("currency"),
                "amount": refund_pending.get("amount"),
            },
        },
    }


async def main() -> None:
    started_at = datetime.now(tz=UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-stripe-depth8.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-04-02-stripe-depth8.json"
    org_id = f"org_runtime_review_stripe_{stamp.lower()}"

    payload: dict[str, Any] = {
        "provider": PROVIDER,
        "capability_id": CAPABILITY_ID,
        "method": METHOD,
        "path": PATH,
        "review_kind": "current_depth8",
        "organization_id": org_id,
        "artifact_path": str(artifact_path),
    }
    _json_dump(artifact_path, payload)

    stripe_api_key, key_source = _require_stripe_key()
    payload["direct_credential_source"] = key_source
    _json_dump(artifact_path, payload)

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-stripe-{stamp}",
        starter_credits_cents=5000,
    )
    payload["bootstrap"] = bootstrap

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-stripe-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for Stripe depth-8 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", "stripe"],
    )
    payload["review_agent"] = {"agent_id": agent_id, "organization_id": org_id}

    access_id = await store.grant_service_access(agent_id, PROVIDER)
    payload["grant_access"] = {"status": "success", "access_id": access_id}
    _json_dump(artifact_path, payload)

    try:
        counts_before = await _fetch_public_review_stats(PUBLIC_SERVICE_SLUG)
        current_depth = int(counts_before.get("runtime_backed_reviews") or 0)
        target_depth = current_depth + 1

        estimate = await _request_json(
            "GET",
            f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute/estimate",
            headers={"X-Rhumb-Key": api_key},
            params={"provider": PROVIDER, "credential_mode": "byo"},
            timeout=60.0,
        )
        execute = await _request_json(
            "POST",
            f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute",
            headers={"X-Rhumb-Key": api_key},
            json_body={
                "provider": PROVIDER,
                "credential_mode": "byo",
                "method": METHOD,
                "path": PATH,
            },
            timeout=120.0,
        )
        direct = await _request_json(
            "GET",
            DIRECT_URL,
            headers={
                "Authorization": f"Bearer {stripe_api_key}",
                "User-Agent": "rhumb-runtime-review/1.0",
            },
            timeout=120.0,
        )

        execute_payload = ((execute.body or {}).get("data") or {}) if isinstance(execute.body, dict) else {}
        rhumb_upstream = (execute_payload.get("upstream_response") or {}) if isinstance(execute_payload, dict) else {}
        rhumb_fields = _pick_fields(rhumb_upstream if isinstance(rhumb_upstream, dict) else {})
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
            estimate.status_code == 200
            and execute.status_code == 200
            and direct.status_code == 200
            and execute_payload.get("provider_used") == PROVIDER
            and execute_payload.get("upstream_status") == 200
            and comparison["parity"]
        ) else "fail"

        payload.update(
            {
                "observed_at": observed_at,
                "fresh_until": fresh_until,
                "counts_before": counts_before,
                "target_depth": target_depth,
                "estimate": {"status": estimate.status_code, "data": estimate.body},
                "rhumb": {"status": execute.status_code, "data": execute.body},
                "direct": {"status": direct.status_code, "data": direct.body},
                "comparison": comparison,
                "verdict": verdict,
            }
        )
        _json_dump(artifact_path, payload)

        if verdict != "pass":
            raise RuntimeError("Stripe depth-8 runtime pass failed; inspect artifact for parity details")

        execution_id = execute_payload.get("execution_id") or ""
        publication = _run_publish(
            [
                "--service", PROVIDER,
                "--headline", f"Stripe: depth-{target_depth} rerun confirms wallet.get_balance parity through Rhumb Resolve",
                "--summary", f"Fresh depth-{target_depth} runtime rerun passed for Stripe wallet.get_balance through Rhumb Resolve. The execute-route BYO call on GET /v1/balance matched direct Stripe control on balance object, livemode, available funds, pending funds, and refund/dispute prefunding amounts.",
                "--evidence-title", f"Stripe depth-{target_depth} runtime rerun parity check via Rhumb Resolve",
                "--evidence-summary", f"Fresh depth-{target_depth} runtime rerun passed for Stripe wallet.get_balance through Rhumb Resolve. The execute-route BYO call on GET /v1/balance matched direct Stripe control on the normalized balance fields.",
                "--source-ref", f"runtime-review:stripe:{stamp}",
                "--source-batch-id", f"runtime-review:stripe:{stamp}",
                "--reviewed-at", observed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", execution_id,
                "--tag", "runtime_review",
                "--tag", "stripe",
                "--tag", CAPABILITY_ID,
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
