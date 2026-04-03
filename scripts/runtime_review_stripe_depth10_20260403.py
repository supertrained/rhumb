#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
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
SERVICE_SLUG = "stripe"
CAPABILITY_ID = "wallet.get_balance"
METHOD = "GET"
PATH = "/v1/balance"
DIRECT_URL = "https://api.stripe.com/v1/balance"
STRIPE_ENV_VAR = "RHUMB_CREDENTIAL_STRIPE_API_KEY"
STRIPE_1PASSWORD_ITEM = "Stripe Test Secret Key (Rhumb)"
POST_GRANT_PROPAGATION_DELAY_SECONDS = 5
ESTIMATE_AUTH_RETRY_ATTEMPTS = 4
ESTIMATE_AUTH_RETRY_DELAY_SECONDS = 5


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
    short = uuid.uuid4().hex[:8]
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-stripe-depth10.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-04-03-stripe-depth10.json"
    org_id = f"org_runtime_review_stripe_{stamp.lower()}_{short}"

    payload: dict[str, Any] = {
        "provider": SERVICE_SLUG,
        "capability_id": CAPABILITY_ID,
        "method": METHOD,
        "path": PATH,
        "review_kind": "current_depth10",
        "organization_id": org_id,
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "started_at": started_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
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
    payload["wallet_bootstrap"] = bootstrap

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-stripe-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for Stripe depth-10 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", SERVICE_SLUG, "depth10"],
    )
    payload["review_agent"] = {"agent_id": agent_id, "organization_id": org_id}

    access_id = await store.grant_service_access(agent_id, SERVICE_SLUG)
    payload["grant_access"] = {"status": "success", "access_id": access_id}
    payload["post_grant_delay_seconds"] = POST_GRANT_PROPAGATION_DELAY_SECONDS
    _json_dump(artifact_path, payload)

    await asyncio.sleep(POST_GRANT_PROPAGATION_DELAY_SECONDS)

    api_headers = {"X-Rhumb-Key": api_key}

    try:
        counts_before = await _fetch_public_review_stats(SERVICE_SLUG)

        estimate_attempts = 0
        estimate = HttpResult(status_code=0, body=None)
        while estimate_attempts < ESTIMATE_AUTH_RETRY_ATTEMPTS:
            estimate_attempts += 1
            estimate = await _request_json(
                "GET",
                f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute/estimate",
                headers=api_headers,
                params={"provider": SERVICE_SLUG, "credential_mode": "byo"},
                timeout=60.0,
            )
            if not (
                estimate.status_code == 401
                and _looks_like_invalid_key(estimate.body)
                and estimate_attempts < ESTIMATE_AUTH_RETRY_ATTEMPTS
            ):
                break
            await asyncio.sleep(ESTIMATE_AUTH_RETRY_DELAY_SECONDS)

        execute = await _request_json(
            "POST",
            f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute",
            headers=api_headers,
            json_body={
                "provider": SERVICE_SLUG,
                "credential_mode": "byo",
                "method": METHOD,
                "path": PATH,
                "interface": "runtime_review",
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

        rhumb_payload = ((execute.body or {}).get("data") or {}) if isinstance(execute.body, dict) else {}
        rhumb_upstream = (rhumb_payload.get("upstream_response") or {}) if isinstance(rhumb_payload, dict) else {}
        rhumb_fields = _pick_fields(rhumb_upstream if isinstance(rhumb_upstream, dict) else {})
        direct_fields = _pick_fields(direct.body if isinstance(direct.body, dict) else {})
        field_matches = {
            "object_match": rhumb_fields.get("object") == direct_fields.get("object"),
            "livemode_match": rhumb_fields.get("livemode") == direct_fields.get("livemode"),
            "available_match": rhumb_fields.get("available") == direct_fields.get("available"),
            "pending_match": rhumb_fields.get("pending") == direct_fields.get("pending"),
            "refund_prefunding_match": rhumb_fields.get("refund_and_dispute_prefunding") == direct_fields.get("refund_and_dispute_prefunding"),
        }

        observed_at = _iso_now()
        fresh_until = (
            datetime.fromisoformat(observed_at.replace("Z", "+00:00")) + timedelta(days=30)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        comparison = {
            "provider_used": rhumb_payload.get("provider_used"),
            "upstream_status": rhumb_payload.get("upstream_status"),
            "execution_id": rhumb_payload.get("execution_id"),
            "rhumb_fields": rhumb_fields,
            "direct_fields": direct_fields,
            "field_matches": field_matches,
        }

        verdict = "pass" if (
            estimate.status_code == 200
            and execute.status_code == 200
            and direct.status_code == 200
            and rhumb_payload.get("provider_used") == SERVICE_SLUG
            and rhumb_payload.get("upstream_status") == 200
            and all(field_matches.values())
        ) else "fail"

        payload.update(
            {
                "reviewed_at": observed_at,
                "fresh_until": fresh_until,
                "counts_before": counts_before,
                "estimate": {
                    "status_code": estimate.status_code,
                    "body": estimate.body,
                    "attempts": estimate_attempts,
                },
                "rhumb_execute": asdict(execute),
                "direct": asdict(direct),
                "comparison": comparison,
                "verdict": verdict,
            }
        )
        _json_dump(artifact_path, payload)

        if verdict != "pass":
            raise RuntimeError("Stripe depth-10 runtime pass failed; inspect artifact for parity details")

        publication = _run_publish(
            [
                "--service", SERVICE_SLUG,
                "--headline", "Stripe: depth-10 runtime review confirms wallet.get_balance parity through Rhumb Resolve",
                "--summary", "Fresh depth-10 runtime review passed for Stripe wallet.get_balance through Rhumb Resolve. Managed and direct executions matched on balance object, livemode, available funds, pending funds, and refund/dispute prefunding amounts.",
                "--evidence-title", "Stripe depth-10 runtime review parity check via Rhumb Resolve",
                "--evidence-summary", "Fresh depth-10 runtime review passed for Stripe wallet.get_balance through Rhumb Resolve. Managed and direct executions matched on balance object, livemode, available funds, pending funds, and refund/dispute prefunding amounts.",
                "--source-ref", f"runtime-review:stripe:{stamp}",
                "--source-batch-id", f"runtime-review:stripe:{stamp}",
                "--reviewed-at", observed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", rhumb_payload.get("execution_id") or "",
                "--tag", "runtime_review",
                "--tag", SERVICE_SLUG,
                "--tag", CAPABILITY_ID,
                "--tag", "current_pass",
                "--tag", "phase3",
                "--tag", "depth10",
                "--raw-payload-file", str(artifact_path.relative_to(REPO_ROOT)),
            ],
            publication_path,
        )
        payload["publication"] = publication
        payload["counts_after"] = await _fetch_public_review_stats(SERVICE_SLUG)
        _json_dump(artifact_path, payload)
    finally:
        disabled = await store.disable_agent(agent_id)
        payload["disable_agent"] = {
            "status_code": 200 if disabled else 404,
            "body": {"status": "success" if disabled else "not_found", "agent_id": agent_id},
        }
        _json_dump(artifact_path, payload)


if __name__ == "__main__":
    asyncio.run(main())
