BEGIN;

-- Migration 0145: Scheduling discovery expansion (2026-04-01)
-- Rationale: live production still shows the scheduling category at only five
-- providers despite scheduling/delayed execution being a core agent primitive
-- for reminders, retries, deferred work, recurring jobs, and background task
-- orchestration.
--
-- This batch deepens the category with modern API-backed scheduling and task
-- orchestration surfaces spanning developer-first job platforms, durable cloud
-- task queues, and workflow-native schedulers.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'trigger-dev',
    'Trigger.dev',
    'scheduling',
    'Developer-first background jobs and scheduling platform with APIs for task runs, delayed execution, schedules, retries, webhooks, and long-running job orchestration.',
    'https://trigger.dev/docs',
    'api.trigger.dev'
  ),
  (
    'inngest',
    'Inngest',
    'scheduling',
    'Event-driven job orchestration platform with APIs for functions, delayed execution, cron schedules, retries, and durable background workflows for application and agent systems.',
    'https://www.inngest.com/docs',
    'api.inngest.com'
  ),
  (
    'temporal-cloud',
    'Temporal Cloud',
    'scheduling',
    'Durable workflow orchestration platform with cloud APIs for namespaces, schedules, workflow execution, retries, timers, and long-running stateful job control.',
    'https://docs.temporal.io/cloud',
    'api.temporal.io'
  ),
  (
    'google-cloud-tasks',
    'Google Cloud Tasks',
    'scheduling',
    'Managed task queue and delayed execution service with APIs for queue management, task creation, scheduling, retries, rate limits, and HTTP task dispatch.',
    'https://cloud.google.com/tasks/docs/reference/rest',
    'cloudtasks.googleapis.com'
  ),
  (
    'aws-eventbridge-scheduler',
    'AWS EventBridge Scheduler',
    'scheduling',
    'AWS scheduling service with APIs for one-time and recurring schedules, flexible time windows, target invocation, retries, dead-letter routing, and large-scale time-based automation.',
    'https://docs.aws.amazon.com/scheduler/latest/APIReference/Welcome.html',
    'scheduler.amazonaws.com'
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
    'trigger-dev',
    8.45,
    8.55,
    8.25,
    0.68,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-01","category_rationale":"scheduling expansion","notes":"Best immediate Phase 0 candidate in the batch. Trigger.dev is purpose-built for developer-managed background jobs and delayed execution with a modern API surface that maps well to job.schedule.create, job.run.list, and job.cancel primitives."}'::jsonb,
    now()
  ),
  (
    'inngest',
    8.35,
    8.45,
    8.15,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-01","category_rationale":"scheduling expansion","notes":"Strong second developer-first scheduling rail with explicit support for cron, delayed events, retries, and durable background execution. Good long-term fit for normalized agent scheduling and deferred follow-up workflows."}'::jsonb,
    now()
  ),
  (
    'temporal-cloud',
    8.20,
    8.35,
    7.95,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-01","category_rationale":"scheduling expansion","notes":"Strategically important durable workflow rail with serious scheduling depth. Slightly heavier than the cleanest first target, but highly relevant for long-running agent workflows, retries, timers, and schedule ownership."}'::jsonb,
    now()
  ),
  (
    'google-cloud-tasks',
    8.10,
    8.25,
    7.90,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-01","category_rationale":"scheduling expansion","notes":"Excellent delayed HTTP task and queue primitive with explicit task scheduling, retry controls, and queue governance. Strong enterprise relevance, though Google auth setup makes it a slightly heavier first Resolve wedge than Trigger.dev."}'::jsonb,
    now()
  ),
  (
    'aws-eventbridge-scheduler',
    8.05,
    8.20,
    7.85,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-01","category_rationale":"scheduling expansion","notes":"Broad-scale schedule creation rail for one-time and recurring invocations across AWS targets. Valuable category depth and a strong future target once the simpler cross-provider schedule-create shape is proven."}'::jsonb,
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
