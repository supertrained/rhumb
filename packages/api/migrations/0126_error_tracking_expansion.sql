BEGIN;

-- Migration 0126: Error-tracking discovery expansion (2026-03-30)
-- Rationale: agents increasingly need direct access to grouped production-failure
-- context before taking remediation or escalation actions, but Rhumb still treats
-- most of this surface indirectly through logging/search vendors. Add five real
-- error-tracking / crash-reporting platforms with read-first API posture and
-- credible Phase 0 potential around normalized error_group.list / error_group.read
-- and error_event.search capabilities.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'bugsnag',
    'BugSnag',
    'error-tracking',
    'Application stability and crash-reporting platform with data-access, release, event, trace, and project APIs for grouped error inspection and production failure triage.',
    'https://developer.smartbear.com/bugsnag/docs/getting-started',
    'api.bugsnag.com'
  ),
  (
    'rollbar',
    'Rollbar',
    'error-tracking',
    'Error monitoring and incident triage platform with item, occurrence, deploy, and project APIs suited to grouped exception review and production issue investigation.',
    'https://docs.rollbar.com/docs/overview',
    'api.rollbar.com'
  ),
  (
    'honeybadger',
    'Honeybadger',
    'error-tracking',
    'Application monitoring and exception tracking platform with notice, fault, deployment, uptime, and project APIs that fit read-first issue triage and incident follow-up workflows.',
    'https://docs.honeybadger.io/api/',
    'api.honeybadger.io'
  ),
  (
    'airbrake',
    'Airbrake',
    'error-tracking',
    'Error monitoring surface with groups, notices, project activities, deploys, and performance APIs that support grouped failure review and operator escalation workflows.',
    'https://docs.airbrake.io/docs/devops-tools/api/',
    'api.airbrake.io'
  ),
  (
    'appsignal',
    'AppSignal',
    'error-tracking',
    'Application performance and exception monitoring platform with application-scoped JSON APIs for incidents, metrics, and error context that can inform automation safety checks.',
    'https://docs.appsignal.com/api',
    'appsignal.com'
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
    'bugsnag',
    8.20,
    8.35,
    8.00,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"error-tracking expansion","notes":"Strong grouped-error and project data surface with credible read-first APIs for issue inventory, release-aware triage, and production failure review."}'::jsonb,
    now()
  ),
  (
    'rollbar',
    8.10,
    8.25,
    7.95,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"error-tracking expansion","notes":"Best first Phase 0 target in the batch. Clean incident-oriented item and occurrence surfaces make Rollbar a practical normalization target for error_group.list and error_group.read."}'::jsonb,
    now()
  ),
  (
    'honeybadger',
    7.95,
    8.05,
    7.80,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"error-tracking expansion","notes":"Good operational breadth across exceptions, check-ins, deployments, and faults. Strong operator value for read-first triage without forcing mutation-heavy workflows."}'::jsonb,
    now()
  ),
  (
    'airbrake',
    7.80,
    7.95,
    7.60,
    0.59,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"error-tracking expansion","notes":"Clear group and notice APIs make it useful category depth for production-failure review, even if auth/query ergonomics look slightly older than the leaders."}'::jsonb,
    now()
  ),
  (
    'appsignal',
    7.70,
    7.85,
    7.55,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"error-tracking expansion","notes":"Credible application-scoped API with practical incident context, though app-scoped token/query semantics make it a slightly noisier first normalization target than Rollbar or Bugsnag."}'::jsonb,
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
