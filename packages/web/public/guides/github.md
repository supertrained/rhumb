# GitHub — Agent-Native Service Guide

> **AN Score:** 8.0 · **Tier:** L3 · **Category:** Source Control & Developer Platform

---

## 1. Synopsis

GitHub is the world's largest source code hosting platform, providing git repositories, pull requests, issues, CI/CD (Actions), packages, and code review. For agents, GitHub is a critical workflow node: create repositories, open issues from bug reports, submit pull requests with code changes, trigger CI pipelines, and manage releases. The REST and GraphQL APIs are comprehensive, well-documented, and battle-tested. The `gh` CLI provides a fast path for common operations. Free tier: unlimited public repos, unlimited collaborators, 2,000 Actions minutes/month (private repos).

---

## 2. Connection Methods

### REST API
- **Base URL:** `https://api.github.com`
- **Auth:** Bearer token (`Authorization: Bearer ghp_...` or `Authorization: token ghp_...`)
- **Content-Type:** `application/json`
- **Accept:** `application/vnd.github+json` (recommended)
- **Rate Limits:** 5,000 requests/hour (authenticated), 60/hour (unauthenticated)
- **Docs:** https://docs.github.com/en/rest

### GraphQL API
- **Endpoint:** `https://api.github.com/graphql`
- **Auth:** Same Bearer token
- **Rate Limits:** 5,000 points/hour (query complexity-weighted)
- **Docs:** https://docs.github.com/en/graphql

### CLI
- **Install:** `brew install gh` or https://cli.github.com
- **Auth:** `gh auth login` or `GH_TOKEN` env var
- **Common:** `gh pr create`, `gh issue list`, `gh run view`

### SDKs
- **JavaScript:** `npm install @octokit/rest` — official (Octokit)
- **Python:** `pip install PyGithub` — community, widely used
- **Go:** `go get github.com/google/go-github/v60/github`
- **Ruby:** `gem install octokit`

### MCP
- GitHub MCP server available at https://github.com/modelcontextprotocol/servers
- Provides repository access, issue management, and PR operations via MCP

### Webhooks
- **Configure:** Repo Settings → Webhooks
- **Events:** 60+ event types (`push`, `pull_request`, `issues`, `workflow_run`, etc.)
- **Signature:** HMAC-SHA256 via `X-Hub-Signature-256` header
- **Retry:** GitHub retries failed deliveries (check webhook deliveries in Settings)

### Auth Flows
- **Personal Access Tokens (PAT):** Fine-grained (recommended) or classic
- **GitHub Apps:** For automated integrations with installation tokens
- **OAuth Apps:** For user-facing applications
- **GITHUB_TOKEN:** Auto-generated in Actions workflows (scoped to repo)

---

## 3. Key Primitives

| Primitive | Endpoint | Description |
|-----------|----------|-------------|
| `repo.create` | `POST /user/repos` | Create a new repository |
| `issue.create` | `POST /repos/{owner}/{repo}/issues` | Open an issue |
| `issue.list` | `GET /repos/{owner}/{repo}/issues` | List issues with filters |
| `pr.create` | `POST /repos/{owner}/{repo}/pulls` | Create a pull request |
| `contents.get` | `GET /repos/{owner}/{repo}/contents/{path}` | Read file contents |
| `contents.update` | `PUT /repos/{owner}/{repo}/contents/{path}` | Create or update a file |
| `actions.dispatch` | `POST /repos/{owner}/{repo}/dispatches` | Trigger a workflow |

---

## 4. Setup Guide

### For Humans
1. Create account at https://github.com/signup
2. Navigate to **Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens**
3. Click **Generate new token**
4. Select repositories (specific or all), set permissions:
   - **Contents:** Read and write (for code)
   - **Issues:** Read and write
   - **Pull requests:** Read and write
   - **Actions:** Read (for CI status)
5. Copy token (starts with `github_pat_` for fine-grained)
6. Install `gh` CLI for command-line access: `brew install gh && gh auth login`

### For Agents
1. **Credential retrieval:** Pull `GITHUB_TOKEN` from secure store (or `GH_TOKEN` for `gh` CLI)
2. **Connection validation:**
   ```bash
   curl -s https://api.github.com/user \
     -H "Authorization: Bearer $GITHUB_TOKEN" \
     -H "Accept: application/vnd.github+json" | jq .login
   # Should return your GitHub username
   ```
3. **Error handling:** Check HTTP status codes. `401` — bad token. `403` — rate limited or insufficient permissions. `404` — resource not found (or private repo without access). `422` — validation error (check `errors` array).
4. **Rate limit monitoring:**
   ```bash
   curl -s https://api.github.com/rate_limit \
     -H "Authorization: Bearer $GITHUB_TOKEN" | jq .resources.core
   ```
5. **Fallback:** On rate limit, check `X-RateLimit-Reset` header for reset time. Use conditional requests (`If-None-Match` with ETag) to reduce rate limit consumption.

---

## 5. Integration Example

```python
import requests
import os
import base64

token = os.environ["GITHUB_TOKEN"]
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

# Create an issue
issue = requests.post(
    "https://api.github.com/repos/your-org/your-repo/issues",
    headers=headers,
    json={
        "title": "Bug: API returns 500 on /users endpoint",
        "body": "## Steps to Reproduce\n1. Call GET /users\n2. Observe 500\n\n## Expected\n200 with user list\n\n_Created by Rhumb agent_",
        "labels": ["bug", "agent-created"],
        "assignees": []
    }
)
print(f"Issue created: {issue.json()['html_url']}")

# Read a file from a repo
file_resp = requests.get(
    "https://api.github.com/repos/your-org/your-repo/contents/README.md",
    headers=headers
)
content = base64.b64decode(file_resp.json()["content"]).decode("utf-8")
print(f"README length: {len(content)} chars")

# Create a pull request
pr = requests.post(
    "https://api.github.com/repos/your-org/your-repo/pulls",
    headers=headers,
    json={
        "title": "fix: handle null response in /users endpoint",
        "body": "## Changes\n- Added null check in user handler\n- Added test coverage\n\n_Automated PR by Rhumb agent_",
        "head": "fix/users-null-check",
        "base": "main"
    }
)
print(f"PR created: {pr.json()['html_url']}")

# List recent workflow runs
runs = requests.get(
    "https://api.github.com/repos/your-org/your-repo/actions/runs",
    headers=headers,
    params={"per_page": 5, "status": "completed"}
)
for run in runs.json()["workflow_runs"]:
    print(f"  {run['name']}: {run['conclusion']} ({run['html_url']})")
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Latency (P50)** | ~150ms | Simple API calls (get user, list issues) |
| **Latency (P95)** | ~400ms | Writes (create issue, create PR) |
| **Latency (P99)** | ~1s | Large file operations or complex search queries |
| **Uptime** | 99.9%+ | Check https://www.githubstatus.com |
| **Rate Limits** | 5,000 req/hour (REST), 5,000 points/hour (GraphQL) | Per authenticated user |
| **Free Tier** | Unlimited repos, 2,000 Actions min/month | Private repos included |

---

## 7. Agent-Native Notes

- **Idempotency:** Most write operations are NOT idempotent. Creating an issue twice creates two issues. Agents must check for existing issues (search by title or labels) before creating. `PUT /contents/{path}` requires the file's current SHA — this provides natural conflict detection.
- **Retry behavior:** On 403 with rate limit, wait until `X-RateLimit-Reset`. On 422, do not retry — fix the request. On 500+, retry up to 3 times with exponential backoff. Use conditional requests to conserve rate limit.
- **Error codes → agent decisions:** `401` → token expired/invalid, re-authenticate. `403` with `rate limit exceeded` → wait. `404` → resource doesn't exist or token lacks access. `422` → validation error, read `errors` array for field-level issues.
- **Schema stability:** GitHub's REST API is extremely stable. Breaking changes are rare and announced well in advance. GraphQL is also stable. API version pinning via `X-GitHub-Api-Version` header is recommended. MTBBC is excellent.
- **Cost-per-operation:** No per-API-call cost. Free tier is generous. Actions minutes cost $0.008/min (Linux) on paid plans. Agent routing: GitHub is the default for all source control operations.
- **GraphQL vs REST:** Use GraphQL for queries that need nested data (e.g., PR with reviews, checks, and comments in one call). Use REST for simple CRUD. GraphQL reduces API calls and rate limit consumption for complex queries.
- **GitHub Apps:** For production agent integrations, use GitHub Apps instead of PATs. Apps get higher rate limits (5,000 per installation), granular permissions, and installation-scoped access. Better for multi-repo agents.
- **Sensitive admin actions are less agent-native than repo workflows:** day-to-day repo work is clean, but account-security surfaces can introduce human-held gates. Example: generating an OAuth App client secret may trigger GitHub `sudo` mode and send a verification code to the account email inbox. That step is not agent-native unless the agent also controls the inbox/session needed to satisfy the check.
- **Search API:** `GET /search/issues?q=...` is powerful for agents — search by label, author, date, state. Rate limited separately (30 req/min). Use for dedup checks before creating issues.

---

## 8. Rhumb Context: Why GitHub Scores 8.0 (L3)

GitHub's **8.0 score** reflects the most complete developer platform for agent-native code workflows, with rate limits and write-idempotency gaps keeping it from the top tier:

1. **Execution Autonomy (8.0)** — Fine-grained PATs let agents operate with minimal permissions (Contents + Issues + PRs only). ETag conditional requests (`If-None-Match`) reduce rate limit consumption for read-heavy agents. The `X-GitHub-Api-Version` header pins API behavior. The GraphQL API lets agents retrieve PR + reviews + CI status in a single call, reducing round trips. The main gap: write operations aren't idempotent — agents must search before creating to avoid duplicate issues or PRs.

2. **Access Readiness (8.5)** — Free tier is permanent and genuinely useful (unlimited repos, 2,000 Actions minutes/month). The `gh` CLI installs in seconds and authenticates via `GH_TOKEN`. Fine-grained token creation has a clear permission matrix. The `GITHUB_TOKEN` auto-injection in Actions workflows means agents running as CI steps require zero credential management. The caveat: some higher-privilege account-admin actions (like generating an OAuth App client secret) can trip GitHub `sudo` mode and require an email verification code, which is a real non-agent-native gate.

3. **Agent Autonomy (7.5)** — 60+ webhook event types cover the full developer lifecycle (push, PR, CI run, deployment, release). The MCP server for GitHub (official) provides repository, issue, and PR operations via MCP tool calls. GitHub Actions' `workflow_dispatch` event lets agents trigger CI pipelines programmatically. The rate limit (5,000 req/hour) is the binding constraint for high-frequency agent loops — GraphQL helps by batching data, but bulk write agents will hit ceilings.

**Bottom line:** GitHub is the default source control and code collaboration platform for agents. No competitor matches its ecosystem breadth, webhook event coverage, or free tier generosity. For agents that need to read code, open issues, submit PRs, and trigger CI — GitHub is the only rational choice in most stacks.

**Competitor context:** GitLab (6.8) scores lower due to more complex API structure, slower response times, and a smaller ecosystem of agent tooling. Bitbucket (5.9) is significantly weaker on API completeness and has no comparable Actions-equivalent. GitHub's lead in this category is durable.
