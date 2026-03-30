BEGIN;

-- Migration 0122: Forms discovery expansion II (2026-03-30)
-- Rationale: live forms coverage is still too thin for a workflow primitive agents
-- repeatedly use for intake, lead capture, structured request collection, and
-- lightweight workflow handoffs. Add five more API-backed / submission-backed
-- form providers that broaden the category beyond visual builders.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'formspree',
    'Formspree',
    'forms',
    'Headless form backend and hosted forms platform with direct HTML form endpoints, a Forms API, file uploads, spam protection, and webhook-friendly submission collection for lead capture and intake workflows.',
    'https://help.formspree.io/hc/en-us',
    'formspree.io'
  ),
  (
    'basin',
    'Basin',
    'forms',
    'No-code form backend with hosted submission handling, spam protection, file uploads, notifications, webhooks, and a REST API for programmatic access to collected form data.',
    'https://docs.usebasin.com/',
    'usebasin.com'
  ),
  (
    'forminit',
    'Forminit',
    'forms',
    'Headless form backend API focused on structured submission handling, file uploads, validation blocks, notifications, and action-driven form processing across custom frontends.',
    'https://forminit.com/docs/',
    'forminit.com'
  ),
  (
    'formcarry',
    'Formcarry',
    'forms',
    'Hosted form endpoint and dashboard for static sites and app forms with spam filtering, notifications, integrations, and lightweight developer-friendly submission capture.',
    'https://formcarry.com/docs',
    'formcarry.com'
  ),
  (
    'web3forms',
    'Web3Forms',
    'forms',
    'Lightweight API-first form submission service for static sites with access-key auth, custom redirects, attachments, and simple serverless contact/intake collection flows.',
    'https://docs.web3forms.com/',
    'api.web3forms.com'
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
    'formspree',
    8.10,
    8.20,
    7.95,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"forms expansion ii","notes":"Strongest Phase 0 candidate in the batch. Formspree exposes a very clear submission contract, broad static-site / lightweight app relevance, and a clean path to extending forms.collect beyond the current single-provider lane."}'::jsonb,
    now()
  ),
  (
    'basin',
    8.00,
    8.10,
    7.85,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"forms expansion ii","notes":"Strong operational form backend with REST API, webhooks, spam controls, and file uploads. Good second Phase 0 target for forms.collect and submission-list workflows."}'::jsonb,
    now()
  ),
  (
    'forminit',
    7.90,
    8.00,
    7.75,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"forms expansion ii","notes":"Interesting headless posture with block-structured submission handling and action hooks. Valuable category depth and a credible future Phase 0 candidate once the newer platform matures further."}'::jsonb,
    now()
  ),
  (
    'formcarry',
    7.70,
    7.80,
    7.60,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"forms expansion ii","notes":"Lightweight hosted endpoint model is useful for straightforward intake and contact workflows. Less expansive than the leaders but still a real form-collection surface agents may need."}'::jsonb,
    now()
  ),
  (
    'web3forms',
    7.55,
    7.60,
    7.50,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"forms expansion ii","notes":"Very simple static-site form submission API with low setup friction. Good long-tail coverage for lightweight collection use cases, though the operator surface is narrower than Formspree or Basin."}'::jsonb,
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
