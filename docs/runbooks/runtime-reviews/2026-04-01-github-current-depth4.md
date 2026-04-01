# Runtime Review — GitHub depth 3→4 (→5)

**Date:** 2026-04-01
**Owner:** Pedro / Keel runtime review loop

## Why GitHub

Fresh callable audit showed GitHub in the weakest depth-3 bucket. Previous depth-3 pass used `social.get_profile` on `supertrained`. This pass uses the proxy directly on a different target (`octocat`) to prove broader routing parity.

## Pass Details

- **Endpoint:** GET /users/octocat (safe read, no side effects)
- **Previous pass:** v1 execute on social.get_profile for supertrained
- **This pass:** proxy-based GET on octocat, expanded to 10 parity fields

### Parity Fields (10)
1. `login` — octocat
2. `id` — 583231
3. `type` — User
4. `site_admin` — false
5. `name` — The Octocat
6. `company` — @github
7. `blog` — https://github.blog
8. `location` — San Francisco
9. `public_repos` — 8
10. `created_at` — 2011-01-25T18:44:36Z

**All 10 fields matched exactly between managed proxy and direct GitHub API.**

## Published Trust Rows
- Evidence: `c4b77794-518c-4f72-a4ff-a94b525f6169`
- Review: `37e3111b-bb68-411a-b0a1-9448d9daafb8`

## Coverage Impact
- GitHub claim-safe runtime-backed reviews: **3 → 5** (depth-3 from earlier + this depth-4 pass)
- **Callable review floor moved: 3 → 4** (all 16 providers now at ≥4)
- Keel cron runs advanced twilio and algolia to depth 4 in parallel

## Artifacts
- Runtime pass: `artifacts/runtime-review-pass-20260401T120650Z-github-depth4.json`
- Post-pass audit: `artifacts/callable-review-coverage-2026-04-01-post-github-depth4.json`
- Helper script: `scripts/runtime_review_github_depth4_20260401.py`
