-- 0033: Align usdc_receipts with capability_execute.py x402 flow
-- Adds columns that the execute route inserts but 0032 didn't define

-- usdc_receipts: add missing columns
ALTER TABLE usdc_receipts ADD COLUMN IF NOT EXISTS amount_usd_cents INTEGER;
ALTER TABLE usdc_receipts ADD COLUMN IF NOT EXISTS org_id TEXT REFERENCES orgs(id);
ALTER TABLE usdc_receipts ADD COLUMN IF NOT EXISTS execution_id TEXT;
ALTER TABLE usdc_receipts ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'confirmed';

-- Index for org lookups on receipts
CREATE INDEX IF NOT EXISTS idx_usdc_receipts_org ON usdc_receipts(org_id) WHERE org_id IS NOT NULL;
