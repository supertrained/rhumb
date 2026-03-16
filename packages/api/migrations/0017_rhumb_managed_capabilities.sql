-- Migration 0017: Rhumb-managed capabilities table
-- Tracks which capabilities Rhumb can execute using its own credentials
-- Mode 2 in the three-credential-mode architecture

CREATE TABLE IF NOT EXISTS rhumb_managed_capabilities (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    capability_id TEXT NOT NULL REFERENCES capabilities(id),
    service_slug TEXT NOT NULL,
    description TEXT,
    -- Rhumb's own credential env var names (NOT the values)
    credential_env_keys TEXT[] NOT NULL DEFAULT '{}',
    -- Default request template for zero-config execution
    default_method TEXT NOT NULL DEFAULT 'POST',
    default_path TEXT NOT NULL,
    default_headers JSONB DEFAULT '{}',
    -- Limits and metering
    enabled BOOLEAN NOT NULL DEFAULT true,
    daily_limit_per_agent INT,  -- null = unlimited
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(capability_id, service_slug)
);

-- Index for catalog queries
CREATE INDEX IF NOT EXISTS idx_rhumb_managed_enabled
    ON rhumb_managed_capabilities(enabled) WHERE enabled = true;

-- RLS: read-only for anon/authenticated, full for service_role
ALTER TABLE rhumb_managed_capabilities ENABLE ROW LEVEL SECURITY;

CREATE POLICY "rhumb_managed_read" ON rhumb_managed_capabilities
    FOR SELECT USING (true);

CREATE POLICY "rhumb_managed_admin" ON rhumb_managed_capabilities
    FOR ALL USING (auth.role() = 'service_role');

COMMENT ON TABLE rhumb_managed_capabilities IS
    'Capabilities that Rhumb can execute using its own credentials (Mode 2). '
    'Agents get zero-config access — no BYO credentials needed.';
