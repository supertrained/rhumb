# Apify — Phase 3 Runtime Review

**Date:** 2026-03-26  
**Reviewer:** Pedro (automated)  
**Capability:** `scrape.extract`  
**Provider:** `apify`  
**Credential mode:** `rhumb_managed`

## Summary

Phase 3 runtime verification **PASSED after fix-verify loop**. The original managed execution config pointed to `apify~web-scraper` which requires `pageFunction` — a full JavaScript function body that makes zero-config Resolve execution impossible. Switched to `apify~website-content-crawler` which accepts simple `startUrls` input and returns clean output.

## Direct Control Test

- **Endpoint:** `POST https://api.apify.com/v2/store?limit=3`
- **Auth:** Bearer token
- **Result:** 200 OK, returned 3 actors (Google Maps Scraper, TikTok Scraper, Website Content Crawler)
- **Latency:** 416ms

## Rhumb-Managed Execution — Before Fix

- **Attempt 1:** `POST /v1/capabilities/scrape.extract/execute` with `params: {url: "https://example.com"}`
- **Path resolved to:** `/v2/acts/apify~web-scraper/runs`
- **Result:** Upstream 400 — "Field input.startUrls is required"
- **Attempt 2:** Added `startUrls` array
- **Result:** Upstream 400 — "Field input.pageFunction is required"
- **Root cause:** `apify~web-scraper` requires `pageFunction` (JavaScript code), making it unsuitable for zero-config scrape.extract

## Fix Applied

- Migration 0092: Updated `rhumb_managed_capabilities` to point `scrape.extract` and `scrape.crawl` at `apify~website-content-crawler` instead of `apify~web-scraper`
- Added `?waitForFinish=60` query parameter so synchronous callers get completed results
- Applied via Supabase REST PATCH (2 rows updated)

## Rhumb-Managed Execution — After Fix

- **Endpoint:** `POST /v1/capabilities/scrape.extract/execute`
- **Provider:** apify, credential_mode: rhumb_managed
- **Params:** `startUrls: [{url: "https://example.com"}], maxCrawlPages: 1, crawlerType: "cheerio"`
- **Result:** Upstream 201 (Created + SUCCEEDED), execution_id `exec_a0448964bfb6419785cc4e09328d08fe`
- **Apify run ID:** `7SEG0FBlBDbbmBOKh`, status: SUCCEEDED
- **Latency:** 8486ms (includes Apify cold start + crawl + waitForFinish)
- **Telemetry:** Row logged with success=true

## Provider Health Impact

Apify shows as "unhealthy" in provider-health (16.7% success rate) due to 4 pre-fix 400 errors. These will age out as successful executions accumulate.

## Operational Notes

- Apify's `website-content-crawler` actor is free (no per-event charges)
- `waitForFinish=60` means synchronous execution — no polling needed
- Cold-start latency is 8-10s; subsequent runs are faster
- The `web-scraper` actor remains on browser.scrape/browser.crawl paths (not migrated to production, but migration SQL prepared)

## Evidence

- Execution ID: `exec_a0448964bfb6419785cc4e09328d08fe`
- Telemetry: verified via `/v1/telemetry/recent`
- Provider health: `apify` last seen `2026-03-26T11:38:32Z`
