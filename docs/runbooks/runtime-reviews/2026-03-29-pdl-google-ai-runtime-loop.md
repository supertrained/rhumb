# Runtime review loop — PDL reconfirm + Google AI weakest-bucket pass

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop

## Mission 0 — PDL fix-verify rerun

### Why this happened

Mission 0 for this pass was explicit: rerun **People Data Labs** in production after the slug-normalization fix shipped in commit `94c8df8`.

The requirement was not "assume the fix still works." It was:
- rerun the full Rhumb Resolve path in production
- run a direct provider control against PDL itself
- confirm parity on the same input
- publish the new proof so the fix-verify loop ends with evidence, not hope

### Test setup

#### Rhumb Resolve
- Capability: `data.enrich_person`
- Estimate: `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
- Execute: `POST /v1/capabilities/data.enrich_person/execute`
- Provider: `people-data-labs`
- Credential mode: `rhumb_managed`
- Input:
  ```json
  {
    "profile": "https://www.linkedin.com/in/satyanadella/"
  }
  ```

#### Direct provider control
- Endpoint: `GET https://api.peopledatalabs.com/v5/person/enrich`
- Auth: direct PDL `X-Api-Key`
- Input: same LinkedIn profile URL

### Results

#### Rhumb Resolve
- Estimate: **200**
- Execute: **200**
- Upstream status: **200**
- Key returned fields:
  - `full_name`: `satya nadella`
  - `job_title`: `board member`
  - `job_company_name`: `starbucks`
  - `linkedin_url`: `linkedin.com/in/satyanadella`

#### Direct PDL control
- HTTP status: **200**
- Same key fields matched exactly:
  - `full_name`: `satya nadella`
  - `job_title`: `board member`
  - `job_company_name`: `starbucks`
  - `linkedin_url`: `linkedin.com/in/satyanadella`

### Investigation outcome

No fresh execution-layer failure reproduced.

That means Mission 0 ended correctly for this pass:
- the control path succeeded
- the Rhumb path succeeded
- there was no new slug, auth-injection, credential-store, or execution-config defect to fix
- the `94c8df8` slug-normalization repair received another live production confirmation

### Public trust surface update

Published from this pass:
- Evidence: `5815815c-4371-4d6d-ba5a-17ca008d7ecb`
- Review: `8283d4cc-42aa-4c2a-9c12-cbf60203df57`

Depth moved:
- `people-data-labs` runtime-backed reviews: **5 → 6**
- total published reviews: **10 → 11**

Artifact bundle:
- `rhumb/artifacts/runtime-review-pass-20260329T110403Z-pdl-google-ai.json`

## Mission 1 — weakest-bucket callable provider pass

### Provider selection

I refreshed callable coverage first:
- `GET /v1/proxy/services` still showed **16 callable providers**
- the pre-loop audit showed the weakest runtime-backed depth was **2 reviews** across:
  - `algolia`
  - `apify`
  - `apollo`
  - `e2b`
  - `exa`
  - `google-ai`
  - `replicate`
  - `unstructured`

I picked **Google AI** from that tie set because it has the cleanest deterministic direct-control path: exact-text generation on a live current model with `temperature: 0`.

### Test setup

#### Rhumb Resolve
- Capability: `ai.generate_text`
- Estimate: `GET /v1/capabilities/ai.generate_text/execute/estimate?provider=google-ai&credential_mode=rhumb_managed`
- Execute: `POST /v1/capabilities/ai.generate_text/execute`
- Provider: `google-ai`
- Credential mode: `rhumb_managed`
- Model: `gemini-2.5-flash`
- Prompt sentinel: `Reply with exactly: RHUMB_GOOGLE_AI_20260329_LOOP`
- Generation config: `temperature: 0`

#### Direct provider control
- Endpoint: `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent`
- Auth: direct Google AI API key
- Payload: same model, same sentinel prompt, same temperature

### Results

#### Rhumb Resolve
- Estimate: **200**
- Execute: **200**
- Upstream status: **200**
- Returned text: `RHUMB_GOOGLE_AI_20260329_LOOP`

#### Direct Google AI control
- HTTP status: **200**
- Returned text: `RHUMB_GOOGLE_AI_20260329_LOOP`

### Comparison

| Dimension | Rhumb Resolve | Direct Google AI |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed key injection | Direct Google AI key |
| Model | `gemini-2.5-flash` | `gemini-2.5-flash` |
| Output | `RHUMB_GOOGLE_AI_20260329_LOOP` | `RHUMB_GOOGLE_AI_20260329_LOOP` |
| Investigation need | None — no failure reproduced | N/A |

### Public trust surface update

Published from this pass:
- Evidence: `6eb5ab47-23e7-4484-987c-181036231f7f`
- Review: `2e73c81e-2711-4955-9fd2-dac1ff024990`

Depth moved:
- `google-ai` runtime-backed reviews: **2 → 3**
- total published reviews: **7 → 8**

Artifact bundle:
- `rhumb/artifacts/runtime-review-pass-20260329T110610Z-google-ai.json`

## Coverage impact

Pre-loop audit:
- weakest callable depth: **2 runtime-backed reviews across 8 providers**

Post-loop audit:
- weakest callable depth: **2 runtime-backed reviews across 7 providers**

Updated weakest bucket:
- `algolia`
- `apify`
- `apollo`
- `e2b`
- `exa`
- `replicate`
- `unstructured`

So this pass:
- reconfirmed PDL after the slug fix
- removed `google-ai` from the weakest callable bucket
- left the next cleanest depth targets in the seven-provider tie above

## Mission 2 — discovery expansion

After verification work, I expanded the **logging** category.

Why logging:
- live catalog depth is only **6** providers
- adjacent categories are much deeper (`monitoring` **43**, `devops` **83**)
- agents regularly need read-first log search for debugging, support, and incident triage

Added services:
- `sumo-logic`
- `coralogix`
- `logz-io`
- `sematext-logs`
- `crowdstrike-logscale`

Phase 0 assessment:
- strongest initial Resolve wedge: **`log.query`**
- best first provider target: **Sumo Logic**
- strongest follow-ons: **Coralogix**, **Sematext Logs**, **Logz.io**

Discovery artifacts:
- `rhumb/packages/api/migrations/0116_logging_expansion.sql`
- `rhumb/docs/runbooks/discovery-expansion/2026-03-29-logging-expansion.md`

## Artifact bundle for this loop

- `rhumb/artifacts/callable-review-coverage-2026-03-29-pre-loop.json`
- `rhumb/artifacts/runtime-review-pass-20260329T110403Z-pdl-google-ai.json`
- `rhumb/artifacts/runtime-review-pass-20260329T110610Z-google-ai.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-29-post-loop.json`

## Verdict

This run completed all three missions in order:
1. **PDL was rerun and reconfirmed in production after the slug-normalization fix**
2. **Google AI received a fresh weakest-bucket runtime-backed review with direct-provider parity**
3. **Logging discovery depth was expanded with five new services and a clear Phase 0 wedge**
