#!/usr/bin/env python3
"""
Slack depth-4 runtime review pass.

Previous passes (depth 1-3) all used POST /api/auth.test and verified
team/user/bot identity fields. This pass uses the same safe-read endpoint
but expands the parity assertion surface to include url, team_id,
is_enterprise_install, and the full set of identity fields — proving
the proxy continues to pass through a complete, unmodified Slack response.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

API_BASE = os.environ.get("RHUMB_API_BASE", "https://api.rhumb.dev")


def get_admin_key():
    key = os.environ.get("RHUMB_ADMIN_KEY")
    if key:
        return key
    try:
        result = subprocess.run(
            ["sop", "item", "get", "Rhumb Admin Secret (Railway)", "--vault", "OpenClaw Agents",
             "--fields", "credential", "--reveal"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    raise RuntimeError("No admin key available")


def get_slack_token():
    token = os.environ.get("RHUMB_CREDENTIAL_SLACK_BOT_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["sop", "item", "get", "Slack - TeamSuper Bot Token", "--vault", "OpenClaw Agents",
             "--fields", "credential", "--reveal"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    raise RuntimeError("No Slack bot token available")


def api(method, path, headers=None, json_body=None):
    import urllib.request
    url = f"{API_BASE}{path}"
    data = json.dumps(json_body).encode() if json_body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            if v is not None:
                req.add_header(k, str(v))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body.decode(errors="replace")}


def main():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    admin_key = get_admin_key()
    slack_token = get_slack_token()
    admin_headers = {"X-Rhumb-Admin-Key": admin_key}

    # 1. Create temp agent
    print("Creating temp agent...")
    _, agent_resp = api("POST", "/v1/admin/agents", admin_headers, {
        "organization_id": "org_rhumb_internal",
        "name": f"slack-depth4-reviewer-{ts}",
    })
    agent_id = agent_resp.get("agent_id")
    api_key = agent_resp.get("api_key")
    print(f"Agent: {agent_id}")

    if not api_key:
        print(f"ERROR: No API key returned. Response: {json.dumps(agent_resp, indent=2)}")
        return 1

    # 2. Grant service access to slack
    print("Granting slack access...")
    grant_status, grant_resp = api("POST", f"/v1/admin/agents/{agent_id}/grant-access", admin_headers, {
        "service": "slack"
    })
    print(f"Grant: {grant_status} - {grant_resp.get('status', grant_resp.get('error', 'unknown'))}")
    if grant_status not in (200, 201):
        print(f"Grant failed: {json.dumps(grant_resp, indent=2)}")
        return 1

    agent_headers = {"X-Rhumb-Key": api_key}

    # 3. Managed execution: POST /api/auth.test via Rhumb proxy
    print("\n--- Managed: POST /api/auth.test via Rhumb proxy ---")
    managed_status, managed_resp = api("POST", "/v1/proxy/", agent_headers, {
        "service": "slack",
        "method": "POST",
        "path": "/api/auth.test"
    })
    print(f"HTTP status: {managed_status}")

    # Proxy returns body in the "body" key
    managed_body = managed_resp.get("body", {})
    execution_id = managed_resp.get("execution_id", "unknown")
    managed_latency = managed_resp.get("latency_ms")
    managed_upstream_latency = managed_resp.get("upstream_latency_ms")

    managed_fields = {
        "ok": managed_body.get("ok"),
        "url": managed_body.get("url"),
        "team": managed_body.get("team"),
        "team_id": managed_body.get("team_id"),
        "user": managed_body.get("user"),
        "user_id": managed_body.get("user_id"),
        "bot_id": managed_body.get("bot_id"),
        "is_enterprise_install": managed_body.get("is_enterprise_install"),
    }
    print(f"Managed fields: {json.dumps(managed_fields, indent=2)}")

    # 4. Direct Slack control: auth.test
    print("\n--- Direct: POST https://slack.com/api/auth.test ---")
    import urllib.request
    direct_req = urllib.request.Request(
        "https://slack.com/api/auth.test",
        method="POST",
        data=b""
    )
    direct_req.add_header("Authorization", f"Bearer {slack_token}")
    direct_req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(direct_req, timeout=30) as resp:
            direct_status = resp.status
            direct_data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        direct_status = e.code
        direct_data = json.loads(e.read())

    direct_fields = {
        "ok": direct_data.get("ok"),
        "url": direct_data.get("url"),
        "team": direct_data.get("team"),
        "team_id": direct_data.get("team_id"),
        "user": direct_data.get("user"),
        "user_id": direct_data.get("user_id"),
        "bot_id": direct_data.get("bot_id"),
        "is_enterprise_install": direct_data.get("is_enterprise_install"),
    }
    print(f"Direct status: {direct_status}")
    print(f"Direct fields: {json.dumps(direct_fields, indent=2)}")

    # 5. Parity check — expanded assertion surface
    print("\n--- Parity check (expanded) ---")
    parity_ok = True
    for field in ["ok", "url", "team", "team_id", "user", "user_id", "bot_id", "is_enterprise_install"]:
        mv = managed_fields.get(field)
        dv = direct_fields.get(field)
        match = mv == dv
        print(f"  {field}: managed={mv} direct={dv} match={match}")
        if not match:
            parity_ok = False

    # 6. Build artifact
    artifact = {
        "pass_id": f"slack-depth4-{ts}",
        "provider": "slack",
        "capability": "auth.test (expanded parity surface)",
        "timestamp": ts,
        "managed": {
            "http_status": managed_status,
            "fields": managed_fields,
            "execution_id": execution_id,
            "latency_ms": managed_latency,
            "upstream_latency_ms": managed_upstream_latency,
        },
        "direct": {
            "http_status": direct_status,
            "fields": direct_fields
        },
        "parity": parity_ok,
        "parity_fields_checked": ["ok", "url", "team", "team_id", "user", "user_id", "bot_id", "is_enterprise_install"],
        "agent_id": agent_id,
        "org_id": "org_rhumb_internal"
    }

    out = f"artifacts/runtime-review-pass-{ts}-slack-depth4.json"
    if len(sys.argv) > 2 and sys.argv[1] == "--json-out":
        out = sys.argv[2]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        json.dump(artifact, f, indent=2)
    print(f"\nArtifact: {out}")
    print(f"Parity: {'PASS' if parity_ok else 'FAIL'}")

    # 7. Disable temp agent
    api("PUT", f"/v1/admin/agents/{agent_id}", admin_headers, {"enabled": False})
    print(f"Agent {agent_id} disabled")

    return 0 if parity_ok else 1


if __name__ == "__main__":
    sys.exit(main())
