BEGIN;

-- Migration 0114: Forms discovery expansion (2026-03-28)
-- Rationale: forms are a high-demand operational surface for agents collecting
-- leads, onboarding data, approvals, support intake, and structured user input,
-- but Rhumb's catalog depth is still thin. Add four more API-backed form
-- providers with credible submission/read surfaces and assess the clearest
-- Phase 0 wedge against the existing forms.collect capability family.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'formstack',
    'Formstack',
    'forms',
    'Forms and workflow platform with APIs for form definitions, submissions, webhooks, and operational data collection across lead capture, intake, and internal workflows.',
    'https://developers.formstack.com/',
    'api.formstack.com'
  ),
  (
    'wufoo',
    'Wufoo',
    'forms',
    'Hosted form builder with APIs for forms, fields, entries, reports, and lightweight submission workflows used across lead capture and operations intake.',
    'https://wufoo.github.io/docs/',
    'api.wufoo.com'
  ),
  (
    'cognito-forms',
    'Cognito Forms',
    'forms',
    'Online form automation platform with APIs for forms, entries, documents, payments-adjacent workflows, and structured business data collection.',
    'https://www.cognitoforms.com/support',
    'www.cognitoforms.com'
  ),
  (
    'formsite',
    'Formsite',
    'forms',
    'Form builder and response-collection platform with API access for forms, results, item metadata, and business workflow integrations.',
    'https://support.formsite.com/hc/en-us',
    'www.formsite.com'
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
    'formstack',
    8.20,
    8.35,
    8.05,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"forms expansion","notes":"Strongest Phase 0 candidate in the batch. Cleanest immediate wedge for extending the existing forms.collect lane beyond Fillout into a broader forms/submissions surface."}'::jsonb,
    now()
  ),
  (
    'wufoo',
    7.95,
    8.05,
    7.85,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"forms expansion","notes":"Stable entries/forms API with straightforward read-first collection patterns. Older product posture than Formstack, but still a credible Resolve target for forms.collect-style primitives."}'::jsonb,
    now()
  ),
  (
    'cognito-forms',
    7.85,
    7.95,
    7.75,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"forms expansion","notes":"Attractive business-forms surface with structured entries and document generation. Good follow-on Phase 0 candidate once core collection primitives are normalized."}'::jsonb,
    now()
  ),
  (
    'formsite',
    7.65,
    7.75,
    7.55,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"forms expansion","notes":"Useful breadth addition with practical forms/results APIs for intake and back-office workflows. Slightly less modern API posture than Formstack or Cognito Forms, but still worthy catalog coverage."}'::jsonb,
    now()
  );

COMMIT;
