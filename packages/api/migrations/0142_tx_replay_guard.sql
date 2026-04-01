-- AUD-25: Durable transaction replay prevention
-- Persists tx_hash claims across restarts and workers

CREATE TABLE IF NOT EXISTS tx_replay_guard (
    tx_hash TEXT PRIMARY KEY,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tx_replay_guard_expires
    ON tx_replay_guard (expires_at);

ALTER TABLE tx_replay_guard ENABLE ROW LEVEL SECURITY;
