-- AUD-3 follow-on: durable chain checkpoints / internal checkpoint ledger
--
-- Retention purges and future external anchoring need a durable, signed record
-- of chain heads before continuity is rewritten. This table stores checkpoint
-- records for append-only chains (starting with audit retention purges).
--
-- checkpoint_hash is an HMAC over the semantic checkpoint payload using the
-- active signing key version. It is intentionally independent from the source
-- stream's chain_hash so later external anchoring can publish either the source
-- head hash or the checkpoint hash without changing this schema.

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
