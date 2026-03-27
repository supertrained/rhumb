BEGIN;

-- Migration 0101: Document-processing discovery expansion (2026-03-26)
-- Rationale: document processing is a high-demand operational category for agents,
-- but the catalog lacks breadth across modern IDP/OCR specialists. Add 5
-- API-first providers with initial scoring.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'veryfi',
    'Veryfi',
    'document-processing',
    'OCR and document capture API for receipts, invoices, W-2s, bills, and expense data extraction with bookkeeping-oriented outputs.',
    'https://docs.veryfi.com/',
    'api.veryfi.com'
  ),
  (
    'mindee',
    'Mindee',
    'document-processing',
    'API-first document parsing platform for invoices, receipts, IDs, passports, business cards, and custom extraction workflows.',
    'https://developers.mindee.com/docs',
    'api.mindee.net'
  ),
  (
    'rossum',
    'Rossum',
    'document-processing',
    'Intelligent document processing platform focused on invoice and business-document automation with validation and workflow layers.',
    'https://elis.rossum.ai/api/docs/',
    'elis.rossum.ai'
  ),
  (
    'docparser',
    'Docparser',
    'document-processing',
    'Template-driven document parsing API for extracting structured fields, tables, and line items from PDFs, emails, and scanned files.',
    'https://docparser.com/api/',
    'api.docparser.com'
  ),
  (
    'parseur',
    'Parseur',
    'document-processing',
    'Email and document parsing platform that extracts structured data from PDFs, invoices, orders, and inbound email attachments.',
    'https://help.parseur.com/en/collections/6955304-api',
    'api.parseur.com'
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
    'veryfi',
    7.70,
    7.95,
    7.35,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"document-processing expansion","notes":"Strong expense and financial-document extraction product with practical accounting/ops value for agents handling receipts, invoices, and bills."}'::jsonb,
    now()
  ),
  (
    'mindee',
    7.90,
    8.15,
    7.55,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"document-processing expansion","notes":"Best immediate Phase 0 candidate in the batch. Productized extraction APIs map cleanly to invoice.extract, receipt.extract, identity.extract_document, and generic document.extract_fields primitives."}'::jsonb,
    now()
  ),
  (
    'rossum',
    7.60,
    7.85,
    7.20,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"document-processing expansion","notes":"Enterprise-grade invoice and document workflow platform with strong AP automation depth, but more workflow-heavy than a first-wave normalized extraction primitive."}'::jsonb,
    now()
  ),
  (
    'docparser',
    7.35,
    7.60,
    7.00,
    0.55,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"document-processing expansion","notes":"Template-oriented parsing platform with useful extraction breadth for semi-structured business docs, especially when agents need predictable field outputs from recurring document shapes."}'::jsonb,
    now()
  ),
  (
    'parseur',
    7.45,
    7.65,
    7.10,
    0.55,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"document-processing expansion","notes":"Good fit for email-driven parsing and operations automation. Valuable for invoice/order inboxes, but less general than Mindee or Veryfi for a first Resolve target."}'::jsonb,
    now()
  );

COMMIT;
