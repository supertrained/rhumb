-- Migration 0019: Agent budgets for cost-aware execution
-- Phase 4, Round 19: Budget enforcement

-- Agent budget table
CREATE TABLE IF NOT EXISTS agent_budgets (
    id BIGSERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,
    budget_usd NUMERIC(12, 4) NOT NULL DEFAULT 0,
    spent_usd NUMERIC(12, 4) NOT NULL DEFAULT 0,
    period TEXT NOT NULL DEFAULT 'monthly' CHECK (period IN ('daily', 'weekly', 'monthly', 'total')),
    period_start TIMESTAMPTZ NOT NULL DEFAULT date_trunc('month', now()),
    hard_limit BOOLEAN NOT NULL DEFAULT true,
    alert_threshold_pct INTEGER NOT NULL DEFAULT 80,
    alert_fired BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(agent_id)
);

-- RLS
ALTER TABLE agent_budgets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on agent_budgets"
    ON agent_budgets FOR ALL
    USING (true)
    WITH CHECK (true);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_agent_budgets_agent_id ON agent_budgets(agent_id);

-- Atomic check-and-decrement function
-- Returns: remaining_usd after deduction, or -1 if insufficient budget (hard limit)
-- On soft limit (hard_limit=false), always deducts and returns remaining (can go negative)
CREATE OR REPLACE FUNCTION check_and_decrement_budget(
    p_agent_id TEXT,
    p_cost NUMERIC(12, 4)
) RETURNS NUMERIC AS $$
DECLARE
    v_remaining NUMERIC;
    v_hard BOOLEAN;
    v_budget_usd NUMERIC;
    v_spent NUMERIC;
    v_threshold INTEGER;
    v_alert_fired BOOLEAN;
BEGIN
    -- Atomic update with check
    UPDATE agent_budgets
    SET spent_usd = spent_usd + p_cost,
        updated_at = now()
    WHERE agent_id = p_agent_id
      AND (NOT hard_limit OR (budget_usd - spent_usd) >= p_cost)
    RETURNING budget_usd - spent_usd, hard_limit, budget_usd, spent_usd, alert_threshold_pct, alert_fired
    INTO v_remaining, v_hard, v_budget_usd, v_spent, v_threshold, v_alert_fired;

    -- If no row updated, check why
    IF NOT FOUND THEN
        -- Check if agent has a budget at all
        SELECT hard_limit, budget_usd, spent_usd
        INTO v_hard, v_budget_usd, v_spent
        FROM agent_budgets
        WHERE agent_id = p_agent_id;

        IF NOT FOUND THEN
            -- No budget configured = unlimited (return a large sentinel)
            RETURN 999999.0;
        END IF;

        -- Budget exists but insufficient (hard limit blocked it)
        RETURN -1;
    END IF;

    -- Fire alert if threshold crossed and not already fired
    IF NOT v_alert_fired AND v_budget_usd > 0 AND
       (v_spent / v_budget_usd * 100) >= v_threshold THEN
        UPDATE agent_budgets
        SET alert_fired = true
        WHERE agent_id = p_agent_id;
    END IF;

    RETURN v_remaining;
END;
$$ LANGUAGE plpgsql;

-- Budget release function (on execution failure)
CREATE OR REPLACE FUNCTION release_budget(
    p_agent_id TEXT,
    p_cost NUMERIC(12, 4)
) RETURNS NUMERIC AS $$
DECLARE
    v_remaining NUMERIC;
BEGIN
    UPDATE agent_budgets
    SET spent_usd = GREATEST(0, spent_usd - p_cost),
        updated_at = now()
    WHERE agent_id = p_agent_id
    RETURNING budget_usd - spent_usd
    INTO v_remaining;

    IF NOT FOUND THEN
        RETURN 999999.0;
    END IF;

    RETURN v_remaining;
END;
$$ LANGUAGE plpgsql;

-- Budget period reset function (called by cron or application)
CREATE OR REPLACE FUNCTION reset_expired_budgets() RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    UPDATE agent_budgets
    SET spent_usd = 0,
        alert_fired = false,
        period_start = CASE
            WHEN period = 'daily' THEN date_trunc('day', now())
            WHEN period = 'weekly' THEN date_trunc('week', now())
            WHEN period = 'monthly' THEN date_trunc('month', now())
            ELSE period_start  -- 'total' never resets
        END,
        updated_at = now()
    WHERE period != 'total'
      AND CASE
          WHEN period = 'daily' THEN period_start < date_trunc('day', now())
          WHEN period = 'weekly' THEN period_start < date_trunc('week', now())
          WHEN period = 'monthly' THEN period_start < date_trunc('month', now())
          ELSE false
      END;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;
