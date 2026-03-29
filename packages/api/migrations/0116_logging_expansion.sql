BEGIN;

-- Migration 0116: Logging discovery expansion (2026-03-29)
-- Rationale: logging is a high-demand operational surface for agents doing
-- production debugging, incident triage, regression investigation, user-impact
-- tracing, and automated support escalation, but Rhumb's live catalog depth is
-- still thin relative to adjacent observability categories. Add 5 more
-- API-backed logging platforms with credible query/search surfaces and note the
-- cleanest Phase 0 wedge for Resolve.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'sumo-logic',
    'Sumo Logic',
    'logging',
    'Cloud log management and observability platform with APIs for search jobs, collectors, sources, monitors, dashboards, and alert-driven operational workflows.',
    'https://help.sumologic.com/docs/api/',
    'api.sumologic.com'
  ),
  (
    'coralogix',
    'Coralogix',
    'logging',
    'Observability platform with programmable log query, alerting, pipelines, dashboards, and dataset-level operational analysis across production systems.',
    'https://coralogix.com/docs/developer-portal/',
    'api.coralogix.com'
  ),
  (
    'logz-io',
    'Logz.io',
    'logging',
    'Managed log analytics and observability stack exposing APIs for search, dashboards, alerting, account resources, and operational troubleshooting workflows.',
    'https://docs.logz.io/',
    'api.logz.io'
  ),
  (
    'sematext-logs',
    'Sematext Logs',
    'logging',
    'Log management platform with API-backed ingestion, search, alerting, and retention controls for application, infrastructure, and security troubleshooting.',
    'https://sematext.com/docs/logs/',
    NULL
  ),
  (
    'crowdstrike-logscale',
    'CrowdStrike LogScale',
    'logging',
    'High-scale log management and search platform formerly known as Humio, with APIs for repositories, saved searches, alerts, dashboards, and operational investigations.',
    'https://library.humio.com/',
    'cloud.humio.com'
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
    'sumo-logic',
    8.20,
    8.40,
    8.00,
    0.65,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"logging expansion","notes":"Strongest Phase 0 candidate in the batch. Search-job APIs and saved search semantics map cleanly onto log.query and incident-triage primitives with clear operator value."}'::jsonb,
    now()
  ),
  (
    'coralogix',
    8.10,
    8.30,
    7.90,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"logging expansion","notes":"High-value modern observability surface with strong query and alert automation potential. Good near-term Resolve target after Sumo Logic because the read-first search lane is portable."}'::jsonb,
    now()
  ),
  (
    'sematext-logs',
    7.95,
    8.10,
    7.80,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"logging expansion","notes":"Useful breadth addition with practical log search and alerting surfaces across SMB and mid-market teams. Credible later candidate for log.query and saved search execution."}'::jsonb,
    now()
  ),
  (
    'logz-io',
    7.85,
    8.05,
    7.65,
    0.59,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"logging expansion","notes":"Important Elasticsearch-adjacent logging platform with workable search and alerting primitives. Slightly more ecosystem-shaped than Sumo or Coralogix, but still worthy coverage for operator workflows."}'::jsonb,
    now()
  ),
  (
    'crowdstrike-logscale',
    7.90,
    8.20,
    7.55,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"logging expansion","notes":"Strategically valuable high-scale log search surface with strong query ergonomics. Lower access readiness than Sumo Logic because enterprise setup is heavier, but execution potential is solid once configured."}'::jsonb,
    now()
  );

COMMIT;
