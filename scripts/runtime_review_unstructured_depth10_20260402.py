#!/usr/bin/env python3
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
SERVICE_SLUG = "unstructured"
CAPABILITY_ID = "document.parse"
TEXT_FILENAME = "runtime-review-unstructured-depth10.txt"
TEXT_CONTENT = (
    "Rhumb Runtime Review\n\n"
    "Unstructured should parse this short sample into a Title and a NarrativeText block."
)
DIRECT_URL = "https://api.unstructuredapp.io/general/v0/general"
UNSTRUCTURED_SECRET_ITEM = "Unstructured API Key"


@dataclass
class HttpResult:
    status_code: int
    body: Any


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


async def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    data: dict[str, Any] | list[tuple[str, str]] | None = None,
    files: Any | None = None,
    timeout: float = 120.0,
) -> HttpResult:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            data=data,
            files=files,
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


def _extract_elements(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    return []


async def main() -> None:
    started_at = datetime.now(tz=UTC)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-unstructured-depth10.json"
    publication_path = REPO_ROOT / "artifacts/runtime-review-publication-2026-04-02-unstructured-depth10.json"
    org_id = f"org_runtime_review_unstructured_{stamp.lower()}"

    payload: dict[str, Any] = {
        "provider": SERVICE_SLUG,
        "capability_id": CAPABILITY_ID,
        "review_kind": "current_depth10",
        "organization_id": org_id,
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "input_shape": {
            "filename": TEXT_FILENAME,
            "strategy": "fast",
        },
        "started_at": started_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    _json_dump(artifact_path, payload)

    unstructured_api_key = os.environ.get("RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY") or _get_secret(UNSTRUCTURED_SECRET_ITEM)

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"runtime-review-unstructured-{stamp}",
        starter_credits_cents=5000,
    )
    payload["bootstrap"] = bootstrap

    agent_id, api_key = await store.register_agent(
        name=f"runtime-review-unstructured-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for Unstructured depth-10 runtime pass",
        tags=["runtime_review", "phase3", "current_pass", "unstructured", "depth10"],
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
            json_body={
                "strategy": "fast",
                "files": [
                    {
                        "filename": TEXT_FILENAME,
                        "text": TEXT_CONTENT,
                        "content_type": "text/plain",
                    }
                ],
            },
            timeout=120.0,
        )
        direct = await _request_json(
            "POST",
            DIRECT_URL,
            headers={"unstructured-api-key": unstructured_api_key},
            data={"strategy": "fast"},
            files={"files": (TEXT_FILENAME, TEXT_CONTENT.encode("utf-8"), "text/plain")},
            timeout=120.0,
        )

        rhumb_payload = ((execute.body or {}).get("data") or {}) if isinstance(execute.body, dict) else {}
        rhumb_elements = _extract_elements(rhumb_payload.get("upstream_response") if isinstance(rhumb_payload, dict) else [])
        direct_elements = _extract_elements(direct.body)
        rhumb_types = [row.get("type") for row in rhumb_elements]
        direct_types = [row.get("type") for row in direct_elements]
        rhumb_texts = [row.get("text") for row in rhumb_elements]
        direct_texts = [row.get("text") for row in direct_elements]
        observed_at = _iso_now()
        reviewed_at_dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        fresh_until = (reviewed_at_dt + timedelta(days=30)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        comparison = {
            "rhumb_provider_used": rhumb_payload.get("provider_used"),
            "rhumb_upstream_status": rhumb_payload.get("upstream_status"),
            "rhumb_count": len(rhumb_elements),
            "direct_count": len(direct_elements),
            "rhumb_types": rhumb_types,
            "direct_types": direct_types,
            "rhumb_texts": rhumb_texts,
            "direct_texts": direct_texts,
            "count_match": len(rhumb_elements) == len(direct_elements),
            "types_match": rhumb_types == direct_types,
            "texts_match": rhumb_texts == direct_texts,
        }

        verdict = "pass" if (
            estimate.status_code == 200
            and execute.status_code == 200
            and direct.status_code == 200
            and rhumb_payload.get("provider_used") == SERVICE_SLUG
            and rhumb_payload.get("upstream_status") == 200
            and comparison["count_match"]
            and comparison["types_match"]
            and comparison["texts_match"]
        ) else "fail"

        payload.update(
            {
                "observed_at": observed_at,
                "fresh_until": fresh_until,
                "counts_before": counts_before,
                "estimate": {"status": estimate.status_code, "data": estimate.body},
                "rhumb": {"status": execute.status_code, "data": execute.body},
                "direct": {"status": direct.status_code, "data": direct.body},
                "comparison": comparison,
                "verdict": verdict,
            }
        )
        _json_dump(artifact_path, payload)

        if verdict != "pass":
            raise RuntimeError("Unstructured depth-10 runtime pass failed; inspect artifact for parity details")

        execution_id = rhumb_payload.get("execution_id") or ""
        publication = _run_publish(
            [
                "--service", SERVICE_SLUG,
                "--headline", "Unstructured: depth-10 runtime review confirms document.parse parity through Rhumb Resolve",
                "--summary", "Fresh depth-10 runtime review passed for Unstructured document.parse through Rhumb Resolve. Managed and direct executions matched exactly on parsed element count, element type ordering, and extracted text for the same sample file.",
                "--evidence-title", "Unstructured depth-10 runtime review parity check via Rhumb Resolve",
                "--evidence-summary", "Fresh depth-10 runtime review passed for Unstructured document.parse through Rhumb Resolve. Managed and direct executions matched exactly on parsed element count, element type ordering, and extracted text for the same sample file.",
                "--source-ref", f"runtime-review:unstructured:{stamp}",
                "--source-batch-id", f"runtime-review:unstructured:{stamp}",
                "--reviewed-at", observed_at,
                "--fresh-until", fresh_until,
                "--reviewer-agent-id", agent_id,
                "--agent-id", agent_id,
                "--run-id", execution_id,
                "--tag", "runtime_review",
                "--tag", "unstructured",
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
