-- Migration 0020: Routing strategies + spend visibility
-- Phase 4, Round 20

-- Agent routing strategy preferences
CREATE TABLE IF NOT EXISTS agent_routing_strategies (
    id BIGSERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,
    strategy TEXT NOT NULL DEFAULT 'balanced' CHECK (strategy IN ('cheapest', 'fastest', 'highest_quality', 'balanced')),
    quality_floor NUMERIC(4, 2) NOT NULL DEFAULT 6.0,
    max_cost_per_call_usd NUMERIC(12, 4),
    weight_score NUMERIC(4, 2) NOT NULL DEFAULT 0.40,
    weight_cost NUMERIC(4, 2) NOT NULL DEFAULT 0.30,
    weight_health NUMERIC(4, 2) NOT NULL DEFAULT 0.30,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(agent_id)
);

-- RLS
ALTER TABLE agent_routing_strategies ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on agent_routing_strategies"
    ON agent_routing_strategies FOR ALL
    USING (true)
    WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_agent_routing_agent_id ON agent_routing_strategies(agent_id);

-- Free tier usage tracking per service
CREATE TABLE IF NOT EXISTS agent_free_tier_usage (
    id BIGSERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,
    service_slug TEXT NOT NULL,
    calls_used INTEGER NOT NULL DEFAULT 0,
    period_start TIMESTAMPTZ NOT NULL DEFAULT date_trunc('month', now()),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(agent_id, service_slug)
);

ALTER TABLE agent_free_tier_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on agent_free_tier_usage"
    ON agent_free_tier_usage FOR ALL
    USING (true)
    WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_free_tier_agent_service ON agent_free_tier_usage(agent_id, service_slug);
