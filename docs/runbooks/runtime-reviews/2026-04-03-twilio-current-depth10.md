# Twilio runtime review — depth 10 (2026-04-03 PT)

## What this pass did
- Re-ran live callable-review coverage first and confirmed the weakest claim-safe callable bucket was still depth **9**.
- Confirmed **Twilio** was the freshness-ordered stalest member of that weakest bucket:
  - `twilio` freshest evidence before the pass: `2026-04-02T20:38:14Z`
  - `slack` freshest evidence before the pass: `2026-04-02T22:34:39Z`
- Added `scripts/runtime_review_twilio_depth10_20260403.py` for a reusable production parity pass.
- Ran the pass through Railway production context against Rhumb Resolve and direct Twilio Lookup v2.

## Production result
- Capability: `phone.lookup`
- Provider: `twilio`
- Target number: `+14155552671`
- Lookup field: `line_type_intelligence`
- Estimate: `200` (after **2** attempts; first estimate hit the known fresh-key auth propagation race)
- Rhumb execute: `200`
- Direct Twilio control: `200`
- Execution ID: `exec_77484203dbcf4ae8b333ec0cbacf931c`

## Parity fields checked
- `phone_number`
- `valid`
- `country_code`
- `calling_country_code`
- `national_format`
- `line_type_intelligence.type`
- `line_type_intelligence.carrier_name`
- `line_type_intelligence.error_code`

## Observed parity
- Rhumb and direct control both returned:
  - `phone_number = +14155552671`
  - `valid = true`
  - `country_code = US`
  - `calling_country_code = 1`
  - `national_format = (415) 555-2671`
  - `line_type_intelligence.type = null`
  - `line_type_intelligence.carrier_name = null`
  - `line_type_intelligence.error_code = 60600`
- Published trust rows:
  - evidence `65017973-b1f7-48da-8d04-de816cb57c7b`
  - review `9d229c1c-68e5-44fe-af0e-9f0ff446cdb4`

## Harness / catalog note worth preserving
- The hardened post-grant delay + bounded invalid-key estimate retry guard was needed again here: the estimate path succeeded on the **second** attempt.
- The estimate surface still advertises:
  - `GET /v2/PhoneNumbers/{number}?Fields=carrier`
- The live successful runtime review used:
  - `Fields=line_type_intelligence`
- Honest read: execution is healthy, but the estimate/catalog layer still reflects the deprecated `carrier` field and should eventually be corrected so docs + runtime expectations match Twilio Lookup v2 reality.

## Coverage impact
- **Twilio moved from 9 → 10 claim-safe runtime-backed reviews.**
- The weakest callable-review depth stays **9**.
- The weakest callable bucket is now **Slack only**.
- Freshness-ordered next target is now **Slack**.

## Artifacts
- `artifacts/callable-review-coverage-2026-04-03-pre-twilio-current-pass-from-cron-0142.json`
- `artifacts/runtime-review-pass-20260403T084616Z-twilio-depth10.json`
- `artifacts/runtime-review-publication-2026-04-03-twilio-depth10.json`
- `artifacts/callable-review-coverage-2026-04-03-post-twilio-current-pass-from-cron-0142.json`
