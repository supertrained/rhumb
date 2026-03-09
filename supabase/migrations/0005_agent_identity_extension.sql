-- Migration 0005: Agent Identity Extension (Round 11 — WU 2.2)
--
-- Extends the agents table with organization scoping, API key management,
-- rate limiting, and metadata fields. Creates the agent_service_access
-- table for per-agent per-service access control and the agent_usage_events
-- table for usage tracking.

-- ── 1. Create agents table if it doesn't exist ─────────────────────
-- (Round 10 may not have created this table in a migration)

CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ── 2. Extend agents table with identity columns ───────────────────

ALTER TABLE agents ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS api_key_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS api_key_prefix TEXT NOT NULL DEFAULT '';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS api_key_created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE agents ADD COLUMN IF NOT EXISTS api_key_rotated_at TIMESTAMPTZ;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS disabled_at TIMESTAMPTZ;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS rate_limit_qpm INTEGER NOT NULL DEFAULT 100;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS timeout_seconds INTEGER NOT NULL DEFAULT 30;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS retry_policy JSONB DEFAULT '{"max_retries": 3, "backoff_ms": 100}';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS custom_attributes JSONB DEFAULT '{}';

-- Indexes on agents
CREATE INDEX IF NOT EXISTS idx_agents_organization ON agents(organization_id);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_agents_api_key_hash ON agents(api_key_hash);

-- ── 3. Agent service access table ──────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_service_access (
    access_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    service TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    rate_limit_qpm_override INTEGER NOT NULL DEFAULT 0,
    credential_account_id TEXT,
    last_used_at TIMESTAMPTZ,
    last_used_result TEXT,
    UNIQUE(agent_id, service)
);

CREATE INDEX IF NOT EXISTS idx_agent_service_access_agent ON agent_service_access(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_service_access_service ON agent_service_access(service);
CREATE INDEX IF NOT EXISTS idx_agent_service_access_status ON agent_service_access(status);

-- ── 4. Agent usage events table (feeds Round 12 billing) ───────────

CREATE TABLE IF NOT EXISTS agent_usage_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    service TEXT NOT NULL,
    result TEXT NOT NULL,  -- 'success', 'error', 'rate_limited', 'auth_failed'
    latency_ms REAL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_usage_events_agent ON agent_usage_events(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_events_service ON agent_usage_events(service, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_events_agent_service ON agent_usage_events(agent_id, service, created_at DESC);

-- ── 5. RLS policies (optional, prep for multi-tenant) ──────────────

ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_service_access ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_usage_events ENABLE ROW LEVEL SECURITY;

-- Service role can do everything (used by the API backend)
CREATE POLICY IF NOT EXISTS agents_service_all ON agents
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY IF NOT EXISTS agent_service_access_service_all ON agent_service_access
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY IF NOT EXISTS agent_usage_events_service_all ON agent_usage_events
    FOR ALL USING (true) WITH CHECK (true);
