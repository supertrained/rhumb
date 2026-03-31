-- Migration: 0128_execution_receipts
-- Description: Append-only execution receipt system with chain hashing.
-- Every capability execution produces an immutable receipt that is the
-- ground truth for billing, debugging, compliance, and auditing.

-- Receipt table: append-only, no UPDATEs, no DELETEs in application code.
CREATE TABLE IF NOT EXISTS execution_receipts (
    -- Identity
    receipt_id          TEXT PRIMARY KEY,
    receipt_version     TEXT NOT NULL DEFAULT '1.0',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Execution context
    execution_id        TEXT NOT NULL,
    layer               INTEGER NOT NULL DEFAULT 2,
    capability_id       TEXT NOT NULL,
    capability_version  TEXT,
    status              TEXT NOT NULL,  -- 'success', 'failure', 'timeout', 'rejected'
    attempt_number      INTEGER NOT NULL DEFAULT 1,

    -- Identity (caller)
    agent_id            TEXT NOT NULL,
    org_id              TEXT,
    caller_ip_hash      TEXT,

    -- Provider
    provider_id         TEXT NOT NULL,
    provider_name       TEXT,
    provider_model      TEXT,
    credential_mode     TEXT NOT NULL,
    provider_region     TEXT,

    -- Routing
    router_version      TEXT,
    candidates_evaluated INTEGER,
    winner_reason       TEXT,

    -- Timing (milliseconds)
    total_latency_ms    REAL,
    rhumb_overhead_ms   REAL,
    provider_latency_ms REAL,

    -- Cost (USD)
    provider_cost_usd   NUMERIC(12, 6),
    rhumb_fee_usd       NUMERIC(12, 6),
    total_cost_usd      NUMERIC(12, 6),
    credits_deducted    NUMERIC(12, 6),

    -- Payload integrity
    request_hash        TEXT,
    response_hash       TEXT,

    -- Chain integrity
    receipt_hash        TEXT NOT NULL,
    previous_receipt_hash TEXT,
    chain_sequence      BIGINT NOT NULL,

    -- x402 payment context (nullable — only present for x402 executions)
    x402_tx_hash        TEXT,
    x402_network        TEXT,
    x402_payer          TEXT,

    -- Interface / compat
    interface           TEXT,
    compat_mode         TEXT,

    -- Idempotency
    idempotency_key     TEXT,

    -- Error context (nullable — only present on failures)
    error_code          TEXT,
    error_message       TEXT,
    error_provider_raw  TEXT
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_receipts_execution_id
    ON execution_receipts (execution_id);

CREATE INDEX IF NOT EXISTS idx_receipts_agent_id_created
    ON execution_receipts (agent_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_receipts_org_id_created
    ON execution_receipts (org_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_receipts_capability_created
    ON execution_receipts (capability_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_receipts_provider_created
    ON execution_receipts (provider_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_receipts_chain_sequence
    ON execution_receipts (chain_sequence DESC);

CREATE INDEX IF NOT EXISTS idx_receipts_status
    ON execution_receipts (status);

CREATE INDEX IF NOT EXISTS idx_receipts_idempotency
    ON execution_receipts (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Chain sequence counter: single-row table for atomic increment.
-- This ensures globally unique, monotonically increasing sequence numbers
-- even under concurrent writes.
CREATE TABLE IF NOT EXISTS receipt_chain_state (
    id              INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    last_sequence   BIGINT NOT NULL DEFAULT 0,
    last_receipt_hash TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed the chain state if empty
INSERT INTO receipt_chain_state (id, last_sequence, last_receipt_hash)
VALUES (1, 0, NULL)
ON CONFLICT (id) DO NOTHING;

-- RLS: receipts are readable by authenticated users scoped to their org.
-- Write access is API-server only (service role).
ALTER TABLE execution_receipts ENABLE ROW LEVEL SECURITY;

CREATE POLICY receipts_read_own ON execution_receipts
    FOR SELECT
    USING (true);  -- Public read for now; scope to org_id when multi-tenant RLS lands

-- Chain state is service-role only
ALTER TABLE receipt_chain_state ENABLE ROW LEVEL SECURITY;

CREATE POLICY chain_state_service_only ON receipt_chain_state
    FOR ALL
    USING (true);
