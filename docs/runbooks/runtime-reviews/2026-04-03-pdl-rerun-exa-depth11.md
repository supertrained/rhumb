# Runtime review runbook — PDL rerun + Exa depth-11 pass

Date: 2026-04-03 (run executed 2026-04-04T06:55 UTC)
Owner: Pedro / Keel runtime review loop

## Mission 0 — PDL production rerun

### Purpose
Mandatory per-run reconfirmation of the PDL slug-normalization fix shipped in commit `94c8df8`.

### Result
- Estimate: `200` (1 attempt, clean)
- Rhumb execute: `200`
- Provider used: `people-data-labs`
- Rhumb upstream: `402` (quota exhausted)
- Direct PDL control: `402` (quota exhausted)
- Error parity: exact (`You have hit your account maximum for person enrichment (all matches used)`)
- Verdict: **PASS** — slug routing is working correctly; blocker is only PDL account quota

### Artifact
`rhumb/artifacts/runtime-review-pass-20260404T065703Z-pdl-fix-verify-20260401b.json`

### Conclusion
Commit `94c8df8` is confirmed live and healthy for the 11th consecutive rerun. PDL will continue to return 402 until account quota resets — this is not a Rhumb execution failure.

---

## Mission 1 — Exa depth-11 runtime pass

### Provider selection
- Pre-pass callable coverage audit: 16 callable providers; callable floor at depth 10.
- PDL excluded (Mission 0 handled).
- Exa was the freshness-ordered oldest non-PDL member of the depth-10 bucket (`2026-04-02T23:48:31Z`).

### Test parameters
- Capability: `search.query`
- Provider: `exa`
- Credential mode: `rhumb_managed`
- Request body: `{"query": "best AI agent observability tools", "numResults": 3}`
- Post-grant propagation delay: 5 seconds
- Estimate retry guard: 4 attempts with 5-second back-off on `401 Invalid or expired Rhumb API key`

### Result
- Estimate: `200` (1 attempt, clean — no auth propagation race)
- Rhumb execute: `200`
- Provider used: `exa`
- Upstream status: `200`
- Direct Exa control: `200`
- Execution ID: `exec_17917ac7f64d4ed9814557d33fd94462`
- Parity fields:
  - result count (3 / 3): `true`
  - top title: `"5 best AI agent observability tools for agent reliability in 2026 - Articles"` — match
  - top URL: `https://www.braintrust.dev/articles/best-ai-agent-observability-tools-2026` — match
  - top-3 URL ordering: exact match
- All checked: `true`
- Verdict: **PASS**

### Published trust rows
- Evidence ID: `80448940-26b7-4a66-8cb6-e310cc24931c`
- Review ID: `9d9f359d-07d8-4005-8703-e261ccc944da`

### Coverage impact
- Exa moved **10 → 11** claim-safe runtime-backed reviews
- Callable floor remains **10**
- Exa exits the depth-10 weakest bucket
- Post-pass weakest bucket depth-10 providers: github, slack, stripe, apify, replicate, unstructured, algolia, people-data-labs, twilio
- Freshness-ordered next honest non-PDL target: **Unstructured** (`2026-04-03T00:40:33Z`)

### Artifacts
- `rhumb/artifacts/runtime-review-pass-20260404T065913Z-exa-depth11.json`
- `rhumb/artifacts/runtime-review-publication-2026-04-03-exa-depth11.json`
- `rhumb/artifacts/callable-review-coverage-2026-04-03-pre-current-pass-from-cron-2355.json`
- `rhumb/artifacts/callable-review-coverage-2026-04-03-post-exa-depth11.json`

---

## Mission 2 — APM expansion II

### Category rationale
APM had only 5 providers in the catalog (aspecto, elastic-apm, jaeger, lightstep, opentelemetry) — all open-source/SDK-first with no clean externally-accessible managed API surface. APM is high-demand for agent-driven incident response and autonomous monitoring workflows.

### Added services
| Slug | Score | Phase 0 potential |
|------|-------|------------------|
| `appsignal` | 8.25 | Best: `apm.errors.list`, `apm.performance.summary` (REST + API key) |
| `middleware-io` | 8.10 | Strong: `apm.trace.get`, `apm.metrics.query` |
| `instana` | 8.05 | Enterprise: `apm.service.list`, `apm.events.list` |
| `appdynamics` | 7.80 | Business transactions, health rules (Splunk-wrapped, second-wave) |
| `apache-skywalking` | 7.70 | GraphQL topology + trace queries (self-hosted, deferred) |

### Best first Phase 0 target
**AppSignal** — `apm.errors.list` via `GET /api/errors.json`

### Migration
`rhumb/packages/api/migrations/0157_apm_expansion_ii.sql`
