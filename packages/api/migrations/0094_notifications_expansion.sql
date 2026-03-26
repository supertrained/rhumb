BEGIN;

-- Migration 0094: Notifications discovery expansion (2026-03-26)
-- Rationale: notifications is a high-demand operational category for agents,
-- but the public catalog only had two notification-centric providers.
-- Add 4 widely-used notification infrastructure providers with initial scoring.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'knock',
    'Knock',
    'notifications',
    'Cross-channel notification infrastructure with workflows, recipients, schedules, broadcasts, preferences, and in-product messaging APIs.',
    'https://docs.knock.app/api-reference/overview',
    'api.knock.app'
  ),
  (
    'novu',
    'Novu',
    'notifications',
    'Open-core notification infrastructure for subscribers, workflows, providers, multi-channel delivery, and in-app/product notifications via server-side API.',
    'https://docs.novu.co/api-reference/overview',
    'api.novu.co'
  ),
  (
    'suprsend',
    'SuprSend',
    'notifications',
    'Omni-channel notification platform with workflow abstraction, vendor routing, templates, preferences, and HTTPS APIs for product messaging.',
    'https://docs.suprsend.com/docs/what-is-suprsend.md'
  ),
  (
    'magicbell',
    'MagicBell',
    'notifications',
    'Notification inbox and delivery API with recipient targeting, batching, OpenAPI coverage, and in-app notification infrastructure.',
    'https://www.magicbell.com/docs/api',
    'api.magicbell.com'
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
    'knock',
    7.70,
    7.90,
    7.45,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"notifications expansion","notes":"Strong workflow-driven notification platform with clear REST docs, bearer auth, recipients/channels abstractions, and a practical fit for normalized notification.send and notification.broadcast capabilities."}'::jsonb,
    now()
  ),
  (
    'novu',
    7.40,
    7.60,
    7.10,
    0.55,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"notifications expansion","notes":"Open-core notification infrastructure with server-side API, subscriber model, and multi-channel provider abstraction. Strong Phase 0 candidate for notification send/schedule flows."}'::jsonb,
    now()
  ),
  (
    'suprsend',
    7.20,
    7.45,
    6.95,
    0.54,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"notifications expansion","notes":"Omni-channel HTTPS API and workflow model make it a credible notification orchestration surface for agents, though setup complexity looks somewhat higher than Knock/Novu."}'::jsonb,
    now()
  ),
  (
    'magicbell',
    6.90,
    7.15,
    6.65,
    0.52,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-26","category_rationale":"notifications expansion","notes":"Useful notification inbox/delivery API with batching and OpenAPI, but narrower orchestration scope than the leading notification workflow platforms in this batch."}'::jsonb,
    now()
  );

COMMIT;
