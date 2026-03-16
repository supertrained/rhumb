-- Capability execution log
-- Tracks every capability execution through the proxy layer.

CREATE TABLE capability_executions (
    id TEXT PRIMARY KEY DEFAULT 'exec_' || replace(gen_random_uuid()::text, '-', ''),
    agent_id TEXT NOT NULL,
    capability_id TEXT NOT NULL REFERENCES capabilities(id),
    provider_used TEXT NOT NULL,
    credential_mode TEXT NOT NULL DEFAULT 'byo',
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    upstream_status INTEGER,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    cost_estimate_usd NUMERIC,
    total_latency_ms NUMERIC,
    upstream_latency_ms NUMERIC,
    fallback_attempted BOOLEAN DEFAULT FALSE,
    fallback_provider TEXT,
    idempotency_key TEXT,
    error_message TEXT,
    executed_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_cap_exec_agent ON capability_executions(agent_id);
CREATE INDEX idx_cap_exec_capability ON capability_executions(capability_id);
CREATE INDEX idx_cap_exec_time ON capability_executions(executed_at DESC);
CREATE INDEX idx_cap_exec_idempotency ON capability_executions(idempotency_key) WHERE idempotency_key IS NOT NULL;

ALTER TABLE capability_executions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "cap_exec_service_role" ON capability_executions FOR ALL USING (current_role = 'service_role');
