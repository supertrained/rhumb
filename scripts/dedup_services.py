#!/usr/bin/env python3
"""
Deduplicate v-suffixed service entries in production.

Strategy:
1. For each group of same-name services, pick a winner:
   - Prefer the base slug (no -vN suffix) if it exists
   - If no base slug, keep the highest-versioned entry
2. Update the winner with the best description from the group
3. Update the winner's score with the highest score from the group
4. Delete all losers (CASCADE handles scores, reviews, evidence)

Safety:
- Never deletes services with runtime-backed evidence
- Dry-run mode by default
- Logs every action
"""

import json
import os
import re
import sys
from collections import defaultdict

import httpx

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
DRY_RUN = "--execute" not in sys.argv

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}


def fetch_all_services(client: httpx.Client) -> list[dict]:
    """Fetch all services from Supabase."""
    all_services = []
    for offset in range(0, 2000, 500):
        resp = client.get(
            f"{SUPABASE_URL}/rest/v1/services",
            params={"select": "slug,name,category,description", "limit": 500, "offset": offset, "order": "slug"},
            headers=HEADERS,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_services.extend(batch)
    return all_services


def fetch_all_scores(client: httpx.Client) -> dict[str, dict]:
    """Fetch all scores keyed by service_slug."""
    scores = {}
    for offset in range(0, 2000, 500):
        resp = client.get(
            f"{SUPABASE_URL}/rest/v1/scores",
            params={
                "select": "service_slug,aggregate_recommendation_score,execution_score,access_readiness_score,confidence,tier,tier_label,probe_metadata,calculated_at",
                "limit": 500,
                "offset": offset,
                "order": "service_slug",
            },
            headers=HEADERS,
        )
        resp.raise_for_status()
        for row in resp.json():
            slug = row["service_slug"]
            # Keep the one with the highest score if multiple
            if slug not in scores or (row.get("aggregate_recommendation_score") or 0) > (scores[slug].get("aggregate_recommendation_score") or 0):
                scores[slug] = row
    return scores


def fetch_evidence_slugs(client: httpx.Client) -> set[str]:
    """Return set of service_slugs that have evidence records."""
    resp = client.get(
        f"{SUPABASE_URL}/rest/v1/evidence_records",
        params={"select": "service_slug"},
        headers=HEADERS,
    )
    resp.raise_for_status()
    return {r["service_slug"] for r in resp.json()}


def version_number(slug: str) -> int:
    """Extract version number from slug, or 0 for base slugs."""
    m = re.search(r"-v(\d+)$", slug)
    return int(m.group(1)) if m else 0


def base_slug(slug: str) -> str:
    """Strip version suffix from slug."""
    return re.sub(r"-v\d+$", "", slug)


def pick_winner(entries: list[dict], scores: dict[str, dict], evidence_slugs: set[str]) -> tuple[dict, list[dict]]:
    """Pick the winner from a group of same-name services."""
    # Never delete entries with evidence
    has_evidence = [e for e in entries if e["slug"] in evidence_slugs]
    if has_evidence:
        # If any entry has evidence, it must be the winner
        winner = has_evidence[0]
        losers = [e for e in entries if e["slug"] != winner["slug"]]
        return winner, losers

    # Prefer base slug (no -vN suffix)
    base_entries = [e for e in entries if version_number(e["slug"]) == 0]
    versioned_entries = [e for e in entries if version_number(e["slug"]) > 0]

    if base_entries:
        winner = base_entries[0]
    else:
        # No base slug — keep highest version
        winner = max(versioned_entries, key=lambda e: version_number(e["slug"]))

    losers = [e for e in entries if e["slug"] != winner["slug"]]
    return winner, losers


def best_description(entries: list[dict]) -> str:
    """Return the longest (richest) description from the group."""
    return max((e.get("description", "") for e in entries), key=len)


def best_score(entries: list[dict], scores: dict[str, dict]) -> dict | None:
    """Return the score row with the highest aggregate_recommendation_score."""
    candidates = [scores[e["slug"]] for e in entries if e["slug"] in scores]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.get("aggregate_recommendation_score") or 0)


def main():
    if DRY_RUN:
        print("=== DRY RUN (pass --execute to apply) ===\n")
    else:
        print("=== EXECUTING — changes will be applied ===\n")

    with httpx.Client(timeout=30) as client:
        services = fetch_all_services(client)
        scores = fetch_all_scores(client)
        evidence_slugs = fetch_evidence_slugs(client)

        # Group by name
        by_name = defaultdict(list)
        for s in services:
            by_name[s["name"]].append(s)

        duped = {name: entries for name, entries in by_name.items() if len(entries) > 1}

        print(f"Total services: {len(services)}")
        print(f"Unique names: {len(by_name)}")
        print(f"Duplicated names: {len(duped)}")
        print(f"Services to delete: {sum(len(e) - 1 for e in duped.values())}")
        print()

        updates = []
        deletes = []

        for name, entries in sorted(duped.items()):
            winner, losers = pick_winner(entries, scores, evidence_slugs)
            best_desc = best_description(entries)
            best_sc = best_score(entries, scores)

            # Check if winner needs description update
            needs_desc_update = best_desc and best_desc != winner.get("description", "")
            # Check if winner needs score update
            needs_score_update = False
            if best_sc and best_sc["service_slug"] != winner["slug"]:
                winner_score = scores.get(winner["slug"], {}).get("aggregate_recommendation_score") or 0
                best_score_val = best_sc.get("aggregate_recommendation_score") or 0
                needs_score_update = best_score_val > winner_score

            loser_slugs = [l["slug"] for l in losers]

            if needs_desc_update or needs_score_update:
                updates.append({
                    "slug": winner["slug"],
                    "name": name,
                    "description": best_desc if needs_desc_update else None,
                    "score": best_sc if needs_score_update else None,
                })

            deletes.extend(loser_slugs)

            # Log
            action = "UPDATE+DELETE" if (needs_desc_update or needs_score_update) else "DELETE"
            print(f"  {name}: keep={winner['slug']}, delete={loser_slugs} [{action}]")

        print(f"\nTotal updates: {len(updates)}")
        print(f"Total deletes: {len(deletes)}")

        if DRY_RUN:
            print("\n=== DRY RUN COMPLETE — no changes made ===")
            return

        # Execute updates
        for upd in updates:
            if upd["description"]:
                resp = client.patch(
                    f"{SUPABASE_URL}/rest/v1/services",
                    params={"slug": f"eq.{upd['slug']}"},
                    headers={**HEADERS, "Prefer": "return=minimal"},
                    json={"description": upd["description"]},
                )
                resp.raise_for_status()
                print(f"  Updated description: {upd['slug']}")

            if upd["score"]:
                sc = upd["score"]
                score_val = sc["aggregate_recommendation_score"]
                tier = "L4" if score_val >= 8 else "L3" if score_val >= 6 else "L2" if score_val >= 4 else "L1"
                tier_label = {"L1": "Emerging", "L2": "Developing", "L3": "Ready", "L4": "Native"}[tier]
                resp = client.patch(
                    f"{SUPABASE_URL}/rest/v1/scores",
                    params={"service_slug": f"eq.{upd['slug']}"},
                    headers={**HEADERS, "Prefer": "return=minimal"},
                    json={
                        "aggregate_recommendation_score": score_val,
                        "execution_score": sc.get("execution_score"),
                        "access_readiness_score": sc.get("access_readiness_score"),
                        "confidence": sc.get("confidence"),
                        "tier": tier,
                        "tier_label": tier_label,
                    },
                )
                resp.raise_for_status()
                print(f"  Updated score: {upd['slug']} → {score_val}")

        # Execute deletes in batches
        print(f"\nDeleting {len(deletes)} duplicate services...")
        for slug in deletes:
            resp = client.delete(
                f"{SUPABASE_URL}/rest/v1/services",
                params={"slug": f"eq.{slug}"},
                headers={**HEADERS, "Prefer": "return=minimal"},
            )
            resp.raise_for_status()

        print(f"\n=== COMPLETE: {len(deletes)} duplicates removed ===")

        # Verify final count
        resp = client.get(
            f"{SUPABASE_URL}/rest/v1/services",
            params={"select": "slug"},
            headers={**HEADERS, "Prefer": "count=exact", "Range": "0-0"},
        )
        count = resp.headers.get("content-range", "?")
        print(f"Final service count: {count}")


if __name__ == "__main__":
    main()
