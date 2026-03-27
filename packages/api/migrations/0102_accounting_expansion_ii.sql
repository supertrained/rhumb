BEGIN;

-- Migration 0102: Accounting discovery expansion (2026-03-27)
-- Rationale: accounting is a high-demand operator category for agents, but the
-- catalog only had 5 providers. Add 5 more with broad SME + enterprise +
-- international coverage and mark the strongest Phase 0 wedge in metadata.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'xero',
    'Xero',
    'accounting',
    'Cloud accounting platform with APIs for invoices, bills, contacts, bank transactions, reports, and financial operations workflows.',
    'https://developer.xero.com/documentation/api/accounting/overview',
    'api.xero.com'
  ),
  (
    'sage-intacct',
    'Sage Intacct',
    'accounting',
    'Enterprise accounting and financial management platform with REST and XML APIs for GL, AP, AR, vendors, customers, and operational finance automation.',
    'https://developer.sage.com/intacct/docs/1/sage-intacct-rest-api/get-started',
    'api.intacct.com'
  ),
  (
    'freeagent',
    'FreeAgent',
    'accounting',
    'Small-business accounting API covering contacts, invoices, bills, bank transactions, projects, and bookkeeping workflows.',
    'https://dev.freeagent.com/docs',
    'api.freeagent.com'
  ),
  (
    'myob',
    'MYOB',
    'accounting',
    'Accounting and business platform with APIs for company files, contacts, sales, purchases, ledger data, and finance operations in APAC-heavy markets.',
    'https://developer.myob.com/api/myob-business-api/api-overview',
    'api.myob.com'
  ),
  (
    'wave',
    'Wave',
    'accounting',
    'SMB accounting and invoicing platform with developer-accessible GraphQL APIs for customer, invoice, payment, and bookkeeping-adjacent workflows.',
    'https://developer.waveapps.com/hc/en-us/articles/360019968212-API-Reference',
    'gql.waveapps.com'
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
    'xero',
    8.15,
    8.40,
    7.90,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"accounting expansion","notes":"Best Phase 0 candidate in the batch. Cleanest wedge for normalized invoice.list, contact.list, and bill surfaces with strong real-world operator demand."}'::jsonb,
    now()
  ),
  (
    'sage-intacct',
    7.85,
    8.05,
    7.55,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"accounting expansion","notes":"Enterprise-grade finance API with strong long-term utility for AR/AP and ledger-adjacent workflows, though heavier than Xero for a first Resolve target."}'::jsonb,
    now()
  ),
  (
    'freeagent',
    7.55,
    7.75,
    7.30,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"accounting expansion","notes":"Practical SMB accounting API with good invoice/contact coverage and a favorable read-first Phase 0 profile."}'::jsonb,
    now()
  ),
  (
    'myob',
    7.40,
    7.60,
    7.15,
    0.55,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"accounting expansion","notes":"Useful regional breadth expansion for APAC accounting operations. Strong enough to catalog now even if not the very first Resolve target."}'::jsonb,
    now()
  ),
  (
    'wave',
    7.10,
    6.95,
    7.20,
    0.54,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"accounting expansion","notes":"Relevant SMB/free accounting product with lighter API posture. Worth discovery coverage, but weaker than Xero and FreeAgent for Phase 0 execution normalization."}'::jsonb,
    now()
  );

COMMIT;