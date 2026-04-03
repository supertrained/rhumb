BEGIN;

-- Migration 0151: Forms discovery expansion II (2026-04-02)
-- Rationale: live production still shows forms as an underrepresented,
-- high-demand category even though agents routinely need to inspect intake
-- pipelines, fetch submission payloads, monitor lead capture health, and
-- trigger downstream workflows from structured responses. The first wave
-- only covered five providers, leaving meaningful gaps across widely used
-- form builders with real APIs.
-- Add five more API-backed forms surfaces and document the cleanest
-- read-first Resolve wedge.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'formstack',
    'Formstack',
    'forms',
    'Form and workflow platform with APIs for forms, submissions, document generation, approvals, and intake automation across marketing, operations, and back-office workflows.',
    'https://developers.formstack.com/',
    'api.formstack.com'
  ),
  (
    'cognito-forms',
    'Cognito Forms',
    'forms',
    'Online form builder with APIs for forms, entries, workflows, calculations, payments, and structured intake workflows for teams that need operationally useful submission data.',
    'https://www.cognitoforms.com/support',
    'www.cognitoforms.com'
  ),
  (
    'formsite',
    'Formsite',
    'forms',
    'Hosted forms platform with APIs for form metadata, results, file uploads, workflow notifications, and submission reporting across surveys, intake, and internal process automation.',
    'https://support.formsite.com/hc/en-us',
    'api.formsite.com'
  ),
  (
    'zoho-forms',
    'Zoho Forms',
    'forms',
    'Form builder with API-backed form management, submissions, approvals, payments, and integration workflows inside the broader Zoho business stack.',
    'https://www.zoho.com/forms/',
    'forms.zoho.com'
  ),
  (
    'wufoo',
    'Wufoo',
    'forms',
    'Longstanding hosted forms platform with APIs for form definitions, entries, reporting, and lightweight operational intake workflows.',
    'https://help.surveymonkey.com/en/wufoo/',
    'api.wufoo.com'
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
    8.45,
    8.55,
    8.20,
    0.68,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"forms expansion ii","phase0_assessment":"Best immediate Resolve candidate in the batch because Formstack exposes a mature API around forms and submissions that maps cleanly onto read-first intake inspection and submission retrieval workflows.","notes":"Strong operational relevance for lead capture, onboarding, approvals, and back-office intake where agents need to inspect structured responses before acting downstream."}'::jsonb,
    now()
  ),
  (
    'cognito-forms',
    8.20,
    8.25,
    8.10,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"forms expansion ii","phase0_assessment":"Strong follow-on candidate for forms.get and form.responses.list because Cognito Forms emphasizes structured entries, calculations, and operational workflows rather than purely marketing capture.","notes":"Useful for rich intake and internal process automation where submission payload quality matters."}'::jsonb,
    now()
  ),
  (
    'zoho-forms',
    8.15,
    8.20,
    8.00,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"forms expansion ii","phase0_assessment":"Credible Resolve candidate for submission retrieval and form metadata inspection, especially for teams already operating inside the Zoho stack.","notes":"Strategically relevant because Zoho remains a common SMB operational system even if the API surface is less elegant than the cleanest first wedge."}'::jsonb,
    now()
  ),
  (
    'formsite',
    8.00,
    8.05,
    7.95,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"forms expansion ii","phase0_assessment":"Useful long-tail Resolve candidate for result retrieval and form reporting once the cleaner modern providers are normalized.","notes":"Adds practical coverage for teams running older but still active form-driven intake workflows."}'::jsonb,
    now()
  ),
  (
    'wufoo',
    7.85,
    7.80,
    7.95,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"forms expansion ii","phase0_assessment":"Still API-viable for form entry retrieval, but best treated as catalog-depth support after newer form platforms are covered.","notes":"Legacy brand, but enough installed-base relevance to justify inclusion in a discovery layer that aims to reflect what agents will actually encounter in the wild."}'::jsonb,
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
