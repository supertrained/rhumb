# Discovery expansion — logging II

Date: 2026-04-02
Owner: Pedro / Keel runtime review loop

## Why this category

Live production still shows **`logging`** as thin relative to operator demand.

Why that matters:
- agents repeatedly need **log search** during incidents, regressions, and user-impact debugging
- support and ops workflows often start with **find the failing request / trace / job / error signature**
- logging is one of the cleanest cross-provider read-first surfaces to normalize honestly before attempting broader observability automation

So the honest Mission 2 move was to deepen **logging** again instead of adding another novelty category.

## Added services

### 1. Google Cloud Logging
- Slug: `google-cloud-logging`
- Score: **8.45**
- Execution: **8.60**
- Access readiness: **8.20**
- Why it made the cut:
  - explicit REST API for log entry search, filters, tailing, sinks, and saved-query style workflows
  - strategically important because many modern products already run on GCP

### 2. Splunk Cloud Platform
- Slug: `splunk-cloud-platform`
- Score: **8.35**
- Execution: **8.50**
- Access readiness: **8.05**
- Why it made the cut:
  - mature enterprise search-job semantics with obvious operator value
  - strong fit for incident triage, alert follow-up, and forensic search workflows

### 3. Graylog
- Slug: `graylog`
- Score: **8.25**
- Execution: **8.35**
- Access readiness: **8.00**
- Why it made the cut:
  - strong REST-first search and stream model
  - important self-hosted and mid-market operational footprint

### 4. Azure Monitor Logs
- Slug: `azure-monitor-logs`
- Score: **8.15**
- Execution: **8.30**
- Access readiness: **7.85**
- Why it made the cut:
  - explicit KQL query API with direct relevance to Microsoft-heavy shops
  - strategically necessary coverage for real enterprise operator environments

### 5. SolarWinds Loggly
- Slug: `solarwinds-loggly`
- Score: **7.85**
- Execution: **8.00**
- Access readiness: **7.55**
- Why it made the cut:
  - credible commercial logging/search API
  - useful category depth even if the platform is less modern than the strongest first-wave targets

## Phase 0 capability assessment

All five additions expose accessible APIs and are viable Resolve candidates.

### Strongest candidates for Resolve capability addition
1. **Google Cloud Logging**
2. **Splunk Cloud Platform**
3. **Graylog**
4. **Azure Monitor Logs**

### Candidate capability shapes
- `log.query`
- `log.tail`
- `log.saved_query.list`
- `log.saved_query.read`
- `alert.search`

### Best initial Phase 0 wedge
The cleanest first move is:
- `log.query`

Why:
- it is the most universal read-first primitive across the category
- it supports incident response, support debugging, and ops triage without requiring risky write actions
- it is easier to normalize honestly than alerts, pipelines, dashboards, or retention controls
- **Google Cloud Logging** is the best first provider target because `entries:list` plus filter semantics map directly to a normalized log query shape and the provider matters strategically in real production estates

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0147_logging_expansion_ii.sql`

## Verdict

Logging remains a high-demand category where Rhumb should be materially deeper. This batch adds five more credible API-backed providers and sharpens the next honest Resolve wedge around **`log.query`**, with **Google Cloud Logging** as the best first implementation target.
