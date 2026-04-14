"""
Rhumb Example: Resolve a capability to the best provider and execute it.

This script shows the core Rhumb Resolve flow:
1. Resolve a capability to ranked providers
2. Inspect any machine-readable recovery handoff Rhumb already identified
3. Estimate cost before committing
4. Execute through Resolve with managed credentials

No auth is needed for the initial resolve walkthrough.
RHUMB_API_KEY is required for estimation and execution.
Get one at https://rhumb.dev/auth/login
"""

import os
import httpx
import json

from resolve_helpers import (
    describe_recovery_hint,
    preferred_execute_provider,
    preferred_recovery_handoff,
    recovery_credential_modes_url,
    recovery_resolve_url,
)

BASE = "https://api.rhumb.dev/v1"
API_KEY = os.environ.get("RHUMB_API_KEY")


def _print_recovery_handoff(recovery_handoff: tuple[str, dict[str, object]] | None) -> None:
    if not recovery_handoff:
        return

    handoff_kind, handoff = recovery_handoff
    provider = handoff.get("preferred_provider", "?")
    mode = handoff.get("preferred_credential_mode", "?")
    if handoff_kind == "alternate_execute":
        print(f"Next step: pivot to the alternate execute rail via {provider} ({mode}).")
        if handoff.get("endpoint_pattern"):
            print(f"  Endpoint: {handoff['endpoint_pattern']}")
    else:
        print(f"Next step: finish setup for {provider} ({mode}).")

    if handoff.get("setup_url"):
        print(f"  Setup URL: {handoff['setup_url']}")
    elif handoff.get("setup_hint"):
        print(f"  Setup hint: {handoff['setup_hint']}")



def main():
    if not API_KEY:
        print("ℹ️  No RHUMB_API_KEY set, so this run will stop after resolve.")
        print("   Resolve itself works without auth.")
        print("   Set RHUMB_API_KEY only if you want to continue into estimate and execute.")
        print("   Get one at https://rhumb.dev/auth/login\n")

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
    recovery_handoff = preferred_recovery_handoff(data)
    credential_modes_url = recovery_credential_modes_url(data)
    resolve_url = recovery_resolve_url(data)
    top_provider = preferred_execute_provider(data)
    if recovery_summary:
        print(f"\n⚠️  Recovery hint: {recovery_summary}")

    if not API_KEY:
        if not top_provider:
            print("\nNo execute-ready provider found in the current resolve context.")
            if recovery_handoff:
                _print_recovery_handoff(recovery_handoff)
            elif recovery_summary:
                print("Follow the recovery hint above to finish setup or pivot to the alternate rail.")
            if resolve_url:
                print(f"  Resolve URL: {resolve_url}")
            if credential_modes_url:
                print(f"  Credential modes URL: {credential_modes_url}")
        print("\n💡 Set RHUMB_API_KEY to continue with estimation and execution.")
        return

    # Step 2: Estimate cost before committing
    if not top_provider:
        print("No execute-ready provider found in the current resolve context.")
        if recovery_handoff:
            _print_recovery_handoff(recovery_handoff)
        elif recovery_summary:
            print("Follow the recovery hint above to finish setup or pivot to the alternate rail.")
        if resolve_url:
            print(f"  Resolve URL: {resolve_url}")
        if credential_modes_url:
            print(f"  Credential modes URL: {credential_modes_url}")
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
