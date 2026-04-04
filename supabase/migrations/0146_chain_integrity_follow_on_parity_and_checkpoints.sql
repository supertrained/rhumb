-- AUD-3 follow-on parity mirror for production Supabase
--
-- Mirrors the additive chain-integrity follow-ons that landed under
-- `packages/api/migrations/0156_score_audit_chain_key_version.sql`,
-- `packages/api/migrations/0157_chain_checkpoints.sql`, and
-- `packages/api/migrations/0158_durable_chain_key_version_columns.sql`.
--
-- Why mirrored here:
-- - Supabase production schema is ultimately managed from `supabase/migrations/`
-- - the package-level follow-on SQL landed after the existing mirror spine
-- - production drifted until these additive changes were applied manually on 2026-04-04
--
-- Keep this file additive + idempotent so it is safe on already-remediated DBs.

ALTER TABLE IF EXISTS score_audit_chain
    ADD COLUMN IF NOT EXISTS key_version INTEGER;

COMMENT ON COLUMN score_audit_chain.key_version IS
    'Signing key version used to compute chain_hash; NULL for legacy pre-rotation rows.';

CREATE TABLE IF NOT EXISTS chain_checkpoints (
    checkpoint_id        TEXT PRIMARY KEY,
    stream_name          TEXT NOT NULL,
    reason               TEXT NOT NULL,
    source_head_hash     TEXT NOT NULL,
    source_head_sequence BIGINT,
    source_key_version   INTEGER,
    checkpoint_hash      TEXT NOT NULL,
    key_version          INTEGER,
    metadata             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chain_checkpoints_stream_created
    ON chain_checkpoints (stream_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chain_checkpoints_reason_created
    ON chain_checkpoints (reason, created_at DESC);

COMMENT ON TABLE chain_checkpoints IS
    'Durable signed checkpoint ledger for chain heads before purge/rechain or external anchoring.';

COMMENT ON COLUMN chain_checkpoints.checkpoint_hash IS
    'HMAC over the semantic checkpoint payload using key_version.';

ALTER TABLE IF EXISTS billing_events
    ADD COLUMN IF NOT EXISTS key_version INTEGER;

ALTER TABLE IF EXISTS audit_events
    ADD COLUMN IF NOT EXISTS key_version INTEGER;

COMMENT ON COLUMN billing_events.key_version IS
    'Signing key version used to compute chain_hash; NULL for legacy rows.';

COMMENT ON COLUMN audit_events.key_version IS
    'Signing key version used to compute chain_hash; NULL for legacy rows.';
