"""
Rhumb Example: Discover and evaluate services for a capability.

This script shows the core Rhumb Index flow:
1. Search for services by capability (e.g., "send email")
2. Get the AN Score breakdown for the top result
3. Check known failure modes before integrating

No governed API key needed — all discovery endpoints are public.
"""

import httpx
import json

BASE = "https://api.rhumb.dev/v1"


def main():
    # Step 1: Search for email services
    print("🔍 Searching for email services...\n")
    resp = httpx.get(f"{BASE}/search", params={"q": "email"})
    results = resp.json().get("data", {}).get("items", [])

    if not results:
        print("No results found.")
        return

    for svc in results[:5]:
        slug = svc.get("slug", svc.get("service_slug", "?"))
        score = svc.get("an_score", svc.get("score", "?"))
        tier = svc.get("tier_label", "?")
        print(f"  {slug:20s}  AN Score: {score}  Tier: {tier}")

    # Step 2: Get detailed score for the top result
    top = results[0]
    slug = top.get("slug", top.get("service_slug"))
    print(f"\n📊 Detailed score for {slug}:\n")

    score_resp = httpx.get(f"{BASE}/services/{slug}/score")
    score_data = score_resp.json()
    if "an_score" in score_data:
        print(f"  AN Score:    {score_data['an_score']}")
        print(f"  Execution:   {score_data.get('execution_score', '?')}")
        print(f"  Access:      {score_data.get('access_readiness_score', '?')}")
        print(f"  Autonomy:    {score_data.get('autonomy_score', '?')}")
        print(f"  Tier:        {score_data.get('tier_label', '?')}")
        print(f"  Explanation: {score_data.get('explanation', '?')[:200]}")

    # Step 3: Check failure modes
    print(f"\n⚠️  Known failure modes for {slug}:\n")
    fail_resp = httpx.get(f"{BASE}/services/{slug}/failures")
    fail_data = fail_resp.json()
    failures = fail_data.get("data", {}).get("failures", fail_data.get("failures", []))

    if failures:
        for f in failures[:3]:
            print(f"  • {f.get('title', f.get('name', '?'))}")
            if f.get("description"):
                print(f"    {f['description'][:150]}")
    else:
        print("  No documented failure modes.")


if __name__ == "__main__":
    main()
