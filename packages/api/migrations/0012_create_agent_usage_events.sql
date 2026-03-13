-- GAP-3: Create agent_usage_events table (repo truth).
--
-- Previous migrations ALTER this table but no CREATE exists in repo.
-- Use IF NOT EXISTS so deploys with a hand-created table are safe.

CREATE TABLE IF NOT EXISTS agent_usage_events (
    event_id       UUID PRIMARY KEY,
    agent_id       TEXT NOT NULL,
    service        TEXT NOT NULL,
    result         TEXT NOT NULL,              -- success | error | rate_limited | auth_failed
    latency_ms     DOUBLE PRECISION NOT NULL,
    response_size_bytes BIGINT NOT NULL DEFAULT 0,
    created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Query indexes
CREATE INDEX IF NOT EXISTS idx_agent_usage_events_agent_created
    ON agent_usage_events (agent_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_usage_events_service_created
    ON agent_usage_events (service, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_usage_events_created
    ON agent_usage_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_usage_events_agent_service_created
    ON agent_usage_events (agent_id, service, created_at DESC);
