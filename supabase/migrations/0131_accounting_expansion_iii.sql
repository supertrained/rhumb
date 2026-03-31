BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS idx_scores_service_slug_unique
ON scores (service_slug);

-- Migration 0131: Accounting discovery expansion III (2026-03-31)
-- Rationale: accounting is still too thin in the live catalog for a category
-- agents repeatedly need for invoice reads/writes, customer and vendor sync,
-- expense and bill review, payment-status checks, revenue reporting, and
-- bookkeeping-adjacent automation. Add five more API-backed providers with a
-- clear read-first Resolve path.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'freeagent',
    'FreeAgent',
    'accounting',
    'Cloud accounting platform with APIs for contacts, invoices, bills, bank transactions, projects, expenses, tax surfaces, and SMB bookkeeping workflows.',
    'https://dev.freeagent.com/',
    'api.freeagent.com'
  ),
  (
    'sage-intacct',
    'Sage Intacct',
    'accounting',
    'Cloud accounting and ERP platform with documented APIs for general ledger, AP, AR, vendors, customers, purchasing, cash management, and finance operations.',
    'https://developer.sage.com/intacct/',
    'api.intacct.com'
  ),
  (
    'business-central',
    'Microsoft Dynamics 365 Business Central',
    'accounting',
    'Business accounting and ERP platform with APIs for companies, customers, vendors, items, journal lines, sales invoices, purchase invoices, and finance reporting.',
    'https://learn.microsoft.com/en-us/dynamics365/business-central/dev-itpro/api-reference/v2.0/',
    'api.businesscentral.dynamics.com'
  ),
  (
    'myob',
    'MYOB',
    'accounting',
    'Business accounting platform with APIs for contacts, accounts, invoices, bills, tax codes, banking data, and operational bookkeeping workflows in SMB environments.',
    'https://developer.myob.com/api/myob-business-api/v2/overview/',
    'api.myob.com'
  ),
  (
    'odoo-accounting',
    'Odoo Accounting',
    'accounting',
    'Accounting module within Odoo with external APIs for partners, invoices, journal entries, payments, taxes, and ERP-adjacent finance automation.',
    'https://www.odoo.com/documentation/18.0/developer/reference/external_api.html',
    'odoo.com'
  )
ON CONFLICT (slug) DO NOTHING;

INSERT INTO scores (
  service_slug,
  aggregate_recommendation_score,
  execution_score,
  access_readiness_score,
  confidence,
  tier,
  tier_label,
  probe_metadata,
  calculated_at
)
VALUES
  (
    'freeagent',
    8.15,
    8.25,
    8.00,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"accounting expansion iii","notes":"Best immediate Phase 0 target in the batch. FreeAgent exposes clean customer, invoice, bill, and bank-transaction primitives that map directly to read-first accounting workflows without the heaviest enterprise setup burden."}'::jsonb,
    now()
  ),
  (
    'sage-intacct',
    8.10,
    8.20,
    7.95,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"accounting expansion iii","notes":"High strategic demand and broad finance-system coverage. Strong long-term Resolve target for invoice, vendor, and ledger reads, even if enterprise provisioning makes it a slightly heavier first execution lane than FreeAgent."}'::jsonb,
    now()
  ),
  (
    'business-central',
    8.05,
    8.15,
    7.90,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"accounting expansion iii","notes":"Important mid-market accounting and ERP anchor with explicit API objects for customers, vendors, invoices, and journals. Strong second-wave target after a lighter first provider lands."}'::jsonb,
    now()
  ),
  (
    'myob',
    7.85,
    7.95,
    7.70,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"accounting expansion iii","notes":"Practical SMB accounting depth with usable contact, invoice, and account surfaces. Valuable category coverage addition even if it is not the first provider to normalize."}'::jsonb,
    now()
  ),
  (
    'odoo-accounting',
    7.75,
    7.85,
    7.60,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"accounting expansion iii","notes":"Broad ERP-adjacent accounting surface with partner, invoice, payment, and journal primitives. Slightly more implementation-shaped than the leaders but still useful for catalog depth and future multi-step finance workflows."}'::jsonb,
    now()
  )
ON CONFLICT (service_slug) DO UPDATE SET
  aggregate_recommendation_score = EXCLUDED.aggregate_recommendation_score,
  execution_score = EXCLUDED.execution_score,
  access_readiness_score = EXCLUDED.access_readiness_score,
  confidence = EXCLUDED.confidence,
  tier = EXCLUDED.tier,
  tier_label = EXCLUDED.tier_label,
  probe_metadata = EXCLUDED.probe_metadata,
  calculated_at = EXCLUDED.calculated_at;

COMMIT;
