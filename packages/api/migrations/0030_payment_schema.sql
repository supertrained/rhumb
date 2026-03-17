-- Payment System Phase 0: Orgs, Credits, Ledger
-- Establishes billing entity, credit balance, and immutable event-sourced ledger.
-- Part of WU-0.1 from docs/BUILD-PLAN-PAYMENT-SYSTEM.md

-- Billing entity: one per developer account / org
CREATE TABLE IF NOT EXISTS orgs (
  id             TEXT PRIMARY KEY,
  name           TEXT NOT NULL,
  email          TEXT NOT NULL,
  tier           TEXT NOT NULL DEFAULT 'free',  -- 'free' | 'startup' | 'enterprise'
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Credit wallet: one per org
CREATE TABLE IF NOT EXISTS org_credits (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id                      TEXT NOT NULL UNIQUE REFERENCES orgs(id) ON DELETE CASCADE,
  balance_usd_cents           BIGINT NOT NULL DEFAULT 0 CHECK (balance_usd_cents >= 0),
  reserved_usd_cents          BIGINT NOT NULL DEFAULT 0 CHECK (reserved_usd_cents >= 0),
  auto_reload_enabled         BOOLEAN NOT NULL DEFAULT false,
  auto_reload_threshold_cents BIGINT,
  auto_reload_amount_cents    BIGINT,
  stripe_payment_method_id    TEXT,
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Immutable event-sourced ledger: every money movement recorded here
CREATE TABLE IF NOT EXISTS credit_ledger (
  id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id                     TEXT NOT NULL REFERENCES orgs(id),
  event_type                 TEXT NOT NULL,
    -- 'credit_added'          | top-up via Stripe
    -- 'debit'                 | capability execution cost
    -- 'reservation'           | pre-execution hold
    -- 'reservation_released'  | refund of unused reservation
    -- 'auto_reload_triggered' | auto-reload fired
    -- 'refund'                | manual or system refund
  amount_usd_cents           BIGINT NOT NULL,          -- positive = credit, negative = debit
  balance_after_usd_cents    BIGINT NOT NULL,          -- snapshot of balance after this event
  capability_execution_id    TEXT REFERENCES capability_executions(id),
  stripe_payment_intent_id   TEXT,
  stripe_checkout_session_id TEXT,
  description                TEXT,
  metadata                   JSONB,
  created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for fast queries
CREATE INDEX idx_credit_ledger_org_id_created ON credit_ledger(org_id, created_at DESC);
CREATE INDEX idx_credit_ledger_execution ON credit_ledger(capability_execution_id)
  WHERE capability_execution_id IS NOT NULL;

-- Link orgs to Stripe customers
CREATE TABLE IF NOT EXISTS stripe_customers (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id             TEXT NOT NULL UNIQUE REFERENCES orgs(id),
  stripe_customer_id TEXT NOT NULL UNIQUE,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Extend capability_executions with billing columns
ALTER TABLE capability_executions
  ADD COLUMN IF NOT EXISTS cost_usd_cents        INTEGER,
  ADD COLUMN IF NOT EXISTS upstream_cost_cents    INTEGER,
  ADD COLUMN IF NOT EXISTS margin_cents           INTEGER,
  ADD COLUMN IF NOT EXISTS billing_status         TEXT DEFAULT 'unbilled';
    -- 'unbilled' | 'reserved' | 'billed' | 'refunded'

-- RLS: service_role only on new tables (matches existing pattern)
ALTER TABLE orgs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "orgs_service_role" ON orgs FOR ALL USING (current_role = 'service_role');

ALTER TABLE org_credits ENABLE ROW LEVEL SECURITY;
CREATE POLICY "org_credits_service_role" ON org_credits FOR ALL USING (current_role = 'service_role');

ALTER TABLE credit_ledger ENABLE ROW LEVEL SECURITY;
CREATE POLICY "credit_ledger_service_role" ON credit_ledger FOR ALL USING (current_role = 'service_role');
-- Ledger immutability: no updates allowed
CREATE POLICY "credit_ledger_no_update" ON credit_ledger FOR UPDATE USING (false);

ALTER TABLE stripe_customers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "stripe_customers_service_role" ON stripe_customers FOR ALL USING (current_role = 'service_role');
