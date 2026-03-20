-- Users table for OAuth-authenticated human users
-- Created: 2026-03-19
-- Part of WU-B1: Signup Flow

CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    name TEXT DEFAULT '',
    avatar_url TEXT DEFAULT '',

    -- OAuth provider info
    provider TEXT NOT NULL,           -- 'github' | 'google'
    provider_id TEXT NOT NULL,        -- Provider-specific user ID

    -- Linked Rhumb resources
    organization_id TEXT DEFAULT '',
    default_agent_id TEXT DEFAULT '',  -- References agents.agent_id

    -- Status
    status TEXT DEFAULT 'active',     -- 'active' | 'disabled'
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    -- Unique constraints
    CONSTRAINT unique_provider_id UNIQUE (provider, provider_id),
    CONSTRAINT unique_email UNIQUE (email)
);

-- Index for API lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_provider ON users (provider, provider_id);

-- RLS (Row Level Security) - service role bypasses, anon blocked
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (API uses service role key)
CREATE POLICY "Service role full access" ON users
    FOR ALL
    USING (true)
    WITH CHECK (true);
