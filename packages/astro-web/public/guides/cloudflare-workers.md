# Cloudflare Workers — Agent-Native Service Guide

> **AN Score:** 8.3 · **Tier:** L4 · **Category:** Serverless Compute

---

## 1. Synopsis

Cloudflare Workers is a serverless compute platform that runs JavaScript, TypeScript, Python, and Rust at the edge — across 300+ data centers worldwide. For agents, Workers provide low-latency compute primitives: deploy functions, store data (KV, D1, R2), and run code close to users without managing infrastructure. The platform excels at request routing, API proxying, and lightweight data transformation — common agent compute patterns. Workers are fast to deploy (sub-second), cheap to run, and globally distributed by default. Free tier: 100K requests/day, 10ms CPU time per invocation.

---

## 2. Connection Methods

### REST API
- **Base URL:** `https://api.cloudflare.com/client/v4`
- **Auth:** Bearer token (`Authorization: Bearer <API_TOKEN>`) or API Key + Email
- **Content-Type:** `application/json`
- **Rate Limits:** 1,200 requests/5 minutes for most endpoints
- **Docs:** https://developers.cloudflare.com/api

### CLI (Wrangler)
- **Install:** `npm install -g wrangler`
- **Auth:** `wrangler login` (browser OAuth) or `CLOUDFLARE_API_TOKEN` env var
- **Deploy:** `wrangler deploy` — builds and deploys Worker from project directory
- **Dev:** `wrangler dev` — local development server with remote bindings

### SDKs
- **JavaScript/TypeScript:** Native — Workers runtime IS JavaScript
- **Python:** Workers now supports Python (beta) — check https://developers.cloudflare.com/workers/languages/python/
- **Rust:** Via `workers-rs` crate
- **No traditional SDK needed** — Workers are deployed code, not called via SDK

### MCP
- Cloudflare has published MCP-related tooling; check https://developers.cloudflare.com for current MCP server availability
- Workers can host MCP servers themselves (Workers as MCP endpoints)

### Webhooks
- Workers ARE webhook handlers — deploy a Worker at a URL, point webhooks from other services to it
- Cron Triggers: Schedule Workers to run on a cron schedule (e.g., `*/5 * * * *`)

### Auth Flows
- **API Tokens:** Scoped permissions (recommended — create in Dashboard → My Profile → API Tokens)
- **Global API Key:** Full account access (legacy, not recommended)
- **OAuth:** Via `wrangler login` for CLI

---

## 3. Key Primitives

| Primitive | Method | Description |
|-----------|--------|-------------|
| `worker.deploy` | `PUT /client/v4/accounts/{id}/workers/scripts/{name}` | Deploy or update a Worker script |
| `worker.delete` | `DELETE /client/v4/accounts/{id}/workers/scripts/{name}` | Remove a Worker |
| `kv.put` | `PUT /client/v4/accounts/{id}/storage/kv/namespaces/{ns}/values/{key}` | Write a key-value pair |
| `kv.get` | `GET /client/v4/accounts/{id}/storage/kv/namespaces/{ns}/values/{key}` | Read a value by key |
| `d1.query` | `POST /client/v4/accounts/{id}/d1/database/{db}/query` | Execute SQL on D1 (SQLite at edge) |
| `r2.put` | S3-compatible API | Upload object to R2 storage |
| `worker.tail` | WebSocket via API | Stream live logs from a Worker |

---

## 4. Setup Guide

### For Humans
1. Create account at https://dash.cloudflare.com/sign-up
2. Install Wrangler: `npm install -g wrangler`
3. Authenticate: `wrangler login`
4. Create a new project: `wrangler init my-worker`
5. Edit `src/index.ts` (or `.js`) with your Worker logic
6. Deploy: `wrangler deploy`
7. Create API token at Dashboard → My Profile → API Tokens (for programmatic access)

### For Agents
1. **Credential retrieval:** Pull `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` from secure store
2. **Connection validation:**
   ```bash
   curl -s https://api.cloudflare.com/client/v4/user/tokens/verify \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq .result.status
   # Should return "active"
   ```
3. **Error handling:** All responses have `success` boolean, `errors` array, and `messages` array. Check `success` first, then parse `errors[].code` and `errors[].message`.
4. **Fallback:** On rate limit (429), respect `Retry-After`. On deploy failure, check Worker size limits (1MB free, 10MB paid). Use `wrangler tail` for debugging runtime errors.

---

## 5. Integration Example

```javascript
// Worker script: src/index.ts
// Deployed via `wrangler deploy`

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Route: health check
    if (url.pathname === "/health") {
      return Response.json({ status: "ok", region: request.cf?.colo });
    }

    // Route: store data in KV
    if (url.pathname === "/store" && request.method === "POST") {
      const { key, value } = await request.json();
      await env.MY_KV.put(key, JSON.stringify(value), {
        expirationTtl: 86400, // 24 hours
      });
      return Response.json({ stored: key });
    }

    // Route: query D1 database
    if (url.pathname === "/query" && request.method === "POST") {
      const { sql, params } = await request.json();
      const result = await env.MY_DB.prepare(sql).bind(...(params || [])).all();
      return Response.json({ rows: result.results, meta: result.meta });
    }

    return new Response("Not found", { status: 404 });
  },

  // Cron trigger: runs on schedule
  async scheduled(event, env, ctx) {
    // Example: periodic health check of external services
    const response = await fetch("https://api.example.com/health");
    const status = response.ok ? "healthy" : "degraded";
    await env.MY_KV.put("last_health_check", JSON.stringify({
      status,
      timestamp: new Date().toISOString(),
    }));
  },
};
```

```toml
# wrangler.toml
name = "rhumb-agent-worker"
main = "src/index.ts"
compatibility_date = "2026-03-01"

[triggers]
crons = ["*/5 * * * *"]

[[kv_namespaces]]
binding = "MY_KV"
id = "your-kv-namespace-id"

[[d1_databases]]
binding = "MY_DB"
database_name = "rhumb-db"
database_id = "your-d1-database-id"
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Cold Start** | 0ms | Workers have no cold start — V8 isolates, not containers |
| **Latency (P50)** | ~5-15ms | Worker execution time (excluding external fetches) |
| **Latency (P95)** | ~30ms | Compute-bound operations |
| **Global Latency** | <50ms from anywhere | 300+ edge locations |
| **Uptime** | 99.99%+ | Cloudflare's global network SLA |
| **Rate Limits (API)** | 1,200 req/5 min | For management API; Worker invocations are separate |
| **Free Tier** | 100K req/day, 10ms CPU/req | Paid: $5/mo for 10M req, 30ms CPU |

---

## 7. Agent-Native Notes

- **Idempotency:** Workers are stateless by default. Use KV or D1 to track processed request IDs for idempotent operations. Agents should include an idempotency key in request headers.
- **Retry behavior:** Workers that fetch external APIs should implement retries internally. The platform itself doesn't retry failed invocations (except cron triggers, which retry once on failure).
- **Error codes → agent decisions:** `10000` (authentication) → check API token. `10014` (script too large) → optimize bundle size. `10021` (rate limited) → back off. `10037` (KV key not found) → handle as cache miss.
- **Schema stability:** The Workers runtime API is stable and versioned via `compatibility_date`. Pin this date to avoid unexpected behavior changes. MTBBC is excellent.
- **Cost-per-operation:** Free: 100K req/day. Paid: $0.50/million requests + $12.50/million ms CPU time. Extremely cost-effective for lightweight compute. Agent routing: prefer Workers for latency-sensitive, stateless operations.
- **Bindings:** Workers connect to KV, D1, R2, Queues, Durable Objects via "bindings" — declared in `wrangler.toml`, injected at runtime. Agents should use bindings for state, not external database connections.
- **Edge-first:** Workers run in the data center closest to the caller. This means ~5ms latency from most locations. For agents making many small requests, Workers as a proxy/cache layer can dramatically reduce end-to-end latency.

---

## 8. Rhumb Context: Why Cloudflare Workers Scores 8.3 (L4)

Cloudflare Workers' **8.3 score** reflects a compute platform that removes the two biggest agent friction points — cold starts and infrastructure management:

1. **Execution Autonomy (8.5)** — Zero cold start (V8 isolates, not containers) means agents get consistent sub-15ms execution times regardless of invocation frequency. Cron triggers with built-in retry give agents a reliable scheduling primitive. Error codes are structured and distinct (`10000` auth, `10014` script too large, `10021` rate limited) — agents can route without parsing messages.

2. **Access Readiness (8.3)** — Free tier (100K requests/day, no credit card required) is sufficient for agent development and low-volume production. `wrangler deploy` takes seconds. The `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` pattern is clean. Scoped API tokens (per-zone or per-service) reduce blast radius for agent credentials.

3. **Agent Autonomy (8.0)** — Workers can host MCP servers directly — making them a natural deployment target for agent tool endpoints. KV/D1/R2 bindings let agents maintain state without external database dependencies. The `wrangler.toml` binding system makes infrastructure dependencies explicit and auditable. Workers as webhook handlers means agents deploy their own ingestion endpoints.

**Bottom line:** Workers is the best edge compute option for agent-native workloads. Deploy in seconds, run globally with no cold start, and use bindings for stateful storage — all from a single `wrangler.toml`. Use Workers for latency-sensitive agent operations, webhook ingestion, and MCP server hosting.

**Competitor context:** Vercel Edge Functions (7.8) scores lower — similar V8-based execution but tighter integration with Next.js creates friction for non-frontend agent use cases. AWS Lambda (6.9) has 200-500ms cold starts and significantly higher operational complexity. Workers wins on simplicity and edge distribution.
