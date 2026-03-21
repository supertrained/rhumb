-- Migration 0047: Upgrade credentialed providers to rhumb_managed
-- All these providers have live, verified API keys in Rhumb's credential vault.
-- This migration upgrades their credential_mode from {byo,agent_vault} to include rhumb_managed,
-- making them directly executable through the Rhumb proxy without agent-side credentials.
--
-- Verified credentials (2026-03-21):
--   tavily: search API key (free tier, 1K searches/mo)
--   exa: search API key (free tier, 1K searches/mo)
--   brave-search: web search API key (free tier, 2K queries/mo)
--   e2b: sandbox API key (free tier, 100 hrs/mo)
--   replicate: API token (pay-per-use, no minimum)
--   algolia: search API key + app ID (free tier, 10K records)
--   firecrawl: already rhumb_managed
--   apify: already rhumb_managed

BEGIN;

-- ============================================================
-- 1. Tavily: search.query, search.web_search → rhumb_managed
-- ============================================================
UPDATE provider_capability_mappings
SET credential_mode = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Tavily credential. Purpose-built AI search.'
WHERE provider_id = 'tavily'
  AND capability_id IN ('search.query', 'search.web_search');

-- ============================================================
-- 2. Exa: search.query, search.web_search → rhumb_managed
-- ============================================================
UPDATE provider_capability_mappings
SET credential_mode = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Exa credential. Neural search, returns full content.'
WHERE provider_id = 'exa'
  AND capability_id IN ('search.query', 'search.web_search');

-- ============================================================
-- 3. Brave Search: search.query, search.web_search → rhumb_managed
-- ============================================================
UPDATE provider_capability_mappings
SET credential_mode = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Brave credential. Privacy-focused, 2K/mo free.'
WHERE provider_id = 'brave-search'
  AND capability_id IN ('search.query', 'search.web_search');

-- ============================================================
-- 4. E2B: compute.* → rhumb_managed
-- ============================================================
UPDATE provider_capability_mappings
SET credential_mode = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live E2B credential. Cloud sandboxes, 100 hrs/mo free.'
WHERE provider_id = 'e2b'
  AND capability_id IN ('compute.execute_code', 'compute.create_sandbox', 'compute.run_function');

-- ============================================================
-- 5. Replicate: ai.* → rhumb_managed
-- ============================================================
UPDATE provider_capability_mappings
SET credential_mode = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Replicate credential. Pay-per-prediction, no minimum.'
WHERE provider_id = 'replicate'
  AND capability_id IN ('ai.generate_text', 'ai.generate_image');

-- ============================================================
-- 6. Algolia: search/document caps → rhumb_managed
-- ============================================================
UPDATE provider_capability_mappings
SET credential_mode = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Algolia credential. 10K records free tier.'
WHERE provider_id = 'algolia'
  AND capability_id IN ('search.query', 'search.index', 'search.autocomplete', 'document.search');

-- ============================================================
-- 7. Update proxy_services registry to reflect rhumb_managed status
-- ============================================================
UPDATE proxy_services
SET credential_status = 'rhumb_managed',
    last_verified = NOW()
WHERE id IN ('tavily', 'exa', 'brave-search', 'e2b', 'replicate', 'algolia')
  AND credential_status != 'rhumb_managed';

-- ============================================================
-- 8. Unstructured: document.convert, document.parse → new rhumb_managed mappings
-- ============================================================
INSERT INTO provider_capability_mappings
  (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes)
VALUES
  ('document.convert', 'unstructured', '{byo,rhumb_managed}', 'api_key',
   'POST /general/v0/general',
   'PROXY-CALLABLE — live Unstructured credential. 15K pages free, 64+ file types.'),
  ('document.parse', 'unstructured', '{byo,rhumb_managed}', 'api_key',
   'POST /general/v0/general',
   'PROXY-CALLABLE — live Unstructured credential. Partition + chunk + enrich.')
ON CONFLICT (capability_id, provider_id) DO UPDATE
  SET credential_mode = EXCLUDED.credential_mode,
      notes = EXCLUDED.notes;

-- Also add unstructured to proxy_services if not present
INSERT INTO proxy_services (id, credential_status, last_verified)
VALUES ('unstructured', 'rhumb_managed', NOW())
ON CONFLICT (id) DO UPDATE
  SET credential_status = 'rhumb_managed',
      last_verified = NOW();

-- ============================================================
-- Summary: capabilities now directly executable via Rhumb proxy
-- ============================================================
-- tavily:        search.query, search.web_search (2)
-- exa:           search.query, search.web_search (2)
-- brave-search:  search.query, search.web_search (2)
-- e2b:           compute.execute_code, compute.create_sandbox, compute.run_function (3)
-- replicate:     ai.generate_text, ai.generate_image (2)
-- algolia:       search.query, search.index, search.autocomplete, document.search (4)
-- unstructured:  document.convert, document.parse (2) — NEW
-- firecrawl:     scrape.extract, scrape.crawl, scrape.screenshot (3) — already rhumb_managed
-- apify:         scrape.extract, scrape.crawl, scrape.screenshot (3) — already rhumb_managed
--
-- Unique rhumb_managed capabilities after this migration:
--   search.query, search.web_search, compute.execute_code, compute.create_sandbox,
--   compute.run_function, ai.generate_text, ai.generate_image, search.index,
--   search.autocomplete, document.search, document.convert, document.parse,
--   scrape.extract, scrape.crawl, scrape.screenshot
-- = 15 unique capabilities executable via Rhumb proxy
--
-- Total rhumb_managed provider-capability mappings: 23 new + 6 existing = 29

COMMIT;
