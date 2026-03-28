BEGIN;

-- Migration 0109: Email-validation discovery expansion (2026-03-28)
-- Rationale: email validation is a high-demand operational category for GTM workflows,
-- signup hygiene, CRM enrichment, and outbound automation, but Rhumb only had five
-- providers in the live catalog before this batch. Add five more documented API vendors
-- with clear single-check and batch-check potential for future Resolve normalization.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'emailable',
    'Emailable',
    'email-validation',
    'Email verification platform with public API docs for single-address validation, batch processing, webhook-style workflows, and flexible auth via bearer header or API key parameter.',
    'https://emailable.com/docs/api',
    'api.emailable.com'
  ),
  (
    'bouncer',
    'Bouncer',
    'email-validation',
    'Email verification API covering synchronous verification, asynchronous batch jobs, and deliverability metadata that maps cleanly to agent-facing validation primitives.',
    'https://docs.usebouncer.com/',
    'api.usebouncer.com'
  ),
  (
    'verifalia',
    'Verifalia',
    'email-validation',
    'Enterprise email verification platform with mature API reference, job-based validation flows, SDK coverage, and production-friendly list hygiene workflows.',
    'https://verifalia.com/developers',
    'api.verifalia.com'
  ),
  (
    'debounce',
    'DeBounce',
    'email-validation',
    'Developer-focused email validation and enrichment API with clear single-check, batch, and usage/balance surfaces suitable for operational automation.',
    'https://developers.debounce.com/',
    'api.debounce.io'
  ),
  (
    'mailboxlayer',
    'mailboxlayer',
    'email-validation',
    'REST JSON email validation API with syntax, MX, SMTP, disposable detection, typo suggestion, and score outputs that are easy to normalize into trust surfaces.',
    'https://mailboxlayer.com/documentation',
    'apilayer.net'
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
    'emailable',
    8.45,
    8.60,
    8.30,
    0.68,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"email-validation expansion","notes":"Strongest Phase 0 candidate in the batch. Public docs clearly describe single-address verification plus batch workflows and flexible auth, making it a clean fit for future email.verify and email.batch_verify Resolve contracts."}'::jsonb,
    now()
  ),
  (
    'bouncer',
    8.35,
    8.50,
    8.15,
    0.67,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"email-validation expansion","notes":"Very strong operational fit because the docs explicitly expose real-time, batch, and hybrid verification modes. Good near-term provider for batch email hygiene capabilities."}'::jsonb,
    now()
  ),
  (
    'verifalia',
    8.20,
    8.30,
    8.00,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"email-validation expansion","notes":"Mature vendor with strong API reference and enterprise credibility. Slightly heavier job-oriented model than Emailable, but still a credible Resolve candidate for verification and list hygiene workflows."}'::jsonb,
    now()
  ),
  (
    'debounce',
    7.95,
    8.05,
    7.85,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"email-validation expansion","notes":"Good catalog addition with explicit single-validation and bulk surfaces. Public docs are workable, though positioning and polish are a step below the strongest batch leaders."}'::jsonb,
    now()
  ),
  (
    'mailboxlayer',
    7.80,
    7.90,
    7.70,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-28","category_rationale":"email-validation expansion","notes":"Simple API and recognizable market footprint make it worth catalog coverage now. Access model is straightforward, but the surface looks more utility-grade than best-in-class Phase 0 candidates."}'::jsonb,
    now()
  );

COMMIT;
