-- WU-41.4: AN Score structural separation — audit chain table
--
-- Immutable append-only audit trail for all AN Score changes.
-- Chain-hashed so integrity can be verified programmatically.
-- This table is write-only for the scoring service and read-only
-- for all other consumers.

CREATE TABLE IF NOT EXISTS score_audit_chain (
    entry_id        TEXT PRIMARY KEY,
    service_slug    TEXT NOT NULL,
    old_score       REAL,
    new_score       REAL NOT NULL,
    change_reason   TEXT NOT NULL DEFAULT 'recalculation',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    chain_hash      TEXT NOT NULL,
    prev_hash       TEXT NOT NULL
);

-- Index for per-service history queries
CREATE INDEX IF NOT EXISTS idx_score_audit_chain_slug
    ON score_audit_chain (service_slug, created_at DESC);

-- Index for chain verification (sequential walk)
CREATE INDEX IF NOT EXISTS idx_score_audit_chain_created
    ON score_audit_chain (created_at ASC);

-- Score cache snapshot table — populated by scoring service refresh,
-- read by routing and explanation consumers.
-- This is the physical backing for the in-memory ScoreReadCache.
CREATE TABLE IF NOT EXISTS score_cache (
    service_slug              TEXT PRIMARY KEY,
    an_score                  REAL NOT NULL,
    execution_score           REAL NOT NULL DEFAULT 0.0,
    access_readiness_score    REAL,
    autonomy_score            REAL,
    confidence                REAL NOT NULL DEFAULT 0.5,
    tier                      TEXT NOT NULL DEFAULT 'L1',
    refreshed_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for routing queries (filter by tier / score range)
CREATE INDEX IF NOT EXISTS idx_score_cache_tier
    ON score_cache (tier, an_score DESC);

COMMENT ON TABLE score_audit_chain IS 'Immutable chain-hashed audit trail for AN Score changes. Write: scoring service only. Read: any consumer.';
COMMENT ON TABLE score_cache IS 'Read-only score snapshot for routing and explanation consumers. Write: scoring service refresh only.';
