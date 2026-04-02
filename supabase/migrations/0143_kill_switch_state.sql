-- AUD-1: Durable kill switch state
-- Persists active kill switches across restarts

CREATE TABLE IF NOT EXISTS kill_switch_state (
    switch_key TEXT PRIMARY KEY,
    switch_id TEXT NOT NULL,
    level TEXT NOT NULL,
    target TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'killed',
    reason TEXT NOT NULL DEFAULT '',
    activated_by TEXT NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    restoration_phase TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE kill_switch_state ENABLE ROW LEVEL SECURITY;
