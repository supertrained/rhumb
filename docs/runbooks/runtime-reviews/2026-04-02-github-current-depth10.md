# GitHub runtime review — depth 10 (2026-04-02 PT)

## What this pass did
- Re-ran live callable-review coverage first and confirmed the weakest claim-safe callable bucket was still depth **9**.
- Confirmed **GitHub** was the freshness-ordered oldest member of that weakest bucket.
- Added `scripts/runtime_review_github_depth10_20260402.py` for a reusable production parity pass.
- Ran the pass through Railway production context against Rhumb Resolve and direct GitHub control.

## Production result
- Capability: `social.get_profile`
- Provider: `github`
- Target profile: `torvalds`
- Estimate: `200`
- Rhumb execute: `200`
- Direct GitHub control: `200`
- Execution ID: `exec_12d9a8683120498eb6af529b1d5d6d4e`

## Parity fields checked
- `login`
- `id`
- `type`
- `site_admin`
- `name`
- `company`
- `blog`
- `location`
- `public_repos`
- `followers`
- `following`
- `created_at`

## Observed parity
- Rhumb and direct control both returned:
  - `login = torvalds`
  - `id = 1024025`
  - `type = User`
  - `site_admin = false`
  - `name = Linus Torvalds`
  - `company = Linux Foundation`
  - `blog = ""`
  - `location = Portland, OR`
  - `public_repos = 11`
  - `followers = 294596`
  - `following = 0`
  - `created_at = 2011-09-03T15:26:22Z`
- Published trust rows:
  - evidence `3366e6df-e1c6-4bad-bad0-e5c0c5b3dc4d`
  - review `3650770b-7747-472f-8e56-0389238d3369`

## Harness note worth preserving
- This GitHub rail did **not** reproduce the fresh-agent estimate-path auth flake that hit the Algolia/Twilio-style harnesses.
- I still kept the same post-grant delay + bounded invalid-key estimate retry guard in the helper so future GitHub passes stay aligned with the hardened runtime-review pattern.
- Direct control authenticated with the shared GitHub PAT when available, but the target surface is also a safe public read.

## Coverage impact
- **GitHub moved from 9 → 10 claim-safe runtime-backed reviews.**
- The weakest callable-review depth stays **9**.
- The new weakest callable bucket is:
  - `slack`
  - `stripe`
  - `twilio`
- Freshness-ordered next target is now **Stripe**.

## Artifacts
- `artifacts/callable-review-coverage-2026-04-02-pre-github-current-pass-from-cron-2342.json`
- `artifacts/runtime-review-pass-20260403T064639Z-github-depth10.json`
- `artifacts/runtime-review-publication-2026-04-02-github-depth10.json`
- `artifacts/callable-review-coverage-2026-04-02-post-github-current-pass-from-cron-2342.json`
