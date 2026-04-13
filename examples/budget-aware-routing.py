"""
Rhumb Example: Budget-aware routing with cost controls.

This script shows how to:
1. Set a budget limit for your agent
2. Use cost-optimal routing to pick the cheapest provider above a quality floor
3. Check spend against budget

Requires: RHUMB_API_KEY environment variable.
"""

import os
import httpx

from resolve_helpers import describe_recovery_hint, preferred_execute_provider

BASE = "https://api.rhumb.dev/v1"
API_KEY = os.environ.get("RHUMB_API_KEY")


def main():
    if not API_KEY:
        print("⚠️  Set RHUMB_API_KEY to run this example.")
        print("   Get one at https://rhumb.dev/auth/login")
        return

    headers = {"X-Rhumb-Key": API_KEY, "Content-Type": "application/json"}

    # Step 1: Check current balance
    print("💳 Checking balance...\n")
    balance = httpx.get(f"{BASE}/agent/billing", headers=headers)
    b = balance.json().get("data", balance.json())
    print(f"  Balance: ${b.get('balance_usd', b.get('balance', '?'))}")

    # Step 2: Set routing strategy to cost-optimal
    print("\n⚙️  Setting routing to cost-optimal (quality floor: 6.0)...\n")
    routing = httpx.post(
        f"{BASE}/agent/routing",
        headers=headers,
        json={
            "strategy": "cheapest",
            "quality_floor": 6.0,
            "max_cost_per_call_usd": 0.05,
        },
    )
    print(f"  Routing configured: {routing.status_code}")

    # Step 3: Resolve with routing applied
    capability = "data.enrich_company"
    print(f"\n🔍 Resolving '{capability}' with cost-optimal routing...\n")

    resp = httpx.get(f"{BASE}/capabilities/{capability}/resolve", headers=headers)
    data = resp.json().get("data", {})
    providers = data.get("providers", [])
    execute_hint = data.get("execute_hint") or {}

    for p in providers[:3]:
        slug = p.get("service_slug", "?")
        score = p.get("an_score", "?")
        cost = p.get("cost_per_call", "?")
        print(f"  {slug:20s}  AN Score: {score}  Est. cost: ${cost}")

    preferred_provider = preferred_execute_provider(data)
    if preferred_provider:
        print(f"\n🧭 Preferred execute provider: {preferred_provider}")
        if execute_hint.get("preferred_credential_mode"):
            print(f"  Preferred credential mode: {execute_hint['preferred_credential_mode']}")

    recovery_summary = describe_recovery_hint(data)
    if recovery_summary:
        print(f"  Recovery hint: {recovery_summary}")

    # Step 4: Check spend
    print("\n📊 Current spend...\n")
    spend = httpx.get(f"{BASE}/agent/billing/spend", headers=headers)
    s = spend.json().get("data", spend.json())
    print(f"  Total spend: ${s.get('total_spend_usd', s.get('total', '?'))}")
    print(f"  Calls today: {s.get('calls_today', '?')}")


if __name__ == "__main__":
    main()
