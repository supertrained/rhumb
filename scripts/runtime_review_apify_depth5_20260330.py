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
APIFY_RUN_URL = "https://api.apify.com/v2/acts/apify~website-content-crawler/runs"
TARGET_URL = "https://example.com"
CRAWL_INPUT = {
    "startUrls": [{"url": TARGET_URL}],
    "maxCrawlDepth": 0,
    "maxCrawlPages": 1,
}


@dataclass
class HttpResult:
    status_code: int
    body: Any


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
        response = await client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
        )
    try:
        body: Any = response.json()
    except Exception:
        body = response.text
    return HttpResult(status_code=response.status_code, body=body)


async def _fetch_apify_dataset_item(api_token: str, dataset_id: str) -> HttpResult:
    return await _request_json(
        "GET",
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        headers={"Authorization": f"Bearer {api_token}"},
        params={"clean": "true", "limit": 1},
        timeout=120.0,
    )


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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
        if source_type == "runtime_verified" or trust_label == "🟢 Runtime-verified":
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
    run_id = f"runtime-review-{stamp}-{short}"
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-apify-current-depth5.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-03-30-apify-depth5.json"
    org_id = f"org_runtime_review_apify_{stamp.lower()}_{short}"

    payload: dict[str, Any] = {
        "run_started_at": started_at.isoformat(),
        "run_id": run_id,
        "organization_id": org_id,
        "target_url": TARGET_URL,
        "crawl_input": CRAWL_INPUT,
    }

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-apify-{stamp}",
        starter_credits_cents=5000,
    )
    payload["wallet_bootstrap"] = bootstrap

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-apify-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for Apify depth-5 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", "apify"],
    )
    payload["review_agent"] = {
        "agent_id": agent_id,
        "organization_id": org_id,
    }

    access_id = await store.grant_service_access(agent_id, "apify")
    payload["grant_result"] = {
        "service": "apify",
        "status_code": 200,
        "body": {"status": "success", "access_id": access_id},
    }
    _json_dump(artifact_path, payload)

    api_headers = {"X-Rhumb-Key": api_key}
    apify_token = os.environ["RHUMB_CREDENTIAL_APIFY_API_TOKEN"]

    try:
        counts_before = await _fetch_public_review_stats("apify")
        estimate = await _request_json(
            "GET",
            f"{BASE_URL}/capabilities/scrape.extract/execute/estimate",
            headers=api_headers,
            params={"provider": "apify", "credential_mode": "rhumb_managed"},
            timeout=60.0,
        )
        execute = await _request_json(
            "POST",
            f"{BASE_URL}/capabilities/scrape.extract/execute",
            headers=api_headers,
            params={"provider": "apify", "credential_mode": "rhumb_managed"},
            json_body=CRAWL_INPUT,
            timeout=180.0,
        )
        direct = await _request_json(
            "POST",
            APIFY_RUN_URL,
            headers={"Authorization": f"Bearer {apify_token}"},
            params={"waitForFinish": 60},
            json_body=CRAWL_INPUT,
            timeout=180.0,
        )

        rhumb_run = (((execute.body or {}).get("data") or {}).get("upstream_response") or {}).get("data") if isinstance(execute.body, dict) else None
        direct_run = ((direct.body or {}).get("data")) if isinstance(direct.body, dict) else None
        rhumb_dataset_id = (rhumb_run or {}).get("defaultDatasetId")
        direct_dataset_id = (direct_run or {}).get("defaultDatasetId")

        rhumb_dataset = await _fetch_apify_dataset_item(apify_token, rhumb_dataset_id) if rhumb_dataset_id else HttpResult(status_code=0, body=None)
        direct_dataset = await _fetch_apify_dataset_item(apify_token, direct_dataset_id) if direct_dataset_id else HttpResult(status_code=0, body=None)

        rhumb_sample = rhumb_dataset.body[0] if rhumb_dataset.status_code == 200 and isinstance(rhumb_dataset.body, list) and rhumb_dataset.body else None
        direct_sample = direct_dataset.body[0] if direct_dataset.status_code == 200 and isinstance(direct_dataset.body, list) and direct_dataset.body else None

        sampled_fields = {
            "url": ((rhumb_sample or {}).get("url"), (direct_sample or {}).get("url")),
            "metadata.title": (((rhumb_sample or {}).get("metadata") or {}).get("title"), ((direct_sample or {}).get("metadata") or {}).get("title")),
            "markdown": ((rhumb_sample or {}).get("markdown"), (direct_sample or {}).get("markdown")),
        }
        checks = {field: left == right for field, (left, right) in sampled_fields.items()}
        observed_at = _iso_now()
        execution_id = (((execute.body or {}).get("data") or {}).get("execution_id")) if isinstance(execute.body, dict) else None
        upstream_status = (((execute.body or {}).get("data") or {}).get("upstream_status")) if isinstance(execute.body, dict) else None

        verdict = "pass" if (
            estimate.status_code == 200
            and execute.status_code == 200
            and direct.status_code == 201
            and rhumb_dataset.status_code == 200
            and direct_dataset.status_code == 200
            and all(checks.values())
        ) else "fail"

        payload["apify_depth5_pass"] = {
            "service_slug": "apify",
            "provider": "apify",
            "capability_id": "scrape.extract",
            "counts_before": counts_before,
            "estimate": asdict(estimate),
            "rhumb_execute": asdict(execute),
            "direct_control": asdict(direct),
            "rhumb_dataset": asdict(rhumb_dataset),
            "direct_dataset": asdict(direct_dataset),
            "rhumb_extracted": {
                "run_id": (rhumb_run or {}).get("id"),
                "dataset_id": rhumb_dataset_id,
                "sample": rhumb_sample,
            },
            "direct_extracted": {
                "run_id": (direct_run or {}).get("id"),
                "dataset_id": direct_dataset_id,
                "sample": direct_sample,
            },
            "parity": {
                "sampled_fields": list(sampled_fields.keys()),
                "rhumb_sample": {
                    "url": (rhumb_sample or {}).get("url"),
                    "metadata": {"title": ((rhumb_sample or {}).get("metadata") or {}).get("title")},
                    "markdown": (rhumb_sample or {}).get("markdown"),
                },
                "direct_sample": {
                    "url": (direct_sample or {}).get("url"),
                    "metadata": {"title": ((direct_sample or {}).get("metadata") or {}).get("title")},
                    "markdown": (direct_sample or {}).get("markdown"),
                },
                "checks": checks,
                "all_matched": all(checks.values()),
                "execution_id": execution_id,
                "provider_used": (((execute.body or {}).get("data") or {}).get("provider_used")) if isinstance(execute.body, dict) else None,
                "upstream_status": upstream_status,
            },
            "observed_at": observed_at,
            "verdict": verdict,
        }
        _json_dump(artifact_path, payload)

        if verdict != "pass":
            raise RuntimeError("Apify depth-5 runtime pass failed; inspect artifact for execute vs direct-control details")

        reviewed_at = observed_at
        fresh_until = (
            datetime.fromisoformat(reviewed_at.replace("Z", "+00:00")) + timedelta(days=30)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        publication = _run_publish(
            [
                "--service", "apify",
                "--headline", "Apify: current-depth rerun confirms scrape.extract parity through Rhumb Resolve again",
                "--summary", "Fresh current-depth runtime rerun passed for Apify scrape.extract through Rhumb Resolve. Managed and direct executions matched exactly on URL, metadata.title, and markdown output for the same one-page website-content-crawler target.",
                "--evidence-title", "Apify current-depth runtime rerun parity check via Rhumb Resolve again",
                "--evidence-summary", "Fresh current-depth runtime rerun passed for Apify scrape.extract through Rhumb Resolve. Managed and direct executions matched exactly on URL, metadata.title, and markdown output for the same one-page website-content-crawler target.",
                "--source-ref", f"runtime-review:apify:{stamp}",
                "--source-batch-id", f"runtime-review:apify:{stamp}",
                "--reviewed-at", reviewed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", execution_id or "",
                "--tag", "runtime_review",
                "--tag", "apify",
                "--tag", "scrape.extract",
                "--tag", "current_pass",
                "--tag", "phase3",
                "--raw-payload-file", str(artifact_path.relative_to(REPO_ROOT)),
            ],
            publication_path,
        )
        payload["apify_depth5_pass"]["evidence_id"] = ((publication.get("evidence") or {}).get("id"))
        payload["apify_depth5_pass"]["review_id"] = ((publication.get("review") or {}).get("id"))
        payload["apify_depth5_pass"]["counts_after"] = await _fetch_public_review_stats("apify")
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
