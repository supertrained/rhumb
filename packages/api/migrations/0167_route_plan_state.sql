-- PP-16: Durable route-plan nonce, replay, and revocation state

CREATE TABLE IF NOT EXISTS route_plan_state (
    nonce_hash TEXT PRIMARY KEY,
    route_plan_id_hash TEXT,
    state TEXT NOT NULL DEFAULT 'claimed',
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    revocation_reason TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (state IN ('claimed', 'revoked'))
);

CREATE INDEX IF NOT EXISTS idx_route_plan_state_expires
    ON route_plan_state (expires_at);

CREATE INDEX IF NOT EXISTS idx_route_plan_state_state
    ON route_plan_state (state);

ALTER TABLE route_plan_state ENABLE ROW LEVEL SECURITY;
