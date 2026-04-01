# Discovery expansion — scheduling

Date: 2026-04-01
Owner: Pedro / Keel runtime review loop

## Why this category

Live production still shows **`scheduling`** at only **5** providers:
- `cronitor`
- `mergent`
- `qstash`
- `trevor-io`
- `zeplo`

That is too thin for a category agents need constantly for:
- reminders and delayed follow-ups
- deferred retries and backoff work
- scheduled data refreshes
- recurring background jobs
- queue-backed orchestration and timed execution

The honest Mission 2 move was to deepen **scheduling** with more API-backed rails that agents and developers actually use for durable delayed work, not to add another fringe category.

## Added services

### 1. Trigger.dev
- Slug: `trigger-dev`
- Score: **8.45**
- Execution: **8.55**
- Access readiness: **8.25**
- Why it made the cut:
  - purpose-built for developer-managed background jobs and delayed execution
  - strongest clean candidate for normalized schedule creation and job-run tracking

### 2. Inngest
- Slug: `inngest`
- Score: **8.35**
- Execution: **8.45**
- Access readiness: **8.15**
- Why it made the cut:
  - explicit cron, delayed events, retries, and durable background workflows
  - strategically important modern scheduling rail for agent-native app backends

### 3. Temporal Cloud
- Slug: `temporal-cloud`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **7.95**
- Why it made the cut:
  - serious durable workflow and schedule depth for long-running agent workflows
  - useful category depth beyond lightweight cron/task queues

### 4. Google Cloud Tasks
- Slug: `google-cloud-tasks`
- Score: **8.10**
- Execution: **8.25**
- Access readiness: **7.90**
- Why it made the cut:
  - clear delayed HTTP task and queue surface with retries and rate controls
  - practical scheduling primitive for agent-triggered backend execution

### 5. AWS EventBridge Scheduler
- Slug: `aws-eventbridge-scheduler`
- Score: **8.05**
- Execution: **8.20**
- Access readiness: **7.85**
- Why it made the cut:
  - explicit one-time and recurring schedule creation at infrastructure scale
  - strong enterprise and ops relevance for agent-driven time-based automation

## Phase 0 capability assessment

All five additions expose accessible APIs and are viable Resolve candidates.

### Strongest candidates for Resolve capability addition
1. **Trigger.dev**
2. **Inngest**
3. **Google Cloud Tasks**
4. **AWS EventBridge Scheduler**

### Candidate capability shapes
- `job.schedule.create`
- `job.schedule.list`
- `job.schedule.cancel`
- `task.enqueue`
- `job.run.list`

### Best initial Phase 0 wedge
The cleanest first move is:
- `job.schedule.create`

Why:
- it is the universal primitive across delayed and recurring execution rails
- it supports reminders, retries, follow-ups, and agent-owned deferred work
- it is easier to normalize than full workflow definitions or queue-governance surfaces
- **Trigger.dev** is the best first provider target because its API is purpose-built for developer-facing background jobs and delayed execution rather than being buried inside a much larger cloud control plane

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0145_scheduling_expansion.sql`

## Verdict

Scheduling is still underrepresented in live production. This batch adds five more real API-backed providers and sharpens the next honest Resolve wedge around **`job.schedule.create`**, with **Trigger.dev** as the cleanest first implementation target.
