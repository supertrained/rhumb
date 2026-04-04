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
EXA_URL = "https://api.exa.ai/search"
SERVICE_SLUG = "exa"
CAPABILITY_ID = "search.query"
QUERY = "best AI agent observability tools"
NUM_RESULTS = 3
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


def _get_secret(item_title: str) -> str:
    result = subprocess.run(
        [
            "sop",
            "item",
            "get",
            item_title,
            "--vault",
            "OpenClaw Agents",
            "--fields",
            "credential",
            "--reveal",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"Unable to load secret: {item_title}\n{result.stderr}")
    return result.stdout.strip()


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
        if source_type == "runtime_verified" or trust_label in {"🟢 Runtime-verified", "🧪 Tester-generated"}:
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


async def main() -> None:
    started_at = datetime.now(tz=UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-exa-depth11.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-04-03-exa-depth11.json"
    org_id = f"org_runtime_review_exa_{stamp.lower()}_{short}"

    payload: dict[str, Any] = {
        "provider": SERVICE_SLUG,
        "capability_id": CAPABILITY_ID,
        "query": QUERY,
        "num_results": NUM_RESULTS,
        "review_kind": "current_depth11",
        "organization_id": org_id,
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "started_at": started_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "post_grant_delay_seconds": POST_GRANT_PROPAGATION_DELAY_SECONDS,
    }
    _json_dump(artifact_path, payload)

    exa_api_key = os.environ.get("RHUMB_CREDENTIAL_EXA_API_KEY") or _get_secret("Exa API Key")

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-exa-{stamp}",
        starter_credits_cents=5000,
    )
    payload["wallet_bootstrap"] = bootstrap
    _json_dump(artifact_path, payload)

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-exa-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for Exa depth-11 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", "exa", "depth11"],
    )
    payload["review_agent"] = {"agent_id": agent_id, "organization_id": org_id}

    access_id = await store.grant_service_access(agent_id, SERVICE_SLUG)
    payload["grant_access"] = {"status": "success", "access_id": access_id}
    _json_dump(artifact_path, payload)

    await asyncio.sleep(POST_GRANT_PROPAGATION_DELAY_SECONDS)

    api_headers = {"X-Rhumb-Key": api_key}
    direct_headers = {
        "x-api-key": exa_api_key,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; RhumbRuntimeReview/1.0)",
    }
    direct_body = {
        "query": QUERY,
        "numResults": NUM_RESULTS,
    }

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
                params={"provider": SERVICE_SLUG, "credential_mode": "rhumb_managed"},
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
            params={"provider": SERVICE_SLUG, "credential_mode": "rhumb_managed"},
            json_body={
                "query": QUERY,
                "numResults": NUM_RESULTS,
            },
            timeout=120.0,
        )
        direct = await _request_json(
            "POST",
            EXA_URL,
            headers=direct_headers,
            json_body=direct_body,
            timeout=120.0,
        )

        rhumb_payload = ((execute.body or {}).get("data") or {}) if isinstance(execute.body, dict) else {}
        rhumb_upstream = (rhumb_payload.get("upstream_response") or {}) if isinstance(rhumb_payload, dict) else {}
        rhumb_results = rhumb_upstream.get("results") if isinstance(rhumb_upstream, dict) else []
        direct_results = direct.body.get("results") if isinstance(direct.body, dict) else []
        rhumb_top = rhumb_results[0] if isinstance(rhumb_results, list) and rhumb_results else None
        direct_top = direct_results[0] if isinstance(direct_results, list) and direct_results else None
        rhumb_top3_urls = [row.get("url") for row in rhumb_results[:3] if isinstance(row, dict)] if isinstance(rhumb_results, list) else []
        direct_top3_urls = [row.get("url") for row in direct_results[:3] if isinstance(row, dict)] if isinstance(direct_results, list) else []
        observed_at = _iso_now()
        reviewed_at_dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        fresh_until = (reviewed_at_dt + timedelta(days=30)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        comparison = {
            "provider_used": rhumb_payload.get("provider_used"),
            "upstream_status": rhumb_payload.get("upstream_status"),
            "execution_id": rhumb_payload.get("execution_id"),
            "rhumb_count": len(rhumb_results) if isinstance(rhumb_results, list) else None,
            "direct_count": len(direct_results) if isinstance(direct_results, list) else None,
            "rhumb_top": {
                "title": (rhumb_top or {}).get("title"),
                "url": (rhumb_top or {}).get("url"),
            },
            "direct_top": {
                "title": (direct_top or {}).get("title"),
                "url": (direct_top or {}).get("url"),
            },
            "rhumb_top3_urls": rhumb_top3_urls,
            "direct_top3_urls": direct_top3_urls,
            "result_count_match": isinstance(rhumb_results, list) and isinstance(direct_results, list) and len(rhumb_results) == len(direct_results),
            "top_title_match": (rhumb_top or {}).get("title") == (direct_top or {}).get("title"),
            "top_url_match": (rhumb_top or {}).get("url") == (direct_top or {}).get("url"),
            "top3_urls_match": rhumb_top3_urls == direct_top3_urls,
        }

        verdict = "pass" if (
            estimate.status_code == 200
            and execute.status_code == 200
            and direct.status_code == 200
            and rhumb_payload.get("provider_used") == SERVICE_SLUG
            and rhumb_payload.get("upstream_status") == 200
            and comparison["result_count_match"]
            and comparison["top_title_match"]
            and comparison["top_url_match"]
            and comparison["top3_urls_match"]
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
            raise RuntimeError("Exa depth-11 runtime pass failed; inspect artifact for parity details")

        publication = _run_publish(
            [
                "--service", SERVICE_SLUG,
                "--headline", "Exa: depth-11 runtime review confirms search.query parity through Rhumb Resolve",
                "--summary", "Fresh depth-11 runtime review passed for Exa search.query through Rhumb Resolve. Managed and direct executions matched on result count, top title, top URL, and top-3 URL ordering for the same live search query.",
                "--evidence-title", "Exa depth-11 runtime review parity check via Rhumb Resolve",
                "--evidence-summary", "Fresh depth-11 runtime review passed for Exa search.query through Rhumb Resolve. Managed and direct executions matched on result count, top title, top URL, and top-3 URL ordering for the same live search query.",
                "--source-ref", f"runtime-review:exa:{stamp}",
                "--source-batch-id", f"runtime-review:exa:{stamp}",
                "--reviewed-at", observed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", rhumb_payload.get("execution_id") or "",
                "--tag", "runtime_review",
                "--tag", "exa",
                "--tag", CAPABILITY_ID,
                "--tag", "current_pass",
                "--tag", "phase3",
                "--tag", "depth11",
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
