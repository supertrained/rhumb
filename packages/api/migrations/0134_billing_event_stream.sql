-- WU-41.5: Billing pipeline upgrade — billing event stream table
--
-- Structured, chain-hashed event log for all billing activity.
-- Supports: execution charges, credit purchases, x402 settlements,
-- wallet top-ups, budget alerts, auto-reload triggers.
--
-- Immutable append-only table. No UPDATEs or DELETEs in normal operation.

CREATE TABLE IF NOT EXISTS billing_events (
    event_id            TEXT PRIMARY KEY,
    event_type          TEXT NOT NULL,
    org_id              TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    amount_usd_cents    INTEGER NOT NULL,
    balance_after_cents INTEGER,
    -- Linkage
    receipt_id          TEXT,
    execution_id        TEXT,
    capability_id       TEXT,
    provider_slug       TEXT,
    -- Context
    metadata            JSONB DEFAULT '{}',
    -- Chain integrity
    chain_hash          TEXT NOT NULL,
    prev_hash           TEXT NOT NULL
);

-- Primary query pattern: org events in reverse chronological order
CREATE INDEX IF NOT EXISTS idx_billing_events_org_time
    ON billing_events (org_id, created_at DESC);

-- Filter by event type
CREATE INDEX IF NOT EXISTS idx_billing_events_type
    ON billing_events (event_type, created_at DESC);

-- Provider-level billing aggregation
CREATE INDEX IF NOT EXISTS idx_billing_events_provider
    ON billing_events (provider_slug, created_at DESC)
    WHERE provider_slug IS NOT NULL;

-- Receipt linkage
CREATE INDEX IF NOT EXISTS idx_billing_events_receipt
    ON billing_events (receipt_id)
    WHERE receipt_id IS NOT NULL;

-- Chain verification (sequential walk)
CREATE INDEX IF NOT EXISTS idx_billing_events_chain
    ON billing_events (created_at ASC);

COMMENT ON TABLE billing_events IS 'Immutable chain-hashed billing event stream. Append-only. Feeds trust dashboard, ledger reconciliation, and usage analytics.';
