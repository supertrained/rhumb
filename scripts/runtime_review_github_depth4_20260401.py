#!/usr/bin/env python3
"""
GitHub depth-4 runtime review pass.

Previous passes used social.get_profile on supertrained via v1 execute.
This pass uses the proxy directly on GET /users/octocat to prove
a different target profile and broader response parity.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

API_BASE = os.environ.get("RHUMB_API_BASE", "https://api.rhumb.dev")
TARGET_USER = "octocat"


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


def get_github_token():
    token = os.environ.get("RHUMB_CREDENTIAL_GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["sop", "item", "get", "GitHub PAT (supertrained)", "--vault", "OpenClaw Agents",
             "--fields", "credential", "--reveal"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    # Try gh cli token
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    raise RuntimeError("No GitHub token available")


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
    github_token = get_github_token()
    admin_headers = {"X-Rhumb-Admin-Key": admin_key}

    # 1. Create temp agent + grant github access
    print("Creating temp agent...")
    _, agent_resp = api("POST", "/v1/admin/agents", admin_headers, {
        "organization_id": "org_rhumb_internal",
        "name": f"github-depth4-reviewer-{ts}",
    })
    agent_id = agent_resp.get("agent_id")
    api_key = agent_resp.get("api_key")
    print(f"Agent: {agent_id}")

    if not api_key:
        print(f"ERROR: No API key. Response: {json.dumps(agent_resp, indent=2)}")
        return 1

    print("Granting github access...")
    grant_status, grant_resp = api("POST", f"/v1/admin/agents/{agent_id}/grant-access", admin_headers, {
        "service": "github"
    })
    print(f"Grant: {grant_status} - {grant_resp.get('status', grant_resp.get('error', 'unknown'))}")
    if grant_status not in (200, 201):
        print(f"Grant failed: {json.dumps(grant_resp, indent=2)}")
        return 1

    agent_headers = {"X-Rhumb-Key": api_key}

    # 2. Managed: GET /users/octocat via proxy
    print(f"\n--- Managed: GET /users/{TARGET_USER} via Rhumb proxy ---")
    managed_status, managed_resp = api("POST", "/v1/proxy/", agent_headers, {
        "service": "github",
        "method": "GET",
        "path": f"/users/{TARGET_USER}"
    })
    print(f"HTTP status: {managed_status}")

    managed_body = managed_resp.get("body", {})
    managed_fields = {
        "login": managed_body.get("login"),
        "id": managed_body.get("id"),
        "type": managed_body.get("type"),
        "site_admin": managed_body.get("site_admin"),
        "name": managed_body.get("name"),
        "company": managed_body.get("company"),
        "blog": managed_body.get("blog"),
        "location": managed_body.get("location"),
        "public_repos": managed_body.get("public_repos"),
        "created_at": managed_body.get("created_at"),
    }
    print(f"Managed fields: {json.dumps(managed_fields, indent=2)}")

    # 3. Direct: GET /users/octocat
    print(f"\n--- Direct: GET https://api.github.com/users/{TARGET_USER} ---")
    import urllib.request
    direct_req = urllib.request.Request(
        f"https://api.github.com/users/{TARGET_USER}",
        method="GET"
    )
    direct_req.add_header("Authorization", f"Bearer {github_token}")
    direct_req.add_header("Accept", "application/vnd.github+json")
    direct_req.add_header("User-Agent", "rhumb-runtime-review")
    try:
        with urllib.request.urlopen(direct_req, timeout=30) as resp:
            direct_status = resp.status
            direct_data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        direct_status = e.code
        direct_data = json.loads(e.read())

    direct_fields = {
        "login": direct_data.get("login"),
        "id": direct_data.get("id"),
        "type": direct_data.get("type"),
        "site_admin": direct_data.get("site_admin"),
        "name": direct_data.get("name"),
        "company": direct_data.get("company"),
        "blog": direct_data.get("blog"),
        "location": direct_data.get("location"),
        "public_repos": direct_data.get("public_repos"),
        "created_at": direct_data.get("created_at"),
    }
    print(f"Direct status: {direct_status}")
    print(f"Direct fields: {json.dumps(direct_fields, indent=2)}")

    # 4. Parity check
    print("\n--- Parity check ---")
    parity_ok = True
    for field in ["login", "id", "type", "site_admin", "name", "company", "blog", "location", "public_repos", "created_at"]:
        mv = managed_fields.get(field)
        dv = direct_fields.get(field)
        match = mv == dv
        print(f"  {field}: managed={mv} direct={dv} match={match}")
        if not match:
            parity_ok = False

    # 5. Build artifact
    artifact = {
        "pass_id": f"github-depth4-{ts}",
        "provider": "github",
        "capability": f"GET /users/{TARGET_USER} (safe read)",
        "timestamp": ts,
        "managed": {
            "http_status": managed_status,
            "fields": managed_fields,
        },
        "direct": {
            "http_status": direct_status,
            "fields": direct_fields
        },
        "parity": parity_ok,
        "parity_fields_checked": list(managed_fields.keys()),
        "agent_id": agent_id,
        "org_id": "org_rhumb_internal"
    }

    out = f"artifacts/runtime-review-pass-{ts}-github-depth4.json"
    if len(sys.argv) > 2 and sys.argv[1] == "--json-out":
        out = sys.argv[2]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        json.dump(artifact, f, indent=2)
    print(f"\nArtifact: {out}")
    print(f"Parity: {'PASS' if parity_ok else 'FAIL'}")

    # 6. Disable temp agent
    api("PUT", f"/v1/admin/agents/{agent_id}", admin_headers, {"enabled": False})
    print(f"Agent {agent_id} disabled")

    return 0 if parity_ok else 1


if __name__ == "__main__":
    sys.exit(main())
