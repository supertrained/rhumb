# Runtime Review — GitHub + Algolia depth 3→4

**Date:** 2026-04-01
**Owner:** Pedro / callable freshness loop

## GitHub depth 3→4

- **Capability:** `social.get_profile`
- **Target:** `/users/octocat` (different from depth-3 which used `/users/supertrained`)
- **Parity fields (8):** login, id, type, name, company, blog, created_at, public_repos
- **Result:** All matched exactly
- Published evidence: `55ae8b4f-c2b5-4b47-acb1-77608e22fc85`
- Published review: `48b211bb-8788-4fec-9756-038b0b9710e3`
- Product commit: `ba83633`

## Algolia depth 3→4

- **Capability:** `search.autocomplete`
- **Query:** `runtime test` on index `rhumb_test`
- **Parity fields (4):** nbHits (1), top objectID (1), top name (Rhumb Runtime Test), query
- **Result:** All matched exactly
- Published evidence: `c475b99f-bab7-4397-af81-5eecf4564586`
- Published review: `aabbd919-678b-4396-ba0d-f5abdce1bb17`
- Execution ID: `exec_59f2b357a1114e8aa7866d77bc7e06e3`

## Twilio depth 3→4 — BLOCKED

Attempted Twilio freshness pass but managed execution for `phone.lookup` returns 503:
- `"No managed execution path for 'phone.lookup' via 'twilio'"`
- Proxy route goes to `api.twilio.com` but Twilio Lookup API is at `lookups.twilio.com`
- Previous depth-3 pass worked via Railway env which had correct URL mapping in execution config
- This is an execution config / production wiring issue, not a freshness issue
- **Twilio remains the sole depth-3 holdout blocking the callable floor from lifting to 4**

## Coverage After This Session
- Callable floor: **3** (Twilio only)
- 15 of 16 callable providers at depth ≥ 4
- Next action: fix Twilio execution config, then rerun
