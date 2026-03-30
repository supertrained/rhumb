BEGIN;

-- Migration 0125: Feature-flags discovery expansion II (2026-03-30)
-- Rationale: feature-flags / experimentation remains underrepresented relative
-- to how often agents need rollout awareness, staged-release controls, and
-- safe config reads before taking actions. Add five more API-backed vendors
-- with credible admin/config surfaces and real Phase 0 potential around
-- normalized feature_flag.list / feature_flag.read capabilities.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'devcycle',
    'DevCycle',
    'feature-flags',
    'Feature management and experimentation platform with managed environments, targeting rules, variables, feature configuration, and explicit API surfaces for rollout-aware automation.',
    'https://docs.devcycle.com/api/',
    'api.devcycle.com'
  ),
  (
    'prefab-cloud',
    'Prefab',
    'feature-flags',
    'Feature-flag and dynamic-configuration platform with environment-scoped config, flag evaluation context, and operator-friendly APIs for rollout awareness and application config control.',
    'https://docs.prefab.cloud/docs/api/',
    'api.prefab.cloud'
  ),
  (
    'flipt',
    'Flipt',
    'feature-flags',
    'Open-source-friendly feature-flag platform with REST and gRPC APIs for flags, segments, evaluations, namespaces, and environment-aware rollout control in self-hosted or cloud deployments.',
    'https://docs.flipt.io/v1/reference/',
    'api.flipt.io'
  ),
  (
    'featbit',
    'FeatBit',
    'feature-flags',
    'Feature management service with targeting, variations, environment controls, and admin APIs suitable for flag inventory, rollout inspection, and progressive delivery workflows.',
    'https://docs.featbit.co/',
    'api.featbit.co'
  ),
  (
    'harness-feature-management',
    'Harness Feature Management & Experimentation',
    'feature-flags',
    'Enterprise feature-flag and experimentation surface inside Harness with APIs for flags, targeting, environments, and release controls that fit staged agent-driven rollout workflows.',
    'https://developer.harness.io/docs/feature-management-experimentation/api/',
    'app.harness.io'
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
    'devcycle',
    8.15,
    8.30,
    7.95,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"feature-flags expansion ii","notes":"Best new Phase 0 target in the batch. Clear admin API, modern feature/config model, and strong fit for normalized feature_flag.list and feature_flag.read surfaces."}'::jsonb,
    now()
  ),
  (
    'prefab-cloud',
    8.00,
    8.15,
    7.80,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"feature-flags expansion ii","notes":"Strong config + flag posture for operator agents that need rollout awareness before acting. Good follow-on candidate for read-first flag/config capability shaping."}'::jsonb,
    now()
  ),
  (
    'flipt',
    7.90,
    8.05,
    7.65,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"feature-flags expansion ii","notes":"Open-source-friendly surface with explicit namespaces, flags, segments, and evaluation APIs. Useful catalog depth and practical self-hosted angle for agent operators."}'::jsonb,
    now()
  ),
  (
    'featbit',
    7.75,
    7.90,
    7.55,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"feature-flags expansion ii","notes":"Good flag and targeting depth with straightforward admin posture. Valuable mid-market category coverage even if docs feel slightly less mature than DevCycle or Prefab."}'::jsonb,
    now()
  ),
  (
    'harness-feature-management',
    7.65,
    7.85,
    7.40,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"feature-flags expansion ii","notes":"Credible enterprise release-control surface with feature flags and experimentation, but broader platform complexity makes it a slightly noisier early normalization target than the leaders."}'::jsonb,
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
