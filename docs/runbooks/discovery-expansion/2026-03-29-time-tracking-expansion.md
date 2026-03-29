# Discovery expansion — time-tracking

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop

## Why this category

Time-tracking is still underrepresented relative to how often agents need it.

Current live depth before this batch was only **2** providers:
- `clockify`
- `harvest`

That is too thin for a category agents routinely need for:
- writing worklogs from completed tasks
- listing recent entries for standups and status summaries
- timer start / stop automation
- project and client utilization reporting
- invoice support and budget-vs-hours checks
- syncing operational work across PM, billing, and support systems

## Added services

### 1. Toggl Track
- Slug: `toggl-track`
- Score: **8.30**
- Execution: **8.45**
- Access readiness: **8.10**
- Why it made the cut:
  - mature API with explicit workspaces, projects, users, time entries, and reports
  - cleanest immediate normalization target in the batch
  - strongest fit for read/write worklog automation and timer-adjacent workflows

### 2. Everhour
- Slug: `everhour`
- Score: **8.10**
- Execution: **8.25**
- Access readiness: **7.90**
- Why it made the cut:
  - broad project, timer, schedule, report, and invoice-adjacent surface
  - strong second provider for normalized time-entry and reporting capabilities

### 3. Timely
- Slug: `timely`
- Score: **8.00**
- Execution: **8.15**
- Access readiness: **7.85**
- Why it made the cut:
  - expands the category beyond explicit manual timers into automatic memory-style time capture
  - strategically useful for agent-assisted timesheet drafting and activity reconstruction

### 4. TrackingTime
- Slug: `trackingtime`
- Score: **7.90**
- Execution: **8.05**
- Access readiness: **7.75**
- Why it made the cut:
  - straightforward API around customers, projects, tasks, users, and events
  - good fit for agent-driven reporting and sync flows

### 5. Tick
- Slug: `tickspot`
- Score: **7.80**
- Execution: **7.95**
- Access readiness: **7.65**
- Why it made the cut:
  - adds budget-aware time-tracking depth, not just generic timers
  - useful for hours-vs-budget checks and client/project control workflows

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose accessible APIs.

Strongest early Resolve targets:
1. **Toggl Track**
2. **Everhour**
3. **TrackingTime**
4. **Timely**

### Candidate capability shapes
- `time.entries.list`
- `time.entries.create`
- `time.entries.update`
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
- **Toggl Track** is the best first provider target because its API is explicit, mature, and already shaped around the primitives a normalized time-entry contract needs

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0119_time_tracking_expansion.sql`

## Verdict

Time-tracking depth was too thin for a workflow primitive agents will repeatedly need in operations, billing, and project automation. This batch materially improves the discovery surface, and **Toggl Track is now the clearest next Phase 0 candidate** when the time-tracking capability lane opens.
