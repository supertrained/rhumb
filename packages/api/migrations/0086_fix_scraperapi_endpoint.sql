-- Migration 0086: Fix ScraperAPI endpoint path
-- The original config used /structured which doesn't exist
-- ScraperAPI uses / with api_key as query parameter
-- Applied to production via Supabase REST on 2026-03-22
-- Author: Helm (rhumb-access)

UPDATE rhumb_managed_capabilities
SET default_path = '/',
    default_method = 'GET',
    updated_at = now()
WHERE capability_id = 'scrape.extract'
  AND service_slug = 'scraperapi';
