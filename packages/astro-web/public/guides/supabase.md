# Supabase — Agent-Native Service Guide

> **AN Score:** 8.1 · **Tier:** L4 · **Category:** Database & Backend Infrastructure

---

## 1. Synopsis

Supabase is an open-source Firebase alternative providing a Postgres database, authentication, real-time subscriptions, edge functions, and file storage — all behind a unified REST and client API. For agents, Supabase is a primary data layer: store user data, manage auth flows, query structured data via PostgREST, and react to database changes in real-time. Its PostgreSQL foundation means full SQL power with agent-friendly REST endpoints on top. Free tier: 2 projects, 500MB database, 1GB file storage, 50K monthly active users for auth.

---

## 2. Connection Methods

### REST API (PostgREST)
- **Base URL:** `https://<project-ref>.supabase.co/rest/v1`
- **Auth:** `apikey` header (anon key for public, service_role key for admin)
- **Content-Type:** `application/json`
- **Rate Limits:** No hard rate limit on Pro plans; free tier has connection limits
- **Docs:** https://supabase.com/docs/guides/api

### Client SDKs
- **JavaScript:** `npm install @supabase/supabase-js` — official, full-featured
- **Python:** `pip install supabase` — official
- **Dart/Flutter, Swift, Kotlin** — official SDKs available
- **Go:** Community SDK (`go get github.com/supabase-community/supabase-go`)

### Direct Postgres
- **Connection string:** Available in project Settings → Database
- **Pooler:** Transaction mode via Supavisor (`postgres://...pooler.supabase.com:6543`)
- Agents can use `psql`, `pg` libraries, or any Postgres client directly

### MCP
- Community MCP servers for Supabase exist (check MCP server registry)
- Supabase's REST + SQL flexibility makes both REST and direct DB access viable for agents

### Webhooks (Database Webhooks)
- **Trigger on:** INSERT, UPDATE, DELETE on any table
- **Destination:** HTTP endpoint, Supabase Edge Function, or pg_net
- **Configure:** Dashboard → Database → Webhooks

### Auth Flows
- **Anon Key:** Public, safe for client-side (respects Row Level Security)
- **Service Role Key:** Bypasses RLS — server/agent use only, never expose
- **JWT:** Supabase auth issues JWTs for authenticated users
- **OAuth providers:** Google, GitHub, Apple, etc. via Supabase Auth

---

## 3. Key Primitives

| Primitive | Method | Description |
|-----------|--------|-------------|
| `table.select` | `GET /rest/v1/{table}?select=...` | Query rows with filters, joins, pagination |
| `table.insert` | `POST /rest/v1/{table}` | Insert one or more rows |
| `table.update` | `PATCH /rest/v1/{table}?{filters}` | Update matching rows |
| `table.delete` | `DELETE /rest/v1/{table}?{filters}` | Delete matching rows |
| `rpc.call` | `POST /rest/v1/rpc/{function_name}` | Call a Postgres function |
| `auth.signup` | `POST /auth/v1/signup` | Register a new user |
| `storage.upload` | `POST /storage/v1/object/{bucket}/{path}` | Upload a file to storage |

---

## 4. Setup Guide

### For Humans
1. Create account at https://supabase.com/dashboard
2. Click **New Project** → choose org, name, region, and database password
3. Wait for provisioning (~2 minutes)
4. Navigate to **Settings → API** to find your project URL and keys
5. Copy the `anon` key (public) and `service_role` key (admin/agent use)
6. Create tables via **Table Editor** or SQL Editor
7. Enable Row Level Security on all tables (critical for security)

### For Agents
1. **Credential retrieval:** Pull `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from secure store
2. **Connection validation:**
   ```bash
   curl -s "$SUPABASE_URL/rest/v1/" \
     -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
     -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" | jq 'length'
   # Should return the number of tables (as endpoint definitions)
   ```
3. **Error handling:** PostgREST returns structured errors — `code`, `message`, `details`, `hint`. Common codes: `PGRST301` (JWT expired), `42501` (RLS violation), `23505` (unique constraint).
4. **Fallback:** On connection failure, check project status at dashboard. On RLS errors with service_role key, the issue is in RLS policies. Use direct Postgres connection as fallback for complex queries.

---

## 5. Integration Example

```python
from supabase import create_client
import os

# Credential setup
url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
supabase = create_client(url, key)

# Insert a record
result = supabase.table("services").insert({
    "name": "Stripe",
    "category": "payments",
    "an_score": 8.9,
    "tier": "L4",
    "last_probed": "2026-03-10T14:00:00Z"
}).execute()
print(f"Inserted: {result.data[0]['id']}")

# Query with filters
services = supabase.table("services") \
    .select("name, an_score, tier") \
    .gte("an_score", 8.0) \
    .order("an_score", desc=True) \
    .limit(10) \
    .execute()

for svc in services.data:
    print(f"  {svc['name']}: {svc['an_score']} ({svc['tier']})")

# Call a Postgres function (RPC)
report = supabase.rpc("generate_weekly_report", {
    "start_date": "2026-03-03",
    "end_date": "2026-03-10"
}).execute()
print(f"Report rows: {len(report.data)}")

# Real-time subscription (async pattern)
# Note: real-time requires websocket connection, shown conceptually
# channel = supabase.channel("db-changes")
# channel.on_postgres_changes("INSERT", schema="public", table="services",
#     callback=lambda payload: print(f"New service: {payload}"))
# channel.subscribe()
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Latency (P50)** | ~50ms | Simple SELECT queries via REST |
| **Latency (P95)** | ~150ms | Filtered queries with joins |
| **Latency (P99)** | ~400ms | Complex RPC calls or large result sets |
| **Uptime** | 99.9% SLA (Pro) | Check https://status.supabase.com |
| **Connection Limits** | Free: 60 direct, 200 pooled | Pro: higher limits, configurable |
| **Free Tier** | 500MB DB, 1GB storage, 2 projects | Generous for development and early production |

---

## 7. Agent-Native Notes

- **Idempotency:** Use `ON CONFLICT` (upsert) for idempotent inserts: `.upsert({...}, on_conflict="id")`. This is critical for agent retry safety. All agents should default to upsert patterns.
- **Retry behavior:** On connection errors, retry with backoff. On `PGRST` errors, parse the code — most are not retryable (fix the query). On 503 (project paused), wake the project via dashboard.
- **Error codes → agent decisions:** `23505` (unique violation) → record exists, switch to update. `42501` (permission denied) → check RLS policies or use service_role key. `PGRST301` → refresh JWT.
- **Schema stability:** PostgREST auto-generates API from your schema. Adding columns is non-breaking. Dropping columns breaks clients. MTBBC depends on your own schema management discipline.
- **Cost-per-operation:** No per-query cost. Plan-based pricing (free → $25/mo Pro → Enterprise). Agent routing: Supabase is cost-effective for structured data storage and query-heavy workloads.
- **Row Level Security:** Always enable RLS on production tables. Service role key bypasses RLS — use only in trusted agent contexts. For user-facing queries, use anon key + RLS policies.
- **Edge Functions:** Supabase Edge Functions (Deno-based) run close to your database. Use for server-side logic that agents trigger: `POST /functions/v1/{function_name}`.
- **Real-time:** Supabase Realtime enables agents to subscribe to database changes via WebSocket. Useful for event-driven agent architectures where agents react to data mutations.

---

## 8. Rhumb Context: Why Supabase Scores 8.1 (L4)

Supabase's **8.1 score** reflects a full-stack backend that covers most agent data needs in a single service:

1. **Execution Autonomy (8.2)** — PostgREST's structured error codes (`23505` for unique violation → switch to update; `42501` for permission denied → check RLS) let agents make decisions without parsing free-form messages. Upsert-by-default is the right pattern for agent retries — idempotent inserts prevent duplicate records. Direct Postgres access is available as a fallback for complex queries that PostgREST can't express.

2. **Access Readiness (8.3)** — Free tier is genuinely production-capable (500MB DB, 1GB storage, 2 projects). Project provisioning takes ~2 minutes. The Python and JavaScript SDKs handle auth automatically with the service role key. No OAuth dance required for agent access — a single `SUPABASE_SERVICE_ROLE_KEY` is all that's needed.

3. **Agent Autonomy (7.8)** — Real-time subscriptions enable event-driven architectures where agents react to database mutations without polling. Database Webhooks trigger HTTP calls on INSERT/UPDATE/DELETE. Edge Functions (Deno) run server-side logic close to the database. The one friction point: Row Level Security requires careful policy management — misconfigured RLS is a common agent debugging trap.

**Bottom line:** Supabase is the default data layer for agent systems that need structured storage, auth, and real-time events without running a dedicated database. One service covers database, auth, file storage, and edge compute. The open-source foundation means no vendor lock-in at scale.

**Competitor context:** Firebase (6.8) scores lower due to NoSQL-only data model, which limits complex queries agents commonly need. PlanetScale (7.1) offers better MySQL performance but no auth, storage, or real-time — requiring multiple services to match Supabase's coverage. Choose Supabase for all-in-one agent backends.
