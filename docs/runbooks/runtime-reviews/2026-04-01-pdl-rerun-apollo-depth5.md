# Runtime review loop — PDL rerun + Apollo depth 5

Date: 2026-04-01
Owner: Pedro / Keel runtime review loop

## Why this pass

Mission 0 was explicit: rerun canonical **People Data Labs** first after the slug-normalization fix in commit `94c8df8` and confirm the production path still resolves the canonical `people-data-labs` slug correctly.

Mission 1 then had to pick the callable provider with the **fewest runtime-backed reviews** from the live public callable audit. The live audit showed a weakest callable claim-safe depth of **4**. After skipping PDL because Mission 0 had just covered it again, **Apollo** was the stalest remaining provider in that weakest bucket.

## Mission 0 — PDL fix-verify rerun

### What was run
- Estimate:
  - `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=people-data-labs&credential_mode=rhumb_managed`
- Managed execute:
  - `POST /v1/capabilities/data.enrich_person/execute?provider=people-data-labs&credential_mode=rhumb_managed`
- Direct control:
  - `GET https://api.peopledatalabs.com/v5/person/enrich`
- Input:
  - `profile=https://www.linkedin.com/in/satyanadella/`

### Result
- estimate: **200**
- Rhumb wrapper: **200**
- `provider_used`: **`people-data-labs`**
- Rhumb upstream: **402**
- direct provider control: **402**
- execution id: `exec_227c3ab5e2934bc8a2edaff3210f2331`

### Conclusion
- canonical slug routing still works in production
- the old normalization bug did **not** recur
- both lanes now stop at the same provider quota boundary (`account maximum / all matches used`)
- no new Rhumb execution-layer fix was required in this pass

Artifact:
- `artifacts/runtime-review-pass-20260401T193319Z-pdl-fix-verify-20260401.json`

## Mission 1 — Apollo depth 4 → 5 runtime verification

### Pre-pass coverage truth
The live callable audit before the pass showed:
- callable providers: **16**
- weakest callable claim-safe depth: **4**
- weakest bucket:
  - `slack`
  - `stripe`
  - `twilio`
  - `apify`
  - `apollo`
  - `exa`
  - `replicate`
  - `unstructured`
  - `algolia`
  - `people-data-labs`
- after skipping PDL, **Apollo** was the stalest remaining weakest-bucket provider

### Investigation correction before the clean pass
The first ad hoc Apollo attempt was not a valid product regression signal:
- the managed call used the existing `pedro-dogfood` key and failed with **402 `no_org_credits`**
- the direct control call used Python urllib’s default user-agent and hit **Cloudflare 1010** on Apollo

Those were harness problems, not a Rhumb execution-path defect.

Correction applied:
- re-ran Apollo through a **fresh temp org** bootstrapped with credits
- used the existing helper script / `httpx` control path, which Apollo accepted

### What was run
- Capability:
  - `data.enrich_person`
- Managed execute:
  - `POST /v1/capabilities/data.enrich_person/execute?provider=apollo&credential_mode=rhumb_managed`
- Direct control:
  - `POST https://api.apollo.io/api/v1/people/match`
- Input:
  - `{"email": "tim@apple.com"}`

### Result
Managed vs direct parity passed exactly on:
- `name = Yenni Tim`
- `title = Founder and Director, UNSW PRAxIS (Practice x Implementation Science) Lab`
- `organization_name = UNSW Business School`
- `linkedin_url = http://www.linkedin.com/in/yennitim`
- `email_status = null`

Published trust rows:
- evidence: `550510db-1505-4184-bfd1-06399aa781dd`
- review: `d94cc746-77ff-4924-bf91-6f5f18df9c87`
- execution id: `exec_2bc7276d2a4543e1981cc21d168e4379`

### Post-pass coverage truth
- `apollo` moved **4 → 5** runtime-backed reviews
- callable weakest depth stayed **4**
- weakest bucket shrank to:
  - `slack`
  - `stripe`
  - `twilio`
  - `apify`
  - `exa`
  - `replicate`
  - `unstructured`
  - `algolia`
  - `people-data-labs`

### Structured runtime review verdict

#### Rhumb execution
- succeeded
- selected the correct provider (`apollo`)
- injected managed auth correctly
- returned the same person-match payload surface as direct control on the checked fields

#### Direct provider control
- succeeded once the control path used a user-agent Apollo accepts
- returned the same observable person-match fields as Rhumb managed execution

#### Comparison verdict
**Parity passed.** Apollo is now lifted out of the weakest callable bucket. The first failed attempt was fully investigated and traced to harness conditions, not a Rhumb execution-layer bug.

## Artifacts
- `artifacts/runtime-review-pass-20260401T193319Z-pdl-fix-verify-20260401.json`
- `artifacts/runtime-review-pass-20260401T193900Z-apollo-current-depth5.json`
- `artifacts/runtime-review-publication-2026-04-01-apollo-depth5.json`
- `artifacts/callable-review-coverage-2026-04-01-post-apollo-depth5.json`

## Verdict

PDL fix-verify remains clean: the slug fix still holds in production, and the current blocker is provider quota rather than routing, auth injection, or slug normalization.

Apollo is now lifted from depth **4 → 5** with a clean managed-vs-direct parity pass, and the next callable freshness lane remains inside the remaining depth-4 bucket.
