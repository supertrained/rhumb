# Vercel — Agent-Native Service Guide

> **AN Score:** 7.8 · **Tier:** L3 · **Category:** Deployment & Hosting

---

## 1. Synopsis

Vercel is a frontend deployment and serverless platform optimized for Next.js, React, and modern web frameworks. For agents, Vercel serves two roles: (1) deployment target — push code and get a production URL in seconds, and (2) serverless compute — API routes and edge functions for backend logic. Vercel's git-based deployment model means agents can trigger deploys via git push or the REST API. The platform includes analytics, edge caching, and AI SDK integration. Free tier (Hobby): unlimited static sites, 100GB bandwidth, serverless function execution included.

---

## 2. Connection Methods

### REST API
- **Base URL:** `https://api.vercel.com`
- **Auth:** Bearer token (`Authorization: Bearer <TOKEN>`)
- **Content-Type:** `application/json`
- **Rate Limits:** 500 requests/min for most endpoints
- **Docs:** https://vercel.com/docs/rest-api

### CLI
- **Install:** `npm install -g vercel`
- **Auth:** `vercel login` or `VERCEL_TOKEN` env var
- **Deploy:** `vercel --prod` (from project directory)
- **Useful for agents:** `vercel deploy --prebuilt` for CI/CD pipelines

### SDKs
- **No official SDK** — use REST API directly or `vercel` CLI
- **AI SDK:** `npm install ai @ai-sdk/anthropic` — Vercel's AI SDK for building AI apps (separate from deployment API)
- **Community wrappers** exist for Python

### MCP
- Check https://github.com/modelcontextprotocol/servers for community Vercel MCP servers
- Vercel's REST API is straightforward enough for direct agent integration

### Webhooks (Deploy Hooks)
- **Deploy Hooks:** Trigger a deployment from any webhook source (unique URL per hook)
- **Integration Webhooks:** Events for deployment status, domain changes, etc.
- **Configure:** Project Settings → Git → Deploy Hooks

### Auth Flows
- **Personal Access Tokens:** Settings → Tokens
- **OAuth:** For third-party integrations (Vercel Integrations platform)
- **Team tokens:** Scoped to team/org

---

## 3. Key Primitives

| Primitive | Method | Description |
|-----------|--------|-------------|
| `deployment.create` | `POST /v13/deployments` | Create a new deployment |
| `deployment.list` | `GET /v6/deployments` | List deployments with filters |
| `deployment.get` | `GET /v13/deployments/{id}` | Get deployment status and details |
| `project.list` | `GET /v9/projects` | List all projects |
| `domain.list` | `GET /v5/domains` | List configured domains |
| `env.create` | `POST /v10/projects/{id}/env` | Set environment variables |
| `logs.get` | `GET /v2/deployments/{id}/events` | Stream deployment and runtime logs |

---

## 4. Setup Guide

### For Humans
1. Create account at https://vercel.com/signup
2. Connect your GitHub/GitLab/Bitbucket account
3. Import a project or create new via `vercel init`
4. Navigate to **Settings → Tokens** → Create a new token
5. Copy the token (for API/CLI access)
6. Configure custom domain in Project → Settings → Domains (optional)

### For Agents
1. **Credential retrieval:** Pull `VERCEL_TOKEN` and optionally `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` from secure store
2. **Connection validation:**
   ```bash
   curl -s https://api.vercel.com/v2/user \
     -H "Authorization: Bearer $VERCEL_TOKEN" | jq .user.username
   # Should return your Vercel username
   ```
3. **Error handling:** Errors return `{ "error": { "code": "...", "message": "..." } }`. Common codes: `forbidden`, `not_found`, `rate_limited`, `deployment_error`.
4. **Fallback:** On deployment failure, check build logs via `GET /v2/deployments/{id}/events`. On rate limit, back off per `Retry-After` header. For persistent deploy issues, fall back to git-push-based deployment.

---

## 5. Integration Example

```bash
# Deploy via CLI (simplest agent pattern)
export VERCEL_TOKEN="your-token-here"

# Deploy current directory to production
vercel --prod --yes --token "$VERCEL_TOKEN"
# Output: https://your-project.vercel.app
```

```python
import requests
import os
import json

# REST API deployment example
token = os.environ["VERCEL_TOKEN"]
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# List recent deployments
response = requests.get(
    "https://api.vercel.com/v6/deployments",
    headers=headers,
    params={"limit": 5, "state": "READY"}
)
deployments = response.json()["deployments"]
for dep in deployments:
    print(f"  {dep['name']} → https://{dep['url']} ({dep['state']})")

# Get project environment variables
project_id = os.environ.get("VERCEL_PROJECT_ID", deployments[0]["name"])
env_response = requests.get(
    f"https://api.vercel.com/v9/projects/{project_id}/env",
    headers=headers
)
env_vars = env_response.json()["envs"]
print(f"\nEnvironment variables ({len(env_vars)}):")
for env in env_vars:
    print(f"  {env['key']} ({env['target']}) — {'encrypted' if env.get('type') == 'encrypted' else 'plain'}")

# Trigger a redeployment
redeploy = requests.post(
    "https://api.vercel.com/v13/deployments",
    headers=headers,
    json={
        "name": project_id,
        "target": "production",
        "gitSource": {
            "type": "github",
            "repoId": "your-repo-id",  # Get from project settings
            "ref": "main"
        }
    }
)
if redeploy.ok:
    dep_data = redeploy.json()
    print(f"\nRedeployment triggered: https://{dep_data['url']}")
else:
    print(f"Deploy failed: {redeploy.json()}")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Deploy Time** | 15-60s typical | Depends on build complexity; static sites faster |
| **Cold Start (Serverless)** | 250-500ms | Node.js serverless functions |
| **Cold Start (Edge)** | <5ms | Edge functions (V8 isolates, like Workers) |
| **Latency (CDN)** | <50ms global | Static assets served from edge cache |
| **Uptime** | 99.99% | Check https://www.vercel-status.com |
| **Rate Limits** | 500 req/min API | Deploy hooks: 1 per 2 seconds |
| **Free Tier** | 100GB bandwidth, 100 deploys/day | Hobby plan; Pro: $20/user/month |

---

## 7. Agent-Native Notes

- **Idempotency:** Deployments are inherently idempotent — deploying the same code twice produces the same result. Use deployment URLs (immutable) for referencing specific versions.
- **Retry behavior:** On failed deployments, check build logs before retrying. Build errors (code issues) won't resolve on retry. Infrastructure errors (timeouts) are safe to retry.
- **Error codes → agent decisions:** `deployment_error` → check build logs. `rate_limited` → back off. `forbidden` → token scope issue. `project_not_found` → verify project ID/name.
- **Schema stability:** Vercel's REST API is versioned per endpoint (e.g., `/v13/deployments`). They maintain old versions. MTBBC is good for core endpoints.
- **Cost-per-operation:** No per-API-call cost. Plan-based: Hobby (free), Pro ($20/user/mo), Enterprise. Agent routing: Vercel is the default for Next.js deploys; consider alternatives for non-Next.js workloads.
- **Git integration:** The simplest agent deploy pattern is `git push` to a connected repo. Vercel auto-builds on push. No API call needed. Agents with git access can skip the REST API entirely.
- **Preview deployments:** Every git branch/PR gets a unique preview URL. Agents can create branches, push code, and share preview URLs for review — powerful for iterative development workflows.
- **Environment variables:** Set via API before deploy. Sensitive values are encrypted. Agents should manage env vars programmatically for consistent deployments across environments (preview, production).

---

## 8. Rhumb Context: Why Vercel Scores 7.8 (L3)

Vercel's **7.8 score** reflects strong deployment automation with a narrower agent-native footprint than its compute score might suggest:

1. **Execution Autonomy (7.9)** — Deployments are deterministic and idempotent — same code always produces the same result, immutable deployment URLs enable safe rollbacks. The `vercel --prod` CLI path is simple enough for agents to trigger without the REST API. Build errors are retrievable via `/v2/deployments/{id}/events` for programmatic debugging. The main limitation: no native idempotency key on the API, so agents must check deployment state before triggering new ones.

2. **Access Readiness (8.0)** — Hobby tier (free) is genuinely usable — unlimited static sites, serverless functions included. Token generation is fast. The simplest agent deploy pattern requires only `VERCEL_TOKEN` — no project ID required for CLI-based flows. Preview deployments are automatic on every branch push, giving agents instant staging environments.

3. **Agent Autonomy (7.5)** — Deploy Hooks provide a simple trigger mechanism (POST to a URL = deploy). But the event feedback loop is weak: agents must poll `/v6/deployments` to confirm build status rather than receiving webhook pushes. For agentic CI/CD pipelines, this polling requirement adds latency and complexity compared to platforms with richer event delivery.

**Bottom line:** Vercel earns its score as the default deployment target for Next.js and modern web framework projects. The git-push deploy model is the lowest-friction path for agents managing frontend code. Use Vercel where the stack fits; look to Cloudflare Workers (8.3) for non-Next.js serverless compute where edge performance and zero cold starts matter more.

**Competitor context:** Netlify (6.9) scores lower due to slower build infrastructure and less capable serverless functions. Railway (7.1) is better for full-stack backends but lacks Vercel's CDN and edge caching. Vercel wins on frontend deployment speed and DX; loses on general compute flexibility.
