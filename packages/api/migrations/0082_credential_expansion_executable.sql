-- Migration 0082: Credential Expansion — Executable Upgrades
-- Goal: Increase executable (rhumb_managed) capabilities from ~25 to 50+
-- Strategy:
--   Part A: No-auth public APIs → rhumb_managed (no credential needed)
--   Part B: Existing vault credentials → upgrade byo to rhumb_managed
--
-- Expected delta: +25 unique executable capabilities
-- New rhumb_managed count: ~50+
--
-- Table: capability_services (from 0012_capability_registry)
-- Columns: capability_id, service_slug, credential_modes TEXT[], auth_method, endpoint_pattern, notes

BEGIN;

-- ============================================================
-- PART A: No-auth public APIs → rhumb_managed
-- These APIs require no authentication; Rhumb proxies directly.
-- ============================================================

-- A1. Weather — open-meteo (no auth, free, no rate limit)
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — No auth required. Open-Meteo free public API.'
WHERE service_slug = 'open-meteo'
  AND capability_id IN ('weather.current', 'weather.forecast', 'weather.historical');

-- A2. QR — goqr / qrserver / zxing (no auth, free)
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — No auth required. Free public API.'
WHERE service_slug IN ('goqr', 'qrserver', 'qr-server', 'zxing')
  AND capability_id IN ('qr.generate', 'qr.decode', 'barcode.generate');

-- A3. Crypto — coinbase public endpoints (no auth)
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — No auth required. Coinbase public spot price API.'
WHERE service_slug = 'coinbase'
  AND capability_id IN ('crypto.get_price', 'crypto.get_rates');

-- A4. Network — SSL Labs (no auth), Google DNS (no auth)
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — No auth required. Qualys SSL Labs public API.'
WHERE service_slug = 'ssllabs'
  AND capability_id = 'network.ssl_check';

UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — No auth required. Google DNS-over-HTTPS public API.'
WHERE service_slug IN ('google-dns')
  AND capability_id IN ('dns.lookup', 'network.dns_lookup');

-- A5. Unit conversion — free-unit-api (no auth)
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — No auth required. Free unit conversion API.'
WHERE service_slug = 'free-unit-api'
  AND capability_id IN ('unit.convert');

-- ============================================================
-- PART B: Vault credentials → upgrade to rhumb_managed
-- These providers have live API keys in the Rhumb credential vault.
-- ============================================================

-- B1. OpenAI — chat, embed, NLP (vault: "OpenAI API Key")
-- Pay-per-token, Rhumb absorbs cost on managed tier
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live OpenAI credential. Pay-per-token, Rhumb managed.'
WHERE service_slug = 'openai'
  AND capability_id IN (
    'chat.complete', 'chat.stream', 'chat.function_call',
    'embed.text', 'embed.batch', 'embed.similarity',
    'nlp.summarize'
  );

-- B2. Groq — chat (vault: "Groq API Key")
-- Free tier: generous rate limit
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Groq credential. Free tier: 14.4K tokens/min.'
WHERE service_slug = 'groq'
  AND capability_id IN ('chat.complete', 'chat.stream', 'chat.function_call');

-- B3. Cohere — NLP + embed (vault: "Tester - Cohere")
-- Free trial tier: 1K API calls/month
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Cohere credential. Free trial tier: 1K calls/mo.'
WHERE service_slug = 'cohere'
  AND capability_id IN (
    'nlp.classify', 'nlp.sentiment', 'nlp.extract_entities', 'nlp.summarize',
    'embed.text', 'embed.batch', 'embed.similarity'
  );

-- B4. DataForSEO — SEO (vault: "DataForSEO")
-- Pay-per-task, live credential
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live DataForSEO credential. Pay-per-task.'
WHERE service_slug = 'dataforseo'
  AND capability_id IN ('seo.check', 'seo.keywords');

-- B5. Google Maps/Places — maps (vault: "Google Places API Key")
-- $200/mo free credit covers maps, geocoding, places
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Google Maps credential. $200/mo free credit.'
WHERE service_slug IN ('google-maps', 'google-places')
  AND capability_id IN ('maps.geocode', 'maps.directions');

-- B6. Apollo — contact/data enrichment (vault: "Apollo API Key")
-- Free tier: 10K enrichments/mo
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Apollo credential. Free: 10K enrichments/mo.'
WHERE service_slug = 'apollo'
  AND capability_id IN ('data.enrich_person', 'data.enrich_company', 'data.search_contacts');

-- B7. Google AI (Gemini) — embed (vault: "Google Gemini API Key")
-- Free tier: generous
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Google AI credential. Free tier.'
WHERE service_slug = 'google-ai'
  AND capability_id IN ('embed.text');

-- B8. Together AI — chat (vault: "Tester - Together AI")
-- $5 free credits, 100+ open-source models
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Together AI credential. $5 free credits, 100+ OSS models.'
WHERE service_slug = 'together-ai'
  AND capability_id IN ('chat.complete');

-- ============================================================
-- PART C: Register new providers in services table if not present
-- ============================================================
-- (open-meteo and other no-auth APIs may not be in the services table yet)
-- This is a no-op if they already exist.

INSERT INTO services (slug, name, url, category, score)
SELECT slug, name, url, category, score
FROM (VALUES
  ('open-meteo', 'Open-Meteo', 'https://open-meteo.com', 'weather', 7.5),
  ('goqr', 'GoQR.me', 'https://goqr.me', 'utility', 7.0),
  ('zxing', 'ZXing Decoder', 'https://zxing.org', 'utility', 7.0),
  ('ssllabs', 'Qualys SSL Labs', 'https://www.ssllabs.com', 'security', 8.0),
  ('google-dns', 'Google DNS', 'https://dns.google', 'network', 8.0),
  ('free-unit-api', 'Free Unit API', 'https://freeunitconverterapi.com', 'utility', 6.5)
) AS v(slug, name, url, category, score)
WHERE NOT EXISTS (SELECT 1 FROM services WHERE services.slug = v.slug);

-- ============================================================
-- Summary
-- ============================================================
-- PART A — No-auth public APIs (new rhumb_managed capabilities):
--   weather.current, weather.forecast, weather.historical    (open-meteo)    +3
--   qr.generate, qr.decode, barcode.generate                (goqr/zxing)    +3
--   crypto.get_price, crypto.get_rates                       (coinbase)      +2
--   network.ssl_check                                        (ssllabs)       +1
--   dns.lookup                                               (google-dns)    +1
--   unit.convert                                             (free-unit-api) +1
--   Subtotal: +11 unique executable capabilities
--
-- PART B — Vault credential upgrades:
--   chat.complete, chat.stream, chat.function_call          (openai/groq/together) +3
--   embed.text, embed.batch, embed.similarity               (openai/cohere/google) +3
--   nlp.classify, nlp.sentiment, nlp.extract_entities       (cohere)              +3
--   nlp.summarize                                           (openai/cohere)       +1
--   seo.check, seo.keywords                                 (dataforseo)          +2
--   maps.geocode, maps.directions                           (google-maps)         +2
--   data.enrich_person, data.enrich_company, data.search_contacts (apollo)        +3
--   Subtotal: +17 unique executable capabilities
--
-- Total new: +28 unique executable capabilities
-- Previous: ~25 executable
-- New total: ~53 executable capabilities (target: 50 ✅)
--
-- Providers now rhumb_managed: open-meteo, goqr, qrserver, zxing, coinbase,
--   ssllabs, google-dns, free-unit-api, openai, groq, cohere, dataforseo,
--   google-maps, google-places, apollo, google-ai, together-ai
-- + existing: firecrawl, apify, scraperapi, tavily, exa, brave-search, e2b,
--   replicate, algolia, unstructured, deepgram, ipinfo, betterstack, upstash,
--   resend, postmark, sendgrid

COMMIT;
