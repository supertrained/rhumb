-- Users table for dashboard and agent-facing auth users
-- Created: 2026-03-19
-- Part of WU-B1: Signup Flow

CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    name TEXT DEFAULT '',
    avatar_url TEXT DEFAULT '',

    -- Auth source and verification
    provider TEXT NOT NULL,           -- 'github' | 'google' | 'email'
    provider_id TEXT NOT NULL,        -- Provider-specific ID or email sentinel ID
    signup_method TEXT NOT NULL DEFAULT 'oauth',      -- 'oauth' | 'email_otp'
    email_verified_at TIMESTAMPTZ,
    signup_ip TEXT DEFAULT '',
    signup_subnet TEXT DEFAULT '',
    credit_policy TEXT NOT NULL DEFAULT 'oauth_trial',
    risk_flags JSONB NOT NULL DEFAULT '{}'::jsonb,

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
CREATE INDEX IF NOT EXISTS idx_users_signup_method ON users (signup_method);

-- RLS (Row Level Security) - service role bypasses, anon blocked
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (API uses service role key)
CREATE POLICY "Service role full access" ON users
    FOR ALL
    USING (true)
    WITH CHECK (true);
