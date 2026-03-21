-- Migration 0048: Credential expansion wave 2 — new signups
-- New provider signups with verified live API keys.
-- Each new provider adds rhumb_managed capabilities.
--
-- New signups (2026-03-21):
--   ipinfo:    IP geolocation API (free tier, 50K/mo)
--   scraperapi: web scraping proxy API (5000 free credits)
--
-- Pending email verification (will enable once confirmed):
--   hunter: email finder API (25 free searches/mo)
--   pdfco: document conversion API (free credits)

BEGIN;

-- ============================================================
-- 1. IPinfo → geo.lookup, data.enrich
-- ============================================================
-- First, ensure ipinfo exists as a provider
INSERT INTO proxy_services (id, name, domain, auth_type, credential_status, last_verified)
VALUES ('ipinfo', 'IPinfo', 'api.ipinfo.io', 'bearer_token', 'rhumb_managed', NOW())
ON CONFLICT (id) DO UPDATE
  SET credential_status = 'rhumb_managed',
      last_verified = NOW();

-- Map capabilities
INSERT INTO provider_capability_mappings
  (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes)
VALUES
  ('geo.lookup', 'ipinfo', '{byo,rhumb_managed}', 'bearer_token',
   'GET /lite/{ip}',
   'PROXY-CALLABLE — live IPinfo credential. 50K lookups/mo free.'),
  ('data.enrich', 'ipinfo', '{byo,rhumb_managed}', 'bearer_token',
   'GET /lite/{ip}',
   'PROXY-CALLABLE — live IPinfo credential. IP enrichment with ASN, company, location.')
ON CONFLICT (capability_id, provider_id) DO UPDATE
  SET credential_mode = EXCLUDED.credential_mode,
      notes = EXCLUDED.notes;

-- ============================================================
-- 2. ScraperAPI → scrape.extract, scrape.crawl
-- ============================================================
INSERT INTO proxy_services (id, name, domain, auth_type, credential_status, last_verified)
VALUES ('scraperapi', 'ScraperAPI', 'api.scraperapi.com', 'api_key', 'rhumb_managed', NOW())
ON CONFLICT (id) DO UPDATE
  SET credential_status = 'rhumb_managed',
      last_verified = NOW();

INSERT INTO provider_capability_mappings
  (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes)
VALUES
  ('scrape.extract', 'scraperapi', '{byo,rhumb_managed}', 'api_key',
   'GET /?api_key={key}&url={target}',
   'PROXY-CALLABLE — live ScraperAPI credential. 5K credits free, handles JS rendering.'),
  ('scrape.crawl', 'scraperapi', '{byo,rhumb_managed}', 'api_key',
   'POST /structured',
   'PROXY-CALLABLE — live ScraperAPI credential. Structured data extraction.')
ON CONFLICT (capability_id, provider_id) DO UPDATE
  SET credential_mode = EXCLUDED.credential_mode,
      notes = EXCLUDED.notes;

-- ============================================================
-- Summary: wave 2 additions
-- ============================================================
-- ipinfo:    geo.lookup, data.enrich (2 capabilities)
-- scraperapi: scrape.extract, scrape.crawl (2 capabilities)
--
-- New unique rhumb_managed capabilities: geo.lookup, data.enrich (+2 new unique)
-- scrape.extract and scrape.crawl were already rhumb_managed via firecrawl/apify
-- Running total: 17 unique rhumb_managed capabilities
-- Running total: 33 rhumb_managed provider-capability mappings

COMMIT;
