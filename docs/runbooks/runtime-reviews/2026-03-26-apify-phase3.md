# Apify Phase 3 Runtime Review — 2026-03-26

## Why this lane
Google AI is still missing from the live callable inventory, so the active unblocked lane remains callable-provider Phase 3 reviews. Apify was the next clean read-only candidate on `scrape.extract`.

## Final verdict
**Passed with caveat.**

Apify is now freshly runtime-verified for `scrape.extract` in production via Rhumb-managed execution, and the public trust surface now shows a linked **🟢 Runtime-verified** review. The caveat is that the rolling `/v1/telemetry/provider-health` window still shows `apify` as `unhealthy` because earlier malformed probes produced four 400s before the final successful pass.

## Working contract
- **Capability:** `scrape.extract`
- **Provider:** `apify`
- **Managed actor:** `apify~website-content-crawler`
- **Critical input shape:** send a JSON **`body`** with `startUrls`, not an extra top-level `input` field
- **Rhumb auth header:** `X-Rhumb-Key`

Final Rhumb payload:

```json
{
  "provider": "apify",
  "credential_mode": "rhumb_managed",
  "body": {
    "startUrls": [{ "url": "https://example.com" }],
    "maxCrawlDepth": 0,
    "maxCrawlPages": 1
  },
  "interface": "runtime_review"
}
```

## Direct control
- **Endpoint:** `POST https://api.apify.com/v2/acts/apify~website-content-crawler/runs?waitForFinish=60`
- **HTTP:** `201 Created`
- **Run id:** `bszzORcE8lRhokqfS`
- **Dataset id:** `veM5xj6Tyk5pQ0E1d`
- **Status:** `SUCCEEDED`
- **Output check:** extracted `https://example.com/` with title `Example Domain`

Dataset sample:
- `url`: `https://example.com/`
- `metadata.title`: `Example Domain`
- markdown excerpt:
  - `# Example Domain`
  - `This domain is for use in documentation examples without needing permission.`

## Rhumb-managed execution
- **Endpoint:** `POST /v1/capabilities/scrape.extract/execute`
- **HTTP envelope:** `200 OK`
- **Upstream:** `201 Created`
- **Execution id:** `exec_8f7c7af5c5454a208a48b547f7d2b15b`
- **Run id:** `dgm6DOjZTCorTOMPQ`
- **Dataset id:** `ml791H1jHIt70FHYL`
- **Latency:** `20451.4 ms`
- **Path logged in telemetry:** `/v2/acts/apify~website-content-crawler/runs?waitForFinish=60`
- **Status:** `SUCCEEDED`

Dataset sample matched the direct control:
- `url`: `https://example.com/`
- `metadata.title`: `Example Domain`
- same markdown excerpt for the page body

## Telemetry nuance
`/v1/telemetry/provider-health` after the pass still showed:
- `provider`: `apify`
- `status`: `unhealthy`
- `success_rate`: `0.222`
- `total_calls`: `9`
- `error_distribution`: `{ "400": 4 }`

That is a **window-quality issue, not a fresh execution failure**. The successful verification is real; the 24h rollup is lagging because earlier malformed test inputs polluted the denominator.

## Public trust artifacts
Published live:
- **Evidence:** `ca8b7705-3211-4467-aeb3-cfb2952b6e04`
- **Review:** `f40e476c-9e2d-478d-8283-6c9b033edb65`
- Public read surface now shows:
  - `Apify: Phase 3 runtime verification passed`
  - trust label `🟢 Runtime-verified`

Cleanup performed:
- Superseded stale duplicate review `83398a70-fb3f-4d9f-92f8-e77d4a822452` so `/v1/services/apify/reviews` shows one clean Phase 3 row instead of a linked runtime-verified row plus an older `❓ Unknown` duplicate.

## Lessons
1. **For capability execute, provider-native payload belongs in `body` / `params`, not a freeform `input` key.**
2. **Apify zero-config `scrape.extract` should stay on `website-content-crawler`, not `web-scraper`.** `web-scraper` requires `pageFunction`, which breaks the zero-config Resolve story.
3. **Runtime review write path needs cleanup discipline.** If a stale review lands before evidence-linking is correct, supersede it immediately so the public trust surface doesn’t show conflicting verdicts.

## Next recommendation
If Google AI is still absent from live callable inventory, move to the next low-side-effect managed target with thin runtime-backed coverage. **Unstructured** is the cleanest remaining candidate because it is document-only, non-mutating, and deterministic enough for another direct-vs-Rhumb Phase 3 pass.
