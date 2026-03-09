-- Round 12 (WU 2.3): Metering + Billing pipeline

-- Extend usage events with payload size for billing analytics.
ALTER TABLE agent_usage_events
ADD COLUMN IF NOT EXISTS response_size_bytes BIGINT DEFAULT 0;

-- Organization-level invoices.
CREATE TABLE IF NOT EXISTS invoices (
    invoice_id UUID PRIMARY KEY,
    organization_id TEXT NOT NULL,
    month TEXT NOT NULL,
    subtotal DECIMAL(12, 6) NOT NULL,
    tax DECIMAL(12, 6) NOT NULL,
    total DECIMAL(12, 6) NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    stripe_invoice_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    due_at TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (organization_id, month)
);

-- Organization billing fields.
ALTER TABLE organizations
ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
ADD COLUMN IF NOT EXISTS monthly_spend_cap_usd DECIMAL(12, 2) DEFAULT 100.0;

-- Invoice query performance indexes.
CREATE INDEX IF NOT EXISTS idx_invoices_org_month ON invoices (organization_id, month);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices (status);
