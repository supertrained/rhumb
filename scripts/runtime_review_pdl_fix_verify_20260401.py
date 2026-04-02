#!/usr/bin/env python3
"""Production PDL fix-verification rerun via funded temp-org rail.

Run with the linked Railway production environment and the repo venv, e.g.
  railway run packages/api/.venv/bin/python scripts/runtime_review_pdl_fix_verify_20260401.py

Why this version exists:
- Mission 0 needs a real canonical-path rerun after commit 94c8df8.
- Admin-created agents under org_rhumb_internal can hit a Rhumb x402 billing gate before
  reaching PDL, which hides the provider result.
- A funded temp org plus a short propagation delay after access grant gives a clean Phase 3 rail.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages/api"))

from db.client import get_supabase_client  # noqa: E402
from schemas.agent_identity import AgentIdentityStore  # noqa: E402
from services.billing_bootstrap import ensure_org_billing_bootstrap  # noqa: E402

BASE_URL = os.environ.get("RHUMB_API_BASE", "https://api.rhumb.dev/v1")
PROVIDER = "people-data-labs"
CAPABILITY_ID = "data.enrich_person"
PROFILE_URL = "https://www.linkedin.com/in/satyanadella/"
POST_GRANT_PROPAGATION_DELAY_SECONDS = 5
ESTIMATE_AUTH_RETRY_ATTEMPTS = 4
ESTIMATE_AUTH_RETRY_DELAY_SECONDS = 5


async def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    timeout: float = 120.0,
) -> tuple[int, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method, url, headers=headers, params=params, json=json_body)
    try:
        return response.status_code, response.json()
    except Exception:
        return response.status_code, response.text


def _looks_like_invalid_key(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    detail = str(body.get("detail") or "").lower()
    error = str(body.get("error") or "").lower()
    return "invalid or expired rhumb api key" in detail or "invalid or expired rhumb api key" in error


def _sample_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "full_name": payload.get("full_name"),
        "job_title": payload.get("job_title"),
        "job_company_name": payload.get("job_company_name"),
        "linkedin_url": payload.get("linkedin_url"),
    }


def _write_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


async def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = REPO_ROOT / f"artifacts/runtime-review-pass-{stamp}-pdl-fix-verify-20260401b.json"
    org_id = f"org_runtime_review_pdl_fixverify_{stamp.lower()}"

    payload: dict[str, Any] = {
        "provider": PROVIDER,
        "capability_id": CAPABILITY_ID,
        "review_kind": "fix_verify",
        "started_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "input": {"profile": PROFILE_URL},
        "organization_id": org_id,
        "post_grant_delay_seconds": POST_GRANT_PROPAGATION_DELAY_SECONDS,
    }
    _write_artifact(artifact_path, payload)

    supabase = await get_supabase_client()
    store = AgentIdentityStore(supabase)

    bootstrap = await ensure_org_billing_bootstrap(
        org_id,
        name=f"pdl-fix-verify-{stamp}",
        starter_credits_cents=5000,
    )
    payload["wallet_bootstrap"] = bootstrap
    _write_artifact(artifact_path, payload)

    agent_id, api_key = await store.register_agent(
        name=f"pdl-fix-verify-{stamp}",
        organization_id=org_id,
        rate_limit_qpm=100,
        description="Temp review agent for PDL fix-verification rerun",
        tags=["runtime_review", "phase3", "fix_verify", "people-data-labs"],
    )
    payload["review_agent"] = {
        "agent_id": agent_id,
        "organization_id": org_id,
    }
    _write_artifact(artifact_path, payload)

    access_id = await store.grant_service_access(agent_id, PROVIDER)
    payload["grant_access"] = {"status": "success", "access_id": access_id}
    _write_artifact(artifact_path, payload)

    # Freshly-created grants can race the auth/read path; wait briefly so the estimate call
    # does not flap with a transient invalid-key/permission miss.
    await asyncio.sleep(POST_GRANT_PROPAGATION_DELAY_SECONDS)

    api_headers = {"X-Rhumb-Key": api_key}

    try:
        estimate_attempts = 0
        estimate_status = 0
        estimate_body: Any = None
        while estimate_attempts < ESTIMATE_AUTH_RETRY_ATTEMPTS:
            estimate_attempts += 1
            estimate_status, estimate_body = await _request_json(
                "GET",
                f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute/estimate",
                headers=api_headers,
                params={"provider": PROVIDER, "credential_mode": "rhumb_managed"},
                timeout=60.0,
            )
            if not (
                estimate_status == 401
                and _looks_like_invalid_key(estimate_body)
                and estimate_attempts < ESTIMATE_AUTH_RETRY_ATTEMPTS
            ):
                break
            await asyncio.sleep(ESTIMATE_AUTH_RETRY_DELAY_SECONDS)
        execute_status, execute_body = await _request_json(
            "POST",
            f"{BASE_URL}/capabilities/{CAPABILITY_ID}/execute",
            headers=api_headers,
            params={"provider": PROVIDER, "credential_mode": "rhumb_managed"},
            json_body={"profile": PROFILE_URL},
            timeout=120.0,
        )
        direct_status, direct_body = await _request_json(
            "GET",
            "https://api.peopledatalabs.com/v5/person/enrich",
            headers={"X-Api-Key": os.environ["RHUMB_CREDENTIAL_PDL_API_KEY"]},
            params={"profile": PROFILE_URL},
            timeout=60.0,
        )

        rhumb_data = ((execute_body or {}).get("data") or {}) if isinstance(execute_body, dict) else {}
        rhumb_upstream = (rhumb_data.get("upstream_response") or {}) if isinstance(rhumb_data, dict) else {}
        rhumb_payload = rhumb_upstream.get("data") if isinstance(rhumb_upstream.get("data"), dict) else rhumb_upstream
        direct_payload = direct_body.get("data") if isinstance(direct_body, dict) and isinstance(direct_body.get("data"), dict) else direct_body

        rhumb_sample = _sample_fields(rhumb_payload if isinstance(rhumb_payload, dict) else {})
        direct_sample = _sample_fields(direct_payload if isinstance(direct_payload, dict) else {})
        rhumb_error_message = ((rhumb_upstream.get("error") or {}).get("message")) if isinstance(rhumb_upstream, dict) else None
        direct_error_message = ((direct_body.get("error") or {}).get("message")) if isinstance(direct_body, dict) else None
        control_quota_blocked = direct_status == 402
        parity_ok = False
        if direct_status == 200:
            parity_ok = rhumb_sample == direct_sample
        elif control_quota_blocked:
            parity_ok = (
                rhumb_data.get("upstream_status") == direct_status
                and rhumb_error_message == direct_error_message
                and rhumb_data.get("provider_used") == PROVIDER
            )

        payload.update(
            {
                "estimate": {
                    "status": estimate_status,
                    "attempts": estimate_attempts,
                    "data": estimate_body,
                },
                "rhumb_execute": {"status": execute_status, "data": execute_body},
                "direct_control": {"status": direct_status, "data": direct_body},
                "parity": {
                    "sampled_keys": list(rhumb_sample.keys()),
                    "rhumb_sample": rhumb_sample,
                    "direct_sample": direct_sample,
                    "provider_used": rhumb_data.get("provider_used"),
                    "execution_id": rhumb_data.get("execution_id"),
                    "upstream_status": rhumb_data.get("upstream_status"),
                    "same_error_message": rhumb_error_message == direct_error_message,
                    "all_matched": parity_ok,
                },
                "control_quota_blocked": control_quota_blocked,
                "observed_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "verdict": "pass"
                if (
                    estimate_status == 200
                    and execute_status == 200
                    and rhumb_data.get("provider_used") == PROVIDER
                    and parity_ok
                )
                else "fail",
            }
        )
        _write_artifact(artifact_path, payload)
    finally:
        payload["agent_disabled"] = bool(await store.disable_agent(agent_id))
        _write_artifact(artifact_path, payload)

    if payload.get("verdict") != "pass":
        raise RuntimeError("PDL fix-verify failed; inspect artifact")

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
