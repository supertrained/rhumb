-- Migration: 0003_agent_identity
-- Description: Agent identity table for proxy credential injection & rate limiting
-- Slice: Round 10 / Slice C

CREATE TABLE IF NOT EXISTS agents (
    agent_id    TEXT PRIMARY KEY,
    operator_id TEXT NOT NULL,
    allowed_services TEXT[] NOT NULL,           -- e.g. ARRAY['stripe','slack']
    rate_limit_qpm  INTEGER NOT NULL DEFAULT 100,
    api_token   TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_agents_api_token ON agents(api_token);
CREATE INDEX IF NOT EXISTS idx_agents_operator  ON agents(operator_id);

-- Seed initial agents
INSERT INTO agents (agent_id, operator_id, allowed_services, rate_limit_qpm, api_token)
VALUES
    ('rhumb-lead', 'tom', ARRAY['stripe','slack','github','twilio','sendgrid'], 500, 'rhumb_lead_token_xyz'),
    ('codex',      'tom', ARRAY['stripe','slack','github','twilio','sendgrid'], 200, 'codex_token_abc'),
    ('snowy',      'tom', ARRAY['stripe','slack'],                              100, 'snowy_token_def')
ON CONFLICT (agent_id) DO NOTHING;
