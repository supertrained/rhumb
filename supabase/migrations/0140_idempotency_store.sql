-- AUD-4: Durable idempotency store for recipe executions
-- Prevents duplicate execution/double-charge across restarts and workers

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    recipe_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result_hash TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    org_id TEXT,
    agent_id TEXT
);

-- Index for cleanup of expired entries
CREATE INDEX IF NOT EXISTS idx_idempotency_keys_expires
    ON idempotency_keys (expires_at);

-- Index for org-scoped queries
CREATE INDEX IF NOT EXISTS idx_idempotency_keys_org
    ON idempotency_keys (org_id, created_at DESC);

-- RLS
ALTER TABLE idempotency_keys ENABLE ROW LEVEL SECURITY;

-- Atomic claim function: INSERT if not exists, return existing if it does
-- This prevents TOCTOU races between check() and execute()
CREATE OR REPLACE FUNCTION idempotency_claim(
    p_key TEXT,
    p_execution_id TEXT,
    p_recipe_id TEXT,
    p_status TEXT DEFAULT 'pending',
    p_result_hash TEXT DEFAULT '',
    p_expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '1 hour',
    p_org_id TEXT DEFAULT NULL,
    p_agent_id TEXT DEFAULT NULL
) RETURNS TABLE (
    key TEXT,
    execution_id TEXT,
    recipe_id TEXT,
    status TEXT,
    result_hash TEXT,
    created_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    already_exists BOOLEAN
) LANGUAGE plpgsql AS $$
BEGIN
    -- Try to insert
    BEGIN
        INSERT INTO idempotency_keys (key, execution_id, recipe_id, status, result_hash, expires_at, org_id, agent_id)
        VALUES (p_key, p_execution_id, p_recipe_id, p_status, p_result_hash, p_expires_at, p_org_id, p_agent_id);

        RETURN QUERY SELECT
            p_key, p_execution_id, p_recipe_id, p_status, p_result_hash,
            NOW(), p_expires_at, FALSE;
        RETURN;
    EXCEPTION WHEN unique_violation THEN
        -- Key already exists — return the existing row
        RETURN QUERY SELECT
            ik.key, ik.execution_id, ik.recipe_id, ik.status, ik.result_hash,
            ik.created_at, ik.expires_at, TRUE
        FROM idempotency_keys ik
        WHERE ik.key = p_key AND ik.expires_at > NOW();

        -- If the existing row was expired, delete it and retry
        IF NOT FOUND THEN
            DELETE FROM idempotency_keys WHERE idempotency_keys.key = p_key AND idempotency_keys.expires_at <= NOW();
            INSERT INTO idempotency_keys (key, execution_id, recipe_id, status, result_hash, expires_at, org_id, agent_id)
            VALUES (p_key, p_execution_id, p_recipe_id, p_status, p_result_hash, p_expires_at, p_org_id, p_agent_id);

            RETURN QUERY SELECT
                p_key, p_execution_id, p_recipe_id, p_status, p_result_hash,
                NOW(), p_expires_at, FALSE;
        END IF;
    END;
END;
$$;
