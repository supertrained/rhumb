# Linear — Agent-Native Service Guide

> **AN Score:** 8.4 · **Tier:** L3 · **Category:** Project Management & Issue Tracking

---

## 1. Synopsis

Linear is a streamlined issue tracking and project management tool built for high-velocity engineering teams. Its API is GraphQL-first, fast, and deeply structured — making it one of the best issue trackers for agent integration. Agents use Linear to create issues from bug reports, triage incoming work, update project status, and automate sprint management. Linear's opinionated workflow (Backlog → Todo → In Progress → Done) maps cleanly to agent state machines. Free tier: unlimited issues for up to 250 members (with limited features). Paid plans start at $8/user/month.

---

## 2. Connection Methods

### GraphQL API
- **Endpoint:** `https://api.linear.app/graphql`
- **Auth:** Bearer token (`Authorization: Bearer lin_api_...`)
- **Content-Type:** `application/json`
- **Rate Limits:** 1,500 requests/hour for API keys; complexity-based limiting on queries
- **Docs:** https://developers.linear.app/docs/graphql/working-with-the-graphql-api

### SDKs
- **JavaScript/TypeScript:** `npm install @linear/sdk` — official, well-typed
- **Python:** Community SDK available (`pip install linear-python`); check https://developers.linear.app for current recommendations
- **No official Go/Rust SDKs** — use raw GraphQL

### MCP
- Community MCP servers for Linear exist (check MCP server registry)
- Linear's GraphQL schema is introspectable, making custom MCP wrappers straightforward

### Webhooks
- **Configure:** Settings → API → Webhooks
- **Events:** Issue created/updated/removed, Comment created, Project updates, Cycle updates
- **Payload:** JSON with full object data + `action` field
- **Signature:** HMAC-SHA256 via webhook secret
- **Retry:** Linear retries failed deliveries for up to 24 hours

### Auth Flows
- **Personal API Keys:** Generated in Settings → API → Personal API Keys
- **OAuth 2.0:** For multi-user applications (authorize → token exchange)
- **Workspace API Keys:** Scoped to workspace (recommended for agents)

---

## 3. Key Primitives

| Primitive | Operation | Description |
|-----------|-----------|-------------|
| `issue.create` | `mutation issueCreate` | Create a new issue with title, description, assignee, labels |
| `issue.update` | `mutation issueUpdate` | Update issue state, priority, assignee, or custom fields |
| `issue.list` | `query issues` | Filter and paginate issues (by state, assignee, label, project) |
| `comment.create` | `mutation commentCreate` | Add a comment to an issue |
| `project.list` | `query projects` | List projects with status and progress |
| `cycle.list` | `query cycles` | List sprints/cycles with date ranges |
| `team.list` | `query teams` | List teams and their workflow states |

---

## 4. Setup Guide

### For Humans
1. Create workspace at https://linear.app/join
2. Navigate to **Settings → API → Personal API Keys**
3. Click **Create Key**, name it (e.g., "Rhumb Agent")
4. Copy the key (starts with `lin_api_`)
5. Note your **Team ID** from the URL when viewing a team (or query via API)
6. Set up workflow states if customizing beyond defaults

### For Agents
1. **Credential retrieval:** Pull API key from secure store (env var `LINEAR_API_KEY`)
2. **Connection validation:**
   ```bash
   curl -s https://api.linear.app/graphql \
     -H "Authorization: Bearer $LINEAR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"query": "{ viewer { id name email } }"}' | jq .data.viewer.name
   # Should return your user/bot name
   ```
3. **Bootstrap:** Query teams and workflow states on first run to cache IDs:
   ```graphql
   { teams { nodes { id name states { nodes { id name type } } } } }
   ```
4. **Error handling:** GraphQL errors return HTTP 200 with `errors` array. Check `extensions.userPresentableMessage` for human-readable error text.
5. **Fallback:** On rate limit (HTTP 429), respect `Retry-After` header. Cache team/state IDs to reduce query count.

---

## 5. Integration Example

```javascript
import { LinearClient } from "@linear/sdk";

// Credential setup
const client = new LinearClient({
  apiKey: process.env.LINEAR_API_KEY,
});

// Create an issue
async function createBugReport(title, description, teamId) {
  const issue = await client.createIssue({
    teamId,
    title,
    description,
    priority: 2, // 0=None, 1=Urgent, 2=High, 3=Medium, 4=Low
    labelIds: [], // Add label IDs as needed
  });

  const created = await issue.issue;
  console.log(`Issue created: ${created.identifier} — ${created.url}`);
  return created;
}

// List open issues for a team
async function listOpenIssues(teamId) {
  const issues = await client.issues({
    filter: {
      team: { id: { eq: teamId } },
      state: { type: { in: ["backlog", "unstarted", "started"] } },
    },
    first: 20,
    orderBy: "priority",
  });

  for (const issue of issues.nodes) {
    const state = await issue.state;
    console.log(`  ${issue.identifier} [${state.name}] ${issue.title}`);
  }
}

// Add a comment to an issue
async function addComment(issueId, body) {
  await client.createComment({ issueId, body });
  console.log(`Comment added to ${issueId}`);
}

// Usage
const teamId = "YOUR_TEAM_ID"; // Query via client.teams() first
await createBugReport(
  "API returns 500 on /users endpoint",
  "## Steps to Reproduce\n1. Call GET /users\n2. Observe 500 error\n\n## Expected\n200 with user list",
  teamId
);
await listOpenIssues(teamId);
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Latency (P50)** | ~120ms | Simple queries (single issue fetch) |
| **Latency (P95)** | ~350ms | Complex filtered queries with relations |
| **Latency (P99)** | ~800ms | Bulk operations or deep nested queries |
| **Uptime** | 99.9%+ | Check https://linearstatus.com |
| **Rate Limits** | 1,500 req/hour | Complexity-weighted; simple queries cost less |
| **Free Tier** | Unlimited issues, up to 250 members | Core features free; paid adds advanced features |

---

## 7. Agent-Native Notes

- **Idempotency:** Not built-in for mutations. Agents must track issue identifiers to avoid duplicate creation. Use `title + teamId + description hash` as a dedup key before creating.
- **Retry behavior:** On 429, back off per `Retry-After`. On GraphQL errors (200 with `errors`), parse error codes — `RATELIMITED`, `FORBIDDEN`, `NOT_FOUND` are common.
- **Error codes → agent decisions:** `RATELIMITED` → queue and retry. `FORBIDDEN` → check API key scope. `NOT_FOUND` → issue/team was deleted, update local cache. Validation errors → fix input and retry.
- **Schema stability:** Linear's GraphQL schema is versioned and documented. Breaking changes are announced in advance. MTBBC is good. Use schema introspection to validate before deploying changes.
- **Cost-per-operation:** No per-API-call cost. Plan-based pricing. Agent routing: Linear is the best-in-class choice for structured issue tracking with agent workflows.
- **Pagination:** Linear uses cursor-based pagination (`first`/`after`). Always paginate — default limits are small. Agents should paginate through full result sets for reporting.
- **Batch patterns:** No native batch mutation. For bulk operations, serialize requests with small delays (100ms) to stay within rate limits. Consider using webhooks for event-driven workflows instead of polling.
- **Rich markdown:** Issue descriptions and comments support full Markdown including code blocks, images, and task lists. Agents should format descriptions with structured sections for readability.

---

## 8. Rhumb Context: Why Linear Scores 8.4 (L3)

Linear's **8.4 score** reflects a GraphQL-first design that maps cleanly to agent workflows:

1. **Execution Autonomy (8.5)** — The GraphQL schema is introspectable and fully typed, so agents know exactly what fields are available before querying. Cursor-based pagination is safe to retry. Error responses return distinct codes (`RATELIMITED`, `FORBIDDEN`, `NOT_FOUND`) that agents can route on without parsing message strings.

2. **Access Readiness (8.2)** — Free tier is genuinely useful (unlimited issues, 250 members). API key generation takes under a minute. The main friction is bootstrapping: agents must query teams and workflow states to discover IDs before they can create issues. Cache on first run; this is a one-time cost.

3. **Agent Autonomy (8.5)** — Webhooks cover all meaningful events (issue state changes, comments, project updates) with HMAC signatures for verification. Agents can build event-driven triage loops without polling. Linear's opinionated state machine (Backlog → In Progress → Done) maps directly to agent task lifecycle tracking.

**Bottom line:** Linear is the best-in-class choice for agent-driven issue management. Its GraphQL schema doubles as a contract — agents introspect it, validate inputs, and execute without human guidance. The workflow state machine makes Linear a natural fit for agents that need to model their own task state.

**Competitor context:** Jira (5.8) scores significantly lower due to complex REST pagination, inconsistent error formats, and heavyweight setup. Asana (6.1) is REST-only and lacks webhook reliability. When agents need structured project tracking, Linear is the clear choice over both.
