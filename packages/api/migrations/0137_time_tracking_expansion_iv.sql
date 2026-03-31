BEGIN;

-- Migration 0137: Time-tracking discovery expansion IV (2026-03-31)
-- Rationale: live production still shows time-tracking as an underrepresented
-- operator category despite strong day-to-day demand for time-entry reads,
-- timer control, project/client rollups, and productivity reporting.
-- Add five more API-backed providers with a clean Phase 0 path around
-- time.entries.list/create and timers.start/stop.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'timedoctor',
    'Time Doctor',
    'time-tracking',
    'Time tracking and workforce analytics platform with APIs for users, projects, tasks, worklogs, attendance, screenshots, payroll-adjacent reporting, and operational productivity workflows.',
    'https://developer.timedoctor.com/',
    'api2.timedoctor.com'
  ),
  (
    'kimai',
    'Kimai',
    'time-tracking',
    'Open-source time-tracking platform with REST APIs for timesheets, customers, projects, activities, tags, users, and timer-oriented workflow automation.',
    'https://www.kimai.org/documentation/rest-api.html',
    'kimai.cloud'
  ),
  (
    'jibble',
    'Jibble',
    'time-tracking',
    'Time tracking and attendance platform with APIs for timesheets, members, activities, projects, schedules, payroll-adjacent attendance data, and operational reporting.',
    'https://docs.jibble.io/docs/jibble-2',
    'api.jibble.io'
  ),
  (
    'rescuetime',
    'RescueTime',
    'time-tracking',
    'Automatic time-tracking and productivity analytics platform with APIs for daily summaries, activity data, focus-time reporting, and operator productivity workflows.',
    'https://www.rescuetime.com/apidoc',
    'www.rescuetime.com'
  ),
  (
    'timeular',
    'Timeular',
    'time-tracking',
    'Time tracking platform with APIs for activities, tags, time entries, users, workspaces, and timer-driven operational workflows for agencies and SMB teams.',
    'https://developers.timeular.com/',
    'api.timeular.com'
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
    'timedoctor',
    8.15,
    8.20,
    8.05,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"time-tracking expansion iv","notes":"Strong commercial time-tracking surface for projects, users, worklogs, and attendance. Good future Resolve target for list/create time-entry operations once the lighter open-doc provider is normalized."}'::jsonb,
    now()
  ),
  (
    'kimai',
    8.10,
    8.20,
    7.95,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"time-tracking expansion iv","notes":"Cleanest technical Phase 0 candidate in the batch. Kimai exposes explicit timesheet, customer, project, and activity primitives through a straightforward REST API that maps well to time.entries.list/create and timer-adjacent control."}'::jsonb,
    now()
  ),
  (
    'jibble',
    7.95,
    8.05,
    7.80,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"time-tracking expansion iv","notes":"Useful crossover between time tracking and attendance operations. Good fit for shift-aware time-entry reads and approvals even if it is slightly broader than a pure timer API."}'::jsonb,
    now()
  ),
  (
    'rescuetime',
    7.85,
    7.70,
    8.05,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"time-tracking expansion iv","notes":"More analytics-heavy than timer-heavy, but valuable for read-first productivity and focus reporting workflows. Strong support for operator summaries and coaching-style agent use cases."}'::jsonb,
    now()
  ),
  (
    'timeular',
    7.75,
    7.85,
    7.60,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-31","category_rationale":"time-tracking expansion iv","notes":"Useful additional commercial timer platform with explicit activities and time-entry APIs. Good catalog depth addition even if it trails Kimai and Time Doctor as the first normalization target."}'::jsonb,
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
