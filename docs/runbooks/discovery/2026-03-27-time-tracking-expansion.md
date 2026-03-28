# Discovery expansion — time-tracking (2026-03-27)

Owner: Pedro / Keel runtime loop
Mission: Discovery expansion after Phase 3 runtime verification work

## Why this category

Time-tracking remains underrepresented in the Rhumb catalog despite being a high-demand operational category for:
- agencies and service businesses that need billable-time and client reporting workflows
- product / engineering orgs that need timer, timesheet, and project-time reporting
- finance / revops teams that need utilization, invoicing, and payroll-adjacent syncs

Current category coverage was only 4 services before this pass, including an awkward Toggl duplicate. That is too thin for a category this operationally common.

## Services added

1. **Tempo** — Jira-native worklog, approval, project, and financial planning API surface
2. **Hubstaff** — workforce/time tracking API with OAuth2, webhooks, schedules, tasks, and activity data
3. **Kimai** — open-source self-hosted time tracking with bearer-token REST API
4. **Everhour** — project/time/timer/timesheet/invoice API with API-key auth
5. **Timely** — OAuth-based admin API for projects, time entries, and reporting data

All five were added with initial L3/Ready scores in migration `0106_time_tracking_expansion.sql`.

## Phase 0 Resolve assessment

### Strongest immediate candidate: Hubstaff

Why Hubstaff is the best first Resolve target from this batch:
- public OAuth2 flow is documented
- downloadable OpenAPI document exists
- resource model is explicit and broad
- webhook support exists for event-driven automations
- likely initial primitives:
  - `time_entry.list`
  - `time_entry.create`
  - `project.list`
  - `task.list`
  - `schedule.list`

### Other notable candidates

- **Tempo**: rich API and high market relevance, but Jira-coupled model makes Phase 0 narrower and more opinionated
- **Everhour**: API-key auth and broad CRUD surface make it viable, but beta label lowers confidence for first-wave execution
- **Kimai**: technically very agent-friendly for self-hosted teams, but instance-specific deployment reduces default accessibility
- **Timely**: public API is real, but product boundaries around Memory/private data mean primitive selection needs care

## Recommendation

If we open another Phase 0 lane for discovery-backed provider additions, **Hubstaff should be first from this batch**.
