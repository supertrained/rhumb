BEGIN;

-- Migration 0119: Time-tracking discovery expansion (2026-03-29)
-- Rationale: time-tracking is still underrepresented relative to how often
-- agents need structured worklog reads/writes for project ops, billing,
-- utilization reporting, async standups, and human-in-the-loop automation.
-- Add five API-backed providers with a clean future Resolve wedge around
-- time entry list/create, timer control, and lightweight reporting.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'toggl-track',
    'Toggl Track',
    'time-tracking',
    'Time-tracking platform with a mature JSON API for workspaces, projects, users, time entries, reports, and timer-adjacent workflows that fit agentic worklog automation well.',
    'https://engineering.toggl.com/docs/',
    'api.track.toggl.com'
  ),
  (
    'timely',
    'Timely',
    'time-tracking',
    'Automatic time-tracking and memory-timeline product with a developer API for account data, projects, people, and logged time across planning and reporting workflows.',
    'https://developer.timely.com/',
    'api.timelyapp.com'
  ),
  (
    'everhour',
    'Everhour',
    'time-tracking',
    'Project time-tracking and planning API spanning projects, tasks, users, reports, timers, schedules, and invoice-adjacent workflows for agency and product teams.',
    'https://everhour.docs.apiary.io/',
    'api.everhour.com'
  ),
  (
    'trackingtime',
    'TrackingTime',
    'time-tracking',
    'Time-tracking API with customers, projects, tasks, events, users, and account-scoped worklog reads that map well to agent-driven reporting and sync flows.',
    'https://developers.trackingtime.co/',
    'api.trackingtime.co'
  ),
  (
    'tickspot',
    'Tick',
    'time-tracking',
    'Budget-aware time-tracking platform with a REST API suited to project, budget, and time-entry automation for teams that operate against hours and spend targets.',
    'https://www.tickspot.com/api',
    'www.tickspot.com'
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
    'toggl-track',
    8.30,
    8.45,
    8.10,
    0.67,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"time-tracking expansion","notes":"Best first Phase 0 target in the batch. Mature API surface, explicit workspace/time-entry/reporting primitives, and clean normalization around time-entry list/create plus timer control."}'::jsonb,
    now()
  ),
  (
    'everhour',
    8.10,
    8.25,
    7.90,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"time-tracking expansion","notes":"Broad project/timer/reporting surface makes it a strong second provider for normalized worklog and reporting capabilities."}'::jsonb,
    now()
  ),
  (
    'timely',
    8.00,
    8.15,
    7.85,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"time-tracking expansion","notes":"Strategically valuable because automatic memory-style time capture complements explicit worklog systems and broadens the category beyond manual timers alone."}'::jsonb,
    now()
  ),
  (
    'trackingtime',
    7.90,
    8.05,
    7.75,
    0.59,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"time-tracking expansion","notes":"Practical account/project/task API with straightforward reads and writes that fit agent sync and reporting workflows cleanly."}'::jsonb,
    now()
  ),
  (
    'tickspot',
    7.80,
    7.95,
    7.65,
    0.56,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"time-tracking expansion","notes":"Useful budget-aware time-entry surface that adds hours-vs-budget workflow depth even if the API looks older than the leaders in the batch."}'::jsonb,
    now()
  );

COMMIT;
