BEGIN;

-- Migration 0097: Feature flags discovery expansion (2026-03-26)
-- Rationale: feature flags/experimentation control is a high-demand agent
-- category, but the catalog only had 5 providers. Add 5 widely-used flag and
-- experiment platforms with practical admin APIs and initial AN scoring.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'launchdarkly',
    'LaunchDarkly',
    'feature-flags',
    'Enterprise feature flagging and experimentation platform with REST APIs for projects, environments, flags, targeting rules, approvals, and change history.',
    'https://launchdarkly.com/docs/api',
    'app.launchdarkly.com'
  ),
  (
    'statsig',
    'Statsig',
    'feature-flags',
    'Feature flagging and experimentation platform with management APIs for gates, dynamic configs, experiments, rollouts, and exposure-aware product changes.',
    'https://docs.statsig.com/api-reference/overview',
    'api.statsig.com'
  ),
  (
    'unleash',
    'Unleash',
    'feature-flags',
    'Open-source feature management platform with admin APIs for feature flags, strategies, variants, segments, environments, and rollout governance.',
    'https://docs.getunleash.io/reference/api/unleash',
    'app.unleash-hosted.com'
  ),
  (
    'configcat',
    'ConfigCat',
    'feature-flags',
    'Hosted feature flag and configuration platform with public management APIs for products, environments, settings, rollout rules, and audit-friendly config delivery.',
    'https://configcat.com/docs/api/reference/',
    'api.configcat.com'
  ),
  (
    'split',
    'Split',
    'feature-flags',
    'Feature delivery and experimentation platform with APIs for splits, segments, environments, traffic allocation, and release control.',
    'https://help.split.io/hc/en-us/articles/360020564931-Admin-API-overview',
    'api.split.io'
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
    'launchdarkly',
    7.95,
    8.20,
    7.70,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"feature-flags expansion","notes":"Deep admin API, mature enterprise docs, strong change-governance model, and direct fit for future feature_flag.list/read/update capabilities plus experiment metadata access."}'::jsonb,
    now()
  ),
  (
    'statsig',
    7.70,
    7.95,
    7.45,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"feature-flags expansion","notes":"Strong API-first product for gates/configs/experiments with fast-growing adoption and a practical surface for agent-driven rollout and experimentation workflows."}'::jsonb,
    now()
  ),
  (
    'unleash',
    7.45,
    7.65,
    7.20,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"feature-flags expansion","notes":"Open-source friendly admin API with solid strategy/variant control and strong self-host or hosted deployment flexibility for agent-managed flag operations."}'::jsonb,
    now()
  ),
  (
    'configcat',
    7.20,
    7.40,
    7.00,
    0.54,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"feature-flags expansion","notes":"Clean hosted API surface with sensible rollout/config abstractions and strong fit for SMB-to-midmarket agent flag control, though narrower experimentation depth than LaunchDarkly/Statsig."}'::jsonb,
    now()
  ),
  (
    'split',
    7.05,
    7.25,
    6.85,
    0.53,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"feature-flags expansion","notes":"Established feature delivery platform with admin APIs and experimentation overlap, but docs discoverability and modern DX feel somewhat behind the strongest vendors in this batch."}'::jsonb,
    now()
  );

COMMIT;
