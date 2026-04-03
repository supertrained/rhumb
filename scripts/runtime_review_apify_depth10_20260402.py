#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages/api"))

from db.client import get_supabase_client  # noqa: E402
from schemas.agent_identity import AgentIdentityStore  # noqa: E402
from services.billing_bootstrap import ensure_org_billing_bootstrap  # noqa: E402

BASE_URL = "https://api.rhumb.dev/v1"
SERVICE_SLUG = "apify"
CAPABILITY_ID = "scrape.extract"
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


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        [
            str(REPO_ROOT / "packages/api/.venv/bin/python"),
            str(REPO_ROOT / "scripts/publish_runtime_review_pair.py"),
            *args,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "publish_runtime_review_pair.py failed "
            f"({proc.returncode})\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    payload = json.loads(proc.stdout)
    _json_dump(output_path, payload)
    return payload


async def main() -> None:
    started_at = datetime.now(tz=timezone.utc)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-apify-depth10.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-04-02-apify-depth10.json"
    org_id = f"org_runtime_review_apify_{stamp.lower()}"

    payload: dict[str, Any] = {
        "provider": SERVICE_SLUG,
        "capability_id": CAPABILITY_ID,
        "review_kind": "current_depth10",
        "organization_id": org_id,
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "target_url": TARGET_URL,
        "crawl_input": CRAWL_INPUT,
        "started_at": started_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    _json_dump(artifact_path, payload)

    apify_token = os.environ["RHUMB_CREDENTIAL_APIFY_API_TOKEN"]

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-apify-{stamp}",
        starter_credits_cents=5000,
    )
    payload["bootstrap"] = bootstrap

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-apify-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for Apify depth-10 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", "apify", "depth10"],
    )
    payload["review_agent"] = {
        "agent_id": agent_id,
        "organization_id": org_id,
    }

    access_id = await store.grant_service_access(agent_id, SERVICE_SLUG)
    payload["grant_access"] = {
        "status": "success",
        "access_id": access_id,
    }
    _json_dump(artifact_path, payload)

    api_headers = {"X-Rhumb-Key": api_key}

    try:
        counts_before = await _fetch_public_review_stats(SERVICE_SLUG)
        estimate = await _request_json(
            "GET",
            f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute/estimate",
            headers=api_headers,
            params={"provider": SERVICE_SLUG, "credential_mode": "rhumb_managed"},
            timeout=60.0,
        )
        execute = await _request_json(
            "POST",
            f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute",
            headers=api_headers,
            params={"provider": SERVICE_SLUG, "credential_mode": "rhumb_managed"},
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

        rhumb_payload = ((execute.body or {}).get("data") or {}) if isinstance(execute.body, dict) else {}
        rhumb_run = (rhumb_payload.get("upstream_response") or {}).get("data") if isinstance(rhumb_payload, dict) else {}
        direct_run = ((direct.body or {}).get("data")) if isinstance(direct.body, dict) else {}

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
        reviewed_at_dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        fresh_until = (reviewed_at_dt + timedelta(days=30)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        comparison = {
            "rhumb_provider_used": rhumb_payload.get("provider_used"),
            "rhumb_upstream_status": rhumb_payload.get("upstream_status"),
            "rhumb_execution_id": rhumb_payload.get("execution_id"),
            "rhumb_run_id": (rhumb_run or {}).get("id"),
            "direct_run_id": (direct_run or {}).get("id"),
            "rhumb_dataset_id": rhumb_dataset_id,
            "direct_dataset_id": direct_dataset_id,
            "sampled_fields": list(sampled_fields.keys()),
            "checks": checks,
            "all_matched": all(checks.values()),
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
        }

        verdict = "pass" if (
            estimate.status_code == 200
            and execute.status_code == 200
            and direct.status_code == 201
            and rhumb_dataset.status_code == 200
            and direct_dataset.status_code == 200
            and rhumb_payload.get("provider_used") == SERVICE_SLUG
            and rhumb_payload.get("upstream_status") == 201
            and comparison["all_matched"]
        ) else "fail"

        payload.update(
            {
                "observed_at": observed_at,
                "fresh_until": fresh_until,
                "counts_before": counts_before,
                "estimate": {"status": estimate.status_code, "data": estimate.body},
                "rhumb": {"status": execute.status_code, "data": execute.body},
                "direct": {"status": direct.status_code, "data": direct.body},
                "rhumb_dataset": {"status": rhumb_dataset.status_code, "data": rhumb_dataset.body},
                "direct_dataset": {"status": direct_dataset.status_code, "data": direct_dataset.body},
                "comparison": comparison,
                "verdict": verdict,
            }
        )
        _json_dump(artifact_path, payload)

        if verdict != "pass":
            raise RuntimeError("Apify depth-10 runtime pass failed; inspect artifact for parity details")

        execution_id = rhumb_payload.get("execution_id") or ""
        publication = _run_publish(
            [
                "--service", SERVICE_SLUG,
                "--headline", "Apify: depth-10 runtime review confirms scrape.extract parity through Rhumb Resolve",
                "--summary", "Fresh depth-10 runtime review passed for Apify scrape.extract through Rhumb Resolve. Managed and direct executions matched exactly on URL, metadata.title, and markdown output for the same one-page website-content-crawler target.",
                "--evidence-title", "Apify depth-10 runtime review parity check via Rhumb Resolve",
                "--evidence-summary", "Fresh depth-10 runtime review passed for Apify scrape.extract through Rhumb Resolve. Managed and direct executions matched exactly on URL, metadata.title, and markdown output for the same one-page website-content-crawler target.",
                "--source-ref", f"runtime-review:apify:{stamp}",
                "--source-batch-id", f"runtime-review:apify:{stamp}",
                "--reviewed-at", observed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", execution_id,
                "--tag", "runtime_review",
                "--tag", "apify",
                "--tag", CAPABILITY_ID,
                "--tag", "current_pass",
                "--tag", "phase3",
                "--tag", "depth10",
                "--raw-payload-file", str(artifact_path.relative_to(REPO_ROOT)),
            ],
            publication_path,
        )
        payload["published"] = {
            "service_slug": SERVICE_SLUG,
            "evidence_id": (publication.get("evidence") or {}).get("id"),
            "review_id": (publication.get("review") or {}).get("id"),
            "execution_id": execution_id,
        }
        payload["counts_after"] = await _fetch_public_review_stats(SERVICE_SLUG)
        _json_dump(artifact_path, payload)
    finally:
        disabled = await store.disable_agent(agent_id)
        payload["agent_disabled"] = bool(disabled)
        _json_dump(artifact_path, payload)


if __name__ == "__main__":
    asyncio.run(main())
