"""
Rhumb Example: Resolve a capability to the best provider and execute it.

This script shows the core Rhumb Resolve flow:
1. Resolve a capability to ranked providers
2. Estimate cost before committing
3. Execute through Resolve with managed credentials

Requires: RHUMB_API_KEY environment variable.
Get one at https://rhumb.dev/auth/login
"""

import os
import httpx
import json

from resolve_helpers import describe_recovery_hint, preferred_execute_provider

BASE = "https://api.rhumb.dev/v1"
API_KEY = os.environ.get("RHUMB_API_KEY")


def main():
    if not API_KEY:
        print("⚠️  Set RHUMB_API_KEY to run execution examples.")
        print("   Get one at https://rhumb.dev/auth/login")
        print("\n   Running resolution (no auth needed)...\n")

    headers = {"X-Rhumb-Key": API_KEY} if API_KEY else {}

    # Step 1: Resolve capability to ranked providers
    capability = "search.query"
    print(f"🔍 Resolving '{capability}' to best providers...\n")

    resp = httpx.get(f"{BASE}/capabilities/{capability}/resolve", headers=headers)
    data = resp.json().get("data", {})
    providers = data.get("providers", [])
    execute_hint = data.get("execute_hint") or {}

    for p in providers[:5]:
        slug = p.get("service_slug", "?")
        score = p.get("an_score", "?")
        cost = p.get("cost_per_call", "?")
        print(f"  {slug:20s}  AN Score: {score}  Est. cost: ${cost}")

    if execute_hint:
        print("\n🧭 Execute handoff")
        print(f"  Preferred provider: {execute_hint.get('preferred_provider', '?')}")
        print(f"  Preferred mode:     {execute_hint.get('preferred_credential_mode', '?')}")
        if execute_hint.get("fallback_providers"):
            print(f"  Fallbacks:          {', '.join(execute_hint['fallback_providers'])}")

    recovery_summary = describe_recovery_hint(data)
    if recovery_summary:
        print(f"\n⚠️  Recovery hint: {recovery_summary}")

    if not API_KEY:
        print("\n💡 Set RHUMB_API_KEY to continue with estimation and execution.")
        return

    # Step 2: Estimate cost before committing
    top_provider = preferred_execute_provider(data)
    if not top_provider:
        print("No execute-ready provider found in the current resolve context.")
        return

    print(f"\n💰 Estimating cost for '{capability}' via {top_provider}...\n")
    est_resp = httpx.get(
        f"{BASE}/capabilities/{capability}/execute/estimate",
        params={"provider": top_provider},
        headers=headers,
    )
    est = est_resp.json()
    print(f"  Estimated cost: ${est.get('data', {}).get('estimated_cost_usd', '?')}")
    print(f"  Circuit state:  {est.get('data', {}).get('circuit_state', '?')}")

    # Step 3: Execute
    print(f"\n🚀 Executing '{capability}' via {top_provider}...\n")
    exec_resp = httpx.post(
        f"{BASE}/capabilities/{capability}/execute",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "provider": top_provider,
            "params": {"query": "best practices for AI agent development"},
        },
    )
    result = exec_resp.json()
    print(f"  Status: {exec_resp.status_code}")
    print(f"  Response preview: {json.dumps(result, indent=2)[:500]}")


if __name__ == "__main__":
    main()
