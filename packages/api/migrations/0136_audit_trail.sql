-- Migration 0136: Audit trail (WU-42.5)
-- Append-only, chain-hashed audit log for SOC2 preparation.
-- 15 event types across execution, security, governance, billing, trust, identity.

CREATE TABLE IF NOT EXISTS audit_events (
    event_id        TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    category        TEXT NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Who / what
    org_id          TEXT,
    agent_id        TEXT,
    principal       TEXT,
    -- Resource
    resource_type   TEXT,
    resource_id     TEXT,
    action          TEXT NOT NULL,
    detail          JSONB NOT NULL DEFAULT '{}',
    -- Linkage
    receipt_id      TEXT,
    execution_id    TEXT,
    provider_slug   TEXT,
    -- Chain integrity
    chain_sequence  BIGINT NOT NULL UNIQUE,
    chain_hash      TEXT NOT NULL,
    prev_hash       TEXT NOT NULL
);

-- No UPDATE or DELETE triggers — append-only enforced at application level.
-- RLS and pg policies can additionally enforce immutability in production.

-- Query indexes
CREATE INDEX IF NOT EXISTS idx_audit_events_org_id_timestamp
    ON audit_events (org_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_event_type
    ON audit_events (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_events_severity
    ON audit_events (severity);
CREATE INDEX IF NOT EXISTS idx_audit_events_category
    ON audit_events (category);
CREATE INDEX IF NOT EXISTS idx_audit_events_chain_sequence
    ON audit_events (chain_sequence);
CREATE INDEX IF NOT EXISTS idx_audit_events_resource
    ON audit_events (resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_receipt_id
    ON audit_events (receipt_id)
    WHERE receipt_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_events_execution_id
    ON audit_events (execution_id)
    WHERE execution_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp
    ON audit_events (timestamp DESC);

-- Chain state tracker (single row, like receipt_chain_state)
CREATE TABLE IF NOT EXISTS audit_chain_state (
    id              INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    latest_sequence BIGINT NOT NULL DEFAULT 0,
    latest_hash     TEXT NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO audit_chain_state (id, latest_sequence, latest_hash)
VALUES (1, 0, '0000000000000000000000000000000000000000000000000000000000000000')
ON CONFLICT (id) DO NOTHING;

-- Enable RLS (public read for authenticated orgs, service-role write)
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
