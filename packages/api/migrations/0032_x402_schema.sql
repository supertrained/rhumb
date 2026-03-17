-- Track every x402 payment request issued
CREATE TABLE IF NOT EXISTS payment_requests (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id               TEXT REFERENCES orgs(id),
  capability_id        TEXT NOT NULL,
  execution_id         TEXT,
  amount_usdc_atomic   TEXT NOT NULL,   -- USDC in atomic units (string to avoid overflow)
  amount_usd_cents     INTEGER NOT NULL,
  network              TEXT NOT NULL,   -- 'base-mainnet' | 'base-sepolia'
  pay_to_address       TEXT NOT NULL,   -- Rhumb receive wallet
  asset_address        TEXT NOT NULL,   -- USDC contract address
  status               TEXT NOT NULL DEFAULT 'pending',
    -- 'pending' | 'payment_received' | 'verified' | 'expired' | 'failed'
  payment_tx_hash      TEXT,            -- on-chain transaction hash
  verified_at          TIMESTAMPTZ,
  expires_at           TIMESTAMPTZ NOT NULL DEFAULT now() + interval '5 minutes',
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_payment_requests_status ON payment_requests(status, created_at);
CREATE INDEX idx_payment_requests_org ON payment_requests(org_id);
CREATE INDEX idx_payment_requests_tx_hash ON payment_requests(payment_tx_hash) WHERE payment_tx_hash IS NOT NULL;

-- Track confirmed USDC receipts
CREATE TABLE IF NOT EXISTS usdc_receipts (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_request_id    UUID REFERENCES payment_requests(id),
  tx_hash               TEXT NOT NULL UNIQUE,
  network               TEXT NOT NULL,
  from_address          TEXT NOT NULL,
  to_address            TEXT NOT NULL,
  amount_usdc_atomic    TEXT NOT NULL,
  block_number          BIGINT,
  confirmed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  settled               BOOLEAN NOT NULL DEFAULT false,
  settled_at            TIMESTAMPTZ,
  settlement_batch_id   UUID
);

CREATE INDEX idx_usdc_receipts_tx ON usdc_receipts(tx_hash);
CREATE INDEX idx_usdc_receipts_unsettled ON usdc_receipts(settled, confirmed_at) WHERE settled = false;

-- Settlement batches (daily USDC → USD conversion)
CREATE TABLE IF NOT EXISTS settlement_batches (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_date             DATE NOT NULL UNIQUE,
  total_usdc_atomic      TEXT NOT NULL DEFAULT '0',
  total_usd_cents        INTEGER,
  status                 TEXT NOT NULL DEFAULT 'pending',
    -- 'pending' | 'converting' | 'complete' | 'failed'
  coinbase_conversion_id TEXT,
  converted_at           TIMESTAMPTZ,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Add settlement FK now that table exists
ALTER TABLE usdc_receipts ADD CONSTRAINT fk_usdc_receipts_settlement
  FOREIGN KEY (settlement_batch_id) REFERENCES settlement_batches(id);

-- RLS policies (service role access)
ALTER TABLE payment_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE usdc_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE settlement_batches ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on payment_requests"
  ON payment_requests FOR ALL
  USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on usdc_receipts"
  ON usdc_receipts FOR ALL
  USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on settlement_batches"
  ON settlement_batches FOR ALL
  USING (auth.role() = 'service_role');
