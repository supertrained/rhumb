# GitHub Phase 3 runtime rerun — current pass

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop
Status: ✅ VERIFIED

## Why GitHub on this pass

Mission 1 requires picking the callable provider with the fewest runtime-backed reviews.

The true lowest-coverage callable bucket after the PDL rerun remained:
- `algolia`
- `apify`
- `apollo`
- `brave-search-api`
- `e2b`
- `exa`
- `people-data-labs`
- `replicate`
- `tavily`
- `unstructured`

Those lanes currently depend on direct provider credentials that were inaccessible on this host because the local `sop` 1Password service-account token has been deleted and the tmux-backed desktop fallback did not recover a vault session during this run.

Rather than fake a direct-control claim, I chose the **next unblocked callable provider with a clean public direct-control lane**: GitHub on `social.get_profile`.

This is a deliberate deviation from the pure lowest-coverage ordering, caused by a credential-path blocker external to the provider execution layer.

## Test setup

### Rhumb Resolve execution
- **Estimate:** `GET /v1/capabilities/social.get_profile/execute/estimate?provider=github&credential_mode=byo`
- **Execute:** `POST /v1/capabilities/social.get_profile/execute`
- **Capability:** `social.get_profile`
- **Provider:** `github`
- **Credential mode:** `byo`
- **Input:**
  ```json
  {
    "provider": "github",
    "credential_mode": "byo",
    "method": "GET",
    "path": "/users/supertrained",
    "interface": "runtime_review"
  }
  ```

### Direct provider control
- **Endpoint:** `GET https://api.github.com/users/supertrained`
- **Auth:** none required for this public profile read

## Results

### Rhumb Resolve
- Estimate returned **200 OK**
  - `endpoint_pattern: GET /users/{username}`
  - `circuit_state: closed`
- Execute returned **200 OK**
- Execution id: `exec_ce894a5cf90d418a8a3ff839b443bdc2`
- Upstream status: `200`
- Returned profile highlights:
  - `login: supertrained`
  - `public_repos: 5`
  - `created_at: 2025-06-06T10:53:11Z`
  - `updated_at: 2026-03-26T21:19:10Z`

### Direct GitHub control
- HTTP **200 OK**
- Returned the same public profile fields:
  - `login: supertrained`
  - `public_repos: 5`
  - `created_at: 2025-06-06T10:53:11Z`
  - `updated_at: 2026-03-26T21:19:10Z`

## Comparison

| Dimension | Rhumb Resolve | Direct GitHub |
|---|---|---|
| HTTP status | 200 | 200 |
| Resource identity | `login=supertrained` | `login=supertrained` |
| Repo count | `5` | `5` |
| Created timestamp | `2025-06-06T10:53:11Z` | `2025-06-06T10:53:11Z` |
| Updated timestamp | `2026-03-26T21:19:10Z` | `2026-03-26T21:19:10Z` |

## Verdict

**GitHub remains healthy on the `social.get_profile` runtime lane.**

This pass produced a fresh live execute and a fresh direct provider control with payload parity.

## Important caveat

This run does **not** resolve the low-coverage managed-provider backlog ordering problem. The direct-provider credential path on this host must be repaired so the next Mission 1 pass can return to the true weakest-review bucket instead of taking the next unblocked provider.
