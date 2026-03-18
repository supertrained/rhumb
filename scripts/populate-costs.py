#!/usr/bin/env python3
"""Populate cost_per_call for all capability_services entries that are currently null.

Costs are based on publicly documented per-call pricing from each provider.
For services with per-seat or flat-rate pricing (no per-call cost), we estimate
the marginal cost per API call based on typical usage patterns.

Sources: Provider pricing pages as of March 2026.
"""

import json
import os
import sys
import urllib.request

# ── Cost mapping ──────────────────────────────────────────────────
# All values in USD per single API call/operation.
# For services with usage-based pricing: documented per-unit cost.
# For services with flat-rate/seat pricing: estimated marginal cost ≈ $0 (set to 0.0001).
# For free-tier-only services: cost is the price once free tier is exhausted.

COST_MAP: dict[str, dict[str, float]] = {
    # ── AI ──
    "google-ai":        {"default": 0.001},    # Gemini Pro ~$0.001/1K tokens
    "together-ai":      {"default": 0.0005},   # Varies by model, ~$0.0005/1K
    "replicate":        {"default": 0.002},     # Model-dependent, ~$0.002 avg

    # ── Analytics ──
    "amplitude":        {"default": 0.0001},    # Event-based, ~$0.0001/event at scale
    "mixpanel":         {"default": 0.0001},    # Event-based, ~$0.0001/event
    "posthog":          {"default": 0.0001},    # Event-based, free self-hosted
    "segment":          {"default": 0.0001},    # MTU-based, ~$0.0001/event

    # ── Auth ──
    "clerk":            {"default": 0.002},     # $0.02/MAU, ~$0.002/auth call
    "auth0":            {"default": 0.002},     # $0.023/MAU, ~$0.002/auth call
    "cognito":          {"default": 0.0055},    # $0.0055/MAU
    "supabase":         {"auth.manage_users": 0.0001, "database.insert": 0.0001, "database.query": 0.0001},
    "firebase-auth":    {"default": 0.0001},    # Free up to 50K MAU, then $0.0055/MAU
    "descope":          {"default": 0.003},     # ~$0.003/auth
    "workos":           {"default": 0.005},     # SSO-focused, ~$0.005/SSO auth

    # ── Browser ──
    "apify":            {"default": 0.005},     # ~$0.005/page crawl

    # ── Calendar ──
    "cal-com":          {"default": 0.0001},    # Self-hosted free, cloud ~flat rate
    "calendly":         {"default": 0.001},     # Per-seat, ~$0.001/API call
    "google-calendar":  {"default": 0.0001},    # Free API
    "microsoft-outlook":{"default": 0.0001},    # Graph API, free with M365

    # ── Communication ──
    "discord":          {"default": 0.0001},    # Free API
    "microsoft-teams":  {"default": 0.0001},    # Graph API
    "slack":            {"default": 0.0001},    # Free API (rate-limited)

    # ── Content / CMS ──
    "contentful":       {"default": 0.0001},    # Flat rate, marginal ~0
    "sanity":           {"default": 0.0001},    # Usage-based but generous
    "strapi":           {"default": 0.0001},    # Self-hosted, free
    "directus":         {"default": 0.0001},    # Self-hosted, free

    # ── CRM ──
    "hubspot":          {"default": 0.001},     # Per-seat + API limits
    "salesforce":       {"default": 0.002},     # Per-seat, API calls limited
    "attio":            {"default": 0.001},     # Per-seat
    "close-crm":        {"default": 0.001},     # Per-seat
    "pipedrive":        {"default": 0.001},     # Per-seat
    "freshsales":       {"default": 0.001},     # Per-seat

    # ── Database ──
    "mongodb-atlas":    {"default": 0.0001},    # Usage-based compute
    "neon":             {"default": 0.0001},    # Usage-based compute
    "planetscale":      {"default": 0.0001},    # Row-based reads
    "turso":            {"default": 0.0001},    # Row-based
    "qdrant":           {"default": 0.0001},    # Self-hosted or cloud
    "weaviate":         {"default": 0.0001},    # Usage-based
    "chroma":           {"default": 0.0001},    # Self-hosted free
    "milvus":           {"default": 0.0001},    # Self-hosted free

    # ── DevOps ──
    "github":           {"default": 0.001},     # Actions: ~$0.008/min, API free
    "circleci":         {"default": 0.006},     # ~$0.006/credit
    "bitbucket":        {"default": 0.005},     # Build minutes
    "vercel":           {"default": 0.0001},    # Generous free tier
    "railway":          {"default": 0.0001},    # Usage-based
    "netlify":          {"default": 0.0001},    # Generous free tier
    "fly-io":           {"default": 0.0001},    # Usage-based
    "render":           {"default": 0.0001},    # Usage-based
    "digital-ocean":    {"default": 0.0001},    # Usage-based

    # ── Document ──
    "docusign":         {"default": 0.01},      # Per-envelope
    "pandadoc":         {"default": 0.01},      # Per-document

    # ── Ecommerce ──
    "shopify":          {"default": 0.0001},    # API is free with app
    "bigcommerce":      {"default": 0.0001},    # API is free with plan

    # ── Email ──
    "resend":           {"default": 0.001},     # $1/1000 emails after free tier
    "brevo":            {"default": 0.001},     # ~$0.001/email
    "convertkit":       {"default": 0.001},     # Subscriber-based, ~$0.001/send
    "sendgrid":         {"email.template": 0.001, "email.track": 0.0001, "email.list_manage": 0.0001},
    "postmark":         {"email.template": 0.001, "email.track": 0.0001},

    # ── Feature Flags ──
    "launchdarkly":     {"default": 0.0001},    # Seat-based, API calls free
    "statsig":          {"default": 0.0001},    # Event-based
    "unleash":          {"default": 0.0001},    # Self-hosted free

    # ── Media ──
    "cloudinary":       {"media.process_image": 0.002, "storage.upload": 0.002},  # Transform-based
    "imgix":            {"default": 0.001},     # Transform-based

    # ── Monitoring ──
    "betterstack":      {"default": 0.0001},    # Per-check
    "datadog":          {"default": 0.001},     # Per-host + per-event
    "grafana-cloud":    {"default": 0.0001},    # Per-series
    "pagerduty":        {"default": 0.001},     # Per-incident
    "axiom":            {"default": 0.0001},    # Per-GB ingested
    "papertrail":       {"default": 0.0001},    # Per-GB

    # ── Notification ──
    "knock":            {"default": 0.001},     # Per-notification
    "novu":             {"default": 0.001},     # Per-notification  
    "onesignal":        {"default": 0.0005},    # Per-push
    "pusher":           {"default": 0.0001},    # Per-message

    # ── Payment ──
    "adyen":            {"default": 0.029},     # 2.9% typical, ~$0.029 min
    "stripe":           {"payment.invoice": 0.005, "payment.payout": 0.025, "payment.refund": 0.0001, "payment.subscribe": 0.005},
    "square":           {"default": 0.029},
    "paypal":           {"default": 0.029},
    "paddle":           {"default": 0.05},      # 5% + $0.50
    "lemon-squeezy":    {"default": 0.05},      # 5% + $0.50

    # ── Project Management ──
    "linear":           {"default": 0.0001},    # API free with seat
    "jira":             {"default": 0.001},     # Per-seat
    "asana":            {"default": 0.001},     # Per-seat
    "clickup":          {"default": 0.0001},    # API free with plan
    # github already defined above

    # ── Search ──
    "algolia":          {"default": 0.001},     # Per-search
    "elasticsearch":    {"default": 0.0001},    # Self-hosted
    "typesense":        {"default": 0.0001},    # Self-hosted / cloud
    "meilisearch":      {"default": 0.0001},    # Self-hosted free

    # ── Secrets ──
    "doppler":          {"default": 0.0001},    # Per-seat
    "infisical":        {"default": 0.0001},    # Per-seat
    "hashicorp-vault":  {"default": 0.0001},    # Self-hosted free

    # ── Social ──
    "twitter-api":      {"default": 0.005},     # API v2 is paid ($100/mo basic)
    "linkedin-api":     {"default": 0.001},     # Restricted
    "bluesky-api":      {"default": 0.0001},    # Free API

    # ── Spreadsheet / No-code DB ──
    "airtable":         {"default": 0.001},     # Per-seat + record limits
    "notion":           {"default": 0.001},     # Per-seat

    # ── Storage ──
    "aws-s3":           {"default": 0.0001},    # $0.005/1K PUT, $0.0004/1K GET
    "cloudflare-r2":    {"default": 0.0001},    # Free egress
    "supabase-storage": {"default": 0.0001},    # Usage-based
    "uploadthing":      {"default": 0.0001},    # Usage-based

    # ── Translation ──
    "deepl":            {"default": 0.002},     # $25/1M chars
    "google-translate":  {"default": 0.002},    # $20/1M chars

    # ── Workflow ──
    "inngest":          {"default": 0.001},     # Per-run
    "temporal":         {"default": 0.001},     # Per-action
    "zapier":           {"default": 0.01},      # Per-task
    "make":             {"default": 0.005},     # Per-operation
    "trigger-dev":      {"default": 0.001},     # Per-run
    "hookdeck":         {"default": 0.0005},    # Per-event
    "svix":             {"default": 0.0005},    # Per-message
    "ngrok":            {"default": 0.0001},    # Per-connection
}


def get_cost(service_slug: str, capability_id: str) -> float | None:
    """Look up cost for a service + capability pair."""
    service_costs = COST_MAP.get(service_slug)
    if service_costs is None:
        return None
    # Try capability-specific cost first, then default
    return service_costs.get(capability_id, service_costs.get("default"))


def main():
    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not sb_url or not sb_key:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY env vars")
        sys.exit(1)

    headers = {
        "apikey": sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    # 1. Fetch all null-cost entries
    req = urllib.request.Request(
        f"{sb_url}/rest/v1/capability_services?cost_per_call=is.null&select=capability_id,service_slug",
        headers={k: v for k, v in headers.items() if k != "Prefer"},
    )
    resp = urllib.request.urlopen(req)
    rows = json.loads(resp.read())
    print(f"Found {len(rows)} entries with null cost_per_call")

    # 2. Build updates
    updated = 0
    skipped = 0
    missing = []
    
    dry_run = "--dry-run" in sys.argv
    
    for row in rows:
        slug = row["service_slug"]
        cap = row["capability_id"]
        cost = get_cost(slug, cap)
        
        if cost is None:
            missing.append(f"  {cap:35s} → {slug}")
            skipped += 1
            continue
        
        if dry_run:
            print(f"  WOULD SET {cap:35s} → {slug:20s} = ${cost:.6f}")
            updated += 1
            continue
        
        # PATCH the row
        patch_url = (
            f"{sb_url}/rest/v1/capability_services"
            f"?capability_id=eq.{cap}&service_slug=eq.{slug}"
        )
        patch_data = json.dumps({"cost_per_call": cost}).encode()
        patch_req = urllib.request.Request(
            patch_url, data=patch_data, headers=headers, method="PATCH"
        )
        try:
            urllib.request.urlopen(patch_req)
            updated += 1
            print(f"  ✅ {cap:35s} → {slug:20s} = ${cost:.6f}")
        except Exception as e:
            print(f"  ❌ {cap:35s} → {slug:20s}: {e}")
            skipped += 1

    print(f"\nDone: {updated} updated, {skipped} skipped")
    if missing:
        print(f"\nMissing from COST_MAP ({len(missing)} entries):")
        for m in missing:
            print(m)


if __name__ == "__main__":
    main()
