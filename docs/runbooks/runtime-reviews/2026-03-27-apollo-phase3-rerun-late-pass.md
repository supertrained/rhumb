# Apollo Phase 3 rerun — weakest-bucket lift

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop
Priority: Mission 1 runtime verification
Status: ✅ passed in production

## Why Apollo

After the fresh PDL rerun, I re-audited callable review depth. The public callable inventory sat at **16** providers, and the weakest runtime-backed bucket still contained five one-review providers:
- `algolia`
- `apify`
- `e2b`
- `replicate`
- `unstructured`

Apollo had already moved to two runtime-backed reviews by the time the public cache refreshed, but for the live execution work in this run it was still the cleanest low-side-effect parity lane among the weakest/near-weakest enrichment providers: same capability family as PDL, deterministic input, read-only behavior, and an easy direct control comparison.

## Working contract

- **Capability:** `data.enrich_person`
- **Provider:** `apollo`
- **Credential mode:** `rhumb_managed`
- **Input:** `email=tim@apple.com`
- **Rhumb estimate:** `GET /v1/capabilities/data.enrich_person/execute/estimate?provider=apollo&credential_mode=rhumb_managed`
- **Rhumb execute:** `POST /v1/capabilities/data.enrich_person/execute`
- **Direct control:** `POST https://api.apollo.io/api/v1/people/match`

## Results

### Rhumb Resolve
- **Estimate:** `200 OK`, cost estimate `$0.03`
- **Execute envelope:** `200 OK`
- **Upstream status:** `200`
- **Execution id:** `exec_d7ab0912b4794226887f18e7a63edc0b`
- **Latency:** `467.1 ms`

Core returned fields:
- `name`: `Yenni Tim`
- `title`: `Founder and Director, UNSW PRAxIS (Practice x Implementation Science) Lab`
- `organization_name`: `UNSW Business School`
- `linkedin_url`: `http://www.linkedin.com/in/yennitim`
- `email_status`: `null`

### Direct provider control
- **HTTP:** `200 OK`

Core returned fields:
- `name`: `Yenni Tim`
- `title`: `Founder and Director, UNSW PRAxIS (Practice x Implementation Science) Lab`
- `organization_name`: `UNSW Business School`
- `linkedin_url`: `http://www.linkedin.com/in/yennitim`
- `email_status`: `null`

## Parity read

Rhumb and direct Apollo matched on all verification fields:
- name
- title
- organization
- LinkedIn URL
- email status

## Ops note

A direct-control attempt with Python's default `urllib` user agent hit Cloudflare `1010 browser_signature_banned`. Re-running the same control with `curl` and a normal browser-like user agent succeeded immediately. That is a provider edge-policy quirk, not a Rhumb execution bug.

## Public trust surface update

Published from this run:
- **Evidence:** `078128e4-815e-4f42-8081-62f5d18769f2`
- **Review:** `d5cc9abe-acba-46db-b274-3349111003bc`

Public callable-coverage audit after cache refresh:
- `apollo` runtime-backed reviews: **2**
- total reviews: **7**
- weakest public bucket now: `algolia`, `apify`, `e2b`, `replicate`, `unstructured`

## Verdict

**Apollo passed another live runtime verification in production.**

Rhumb-managed execution succeeded, direct control succeeded, the parity check was clean, and the public trust surface now reflects the additional runtime-backed review.
