# Index score

Index score returns the latest AN Score breakdown for one known service slug so a user can inspect execution quality, access readiness, and honesty fields before choosing a vendor.

## Sub-features

- `score-known` returns a score object for `stripe`.
- `score-fields` includes `an_score`, `execution_score`, `access_readiness_score`, `tier`, and `tier_label`.
- `score-unknown` returns a service-not-found 404 for an invented slug.

## How to get to it (user POV)

- Call `GET https://api.rhumb.dev/v1/services/stripe/score`.
- Open `https://rhumb.dev/service/stripe`.
- Ask an MCP client to `get_score` with slug `stripe`.
- Run `rhumb score stripe --json`.

## Driving it with curl

Preconditions:

- Doctor passed against `$VERIFY_RHUMB_BASE`.
- Slug is a public service such as `stripe`.

- **Known slug.** Fetch the Stripe score. Run `.cursor/skills/verify-rhumb/bin/drive index-score` or `curl -sS -H 'User-Agent: rhumb-verify/1.0' -H 'Accept: application/json' "$VERIFY_RHUMB_BASE/v1/services/stripe/score"`. HTTP 200. Top-level `service_slug` is `stripe`. `an_score` is a number.
- **Breakdown.** Read `execution_score`, `access_readiness_score`, `tier`, and `tier_label` on the same object. Missing `data` wrapper is expected.
- **Unknown slug.** Fetch a fake slug. Run `curl -sS -H 'User-Agent: rhumb-verify/1.0' "$VERIFY_RHUMB_BASE/v1/services/not-a-rhumb-service/score"`. HTTP 404. Do not invent a score.
- **Proof.** Keep the Stripe response. The helper writes `evidence/$VERIFY_RHUMB_RUN_ID/drive-index-score.json` and `evidence/$VERIFY_RHUMB_RUN_ID/http/stripe-score.json`.

## Gotchas

- This response is a top-level object. Wrapping it in `data` will make assertions fail.
- Search results use `an_score`. Some docs still say `aggregate_recommendation_score`. Assert `an_score`.
- Empty `failure_modes` on some slugs is a coverage gap. Read `failure_coverage` and `failure_honesty` before treating `[]` as a clean bill of health.
- Calibration fixtures can fill scores for `stripe`, `hubspot`, `sendgrid`, `resend`, and `github` when a local DB row is missing. Live `api.rhumb.dev` should return a persisted score. Prefer the live host for this map.
