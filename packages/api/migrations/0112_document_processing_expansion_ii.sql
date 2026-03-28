BEGIN;

-- Migration 0112: Document-processing discovery expansion II (2026-03-28)
-- Rationale: document-processing remains a high-demand operational surface for
-- invoices, receipts, underwriting packets, KYC/ID workflows, AP automation,
-- and agent-driven document extraction, but the catalog still leans heavily
-- toward a small set of general parsers. Add four more document-AI vendors
-- with real extraction APIs and distinct operational strengths.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'mindee',
    'Mindee',
    'document-processing',
    'Document AI platform for extracting structured data from invoices, receipts, IDs, passports, and custom document types through production APIs and prebuilt OCR pipelines.',
    'https://docs.mindee.com/',
    'api.mindee.net'
  ),
  (
    'rossum',
    'Rossum',
    'document-processing',
    'Enterprise document automation platform with APIs for ingestion, extraction, validation, and workflow handling across invoices and other transactional documents.',
    'https://rossum.app/api/docs',
    'rossum.app'
  ),
  (
    'veryfi',
    'Veryfi',
    'document-processing',
    'OCR and document-capture API focused on receipts, invoices, bank statements, and expense documents with structured extraction and bookkeeping-oriented outputs.',
    'https://docs.veryfi.com/',
    'api.veryfi.com'
  ),
  (
    'docsumo',
    'Docsumo',
    'document-processing',
    'Document AI and intelligent document processing platform with APIs for upload, extraction, case workflows, and structured data capture from operational business documents.',
    'https://support.docsumo.com/reference/getting-started-with-your-api',
    'api.docsumo.com'
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
    'mindee',
    8.35,
    8.55,
    8.10,
    0.69,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"document-processing expansion ii","notes":"Strongest Phase 0 candidate in the batch. Mindee exposes clean extraction APIs plus prebuilt document models that map directly onto normalized document.extract_fields and invoice.extract contracts."}'::jsonb,
    now()
  ),
  (
    'rossum',
    8.20,
    8.40,
    7.95,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"document-processing expansion ii","notes":"Enterprise-grade document automation surface with explicit ingestion and extraction flows. Slightly heavier workflow model than Mindee, but still a credible Resolve target for structured document capture."}'::jsonb,
    now()
  ),
  (
    'veryfi',
    8.10,
    8.25,
    7.95,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"document-processing expansion ii","notes":"Operationally valuable for receipts, invoices, and bookkeeping extraction. Good fit for expense and AP automation workflows where agents need structured outputs quickly."}'::jsonb,
    now()
  ),
  (
    'docsumo',
    7.95,
    8.10,
    7.75,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"document-processing expansion ii","notes":"Broader IDP workflow surface with strong extraction potential. Slightly lower access readiness because the product leans more workflow-heavy than the cleanest direct-extraction APIs, but still worth live catalog coverage."}'::jsonb,
    now()
  );

COMMIT;
