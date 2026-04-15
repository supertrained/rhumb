"""
Rhumb Example: Repeatable dogfood loop for Resolve + telemetry.

This script turns the one-off internal validation into a reusable harness:
1. Capture a telemetry baseline for an authenticated agent
2. Resolve a capability and pick the execute-ready providers Rhumb recommends
3. Execute a small battery of real calls through Resolve
4. Verify those calls show up in recent telemetry
5. Print a compact dogfood summary you can paste into a log or review

Requires: RHUMB_API_KEY (your governed API key) environment variable.
Optional:
  RHUMB_BASE_URL=https://api.rhumb.dev/v1
  RHUMB_DOGFOOD_CAPABILITY=search.query
  RHUMB_DOGFOOD_QUERIES="query one|query two|query three"
  RHUMB_DOGFOOD_PROVIDER_COUNT=2
  RHUMB_DOGFOOD_DAYS=1

Default target is search.query because it is the safest callable path for repeatable
internal traffic generation.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx

from resolve_helpers import (
    describe_recovery_hint,
    execute_ready_provider_slugs,
    preferred_recovery_handoff,
    recovery_credential_modes_url,
    recovery_resolve_url,
)

BASE = os.environ.get("RHUMB_BASE_URL", "https://api.rhumb.dev/v1").rstrip("/")
API_KEY = os.environ.get("RHUMB_API_KEY")
CAPABILITY = os.environ.get("RHUMB_DOGFOOD_CAPABILITY", "search.query")
PROVIDER_COUNT = max(1, int(os.environ.get("RHUMB_DOGFOOD_PROVIDER_COUNT", "2")))
LOOKBACK_DAYS = max(1, int(os.environ.get("RHUMB_DOGFOOD_DAYS", "1")))
DEFAULT_QUERIES = [
    "best practices for ai agent evaluation",
    "mcp server routing patterns",
    "managed credentials vs byo for agent tools",
]


@dataclass
class RunResult:
    query: str
    provider: str
    status_code: int
    upstream_status: int | None
    execution_id: str | None
    success: bool
    error: str | None = None


def _queries() -> list[str]:
    raw = os.environ.get("RHUMB_DOGFOOD_QUERIES", "").strip()
    if not raw:
        return DEFAULT_QUERIES
    return [item.strip() for item in raw.split("|") if item.strip()]


def _headers() -> dict[str, str]:
    if not API_KEY:
        print("⚠️  Set RHUMB_API_KEY (your governed API key) to run the dogfood loop.")
        print("   Get a governed API key at https://rhumb.dev/auth/login")
        sys.exit(1)
    return {
        "X-Rhumb-Key": API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "rhumb-dogfood-loop/0.1",
    }


def _get_json(client: httpx.Client, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    resp = client.get(f"{BASE}{path}", headers=_headers(), params=params)
    resp.raise_for_status()
    return resp.json()


def _resolve_execute_context(
    client: httpx.Client,
) -> tuple[list[str], str | None, tuple[str, dict[str, Any]] | None, str | None, str | None]:
    payload = _get_json(client, f"/capabilities/{CAPABILITY}/resolve")
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    providers = execute_ready_provider_slugs(data, limit=PROVIDER_COUNT)
    return (
        providers,
        describe_recovery_hint(data),
        preferred_recovery_handoff(data),
        recovery_credential_modes_url(data),
        recovery_resolve_url(data),
    )


def _usage_summary(client: httpx.Client) -> dict[str, Any]:
    payload = _get_json(
        client,
        "/telemetry/usage",
        params={"days": LOOKBACK_DAYS, "capability_id": CAPABILITY},
    )
    return payload.get("data", {})


def _recent_records(client: httpx.Client, limit: int = 50) -> list[dict[str, Any]]:
    payload = _get_json(
        client,
        "/telemetry/recent",
        params={"limit": limit, "capability_id": CAPABILITY},
    )
    return payload.get("data", [])


def _execute_call(client: httpx.Client, *, provider: str, query: str) -> RunResult:
    resp = client.post(
        f"{BASE}/capabilities/{CAPABILITY}/execute",
        headers=_headers(),
        json={
            "provider": provider,
            "params": {"query": query},
            "credential_mode": "auto",
            "interface": "dogfood",
        },
        timeout=60.0,
    )

    if resp.is_success:
        data = resp.json().get("data", {})
        upstream_status = data.get("upstream_status")
        success = upstream_status is not None and int(upstream_status) < 500
        return RunResult(
            query=query,
            provider=provider,
            status_code=resp.status_code,
            upstream_status=upstream_status,
            execution_id=data.get("execution_id"),
            success=success,
        )

    error_text = None
    try:
        payload = resp.json()
        error_text = payload.get("detail") or payload.get("message") or json.dumps(payload)
    except Exception:
        error_text = resp.text[:500]

    return RunResult(
        query=query,
        provider=provider,
        status_code=resp.status_code,
        upstream_status=None,
        execution_id=None,
        success=False,
        error=error_text,
    )


def main() -> None:
    queries = _queries()
    with httpx.Client(timeout=30.0) as client:
        before = _usage_summary(client)
        providers, recovery_summary, recovery_handoff, credential_modes_url, resolve_url = _resolve_execute_context(client)

        if not providers:
            print(f"No execute-ready providers resolved for {CAPABILITY}.")
            if recovery_handoff:
                handoff_kind, handoff = recovery_handoff
                provider = handoff.get("preferred_provider", "?")
                mode = handoff.get("preferred_credential_mode", "?")
                if handoff_kind == "alternate_execute":
                    print(f"Alternate execute rail: {provider} ({mode})")
                    if handoff.get("endpoint_pattern"):
                        print(f"  Endpoint: {handoff['endpoint_pattern']}")
                else:
                    print(f"Setup next: {provider} ({mode})")
                if handoff.get("setup_url"):
                    print(f"  Setup URL: {handoff['setup_url']}")
                elif handoff.get("setup_hint"):
                    print(f"  Setup hint: {handoff['setup_hint']}")
            if resolve_url:
                print(f"  Resolve URL: {resolve_url}")
            if credential_modes_url:
                print(f"  Credential modes URL: {credential_modes_url}")
            if recovery_summary:
                print(f"Recovery hint: {recovery_summary}")
            sys.exit(1)

        print(f"🎯 Dogfood loop for {CAPABILITY}")
        print(f"Base URL: {BASE}")
        print(f"Providers: {', '.join(providers)}")
        print(f"Queries: {len(queries)}")
        print(
            "Baseline calls in telemetry: "
            f"{before.get('summary', {}).get('total_calls', 0)}\n"
        )

        results: list[RunResult] = []
        for idx, query in enumerate(queries):
            provider = providers[idx % len(providers)]
            result = _execute_call(client, provider=provider, query=query)
            results.append(result)
            status = "ok" if result.success else "fail"
            print(
                f"[{status}] provider={provider:<20} "
                f"http={result.status_code} upstream={result.upstream_status} "
                f"query={query}"
            )
            if result.error:
                print(f"      error={result.error}")

        after = _usage_summary(client)
        recent = _recent_records(client)
        recent_ids = {row.get('id') for row in recent if row.get('id')}

        successful_runs = [run for run in results if run.success]
        observed_runs = [run for run in successful_runs if run.execution_id in recent_ids]
        call_delta = (
            after.get("summary", {}).get("total_calls", 0)
            - before.get("summary", {}).get("total_calls", 0)
        )

        print("\n📈 Telemetry summary")
        print(f"  Calls before:  {before.get('summary', {}).get('total_calls', 0)}")
        print(f"  Calls after:   {after.get('summary', {}).get('total_calls', 0)}")
        print(f"  Delta:         {call_delta}")
        print(f"  Successful:    {len(successful_runs)} / {len(results)}")
        print(f"  Seen in recent:{len(observed_runs)} / {len(successful_runs)}")

        top_providers = after.get("by_provider", [])[:5]
        if top_providers:
            print("\n🏥 Provider health snapshot")
            for item in top_providers:
                print(
                    f"  {item.get('provider', '?'):<20} "
                    f"calls={item.get('calls', 0):<3} "
                    f"success_rate={item.get('success_rate', 0)} "
                    f"avg_latency_ms={item.get('avg_latency_ms', 0)}"
                )

        print("\n🧾 Execution IDs")
        for run in results:
            print(f"  {run.provider:<20} {run.execution_id or 'none'}")

        if successful_runs and len(observed_runs) == len(successful_runs):
            print("\n✅ Dogfood loop passed: execution traffic is visible in telemetry.")
        elif successful_runs:
            print("\n⚠️  Calls executed, but telemetry visibility is incomplete. Check /telemetry/recent and execution logs.")
        else:
            print("\n❌ No successful executions. Check provider config or credits before expanding to more agents.")


if __name__ == "__main__":
    main()
