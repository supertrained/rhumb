BEGIN;

-- Migration 0086: Identity-verification discovery expansion (2026-03-25)
-- Rationale: identity-verification is high-demand and underrepresented in the current catalog.
-- Add 5 widely-used KYC / identity-verification providers with initial AN scoring.

INSERT INTO services (slug, name, category, description, official_docs)
VALUES
  (
    'sumsub',
    'Sumsub',
    'identity-verification',
    'Identity verification, AML screening, liveness, and fraud-prevention platform for KYC/KYB onboarding.',
    'https://docs.sumsub.com/'
  ),
  (
    'trulioo',
    'Trulioo',
    'identity-verification',
    'Global identity verification platform for person and business verification, watchlist screening, and onboarding flows.',
    'https://developer.trulioo.com/'
  ),
  (
    'shufti-pro',
    'Shufti Pro',
    'identity-verification',
    'KYC, KYB, document verification, and AML screening platform with API-first onboarding flows.',
    'https://developers.shuftipro.com/'
  ),
  (
    'idenfy',
    'iDenfy',
    'identity-verification',
    'Identity verification and anti-fraud suite covering document checks, AML screening, and proof-of-address verification.',
    'https://documentation.idenfy.com/'
  ),
  (
    'smile-identity',
    'Smile Identity',
    'identity-verification',
    'Digital KYC and identity verification platform with strong Africa coverage, document verification, and authentication flows.',
    'https://docs.usesmileid.com/'
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
    'sumsub',
    7.40,
    7.80,
    7.20,
    0.55,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"identity-verification expansion","notes":"Strong API/docs footprint; broad KYC/KYB coverage."}'::jsonb,
    now()
  ),
  (
    'trulioo',
    7.30,
    7.60,
    7.00,
    0.54,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"identity-verification expansion","notes":"Global identity verification API with strong enterprise adoption."}'::jsonb,
    now()
  ),
  (
    'shufti-pro',
    7.10,
    7.30,
    6.80,
    0.52,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"identity-verification expansion","notes":"API-first KYC/KYB provider with practical verification toolkits."}'::jsonb,
    now()
  ),
  (
    'idenfy',
    7.20,
    7.40,
    6.90,
    0.52,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"identity-verification expansion","notes":"Good anti-fraud coverage and clear developer docs."}'::jsonb,
    now()
  ),
  (
    'smile-identity',
    7.30,
    7.60,
    7.00,
    0.53,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-25","category_rationale":"identity-verification expansion","notes":"Strong regional moat in Africa; API documentation is accessible and implementation-oriented."}'::jsonb,
    now()
  );

COMMIT;
