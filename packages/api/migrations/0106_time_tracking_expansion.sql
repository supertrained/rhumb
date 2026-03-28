BEGIN;

-- Migration 0106: Time-tracking discovery expansion (2026-03-27)
-- Rationale: time-tracking is a high-demand operational category for agencies,
-- consultancies, product teams, and finance ops, but the catalog still has thin
-- coverage and an awkward Toggl duplicate. Add five recognizable vendors spanning
-- Jira-native, workforce, self-hosted, project-tracking, and memory-assisted time capture.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'tempo',
    'Tempo',
    'time-tracking',
    'Jira-native time tracking and financial management platform with a broad REST API covering worklogs, accounts, approvals, projects, budgets, and planning workflows.',
    'https://apidocs.tempo.io/',
    'api.tempo.io'
  ),
  (
    'hubstaff',
    'Hubstaff',
    'time-tracking',
    'Time tracking and workforce operations platform with OAuth2 API access for organizations, projects, tasks, schedules, activity data, and webhooks.',
    'https://developer.hubstaff.com/docs/hubstaff_v2',
    'api.hubstaff.com'
  ),
  (
    'kimai',
    'Kimai',
    'time-tracking',
    'Open-source time-tracking platform with bearer-token REST API support for customers, projects, activities, tags, users, and timesheet records across self-hosted deployments.',
    'https://www.kimai.org/documentation/rest-api.html',
    NULL
  ),
  (
    'everhour',
    'Everhour',
    'time-tracking',
    'Project-centric time tracking and budgeting product with JSON API coverage for projects, tasks, timers, time records, timesheets, invoices, expenses, users, and webhooks.',
    'https://everhour.docs.apiary.io/',
    'api.everhour.com'
  ),
  (
    'timely',
    'Timely',
    'time-tracking',
    'Time-tracking and reporting platform with OAuth-based public API for workspace admins to access projects, time entries, reports, and integration-facing account data.',
    'https://developer.timely.com/',
    'api.timelyapp.com'
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
    'tempo',
    8.15,
    8.35,
    7.90,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"time-tracking expansion","notes":"Strong category anchor. Tempo exposes a large public REST surface and is a plausible future Resolve candidate for worklog.list/create plus project-time approval flows, but the Jira-coupled data model increases Phase 0 complexity."}'::jsonb,
    now()
  ),
  (
    'hubstaff',
    8.05,
    8.20,
    8.00,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"time-tracking expansion","notes":"Best immediate Phase 0 candidate in the batch. Hubstaff publishes OAuth2 docs, webhook setup, and a downloadable OpenAPI document across core team, project, schedule, and time-tracking resources."}'::jsonb,
    now()
  ),
  (
    'kimai',
    7.70,
    7.95,
    7.10,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"time-tracking expansion","notes":"Self-hosted/open-source deployment lowers turnkey access readiness, but the bearer-token REST API is straightforward and maps cleanly to agent-friendly timesheet primitives for teams that control their own instance."}'::jsonb,
    now()
  ),
  (
    'everhour',
    7.85,
    7.95,
    7.75,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"time-tracking expansion","notes":"Healthy API breadth with simple API-key auth and explicit rate-limit guidance. Good later Resolve target for project/task/time-record reads plus timer control, though the API is still labeled beta."}'::jsonb,
    now()
  ),
  (
    'timely',
    7.75,
    7.80,
    7.65,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"time-tracking expansion","notes":"Timely has a public OAuth-based API and clear admin setup docs. Good catalog inclusion now; Phase 0 should wait until we scope which high-value read/write primitives matter most and whether Memory exclusions constrain agent use cases."}'::jsonb,
    now()
  );

COMMIT;
