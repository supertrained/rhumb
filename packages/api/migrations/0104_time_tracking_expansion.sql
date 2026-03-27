BEGIN;

-- Migration 0104: Time-tracking discovery expansion (2026-03-27)
-- Rationale: time tracking is a high-demand operational category for agents,
-- but catalog depth is still thin relative to adjacent operations categories.
-- Add 5 API-backed providers with practical coverage across agency, field-work,
-- Jira-centric engineering, and SMB finance workflows.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'hubstaff',
    'Hubstaff',
    'time-tracking',
    'Time tracking and workforce operations platform with APIs for activities, projects, tasks, organizations, users, and work reporting.',
    'https://developer.hubstaff.com/docs/hubstaff_v2',
    'api.hubstaff.com'
  ),
  (
    'tempo',
    'Tempo',
    'time-tracking',
    'Jira-adjacent time tracking and planning platform with APIs for worklogs, timesheets, accounts, teams, and planning operations.',
    'https://apidocs.tempo.io/',
    'api.tempo.io'
  ),
  (
    'quickbooks-time',
    'QuickBooks Time',
    'time-tracking',
    'Time tracking and scheduling platform (formerly TSheets) with APIs for timesheets, users, jobcodes, reports, and payroll-adjacent operational workflows.',
    'https://tsheetsteam.github.io/api_docs/',
    'rest.tsheets.com'
  ),
  (
    'everhour',
    'Everhour',
    'time-tracking',
    'Time tracking and budgeting platform with APIs for time records, timers, timesheets, tasks, projects, invoices, and reporting workflows.',
    'https://everhour.docs.apiary.io/',
    'api.everhour.com'
  ),
  (
    'timecamp',
    'TimeCamp',
    'time-tracking',
    'Time tracking API for entries, users, projects, tasks, tags, reports, and lightweight operational analytics workflows.',
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
    8.05,
    8.30,
    7.80,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"time-tracking expansion","notes":"Best Phase 0 candidate in the batch. Clean general-purpose surface for time_entry.list, project.list, and workforce activity reads without forcing a Jira-shaped workflow."}'::jsonb,
    now()
  ),
  (
    'tempo',
    7.95,
    8.20,
    7.65,
    0.59,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"time-tracking expansion","notes":"Strong enterprise worklog and planning surface, especially for Jira-heavy teams. Excellent later Resolve target once normalized time-entry primitives are live."}'::jsonb,
    now()
  ),
  (
    'quickbooks-time',
    7.75,
    7.85,
    7.55,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"time-tracking expansion","notes":"Operationally relevant for services, field teams, and payroll-adjacent workflows. API is older than the cleanest modern entrants but still worth catalog coverage."}'::jsonb,
    now()
  ),
  (
    'everhour',
    7.45,
    7.70,
    7.20,
    0.55,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"time-tracking expansion","notes":"Good fit for agency and project-based work with useful time-record and budget-adjacent primitives. Less universal than Hubstaff, but strong enough to include."}'::jsonb,
    now()
  ),
  (
    'timecamp',
    7.35,
    7.55,
    7.10,
    0.54,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-27","category_rationale":"time-tracking expansion","notes":"Solid SMB-oriented time tracking surface for entries, reports, and project reads. Useful breadth addition even if not the first execution wedge."}'::jsonb,
    now()
  );

COMMIT;
