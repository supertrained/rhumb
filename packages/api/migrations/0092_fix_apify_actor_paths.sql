-- Migration 0092: Fix Apify managed execution actor paths
--
-- Problem: All Apify managed configs point to `apify~web-scraper` which requires
-- `pageFunction` (a full JavaScript function) — making it unusable for simple
-- scrape.extract / scrape.crawl use cases via Resolve.
--
-- Fix: Switch scrape.extract and scrape.crawl to `apify~website-content-crawler`
-- which only needs `startUrls` and returns clean markdown/text output.
-- Keep browser.scrape and browser.crawl on web-scraper since those are explicitly
-- about programmable browser automation.
-- Keep scrape.screenshot on screenshot-url (already correct).
--
-- Also add `?waitForFinish=60` so synchronous callers get results without polling.

UPDATE rhumb_managed_capabilities
SET default_path = '/v2/acts/apify~website-content-crawler/runs?waitForFinish=60',
    updated_at = now()
WHERE service_slug = 'apify'
  AND capability_id IN ('scrape.extract', 'scrape.crawl');

-- Add waitForFinish to browser paths too (these keep web-scraper because
-- browser automation genuinely needs pageFunction for complex scenarios,
-- and callers using browser.* presumably know what they're sending).
UPDATE rhumb_managed_capabilities
SET default_path = '/v2/acts/apify~web-scraper/runs?waitForFinish=60',
    updated_at = now()
WHERE service_slug = 'apify'
  AND capability_id IN ('browser.scrape', 'browser.crawl');

-- Add waitForFinish to screenshot path
UPDATE rhumb_managed_capabilities
SET default_path = '/v2/acts/apify~screenshot-url/runs?waitForFinish=60',
    updated_at = now()
WHERE service_slug = 'apify'
  AND capability_id = 'scrape.screenshot';
