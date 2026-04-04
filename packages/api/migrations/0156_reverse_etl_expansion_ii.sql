BEGIN;

-- Migration 0156: Reverse-ETL discovery expansion II (2026-04-03)
-- Rationale: live production still shows the reverse-etl category at only 3 providers
-- (census, hightouch, polytomic) after accounting for the initial expansion in 0105.
-- Reverse ETL is a core agent workflow enabler: agents need to push warehouse truth
-- back into CRMs, support tools, and operational SaaS to close the loop between
-- insight and action. This is the lowest-count category in the entire catalog.
--
-- This batch adds four more API-backed reverse ETL platforms spanning modern
-- warehouse-activation, self-hosted, and cloud-native sync surfaces.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'castled-data',
    'Castled.io',
    'reverse-etl',
    'Cloud-native reverse ETL platform with a REST API for managing models, syncs, destinations, and warehouse activation workflows. Supports PostgreSQL, BigQuery, Snowflake, and Redshift sources with real-time and scheduled sync modes.',
    'https://docs.castled.io/api-reference/introduction',
    'api.castled.io'
  ),
  (
    'nexla',
    'Nexla',
    'reverse-etl',
    'Data operations and reverse ETL platform with a REST API for managing data flows, datasets, transformations, and sync jobs that push enriched warehouse data into operational targets including CRMs, SaaS tools, and custom endpoints.',
    'https://developer.nexla.io/',
    'api.nexla.io'
  ),
  (
    'etleap',
    'Etleap',
    'reverse-etl',
    'ETL and reverse ETL platform with a REST API for pipeline management, schedule control, data flow inspection, and warehouse-to-destination sync operations. Strong cloud data warehouse coverage across Snowflake, Redshift, and BigQuery.',
    'https://app.etleap.com/apidocs',
    'app.etleap.com'
  ),
  (
    'syncari',
    'Syncari',
    'reverse-etl',
    'Multidirectional sync and reverse ETL platform with an API for dataset management, sync pipelines, record inspection, and bi-directional operational data activation across CRMs, support, and marketing systems.',
    'https://developer.syncari.com/',
    'api.syncari.com'
  ),
  (
    'dbt-cloud',
    'dbt Cloud (Reverse Sync)',
    'reverse-etl',
    'dbt Cloud exposes APIs for job runs, model results, and semantic-layer queries that power downstream reverse ETL patterns by making warehouse transformation outputs accessible to downstream activation tools and agents.',
    'https://docs.getdbt.com/dbt-cloud/api-v2',
    'cloud.getdbt.com'
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
    'castled-data',
    8.15,
    8.25,
    7.90,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"reverse-etl expansion II","phase0_assessment":"Best Phase 0 candidate in the batch. Castled.io exposes a clean REST API for syncs, models, and destinations that maps directly to sync.list, sync.run, and sync.status primitives.","notes":"Modern cloud-native reverse ETL with strong read-first API surface and real warehouse-activation use cases for agent workflows."}'::jsonb,
    now()
  ),
  (
    'nexla',
    8.00,
    8.10,
    7.75,
    0.59,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"reverse-etl expansion II","phase0_assessment":"Strong second Phase 0 target for dataflow.list, dataset.get, and sync.status. Nexla covers cross-platform data operations with a developer-focused API.","notes":"Particularly useful for agent workflows that need to monitor transformation runs and sync pipelines across source and destination systems."}'::jsonb,
    now()
  ),
  (
    'etleap',
    7.85,
    7.95,
    7.65,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"reverse-etl expansion II","phase0_assessment":"Pipeline status and run inspection are the best initial Resolve targets. Etleap API is enterprise-grade but more internally-oriented than Castled or Nexla for first-wave normalization.","notes":"Strong enterprise cloud data warehouse coverage and solid scheduling/run management for agent-driven data pipeline monitoring."}'::jsonb,
    now()
  ),
  (
    'syncari',
    7.80,
    7.90,
    7.55,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"reverse-etl expansion II","phase0_assessment":"Dataset and sync inspection are usable Resolve starting points. Bi-directional sync semantics make normalization slightly noisier than pure reverse ETL.","notes":"Valuable for multi-system sync and record reconciliation workflows where agent-driven data activation needs bi-directional awareness."}'::jsonb,
    now()
  ),
  (
    'dbt-cloud',
    8.20,
    8.30,
    7.95,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-03","category_rationale":"reverse-etl expansion II","phase0_assessment":"Best read-first candidate for warehouse output inspection. dbt Cloud job run status and semantic-layer query exposure are clean Phase 0 starting points without requiring mutation of the transformation graph.","notes":"Strategically important because dbt is the transformation layer upstream of virtually every reverse ETL pipeline. Agents that can query dbt job state and semantic-layer output become first-class warehouse-aware actors."}'::jsonb,
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
