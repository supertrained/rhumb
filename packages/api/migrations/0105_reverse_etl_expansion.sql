BEGIN;

-- Migration 0105: Reverse ETL discovery expansion (2026-03-27)
-- Rationale: reverse ETL remains underrepresented in the catalog despite being a
-- real operational category for agent workflows that push warehouse truth back
-- into CRMs, support tools, and growth systems.
-- Add 4 providers spanning API-first SaaS, Snowflake-native sync, self-hosted
-- deployment, and warehouse-activation workflow coverage.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'portable',
    'Portable',
    'reverse-etl',
    'Data movement platform covering ELT and reverse ETL workflows with an admin API for source specs, destinations, syncs, and workspace-managed data activation.',
    'https://developer.portable.io/api-reference/introduction',
    'api.portable.io'
  ),
  (
    'hevo-activate',
    'Hevo Activate',
    'reverse-etl',
    'Warehouse activation and reverse ETL product from Hevo focused on syncing modeled warehouse data into SaaS tools like CRMs and marketing systems.',
    'https://docs.hevodata.com/activate',
    NULL
  ),
  (
    'omnata',
    'Omnata',
    'reverse-etl',
    'Snowflake-native reverse ETL and bi-directional sync platform for operationalizing warehouse data into SaaS applications and custom APIs.',
    'https://docs.omnata.com/',
    NULL
  ),
  (
    'grouparoo',
    'Grouparoo',
    'reverse-etl',
    'Open-source reverse ETL framework with REST API support for syncing warehouse data into downstream SaaS destinations from a self-hosted control plane.',
    'https://www.grouparoo.com/docs/support/rest-api',
    NULL
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
    'portable',
    7.95,
    8.25,
    7.70,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"reverse-etl expansion","notes":"Best immediate Phase 0 candidate in the batch. Portable exposes a real admin API at api.portable.io with listable source specs, sources, destinations, and sync resources that can map into future sync.list/create/read primitives."}'::jsonb,
    now()
  ),
  (
    'hevo-activate',
    7.35,
    7.10,
    7.60,
    0.54,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"reverse-etl expansion","notes":"Important category coverage because Hevo is a real warehouse-activation vendor, but public docs do not show a clean public Activate control API. Good catalog inclusion, weaker first-wave Resolve target."}'::jsonb,
    now()
  ),
  (
    'omnata',
    7.55,
    7.30,
    7.45,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"reverse-etl expansion","notes":"Strong Snowflake-native product with serious operational depth, but the public surface is more Snowflake-native app and plugin oriented than clean standalone admin API. Worth indexing now; Phase 0 later if a clearer programmable control path emerges."}'::jsonb,
    now()
  ),
  (
    'grouparoo',
    7.60,
    7.55,
    7.20,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"reverse-etl expansion","notes":"Open-source and self-hosted shape lowers turnkey access readiness, but the REST API and strong reverse-ETL semantics make it a credible later Resolve candidate for self-hosted-heavy teams."}'::jsonb,
    now()
  );

COMMIT;
