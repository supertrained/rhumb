#!/usr/bin/env python3
"""Issue a governed Rhumb API key for a new agent (small-group onboarding helper).

This script is meant for operator-led onboarding: mint a limited key for a friend/agent,
set a budget, and hand them a copy-paste snippet.

Usage:
  python3 rhumb/scripts/issue_friend_key.py --name "Alice Agent" --budget-usd 10

Auth:
  - Requires the Rhumb admin key in env: RHUMB_ADMIN_KEY (or RHUMB_ADMIN_SECRET)
  - Talks to hosted API by default: https://api.rhumb.dev

Notes:
  - Creates the agent in an existing organization.
  - If --org-id is not provided, it will infer an org_id by listing existing agents
    via /v1/admin/agents and choosing the most common organization_id.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class IssueResult:
    api_base: str
    agent_id: str
    agent_name: str
    organization_id: str
    api_key: str
    budget: dict[str, Any]
    smoke_execute: dict[str, Any] | None = None


def _sha8(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def _env(*names: str) -> str:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return ""


def _require_admin_key() -> str:
    key = _env("RHUMB_ADMIN_KEY", "RHUMB_ADMIN_SECRET")
    if not key:
        raise SystemExit(
            "Missing admin key. Set RHUMB_ADMIN_KEY (preferred) or RHUMB_ADMIN_SECRET in env."
        )
    return key


def _http(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any | None = None,
) -> httpx.Response:
    h = {"User-Agent": "rhumb/scripts/issue_friend_key.py"}
    if headers:
        h.update(headers)
    return client.request(method, url, headers=h, json=json_body)


def _infer_org_id(*, api_base: str, admin_key: str) -> str:
    url = f"{api_base}/v1/admin/agents"
    with httpx.Client(timeout=30) as client:
        resp = _http(client, "GET", url, headers={"X-Rhumb-Admin-Key": admin_key})
    if resp.status_code != 200:
        raise SystemExit(
            f"Failed to list agents for org inference: HTTP {resp.status_code}: {resp.text[:300]}"
        )
    agents = resp.json() if (resp.headers.get("content-type") or "").startswith("application/json") else []
    if not isinstance(agents, list) or not agents:
        raise SystemExit("No agents returned from /v1/admin/agents, cannot infer org_id. Pass --org-id.")

    orgs = [a.get("organization_id") for a in agents if isinstance(a, dict) and a.get("organization_id")]
    if not orgs:
        raise SystemExit("Agents list had no organization_id fields, cannot infer org_id. Pass --org-id.")

    most_common, count = Counter(orgs).most_common(1)[0]
    if not most_common:
        raise SystemExit("Failed to infer org_id. Pass --org-id.")

    # If more than one org exists, warn on stderr but proceed.
    unique = sorted(set(orgs))
    if len(unique) > 1:
        sys.stderr.write(
            "WARN: multiple organization_id values exist in /v1/admin/agents. "
            f"Choosing most common: {most_common} (count={count}). Other orgs: {unique}\n"
        )

    return str(most_common)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", default=_env("RHUMB_API_BASE") or "https://api.rhumb.dev")
    ap.add_argument("--name", required=True)
    ap.add_argument("--org-id", default=_env("RHUMB_DEFAULT_ORG_ID"))
    ap.add_argument("--rate-limit-qpm", type=int, default=60)
    ap.add_argument("--budget-usd", type=float, default=10.0)
    ap.add_argument("--budget-period", default="monthly", choices=["daily", "weekly", "monthly", "total"])
    ap.add_argument("--hard-limit", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--alert-threshold-pct", type=int, default=80)
    ap.add_argument("--tags", default="friend,external")
    ap.add_argument(
        "--no-print-key",
        action="store_true",
        help="Do not print the full API key (for operator smoke tests).",
    )
    ap.add_argument(
        "--smoke-execute",
        action="store_true",
        help="After creating the key and budget, run one simple execute call to verify it works.",
    )
    ap.add_argument("--json", action="store_true", help="Print machine-readable JSON only")
    args = ap.parse_args()

    admin_key = _require_admin_key()
    api_base = args.api_base.rstrip("/")

    org_id = (args.org_id or "").strip()
    if not org_id:
        org_id = _infer_org_id(api_base=api_base, admin_key=admin_key)

    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]

    with httpx.Client(timeout=30) as client:
        create_url = f"{api_base}/v1/admin/agents"
        create_body = {
            "name": args.name,
            "organization_id": org_id,
            "rate_limit_qpm": int(args.rate_limit_qpm),
            "description": "Small-group onboarding key (operator-minted)",
            "tags": tags,
        }
        create_resp = _http(
            client,
            "POST",
            create_url,
            headers={"X-Rhumb-Admin-Key": admin_key},
            json_body=create_body,
        )
        if create_resp.status_code != 200:
            raise SystemExit(
                f"Failed to create agent: HTTP {create_resp.status_code}: {create_resp.text[:500]}"
            )

        created = create_resp.json()
    agent_id = created.get("agent_id")
    api_key = created.get("api_key")
    if not agent_id or not api_key:
        raise SystemExit(f"Create agent response missing agent_id/api_key: {json.dumps(created)[:500]}")

    # Set a budget for the new agent (uses the agent's own key).
    with httpx.Client(timeout=30) as client:
        budget_url = f"{api_base}/v1/agent/budget"
        budget_body = {
            "budget_usd": float(args.budget_usd),
            "period": args.budget_period,
            "hard_limit": bool(args.hard_limit),
            "alert_threshold_pct": int(args.alert_threshold_pct),
        }
        budget_resp = _http(
            client,
            "PUT",
            budget_url,
            headers={"X-Rhumb-Key": api_key},
            json_body=budget_body,
        )
        if budget_resp.status_code != 200:
            raise SystemExit(
                "Agent created but failed to set budget: "
                f"HTTP {budget_resp.status_code}: {budget_resp.text[:500]}"
            )

        budget = (
            budget_resp.json()
            if (budget_resp.headers.get("content-type") or "").startswith("application/json")
            else {}
        )

    smoke_execute: dict[str, Any] | None = None
    if args.smoke_execute:
        with httpx.Client(timeout=45) as client:
            exec_url = f"{api_base}/v1/capabilities/search.query/execute"
            exec_body = {"query": "ping"}
            exec_resp = _http(
                client,
                "POST",
                exec_url,
                headers={
                    "X-Rhumb-Key": api_key,
                    "Content-Type": "application/json",
                },
                json_body=exec_body,
            )
            smoke_execute = {
                "http_status": exec_resp.status_code,
            }

    result = IssueResult(
        api_base=api_base,
        agent_id=str(agent_id),
        agent_name=str(args.name),
        organization_id=str(org_id),
        api_key=str(api_key),
        budget=budget,
        smoke_execute=smoke_execute,
    )

    if args.json:
        payload: dict[str, Any] = {
            "ok": True,
            "api_base": result.api_base,
            "organization_id": result.organization_id,
            "agent_id": result.agent_id,
            "agent_name": result.agent_name,
            "api_key_prefix": (result.api_key.split("_", 1)[0] + "_") if "_" in result.api_key else "",
            "api_key_sha256_8": _sha8(result.api_key),
            "budget": result.budget,
            "smoke_execute": result.smoke_execute,
        }
        if not args.no_print_key:
            payload["api_key"] = result.api_key
        print(
            json.dumps(payload, indent=2)
        )
        return 0

    # Human-friendly output
    print("\nIssued new agent key")
    print("- agent_name:", result.agent_name)
    print("- agent_id:", result.agent_id)
    print("- organization_id:", result.organization_id)
    print(
        "- api_key_prefix:",
        result.api_key.split("_", 1)[0] + "_…" if "_" in result.api_key else result.api_key[:6] + "…",
    )
    print("- api_key_sha256_8:", _sha8(result.api_key))
    print("- budget:", f"${args.budget_usd:g} {args.budget_period} (hard_limit={bool(args.hard_limit)})")
    if result.smoke_execute is not None:
        print("- smoke_execute_http_status:", result.smoke_execute.get("http_status"))

    if args.no_print_key:
        print("\n(API key withheld due to --no-print-key)")
        return 0

    print("\nCopy/paste snippet:")
    print(f"export RHUMB_API_KEY=\"{result.api_key}\"")
    print(f"curl -sS {api_base}/v1/capabilities/search.query/execute \\")
    print("  -H \"Content-Type: application/json\" \\")
    print("  -H \"X-Rhumb-Key: $RHUMB_API_KEY\" \\")
    print("  -d '{\"query\":\"What is Rhumb Resolve?\"}' | jq .")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
