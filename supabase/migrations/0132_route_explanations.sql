-- Route Explanations table (WU-41.3)
--
-- Stores the full routing explanation for every Layer 2 execution.
-- Linked to the receipt chain via receipt_id.
-- explanation_id is globally unique (rexp_<hex>).
-- candidates_json stores the full scored candidate list as JSON.

CREATE TABLE IF NOT EXISTS route_explanations (
    explanation_id   TEXT PRIMARY KEY,
    receipt_id       TEXT,
    capability_id    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Winner
    winner_provider_id    TEXT,
    winner_composite_score NUMERIC(10,6),
    winner_reason          TEXT,

    -- Full candidate evaluation (stored as JSON for flexibility)
    candidates_json  JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Human summary
    human_summary    TEXT,

    -- Evaluation timing
    evaluation_ms    NUMERIC(10,2)
);

-- Index for the primary access pattern: look up explanation by receipt
CREATE INDEX IF NOT EXISTS idx_route_explanations_receipt_id
    ON route_explanations (receipt_id);

-- Index for capability-level analysis
CREATE INDEX IF NOT EXISTS idx_route_explanations_capability_id
    ON route_explanations (capability_id);

-- Index for winner analysis
CREATE INDEX IF NOT EXISTS idx_route_explanations_winner
    ON route_explanations (winner_provider_id);
