# 2026-03-31 — GitHub current-depth3 publication

## Goal
Advance the next honest unblocked callable-review freshness lane using the live public audit instead of the stale continuation target ordering.

At the start of this pass:
- the public callable audit showed weakest claim-safe runtime-backed depth **2**
- the weakest bucket had collapsed to just **`github`**
- the next honest move was to publish a fresh GitHub runtime-backed parity pass, not keep following the older Algolia-first note

## What shipped

### 1) Fresh GitHub runtime pass via the production env rail
Used the linked Railway production context to:
- seed a temp org wallet with `5000` cents
- create a temp review agent
- grant only GitHub access
- run `social.get_profile` through Rhumb Resolve on the BYO runtime-review lane
- compare against direct GitHub control on the same public profile
- disable the temp review agent after the pass

Runtime artifact:
- `artifacts/runtime-review-pass-20260401T002329Z-github-depth3.json`

Live target used:
- capability: `social.get_profile`
- provider: `github`
- path: `/users/supertrained`
- direct URL: `https://api.github.com/users/supertrained`

Observed parity:
- Rhumb execute status: **200**
- direct GitHub status: **200**
- `login` matched exactly: **`supertrained`**
- `public_repos` matched exactly: **`7`**
- `created_at` matched exactly: **`2025-06-06T10:53:11Z`**
- `updated_at` matched exactly: **`2026-03-28T08:02:04Z`**

Execution / temp rail:
- temp org: `org_runtime_review_github_20260401t002329z`
- temp review agent: `b9921835-670d-43a4-94bf-e0997dd26bd6`
- Rhumb execution: `exec_a151691bfa7d48f7a669247aadda9ba3`

### 2) Public trust-surface publication
Published the new runtime-backed evidence/review pair to production.

Publication artifact:
- `artifacts/runtime-review-publication-2026-03-31-github-depth3.json`

Inserted rows:
- evidence: `af8a2172-afc8-4f48-ad8e-17b5094a3d5d`
- review: `93c9deed-a382-4fff-8b58-868440f7fb14`

### 3) Public verification artifacts
- pre-audit: `artifacts/callable-review-coverage-2026-03-31-pre-github-depth3.json`
- post-audit: `artifacts/callable-review-coverage-2026-03-31-post-github-depth3.json`

## Validation

### Public audit before publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-31-pre-github-depth3.json`

Result:
- weakest claim-safe callable depth: **2**
- weakest bucket: **`github`**
- `github` sat at depth **2** before the pass

### Public audit after publication
Artifact:
- `artifacts/callable-review-coverage-2026-03-31-post-github-depth3.json`

Result:
- `github` moved **2 → 3** claim-safe runtime-backed reviews
- weakest callable depth moved **2 → 3**
- the new weakest-bucket providers are:
  - `slack`
  - `stripe`
  - `github`
  - `twilio`
  - `algolia`

Freshness note:
- within that depth-3 bucket, **Stripe** is now the stalest by freshest runtime evidence timestamp, so it is the clean next callable freshness target if no newer dogfood defect lands first

## Outcome
This pass kept the callable freshness rotation honest by following the live public audit instead of a stale priority note.

GitHub moved from claim-safe depth **2 → 3**, and the callable review floor moved from **2 → 3**.

## Next move
- take **Stripe** as the next callable freshness target from the new depth-3 weakest bucket
- continue rerunning the Resolve v2 dogfood harness whenever fresh production fixes land
- keep the continuation brief and tracker surfaces aligned to the live public callable audit, not old target ordering
