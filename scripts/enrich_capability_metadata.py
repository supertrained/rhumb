#!/usr/bin/env python3
"""Enrich capabilities missing input_hint and outcome fields.

Generates agent-useful metadata from the capability ID pattern (domain.action)
and existing description. Uses deterministic rules, not LLM generation.

Safety: dry-run by default, pass --execute to apply.
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

# Action → (input_hint_template, outcome_template) patterns
# {domain} and {action} are substituted at runtime
ACTION_PATTERNS: dict[str, tuple[str, str]] = {
    # CRUD
    "create": ("{domain} details (name, configuration)", "{domain} created with ID"),
    "get": ("{domain} ID or identifier", "{domain} details returned"),
    "list": ("optional: filters, limit, offset", "List of {domain} items"),
    "update": ("{domain} ID, fields to update", "{domain} updated"),
    "delete": ("{domain} ID", "{domain} deleted"),
    # Search / Query
    "search": ("query string, optional: filters, limit", "Matching {domain} results"),
    "query": ("query parameters or expression", "{domain} query results"),
    "find": ("search criteria", "Matching {domain} results"),
    "lookup": ("identifier or key", "{domain} details"),
    "browse": ("optional: category, filters, limit", "Browsable {domain} list"),
    # Send / Deliver
    "send": ("recipient, content/payload", "{domain} sent/delivered"),
    "deliver": ("recipient, content", "{domain} delivered"),
    "notify": ("user_ids, message content", "Notification delivered"),
    "publish": ("content, optional: channel/target", "Content published"),
    "broadcast": ("audience, message", "Message broadcast to audience"),
    # Analyze / Process
    "analyze": ("input data or content", "Analysis results with insights"),
    "score": ("entity or transaction to score", "Score/rating with confidence"),
    "classify": ("text or data to classify", "Classification labels with confidence"),
    "extract": ("source content or URL", "Extracted structured data"),
    "parse": ("raw input (text, file, URL)", "Parsed structured output"),
    "detect": ("input content", "Detection results with confidence"),
    "validate": ("data to validate", "Validation result (pass/fail with details)"),
    "verify": ("data or identity to verify", "Verification result (verified/not)"),
    "check": ("entity or condition to check", "Check result (pass/fail)"),
    "scan": ("target URL or content", "Scan results with findings"),
    "audit": ("target system or data", "Audit report with findings"),
    "review": ("content to review", "Review results with recommendations"),
    "evaluate": ("content or entity to evaluate", "Evaluation score/results"),
    # Transform / Convert
    "convert": ("source content, target format", "Converted output"),
    "transform": ("input data, transformation rules", "Transformed output"),
    "translate": ("text, source_language, target_language", "Translated text"),
    "format": ("data, format specification", "Formatted output"),
    "render": ("template, data", "Rendered output"),
    "resize": ("input, dimensions", "Resized output"),
    "compress": ("input data", "Compressed output"),
    "encode": ("input data, encoding format", "Encoded output"),
    "decode": ("encoded data", "Decoded output"),
    # Generate / Create content
    "generate": ("prompt or parameters", "Generated {domain} content"),
    "synthesize": ("input parameters", "Synthesized {domain} output"),
    "compose": ("components or instructions", "Composed {domain}"),
    "build": ("specification or config", "Built {domain} artifact"),
    # Upload / Download
    "upload": ("file or data, optional: metadata", "Upload URL or confirmation"),
    "download": ("{domain} ID or URL", "File/data content"),
    "import": ("source data or file", "Import result with count"),
    "export": ("optional: filters, format", "Exported data file/URL"),
    # Execute / Run
    "execute": ("command or code", "Execution result"),
    "run": ("task specification", "Run result"),
    "invoke": ("function name, parameters", "Function result"),
    "trigger": ("event or condition", "Trigger confirmation"),
    "start": ("{domain} configuration", "{domain} started with ID"),
    "stop": ("{domain} ID", "{domain} stopped"),
    "restart": ("{domain} ID", "{domain} restarted"),
    "spawn": ("configuration", "New {domain} instance with ID"),
    # Status / Monitor
    "get_status": ("{domain} ID", "Current status and health"),
    "monitor": ("{domain} ID or target", "Monitoring data/metrics"),
    "health": ("optional: {domain} ID", "Health check result"),
    "ping": ("target endpoint", "Latency and availability result"),
    # Auth / Identity
    "authenticate": ("credentials", "Auth token or session"),
    "authorize": ("action, resource", "Authorization decision"),
    "revoke": ("{domain} ID or token", "Revocation confirmation"),
    "issue": ("subject, parameters", "Issued {domain} with ID"),
    "rotate": ("{domain} ID", "New {domain} issued, old revoked"),
    # Schedule / Time
    "schedule": ("time/cron, action details", "Scheduled {domain} with ID"),
    "book": ("date/time, details", "Booking confirmation"),
    "cancel": ("{domain} ID", "Cancellation confirmation"),
    "reschedule": ("{domain} ID, new time", "Rescheduled confirmation"),
    "get_availability": ("date range, optional: resource", "Available time slots"),
    # Payments
    "charge": ("amount, currency, payment_method", "Charge result with ID"),
    "refund": ("transaction_id, optional: amount", "Refund confirmation"),
    "subscribe": ("plan_id, customer details", "Subscription created"),
    "unsubscribe": ("subscription_id", "Unsubscribe confirmation"),
    # Messaging
    "stream": ("input parameters", "Streaming {domain} output"),
    "complete": ("prompt or messages", "Completion response"),
    "function_call": ("function definition, context", "Function call result"),
    # Data ops
    "enrich": ("entity identifier (email, domain, etc.)", "Enriched {domain} data"),
    "merge": ("source records", "Merged result"),
    "deduplicate": ("dataset or records", "Deduplicated results"),
    "batch": ("list of items", "Batch results"),
    "sync": ("source, destination", "Sync status"),
    "backup": ("{domain} ID or config", "Backup confirmation"),
    "restore": ("backup ID", "Restore confirmation"),
    # Geo / Location
    "geocode": ("address or place name", "Coordinates (lat, lng)"),
    "geocode_forward": ("address string", "Coordinates (lat, lng) with confidence"),
    "geocode_reverse": ("lat, lng", "Address/place name"),
    "compute": ("origin, destination, optional: waypoints", "Computed route with distance/duration"),
    "ip_geolocate": ("IP address", "Geolocation data (city, country, coordinates)"),
    # Misc
    "get_insights": ("{domain} ID or data", "Insights and recommendations"),
    "get_transcript": ("recording or call ID", "Text transcript"),
    "get_history": ("{domain} ID", "History/timeline entries"),
    "get_stats": ("optional: date_range, filters", "Statistics and metrics"),
    "get_commissions": ("optional: date_range", "Commission records"),
    "create_link": ("target URL, optional: campaign", "Tracking link URL"),
    "flag_user": ("user_id, reason", "User flagged confirmation"),
    "get_profile": ("user or entity ID", "Profile data"),
    "identify": ("user_id, traits", "Identity recorded"),
    "track": ("event_name, properties", "Event tracked"),
    "set": ("key, value, optional: ttl", "Value stored"),
    "get_url": ("asset ID", "Signed URL for asset access"),
    "log": ("event data", "Log entry recorded"),
    "get_messages": ("optional: topic, filters", "Message list"),
    "subscribe_webhook": ("URL, events", "Webhook subscription created"),
    "list_events": ("optional: date_range, filters", "Event list"),
    "get_info": ("{domain} identifier", "{domain} details"),
    "register": ("{domain} details", "Registration confirmation with ID"),
    "search_availability": ("query, optional: filters", "Available {domain} options"),
    "capture": ("target URL, optional: options", "Captured content/screenshot"),
    "annotate": ("content, annotations", "Annotated content"),
    "report": ("optional: parameters, filters", "Generated report"),
    "get_rates": ("optional: base currency, pairs", "Exchange/conversion rates"),
    "get_price": ("asset or item ID", "Current price data"),
    "verify_address": ("address string", "Address verification result"),
    "analyze_call": ("call_id or recording", "Call analysis with insights"),
    "autocomplete": ("partial input text", "Completion suggestions"),
    "similarity": ("text_a, text_b", "Similarity score (0-1)"),
    "text": ("input text", "Embedding vector"),
    "get_balance": ("account_id", "Balance details"),
    "initiate": ("transfer details", "Transfer initiated with ID"),
    "predict": ("input features", "Prediction with confidence"),
    "train": ("training data, config", "Training job started with ID"),
    "explain": ("model, input", "Explanation of prediction"),
    "optimize": ("objective, constraints", "Optimized result"),
    "segment": ("criteria, data source", "Segment definition with count"),
}


def generate_metadata(cap_id: str, description: str) -> tuple[str, str]:
    """Generate input_hint and outcome from capability ID and description."""
    parts = cap_id.split(".", 1)
    if len(parts) != 2:
        return ("", "")

    domain = parts[0].replace("_", " ")
    action = parts[1]

    if action in ACTION_PATTERNS:
        hint_tmpl, outcome_tmpl = ACTION_PATTERNS[action]
        input_hint = hint_tmpl.replace("{domain}", domain).replace("{action}", action)
        outcome = outcome_tmpl.replace("{domain}", domain).replace("{action}", action)
        return (input_hint, outcome)

    # Fallback: derive from description
    input_hint = f"{domain} parameters"
    outcome = description if description else f"{action.replace('_', ' ').title()} result"
    return (input_hint, outcome)


def main():
    if DRY_RUN:
        print("=== DRY RUN (pass --execute to apply) ===\n")
    else:
        print("=== EXECUTING — changes will be applied ===\n")

    with httpx.Client(timeout=30) as client:
        # Fetch capabilities missing input_hint
        all_missing = []
        for offset in range(0, 500, 100):
            resp = client.get(
                f"{SUPABASE_URL}/rest/v1/capabilities",
                params={
                    "select": "id,domain,action,description,input_hint,outcome",
                    "input_hint": "is.null",
                    "limit": 100,
                    "offset": offset,
                    "order": "id",
                },
                headers=HEADERS,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            all_missing.extend(batch)

        print(f"Capabilities missing input_hint: {len(all_missing)}")

        updates = []
        for cap in all_missing:
            input_hint, outcome = generate_metadata(cap["id"], cap.get("description", ""))
            if input_hint:
                updates.append({
                    "id": cap["id"],
                    "input_hint": input_hint,
                    "outcome": outcome,
                })

        print(f"Updates to apply: {len(updates)}")

        # Show samples
        for u in updates[:10]:
            print(f"  {u['id']}")
            print(f"    input_hint: {u['input_hint']}")
            print(f"    outcome:    {u['outcome']}")

        if DRY_RUN:
            print(f"\n=== DRY RUN COMPLETE — {len(updates)} updates would be applied ===")
            return

        # Apply updates
        updated = 0
        for u in updates:
            resp = client.patch(
                f"{SUPABASE_URL}/rest/v1/capabilities",
                params={"id": f"eq.{u['id']}"},
                headers={**HEADERS, "Prefer": "return=minimal"},
                json={"input_hint": u["input_hint"], "outcome": u["outcome"]},
            )
            resp.raise_for_status()
            updated += 1

        print(f"\n=== COMPLETE: {updated} capabilities enriched ===")


if __name__ == "__main__":
    main()
