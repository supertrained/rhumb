-- Migration: 0004_provisioning_flows
-- Description: Provisioning flows table for multi-step service onboarding
-- Slice: Round 10 / Slice D

CREATE TABLE IF NOT EXISTS provisioning_flows (
    flow_id         UUID PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    service         TEXT NOT NULL,                  -- "stripe", "slack", etc
    flow_type       TEXT NOT NULL,                  -- "signup", "oauth", "payment", "tos", "confirmation"
    state           TEXT NOT NULL DEFAULT 'pending', -- "pending", "in_progress", "human_action_needed", "complete", "failed", "expired"

    payload         JSONB NOT NULL DEFAULT '{}',    -- {email, scopes, plan, tos_hash, etc}
    callback_data   JSONB,                          -- {oauth_code, payment_id, confirmation_token, etc}

    human_action_url TEXT,                          -- URL for human to click
    error_message    TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    retries         INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT fk_provisioning_agent FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);

-- Performance indices
CREATE INDEX IF NOT EXISTS idx_provisioning_flows_agent   ON provisioning_flows(agent_id);
CREATE INDEX IF NOT EXISTS idx_provisioning_flows_service ON provisioning_flows(service);
CREATE INDEX IF NOT EXISTS idx_provisioning_flows_state   ON provisioning_flows(state);
CREATE INDEX IF NOT EXISTS idx_provisioning_flows_expires ON provisioning_flows(expires_at);
CREATE INDEX IF NOT EXISTS idx_provisioning_flows_type    ON provisioning_flows(flow_type);

-- Composite index for common query pattern: agent + service + state
CREATE INDEX IF NOT EXISTS idx_provisioning_flows_agent_service_state
    ON provisioning_flows(agent_id, service, state);
