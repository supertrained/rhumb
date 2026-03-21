# WU-28.1: Schema Reconciliation Migration

## Context
Rhumb has 6 existing Supabase migrations (0001-0007, no 0004). The product specs identified 9 schema conflicts between specs. This migration resolves them all.

## Current State
- `services` table: 11 columns (slug, name, category, description, base_url, docs_url, openapi_url, mcp_server_url, created_at, updated_at + id)
- `an_scores` table: score, confidence, tier, explanation, dimension_snapshot, calculated_at
- `agents` table: has organization_id, api_key_hash, status, rate_limit_qpm, etc.
- Score tiers: L1/L2/L3/L4 used in practice (some legacy platinum/gold/silver refs may exist)
- No `orgs` or `organizations` table exists yet
- No `capability_executions` table exists yet
- Supabase PostgREST exposes `an_scores` as `scores` (view or alias)

## Conflicts to Resolve

### CONFLICT-001: services table needs enrichment
Add columns the API/frontend already read from Supabase but that aren't in a migration:
- `primary_domain TEXT` — domain grouping
- `tier TEXT` — current tier label  
- `tier_label TEXT` — human-readable tier
- `logo_url TEXT` — service icon
- `pricing_model TEXT` — free/freemium/paid/enterprise
- `has_free_tier BOOLEAN DEFAULT false`
- `api_style TEXT` — REST/GraphQL/gRPC/WebSocket
- `auth_methods TEXT[]` — array of supported auth methods
- `sdks_available TEXT[]` — available SDK languages

### CONFLICT-002: Ensure L-tier naming is canonical
Add a CHECK constraint on tier columns: `tier IN ('L1','L2','L3','L4')` on `an_scores.tier`.
Search codebase for any platinum/gold/silver references and note them (don't change app code, just the migration).

### CONFLICT-003: capability_services needs existence
Create `capability_services` if it doesn't exist:
```sql
CREATE TABLE IF NOT EXISTS capability_services (
  capability_id TEXT NOT NULL,
  service_slug TEXT NOT NULL,
  priority INTEGER DEFAULT 0,
  cost_per_call NUMERIC(10,6),
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (capability_id, service_slug)
);
```

### CONFLICT-004: Create capability_executions with BIGINT money columns
```sql
CREATE TABLE IF NOT EXISTS capability_executions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id TEXT NOT NULL,
  capability_id TEXT NOT NULL,
  service_slug TEXT NOT NULL,
  credential_mode TEXT NOT NULL, -- 'byok', 'managed', 'vault'
  status TEXT NOT NULL DEFAULT 'pending', -- pending/running/success/error
  cost_usd_cents BIGINT NOT NULL DEFAULT 0,
  upstream_cost_cents BIGINT NOT NULL DEFAULT 0,
  margin_cents BIGINT NOT NULL DEFAULT 0,
  latency_ms INTEGER,
  error_code TEXT,
  error_message TEXT,
  request_metadata JSONB,
  response_metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_cap_exec_agent ON capability_executions(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cap_exec_capability ON capability_executions(capability_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cap_exec_status ON capability_executions(status);
```

### CONFLICT-005: Create orgs table (canonical billing entity)
```sql
CREATE TABLE IF NOT EXISTS orgs (
  id TEXT PRIMARY KEY, -- format: org_<hex16>
  name TEXT NOT NULL,
  email TEXT,
  tier TEXT NOT NULL DEFAULT 'free',
  stripe_customer_id TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS org_members (
  org_id TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  role TEXT NOT NULL DEFAULT 'member', -- owner, admin, member, billing
  joined_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (org_id, user_id)
);
```

### CONFLICT-006: AN Score dimension names
No migration needed — this is a code-level fix. Skip in this migration.

### CONFLICT-007: No migration needed — API routing fix. Skip.

### CONFLICT-008: No migration needed — already fixed (commit 8d76987). Skip.

### CONFLICT-009: No migration needed — pricing logic fix. Skip.

## Migration File
Create `supabase/migrations/0008_schema_reconciliation.sql`

## Requirements
1. All statements must use `IF NOT EXISTS` / `IF NOT EXISTS` patterns (idempotent)
2. Use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for new columns
3. Don't drop or rename existing columns (backward compatible)
4. Add appropriate indexes for new columns
5. Enable RLS on new tables with service-role-all policies (matching existing pattern)
6. Add a comment header explaining this is the schema reconciliation migration

## Testing
After writing the migration:
1. Check it's valid SQL (no syntax errors)
2. Verify it doesn't conflict with existing migrations
3. List all tables and new columns added

When completely finished, run this command to notify me:
openclaw system event --text "Done: WU-28.1 schema reconciliation migration written (0008)" --mode now
