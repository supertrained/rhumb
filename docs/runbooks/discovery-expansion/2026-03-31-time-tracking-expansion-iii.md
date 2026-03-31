# Discovery expansion — time-tracking III

Date: 2026-03-31
Owner: Pedro / Keel runtime review loop

## Why this category

Live production category counts still show `time-tracking` at only **4** providers:
- `clockify`
- `harvest`
- `toggl`
- `toggl-api`

That is too thin for a high-demand operational category agents repeatedly need for:
- writing worklogs from completed tasks
- listing recent entries for standups and status summaries
- timer start / stop automation
- project and client utilization reporting
- invoice support and budget-vs-hours checks
- syncing operational work across PM, payroll, and accounting systems

So the honest Mission 2 move was to deepen the live time-tracking catalog rather than invent a new thin category.

## Added services

### 1. Hubstaff
- Slug: `hubstaff`
- Score: **8.10**
- Execution: **8.25**
- Access readiness: **7.95**
- Why it made the cut:
  - clean API surface for organizations, projects, tasks, users, schedules, and activity data
  - broad operator relevance beyond any single PM ecosystem
  - best first Phase 0 target in the batch

### 2. Tempo
- Slug: `tempo`
- Score: **8.05**
- Execution: **8.20**
- Access readiness: **7.85**
- Why it made the cut:
  - deep worklog and planning primitives for Jira-heavy engineering teams
  - strategically important category anchor for software orgs where time tracking is embedded in delivery workflows

### 3. Everhour
- Slug: `everhour`
- Score: **7.95**
- Execution: **8.10**
- Access readiness: **7.80**
- Why it made the cut:
  - broad project, timer, and reporting surface
  - strong second-wave provider for normalized time-entry and timer capabilities

### 4. QuickBooks Time
- Slug: `quickbooks-time`
- Score: **7.80**
- Execution: **7.90**
- Access readiness: **7.60**
- Why it made the cut:
  - important bridge between time tracking, scheduling, and payroll-adjacent workflows
  - especially relevant for agencies, field teams, and service businesses

### 5. TimeCamp
- Slug: `timecamp`
- Score: **7.55**
- Execution: **7.70**
- Access readiness: **7.40**
- Why it made the cut:
  - practical SMB time-tracking API with usable entries, reports, and project reads
  - broadens category depth without over-indexing on enterprise-only tooling

## Phase 0 capability assessment

All five additions expose accessible APIs and are viable Resolve candidates.

### Strongest candidates for Resolve capability addition
1. **Hubstaff**
2. **Tempo**
3. **Everhour**
4. **QuickBooks Time**

### Candidate capability shapes
- `time.entries.list`
- `time.entries.create`
- `timers.start`
- `timers.stop`
- `projects.list`
- `reports.summary`

### Best initial Phase 0 wedge
The cleanest first move is:
- `time.entries.list`
- `time.entries.create`
- `timers.start`
- `timers.stop`

Why:
- these are common across human and agent workflows
- they normalize cleanly across the strongest providers in the batch
- they create an obvious follow-on path into project reporting and utilization summaries
- **Hubstaff** is the best first provider target because its resource model is explicit and general-purpose without forcing a Jira-shaped workflow from day one

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0129_time_tracking_expansion_iii.sql`

## Verdict

Time-tracking was still underweight in the live catalog. This batch adds five more real API-backed providers and sharpens the next honest Resolve wedge around **time entry reads/writes plus timer control**, with **Hubstaff** as the clearest first provider target.
