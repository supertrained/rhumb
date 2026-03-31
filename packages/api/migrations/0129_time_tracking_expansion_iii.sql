BEGIN;

-- Migration 0129: Time-tracking discovery expansion III (2026-03-31)
-- Rationale: live production catalog depth for `time-tracking` is still only 4
-- providers, which is too thin for a high-demand operator category that agents
-- repeatedly need for worklog reads/writes, timer control, utilization checks,
-- project budgeting, and invoice-adjacent workflows. Ship five more API-backed
-- providers so the category becomes meaningfully discoverable in production.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'hubstaff',
    'Hubstaff',
    'time-tracking',
    'Time tracking and workforce operations platform with APIs for organizations, projects, tasks, users, schedules, activities, and work reporting.',
    'https://developer.hubstaff.com/docs/hubstaff_v2',
    'api.hubstaff.com'
  ),
  (
    'tempo',
    'Tempo',
    'time-tracking',
    'Jira-native time tracking and planning platform with APIs for worklogs, timesheets, accounts, teams, planning, and budget-aware delivery workflows.',
    'https://apidocs.tempo.io/',
    'api.tempo.io'
  ),
  (
    'quickbooks-time',
    'QuickBooks Time',
    'time-tracking',
    'Time tracking and scheduling platform formerly known as TSheets, with APIs for timesheets, users, jobcodes, reports, and payroll-adjacent operations.',
    'https://tsheetsteam.github.io/api_docs/',
    'rest.tsheets.com'
  ),
  (
    'everhour',
    'Everhour',
    'time-tracking',
    'Project-centric time tracking and budgeting platform with APIs for projects, tasks, time records, timers, users, reports, invoices, and schedule-aware workflows.',
    'https://everhour.docs.apiary.io/',
    'api.everhour.com'
  ),
  (
    'timecamp',
    'TimeCamp',
    'time-tracking',
    'Time tracking platform with APIs for entries, users, projects, tasks, tags, reports, and lightweight operational analytics workflows.',
    'https://developer.timecamp.com/',
    'app.timecamp.com'
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
    'hubstaff',
    8.10,
    8.25,
    7.95,
    0.65,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"time-tracking expansion iii","notes":"Best first Phase 0 target in the batch. Hubstaff exposes general-purpose organization, project, task, and time surfaces without forcing a Jira-shaped workflow."}'::jsonb,
    now()
  ),
  (
    'tempo',
    8.05,
    8.20,
    7.85,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"time-tracking expansion iii","notes":"Strong category anchor for engineering orgs with explicit worklog and planning APIs, though the Jira-coupled model makes it a slightly noisier first normalization target than Hubstaff."}'::jsonb,
    now()
  ),
  (
    'everhour',
    7.95,
    8.10,
    7.80,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"time-tracking expansion iii","notes":"Broad project, timer, and reporting surface makes it a strong second-wave provider for normalized time-entry list/create and timer control."}'::jsonb,
    now()
  ),
  (
    'quickbooks-time',
    7.80,
    7.90,
    7.60,
    0.59,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"time-tracking expansion iii","notes":"Operationally important bridge into scheduling and payroll-adjacent workflows for services firms and field teams, even if the API surface feels older than the category leaders."}'::jsonb,
    now()
  ),
  (
    'timecamp',
    7.55,
    7.70,
    7.40,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"time-tracking expansion iii","notes":"Useful SMB-oriented breadth addition for entries, reports, and project reads. Good catalog coverage even if it is not the first execution wedge."}'::jsonb,
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
