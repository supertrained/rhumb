# Runtime review loop — PDL canonical-slug reconfirm + Google AI weakest-bucket pass

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop

## Mission 0 — PDL fix-verify rerun after 94c8df8

### Why this happened

Mission 0 for this pass was explicit: rerun **People Data Labs** in production after the slug-normalization fix shipped in commit `94c8df8`, and verify the public canonical slug path rather than relying on the proxy alias.

### Test setup

#### Rhumb Resolve
- Capability: `data.enrich_person`
- Estimate: `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=auto`
- Execute: `POST /v1/capabilities/data.enrich_person/execute`
- Provider: `people-data-labs`
- Credential mode: `auto`
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
- Estimate provider: `people-data-labs`
- Execute: **200**
- Upstream status: **200**
- Provider used: `people-data-labs`
- Credential mode resolved to: `rhumb_managed`

#### Direct PDL control
- HTTP status: **200**

#### Key-field parity
- `full_name`: `satya nadella` ↔ `satya nadella`
- `job_title`: `board member` ↔ `board member`
- `job_company_name`: `starbucks` ↔ `starbucks`
- `linkedin_url`: `linkedin.com/in/satyanadella` ↔ `linkedin.com/in/satyanadella`
- `linkedin_username`: `satyanadella` ↔ `satyanadella`

### Investigation outcome

No fresh execution-layer failure reproduced.

That means the fix-verify loop closed correctly for this pass:
- the canonical slug estimate path succeeded
- the Rhumb execution path succeeded
- the direct provider control succeeded
- key response fields matched exactly

So the `94c8df8` slug-normalization fix is holding on the real production path users hit.

Artifact:
- `rhumb/artifacts/runtime-review-pdl-slug-fix-20260330T030556Z.json`

## Mission 1 — weakest-bucket callable provider pass

### Provider selection

I refreshed callable coverage from production first.

Pass-start audit:
- callable providers: **16**
- weakest runtime-backed depth: **3**
- weakest bucket:
  - `algolia`
  - `apify`
  - `apollo`
  - `e2b`
  - `exa`
  - `firecrawl`
  - `google-ai`
  - `replicate`
  - `tavily`
  - `unstructured`

After skipping PDL because Mission 0 had already re-verified it in this pass, I picked **Google AI** from the tie set because it still sits at the coverage floor and offers the cleanest deterministic direct-control parity check.

### Test setup

#### Rhumb Resolve
- Capability: `ai.generate_text`
- Estimate: `GET /v1/capabilities/ai.generate_text/execute/estimate?provider=google-ai&credential_mode=rhumb_managed`
- Execute: `POST /v1/capabilities/ai.generate_text/execute`
- Provider: `google-ai`
- Credential mode: `rhumb_managed`
- Model: `gemini-2.5-flash`
- Prompt sentinel: `Reply with exactly: RHUMB_GOOGLE_AI_20260330_LOOP`
- Generation config: `temperature: 0`

#### Direct provider control
- Endpoint: `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent`
- Auth: direct Google AI API key
- Payload: same model, same prompt, same generation config

### Results

#### Rhumb Resolve
- Estimate: **200**
- Execute: **200**
- Upstream status: **200**
- Provider used: `google-ai`
- Returned text: `RHUMB_GOOGLE_AI_20260330_LOOP`

#### Direct Google AI control
- HTTP status: **200**
- Returned text: `RHUMB_GOOGLE_AI_20260330_LOOP`

### Comparison

| Dimension | Rhumb Resolve | Direct Google AI |
| --- | --- | --- |
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed key injection | Direct Google AI key |
| Model | `gemini-2.5-flash` | `gemini-2.5-flash` |
| Output | `RHUMB_GOOGLE_AI_20260330_LOOP` | `RHUMB_GOOGLE_AI_20260330_LOOP` |
| Investigation need | None — no failure reproduced | N/A |

### Public trust surface update

Published from this pass:
- Evidence: `30bccbe5-7788-4814-a9d2-912595f932d6`
- Review: `e2e0d57f-8257-47a2-a81e-3dd3d52cd561`

Coverage moved:
- `google-ai` runtime-backed reviews: **3 → 4**
- `google-ai` total reviews: **8 → 9**

Post-publish weakest bucket:
- `algolia`
- `apify`
- `apollo`
- `e2b`
- `exa`
- `firecrawl`
- `replicate`
- `tavily`
- `unstructured`

Artifact:
- `rhumb/artifacts/runtime-review-pass-20260330T030750Z-google-ai-current.json`

## Side fix uncovered during setup

While provisioning the temporary production review org, `ensure_org_billing_bootstrap()` raised a JSON decode error when Supabase returned an empty body for `Prefer: return=minimal` POSTs.

I patched `packages/api/services/billing_bootstrap.py` so `_sb_post()` now safely handles empty successful bodies instead of assuming JSON is always present.

Smoke check after patch:
- bootstrap org creation: **passed**
- wallet creation: **passed**
- starter credit seeding: **passed**

## Coverage artifacts

- `rhumb/artifacts/callable-review-coverage-2026-03-30-pre-loop.json`
- `rhumb/artifacts/callable-review-coverage-2026-03-30-post-google-ai.json`

## Verdict

This pass completed the fix-verify requirement correctly:
1. **PDL was rerun on the canonical slug path and matched direct control in production**
2. **Google AI received a fresh weakest-bucket runtime-backed review with exact direct-provider parity**
3. **A runtime-review setup helper bug was fixed instead of being left for the next loop to rediscover**
