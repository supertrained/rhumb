# Runtime Review — GitHub depth 3→4

**Date:** 2026-04-01
**Owner:** Pedro / Keel runtime review loop

## Why GitHub

Fresh callable audit showed weakest claim-safe depth **3** across 3 providers: `github`, `twilio`, `algolia`. GitHub was the next freshest after Slack was just advanced.

## Pass Details

- **Capability:** `social.get_profile`
- **Endpoint:** GET /users/octocat (different target from depth-3 pass which used `/users/supertrained`)
- **Previous depth-3 pass:** 4 parity fields on `supertrained` profile
- **This pass:** 8 parity fields on `octocat` profile — demonstrates proxy handles arbitrary profile targets

### Parity Fields
1. `login` — octocat
2. `id` — 583231
3. `type` — User
4. `name` — The Octocat
5. `company` — @github
6. `blog` — https://github.blog
7. `created_at` — 2011-01-25T18:44:36Z
8. `public_repos` — 8

All 8 fields matched exactly between managed and direct.

### Temp Agent
- Org: `org_rhumb_internal`
- Agent: `864414f1-0edd-42cc-8432-f8e04a654e60`
- Granted explicit `github` service access
- Disabled after pass

## Published Trust Rows
- Evidence: `55ae8b4f-c2b5-4b47-acb1-77608e22fc85`
- Review: `48b211bb-8788-4fec-9756-038b0b9710e3`

## Coverage Impact
- GitHub claim-safe runtime-backed reviews: **3 → 4**
- Callable review floor stayed: **3**
- Weakest bucket shrank: **3 → 2** (twilio, algolia)

## Artifacts
- Runtime pass: `artifacts/runtime-review-pass-20260401T114700Z-github-depth4.json`
- Post-pass audit: `artifacts/callable-review-coverage-2026-04-01-post-github-depth4.json`

## Next Target
Next in the weakest depth-3 bucket: `twilio` (freshest evidence: 2026-03-31T23:28:16Z) or `algolia` (freshest evidence: 2026-03-30T20:44:08Z). Algolia is stalest.
