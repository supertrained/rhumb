BEGIN;

-- Migration 0147: Logging discovery expansion II (2026-04-02)
-- Rationale: live production still shows logging as an underrepresented,
-- high-demand operator category. Agents routinely need log search, incident
-- triage, anomaly investigation, support debugging, audit trace review, and
-- production forensics, but the catalog still skews thin relative to how often
-- these workflows matter in real operations.
-- Add five more API-backed logging platforms with credible query/search
-- surfaces and note the cleanest Phase 0 wedge for Resolve.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'google-cloud-logging',
    'Google Cloud Logging',
    'logging',
    'Managed cloud logging platform with APIs for log entry search, filters, saved queries, sinks, exclusions, tailing, and incident-oriented operational investigation across GCP workloads.',
    'https://cloud.google.com/logging/docs/reference/v2/rest',
    'logging.googleapis.com'
  ),
  (
    'splunk-cloud-platform',
    'Splunk Cloud Platform',
    'logging',
    'Enterprise log search and analytics platform with APIs for search jobs, saved searches, alerts, knowledge objects, and operational troubleshooting workflows.',
    'https://dev.splunk.com/enterprise/reference/api/search/',
    NULL
  ),
  (
    'graylog',
    'Graylog',
    'logging',
    'Log management and security analysis platform with REST APIs for search, streams, dashboards, events, pipelines, and operational debugging workflows.',
    'https://go2docs.graylog.org/current/setting_up_graylog/rest_api.html',
    NULL
  ),
  (
    'azure-monitor-logs',
    'Azure Monitor Logs',
    'logging',
    'Azure log analytics platform with query APIs for workspace search, KQL execution, saved views, and operational investigation across infrastructure and application telemetry.',
    'https://learn.microsoft.com/en-us/azure/azure-monitor/logs/api/access-api',
    'api.loganalytics.io'
  ),
  (
    'solarwinds-loggly',
    'SolarWinds Loggly',
    'logging',
    'Hosted log management platform with APIs for search, saved searches, alerts, sources, and operational troubleshooting across application and infrastructure logs.',
    'https://documentation.solarwinds.com/en/success_center/loggly/content/admin/search-api.htm',
    'logs-01.loggly.com'
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
    'google-cloud-logging',
    8.45,
    8.60,
    8.20,
    0.68,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"logging expansion ii","notes":"Best immediate Phase 0 candidate in the batch. Entries:list and filter-driven search map cleanly onto a normalized log.query primitive, and the platform is strategically important because so many modern products already run on GCP."}'::jsonb,
    now()
  ),
  (
    'splunk-cloud-platform',
    8.35,
    8.50,
    8.05,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"logging expansion ii","notes":"High-value enterprise logging surface with mature search-job semantics, saved searches, and incident workflows. Strong Resolve candidate for log.query after a cleaner cloud-first provider establishes the normalized lane."}'::jsonb,
    now()
  ),
  (
    'graylog',
    8.25,
    8.35,
    8.00,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"logging expansion ii","notes":"Strong self-host and mid-market operator fit with direct REST search semantics. Valuable category depth because many engineering teams run Graylog-like incident/debug workflows even when they are not on the largest commercial stacks."}'::jsonb,
    now()
  ),
  (
    'azure-monitor-logs',
    8.15,
    8.30,
    7.85,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"logging expansion ii","notes":"Important enterprise breadth add with explicit KQL query APIs and strong relevance for Microsoft-heavy environments. Slightly heavier auth and workspace complexity than the cleanest first target, but strategically important coverage."}'::jsonb,
    now()
  ),
  (
    'solarwinds-loggly',
    7.85,
    8.00,
    7.55,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"logging expansion ii","notes":"Useful long-tail commercial logging provider with workable search and alerting APIs. Good catalog-depth addition even if its API and product posture are less modern than Google Cloud Logging, Splunk, or Graylog."}'::jsonb,
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
