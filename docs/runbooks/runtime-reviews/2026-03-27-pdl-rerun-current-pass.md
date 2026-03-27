# Runtime review — People Data Labs current-pass rerun

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop
Status: ⚠️ Rhumb execute PASS, direct-control rerun BLOCKED by local credential path

## Why this note exists

Mission 0 for the current cron pass required rerunning PDL immediately after the slug-normalization repair shipped in commit `94c8df8`.

I first checked:
- `memory/working/continuation-brief.md`
- `memory/2026-03-27.md`

That context confirmed PDL remained the top-priority rerun lane for this pass.

## Rhumb Resolve rerun (current pass)

### Estimate
- Endpoint: `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
- Result: **200 OK**
- Surface:
  - `cost_estimate_usd: 0.1`
  - `endpoint_pattern: GET /v5/person/enrich`
  - `circuit_state: closed`

### Execute
- Endpoint: `POST /v1/capabilities/data.enrich_person/execute`
- Result: **200 OK**
- Execution id: `exec_dc5b9099e2664717938e708334913b59`
- Upstream status: `200`
- Input:
  ```json
  {
    "provider": "people-data-labs",
    "credential_mode": "rhumb_managed",
    "body": {
      "profile": "https://www.linkedin.com/in/satyanadella/"
    },
    "interface": "runtime_review"
  }
  ```
- Core returned fields:
  - `full_name: satya nadella`
  - `job_title: board member`
  - `job_company_name: starbucks`
  - `linkedin_url: linkedin.com/in/satyanadella`
  - `likelihood: 9`

## Direct provider control rerun

Attempted path:
- `sop item get pdl_api_key --vault "OpenClaw Agents" --fields credential --reveal`
- then `GET https://api.peopledatalabs.com/v5/person/enrich?...`

### What blocked it
The local `sop` path failed before the provider request could be authenticated:
- `403 Forbidden (Service Account Deleted)` from the 1Password service-account path
- fallback tmux-based `op` desktop-auth attempt also hung locally and did not produce a usable vault session during this pass

This is a **local credential retrieval blocker**, not evidence of a fresh PDL or Rhumb execution regression.

## Investigation outcome

What is confirmed now:
- the **production Rhumb execution path is healthy right now**
- the slug-normalization fix from `94c8df8` is still holding on the live execute surface
- no fresh alias/auth/env/config failure reproduced in Rhumb

What is not yet re-confirmed on this exact pass:
- a same-minute direct provider control call, because the host-side secret retrieval path is broken

## Operational truth

Today already contains earlier PDL direct-vs-Rhumb confirmations, but for this exact cron pass I am not marking the control rerun as completed. The honest status is:

**PDL current-pass rerun confirms Rhumb production health, while direct-control rerun is blocked by the deleted 1Password service-account credential path.**

## Next action

Repair the host credential path for `sop` / `op`, then rerun the direct PDL control immediately so Mission 0 can close with same-pass parity evidence instead of inherited earlier evidence.
