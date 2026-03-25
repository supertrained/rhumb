BEGIN;

-- Migration 0089: Accounting discovery expansion (2026-03-25)
-- Rationale: accounting was effectively absent as a first-class category despite being
-- one of the highest-demand operational surfaces for real agent workflows.
-- Add 5 widely-used accounting / AP-AR providers with initial AN scoring.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'quickbooks',
    'QuickBooks',
    'accounting',
    'SMB accounting and bookkeeping platform with APIs for invoices, customers, payments, chart of accounts, reports, and bookkeeping workflows via QuickBooks Online.',
    'https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/account',
    'quickbooks.api.intuit.com'
  ),
  (
    'freshbooks',
    'FreshBooks',
    'accounting',
    'Cloud accounting and invoicing platform with API access to clients, invoices, payments, projects, time tracking, and related small-business finance workflows.',
    'https://www.freshbooks.com/api/start',
    'api.freshbooks.com'
  ),
  (
    'bill',
    'BILL',
    'accounting',
    'Financial operations platform for AP, AR, spend management, reimbursements, vendor payments, and invoicing, with REST APIs and webhooks.',
    'https://developer.bill.com/docs/home',
    'gateway.stage.bill.com'
  ),
  (
    'zoho-books',
    'Zoho Books',
    'accounting',
    'REST accounting platform for organizations, contacts, invoices, bills, expenses, items, banking, and reporting within the Zoho suite.',
    'https://www.zoho.com/books/api/v3/introduction/',
    'www.zohoapis.com'
  ),
  (
    'netsuite',
    'NetSuite',
    'accounting',
    'Oracle NetSuite ERP and accounting platform with APIs for finance, records, transactions, inventory, procurement, and enterprise back-office automation.',
    'https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_1554821898.html',
    'restlets.api.netsuite.com'
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
    'quickbooks',
    7.10,
    7.60,
    6.40,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"accounting expansion","notes":"High-demand accounting API with broad object coverage for invoices, customers, payments, accounts, and reports. Strong Phase 0 candidate for invoice and ledger workflows; main friction is OAuth and Intuit app setup."}'::jsonb,
    now()
  ),
  (
    'freshbooks',
    6.90,
    7.20,
    6.50,
    0.52,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"accounting expansion","notes":"Good SMB finance API for invoices, clients, and time/billing workflows. OAuth2 is standard and docs are clear, making it a practical downstream integration for agent-led billing automations."}'::jsonb,
    now()
  ),
  (
    'bill',
    7.20,
    7.50,
    6.80,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"accounting expansion","notes":"Strong AP/AR and spend platform with documented REST APIs, webhooks, and developer keys. Especially attractive for agent workflows around bills, vendors, approvals, payments, and reimbursements."}'::jsonb,
    now()
  ),
  (
    'zoho-books',
    7.00,
    7.30,
    6.60,
    0.54,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"accounting expansion","notes":"Broad REST surface with explicit organization handling and OpenAPI availability. Good Phase 0 candidate for invoices, contacts, bills, and organization-scoped bookkeeping actions."}'::jsonb,
    now()
  ),
  (
    'netsuite',
    6.30,
    6.80,
    5.80,
    0.48,
    'L4',
    'Established',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"accounting expansion","notes":"Enterprise-grade finance/ERP coverage, but higher integration friction due to account-specific domains, enterprise auth patterns, and older SOAP/complexity baggage. Important category presence, lower near-term Resolve priority."}'::jsonb,
    now()
  );

COMMIT;
