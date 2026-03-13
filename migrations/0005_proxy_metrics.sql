-- Migration: 0005_proxy_metrics
-- Description: Proxy latency metrics persistence table
-- Context: GAP-3c surfaced that proxy_latency.persist_to_supabase() writes to this table
-- but it didn't exist in production Supabase.

CREATE TABLE IF NOT EXISTS proxy_metrics (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service         TEXT NOT NULL,
    agent_id        TEXT NOT NULL,

    -- Latency percentiles (milliseconds)
    p50_ms          DOUBLE PRECISION,
    p95_ms          DOUBLE PRECISION,
    p99_ms          DOUBLE PRECISION,
    mean_ms         DOUBLE PRECISION,
    min_ms          DOUBLE PRECISION,
    max_ms          DOUBLE PRECISION,

    -- Counts
    call_count      INTEGER NOT NULL DEFAULT 0,
    error_count     INTEGER NOT NULL DEFAULT 0,

    -- Time window
    window_start    TEXT,           -- ISO timestamp string from LatencySnapshot
    window_end      TEXT,           -- ISO timestamp string from LatencySnapshot

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Performance indices
CREATE INDEX IF NOT EXISTS idx_proxy_metrics_service    ON proxy_metrics(service);
CREATE INDEX IF NOT EXISTS idx_proxy_metrics_agent      ON proxy_metrics(agent_id);
CREATE INDEX IF NOT EXISTS idx_proxy_metrics_created    ON proxy_metrics(created_at);
CREATE INDEX IF NOT EXISTS idx_proxy_metrics_svc_agent  ON proxy_metrics(service, agent_id);
