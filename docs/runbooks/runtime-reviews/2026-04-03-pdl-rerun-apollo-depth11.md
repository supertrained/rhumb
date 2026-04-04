# Runtime review runbook — PDL rerun + Apollo depth-11 pass

Date: 2026-04-03 (run executed 2026-04-04T03:01 UTC)
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
`rhumb/artifacts/runtime-review-pass-20260404T025432Z-pdl-fix-verify-20260401b.json`

### Conclusion
Commit `94c8df8` is confirmed live and healthy. PDL will continue to return 402 until the account quota resets; that is not a Rhumb execution failure.

---

## Mission 1 — Apollo depth-11 runtime pass

### Provider selection
- Pre-pass callable coverage audit: all 16 callable providers at depth 10 or 11.
- PDL excluded (Mission 0 handled).
- Apollo was the freshest-evidence oldest member of the depth-10 bucket (`2026-04-01T19:39:09Z`).

### Test parameters
- Capability: `data.enrich_person`
- Provider: `apollo`
- Credential mode: `rhumb_managed`
- Request body: `{"email": "tim@apple.com"}`
- Post-grant propagation delay: 5 seconds
- Estimate retry guard: 4 attempts with 5-second back-off on `401 Invalid or expired Rhumb API key`

### Result
- Estimate: `200` (1 attempt, clean — no auth propagation race)
- Rhumb execute: `200`
- Provider used: `apollo`
- Upstream status: `200`
- Direct Apollo control: `200`
- Execution ID: `exec_53be556d88d94ca3aa5ff9606440c846`
- Parity fields: `name`, `title`, `organization_name`, `linkedin_url`, `email_status`
- All fields matched: `true`
- Verdict: **PASS**

### Published trust rows
- Evidence ID: `1c485e03-e164-4d64-a23b-8f7441802953`
- Review ID: `236668a4-1a2d-48a7-852b-f3725b10cb13`

### Coverage impact
- Apollo moved **10 → 11** claim-safe runtime-backed reviews
- Callable floor remains **10**
- Apollo exits the weakest bucket
- Freshness-ordered next non-PDL runtime target: **EXA** (oldest remaining depth-10 member at `2026-04-02T23:48:31Z`)

### Artifacts
- `rhumb/artifacts/runtime-review-pass-20260404T030129Z-apollo-depth11.json`
- `rhumb/artifacts/runtime-review-publication-2026-04-03-apollo-depth11.json`
- `rhumb/artifacts/callable-review-coverage-2026-04-03-pre-current-pass-from-cron-1952.json`
- `rhumb/artifacts/callable-review-coverage-2026-04-03-post-apollo-depth11.json`

---

## Mission 2 — Reverse-ETL expansion II

### Category rationale
Reverse-ETL had the lowest service count in the entire catalog (3 live providers).
This category is a core agent workflow enabler: agents need to push warehouse truth
into operational SaaS to close the loop between insight and action.

### Added services
| Slug | Score | Phase 0 potential |
|------|-------|------------------|
| `dbt-cloud` | 8.20 | Best: `warehouse.job.status`, semantic-layer query |
| `castled-data` | 8.15 | Clean: `sync.list`, `sync.run`, `sync.status` |
| `nexla` | 8.00 | Good: `dataflow.list`, `dataset.get` |
| `etleap` | 7.85 | Pipeline run monitoring |
| `syncari` | 7.80 | Bi-directional sync inspection |

### Best first Phase 0 target
**dbt Cloud** — job run status and semantic-layer query via the dbt Cloud REST API.

### Migration
`rhumb/packages/api/migrations/0156_reverse_etl_expansion_ii.sql`
