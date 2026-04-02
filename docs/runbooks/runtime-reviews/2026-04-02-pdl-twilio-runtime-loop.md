# Runtime review loop — PDL reconfirmation + Twilio execute pass

Date: 2026-04-02
Owner: Pedro / Keel runtime review loop

## Mission 0 — PDL fix verification rerun

### Why this rerun happened
Commit `94c8df8` shipped the slug-normalization fix for **People Data Labs**. Even though that fix had already been verified previously, this cron explicitly required a fresh live rerun on the canonical Phase 3 path, so it was rerun rather than assumed.

### Execution path
- Capability: `data.enrich_person`
- Provider: `people-data-labs`
- Credential mode: `rhumb_managed`
- Input: `profile=https://www.linkedin.com/in/satyanadella/`
- Rail: funded temp org + temp review agent + explicit service access grant

### Control test
Direct control hit:
- `GET https://api.peopledatalabs.com/v5/person/enrich?profile=...`
- Header: `X-Api-Key: RHUMB_CREDENTIAL_PDL_API_KEY`

### Result
- Rhumb estimate: **200**
- Rhumb execute: **200**
- Upstream provider status through Rhumb: **402**
- Direct provider control: **402**
- Error parity: **matched**
- `provider_used`: **people-data-labs**
- Verdict: **PASS**

### Interpretation
The fix still holds live.
- canonical slug routing is working
- Rhumb reaches the real PDL upstream
- the current failure mode is provider quota, not execution-layer breakage

Artifact:
- `artifacts/runtime-review-pass-20260402T144637Z-pdl-fix-verify-20260401b.json`

## Mission 1 — Twilio current pass via execute route

### Why Twilio was chosen
Fresh public callable audit before the pass showed the weakest claim-safe callable bucket at **7** reviews:
- `slack`
- `twilio`

PDL was skipped after Mission 0. Twilio was selected because it had a safe real execute-route verifier available (`phone.lookup`) without external side effects.

### Execution path
- Capability: `phone.lookup`
- Provider: `twilio`
- Credential mode: `byo`
- Rhumb route: `POST /v1/capabilities/phone.lookup/execute`
- Upstream path executed through Resolve: `GET /v2/PhoneNumbers/+14155552671?Fields=line_type_intelligence`

### Control test
Direct control hit:
- `GET https://lookups.twilio.com/v2/PhoneNumbers/+14155552671?Fields=line_type_intelligence`
- Header: `Authorization: Basic <Twilio basic auth>`

### Initial failure and investigation
The first production run did **not** show a provider mismatch.

Observed on first run:
- direct Twilio control: **200**
- Rhumb execute: **200**
- normalized field parity: **true**
- but the fresh-agent estimate call returned **401 Invalid or expired Rhumb API key**

Investigation result:
- this was **not** a Twilio execution-layer failure
- it matched the same post-grant auth propagation race already seen in the PDL verifier
- root cause lived in the **runtime-review harness**, not in Twilio slug normalization, auth injection, or credential mapping
- specifically, `scripts/runtime_review_twilio_depth7_20260402.py` lacked the post-grant delay and bounded estimate retry guard already added to the PDL verifier

### Fix implemented
Patched `scripts/runtime_review_twilio_depth7_20260402.py` to:
- wait `5` seconds after service access grant
- detect the transient invalid-key estimate response
- retry the estimate call up to `4` times with bounded delay

Validation:
- `packages/api/.venv/bin/python -m py_compile scripts/runtime_review_twilio_depth7_20260402.py` → passed

### Rerun result
Second production run after the harness fix:
- Rhumb estimate: **200**
- Rhumb execute: **200**
- Rhumb upstream status: **200**
- Direct provider control: **200**
- Field parity: **exact match**
- `provider_used`: **twilio**
- Verdict: **PASS**

Compared normalized fields:
- `phone_number`
- `valid`
- `country_code`
- `calling_country_code`
- `national_format`
- `line_type_intelligence.type`
- `line_type_intelligence.carrier_name`
- `line_type_intelligence.error_code`

### Public trust-surface effect
Post-pass public callable audit moved the weakest bucket to **Slack only** at claim-safe depth **7**.

Artifacts:
- `artifacts/runtime-review-pass-20260402T144800Z-twilio-depth7.json` (false-fail evidence)
- `artifacts/runtime-review-pass-20260402T144917Z-twilio-depth7.json` (passing rerun)
- `artifacts/runtime-review-publication-2026-04-02-twilio-depth7.json`
- `artifacts/callable-review-coverage-2026-04-02-post-twilio-current-pass-from-cron-0744.json`

### Small catalog note
Twilio Lookup v2 accepted `Fields=line_type_intelligence`, but the estimate surface still advertises the deprecated `carrier` field in `endpoint_pattern`. That is now captured in the runtime artifact as a catalog note; it did not block runtime parity.

## Mission 2 — Discovery expansion

Chose **authorization** as the underrepresented high-demand category.

Why:
- live public category counts showed authorization at only **5** providers
- safe agent behavior increasingly depends on read-first permission checks before action
- authorization has a clean, auditable Resolve wedge that is easier to normalize honestly than policy writes or admin mutations

Added services:
- `authzed`
- `spicedb`
- `oso-cloud`
- `aserto`
- `styra-das`

Phase 0 recommendation:
- best first Resolve wedge: `authz.check`
- strongest first provider target: **AuthZed**

Shipped docs/migration:
- `packages/api/migrations/0149_authorization_expansion_ii.sql`
- `docs/runbooks/discovery-expansion/2026-04-02-authorization-expansion-ii.md`

## Net

This loop satisfied the SOP correctly:
- reran the shipped PDL fix on the live canonical path
- investigated a Phase 3 false fail instead of just logging it
- implemented the fix in the review harness and re-verified Twilio successfully
- expanded discovery in a genuinely underweight, high-demand category
