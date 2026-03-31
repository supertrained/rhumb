BEGIN;

-- Migration 0127: CDN discovery expansion II (2026-03-30)
-- Rationale: CDN remains a high-demand operator category for agents that need
-- cache-state awareness, zone inventory, and targeted purge/control actions,
-- but Rhumb still covers only a thin slice of the market. Add five more real
-- CDN vendors with credible API posture and practical Phase 0 potential around
-- read-first `cdn.zone.list` plus follow-on `cache.purge` capability shaping.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'akamai',
    'Akamai',
    'cdn',
    'Enterprise CDN and edge-delivery platform with APIs for property management, cache invalidation, reporting, edge configuration, and zone-level delivery control.',
    'https://techdocs.akamai.com/apis/',
    'api.akamai.com'
  ),
  (
    'gcore',
    'Gcore CDN',
    'cdn',
    'Global CDN and edge cloud platform with APIs for resource inventory, cache purge, origin configuration, logs, and delivery settings suited to operator automation.',
    'https://gcore.com/docs/cdn',
    'api.gcore.com'
  ),
  (
    'cdn77',
    'CDN77',
    'cdn',
    'Content delivery platform with customer APIs for CDN resources, cache purge, analytics, origins, and delivery configuration useful for read-first edge operations.',
    'https://client.cdn77.com/support/api/version/2.0/',
    'client.cdn77.com'
  ),
  (
    'cachefly',
    'CacheFly',
    'cdn',
    'CDN and edge delivery service with APIs for service configuration, cache invalidation, logs, and operational account controls relevant to delivery-path automation.',
    'https://portal.cachefly.com/api/',
    'api.cachefly.com'
  ),
  (
    'cdnsun',
    'CDNSUN',
    'cdn',
    'CDN service with APIs for pull zones, storage zones, statistics, and cache invalidation that map cleanly to agent-facing delivery inspection workflows.',
    'https://cdnsun.com/knowledgebase/api',
    'api.cdnsun.com'
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
    'gcore',
    8.20,
    8.35,
    8.00,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"cdn expansion ii","notes":"Best first Phase 0 target in the batch. Modern API posture and clear CDN resource plus purge surfaces make it the cleanest normalization candidate for cdn.zone.list and cache.purge."}'::jsonb,
    now()
  ),
  (
    'akamai',
    8.10,
    8.15,
    7.85,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"cdn expansion ii","notes":"Category heavyweight with very strong operational breadth, but enterprise auth and product-surface complexity make it a slightly noisier first normalization target than Gcore."}'::jsonb,
    now()
  ),
  (
    'cdn77',
    7.95,
    8.05,
    7.75,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"cdn expansion ii","notes":"Good customer API coverage for zones, purge, and analytics. Strong mid-market CDN addition with practical read-first operator value."}'::jsonb,
    now()
  ),
  (
    'cachefly',
    7.75,
    7.85,
    7.55,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"cdn expansion ii","notes":"Credible cache-control and service-management API surface, though narrower public docs and older operator ergonomics make it a secondary normalization target."}'::jsonb,
    now()
  ),
  (
    'cdnsun',
    7.60,
    7.70,
    7.45,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"cdn expansion ii","notes":"Useful long-tail CDN coverage with pull-zone and purge APIs that fit agent operator workflows even if the platform is less strategically central than the leaders."}'::jsonb,
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
