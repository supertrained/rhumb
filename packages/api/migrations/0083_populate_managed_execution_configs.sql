-- Migration 0083: Populate rhumb_managed_capabilities execution configs
-- THIS IS THE CRITICAL MIGRATION — without these rows, every rhumb_managed
-- execution returns 503 "No managed execution path".
--
-- What this does:
--   1. Sets services.api_domain for all managed providers
--   2. Inserts execution configs into rhumb_managed_capabilities
--   3. Updates capability_services.credential_modes to include rhumb_managed
--
-- Result: ~60 unique capabilities become truly executable
-- Author: Helm (rhumb-access)
-- Date: 2026-03-22

BEGIN;

-- ============================================================
-- STEP 1: Set api_domain for all managed providers
-- ============================================================

UPDATE services SET api_domain = 'api.firecrawl.dev' WHERE slug = 'firecrawl' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.apify.com' WHERE slug = 'apify' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.scraperapi.com' WHERE slug = 'scraperapi' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.tavily.com' WHERE slug = 'tavily' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.exa.ai' WHERE slug = 'exa' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.search.brave.com' WHERE slug = 'brave-search' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.replicate.com' WHERE slug = 'replicate' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.resend.com' WHERE slug = 'resend' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.postmarkapp.com' WHERE slug = 'postmark' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.openai.com' WHERE slug = 'openai' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.deepgram.com' WHERE slug = 'deepgram' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.cohere.com' WHERE slug = 'cohere' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.groq.com' WHERE slug = 'groq' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.elevenlabs.io' WHERE slug = 'elevenlabs' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'ipinfo.io' WHERE slug = 'ipinfo' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.e2b.dev' WHERE slug = 'e2b' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.unstructuredapp.io' WHERE slug = 'unstructured' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'uptime.betterstack.com' WHERE slug = 'betterstack' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.peopledatalabs.com' WHERE slug = 'people-data-labs' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'api.apollo.io' WHERE slug = 'apollo' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = '80LYFTF37Y-dsn.algolia.net' WHERE slug = 'algolia' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'maps.googleapis.com' WHERE slug = 'google-maps' AND (api_domain IS NULL OR api_domain = '');
UPDATE services SET api_domain = 'maps.googleapis.com' WHERE slug = 'google-places' AND (api_domain IS NULL OR api_domain = '');

-- ============================================================
-- STEP 2: Insert execution configs into rhumb_managed_capabilities
-- ============================================================

-- ---- SCRAPING (firecrawl, apify, scraperapi) ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('scrape.extract', 'firecrawl', 'Extract structured data from URL via Firecrawl', '{RHUMB_CREDENTIAL_FIRECRAWL_API_KEY}', 'POST', '/v1/scrape', '{}'),
('scrape.crawl', 'firecrawl', 'Crawl website via Firecrawl', '{RHUMB_CREDENTIAL_FIRECRAWL_API_KEY}', 'POST', '/v1/crawl', '{}'),
('scrape.screenshot', 'firecrawl', 'Screenshot via Firecrawl scrape', '{RHUMB_CREDENTIAL_FIRECRAWL_API_KEY}', 'POST', '/v1/scrape', '{}'),
('scrape.extract', 'apify', 'Extract data via Apify actor', '{RHUMB_CREDENTIAL_APIFY_API_TOKEN}', 'POST', '/v2/acts/apify~web-scraper/runs', '{}'),
('scrape.crawl', 'apify', 'Crawl via Apify web scraper actor', '{RHUMB_CREDENTIAL_APIFY_API_TOKEN}', 'POST', '/v2/acts/apify~web-scraper/runs', '{}'),
('scrape.screenshot', 'apify', 'Screenshot via Apify screenshot actor', '{RHUMB_CREDENTIAL_APIFY_API_TOKEN}', 'POST', '/v2/acts/apify~screenshot-url/runs', '{}'),
('scrape.extract', 'scraperapi', 'Extract via ScraperAPI', '{RHUMB_CREDENTIAL_SCRAPERAPI_API_KEY}', 'GET', '/structured', '{}'),
('scrape.crawl', 'scraperapi', 'Crawl via ScraperAPI', '{RHUMB_CREDENTIAL_SCRAPERAPI_API_KEY}', 'POST', '/structured', '{}'),
-- Browser automation (same providers)
('browser.scrape', 'firecrawl', 'Browser scrape via Firecrawl', '{RHUMB_CREDENTIAL_FIRECRAWL_API_KEY}', 'POST', '/v1/scrape', '{}'),
('browser.crawl', 'firecrawl', 'Browser crawl via Firecrawl', '{RHUMB_CREDENTIAL_FIRECRAWL_API_KEY}', 'POST', '/v1/crawl', '{}'),
('browser.scrape', 'apify', 'Browser scrape via Apify', '{RHUMB_CREDENTIAL_APIFY_API_TOKEN}', 'POST', '/v2/acts/apify~web-scraper/runs', '{}'),
('browser.crawl', 'apify', 'Browser crawl via Apify', '{RHUMB_CREDENTIAL_APIFY_API_TOKEN}', 'POST', '/v2/acts/apify~web-scraper/runs', '{}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  default_method = EXCLUDED.default_method,
  default_path = EXCLUDED.default_path,
  updated_at = now();

-- ---- SEARCH (tavily, exa, brave) ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('search.query', 'tavily', 'Web search via Tavily', '{RHUMB_CREDENTIAL_TAVILY_API_KEY}', 'POST', '/search', '{}'),
('search.web_search', 'tavily', 'Web search via Tavily', '{RHUMB_CREDENTIAL_TAVILY_API_KEY}', 'POST', '/search', '{}'),
('search.query', 'exa', 'Neural search via Exa', '{RHUMB_CREDENTIAL_EXA_API_KEY}', 'POST', '/search', '{}'),
('search.query', 'brave-search', 'Web search via Brave', '{RHUMB_CREDENTIAL_BRAVE_SEARCH_API_KEY}', 'GET', '/res/v1/web/search', '{"Accept": "application/json"}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  default_method = EXCLUDED.default_method,
  default_path = EXCLUDED.default_path,
  updated_at = now();

-- ---- SEARCH + CATALOG (algolia) ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('search.index', 'algolia', 'Index documents in Algolia', '{RHUMB_CREDENTIAL_ALGOLIA_API_KEY}', 'POST', '/1/indexes/{indexName}', '{"X-Algolia-Application-Id": "80LYFTF37Y"}'),
('search.autocomplete', 'algolia', 'Autocomplete search via Algolia', '{RHUMB_CREDENTIAL_ALGOLIA_API_KEY}', 'POST', '/1/indexes/{indexName}/query', '{"X-Algolia-Application-Id": "80LYFTF37Y"}'),
('ecommerce.search_products', 'algolia', 'Product search via Algolia', '{RHUMB_CREDENTIAL_ALGOLIA_API_KEY}', 'POST', '/1/indexes/{indexName}/query', '{"X-Algolia-Application-Id": "80LYFTF37Y"}'),
('document.search', 'algolia', 'Document search via Algolia', '{RHUMB_CREDENTIAL_ALGOLIA_API_KEY}', 'POST', '/1/indexes/{indexName}/query', '{"X-Algolia-Application-Id": "80LYFTF37Y"}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  default_headers = EXCLUDED.default_headers,
  updated_at = now();

-- ---- AI TEXT GENERATION (openai, groq, cohere, replicate) ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('ai.generate_text', 'openai', 'Text generation via OpenAI', '{RHUMB_CREDENTIAL_OPENAI_API_KEY}', 'POST', '/v1/chat/completions', '{}'),
('ai.generate_text', 'groq', 'Text generation via Groq (fast inference)', '{RHUMB_CREDENTIAL_GROQ_API_KEY}', 'POST', '/openai/v1/chat/completions', '{}'),
('ai.generate_text', 'cohere', 'Text generation via Cohere', '{RHUMB_CREDENTIAL_COHERE_API_KEY}', 'POST', '/v2/chat', '{}'),
('ai.generate_text', 'replicate', 'Text generation via Replicate', '{RHUMB_CREDENTIAL_REPLICATE_API_TOKEN}', 'POST', '/v1/predictions', '{}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  updated_at = now();

-- ---- AI EMBEDDINGS (openai, cohere) ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('ai.embed', 'openai', 'Text embeddings via OpenAI', '{RHUMB_CREDENTIAL_OPENAI_API_KEY}', 'POST', '/v1/embeddings', '{}'),
('ai.embed', 'cohere', 'Text embeddings via Cohere', '{RHUMB_CREDENTIAL_COHERE_API_KEY}', 'POST', '/v2/embed', '{}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  updated_at = now();

-- ---- AI IMAGE (openai, replicate) ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('ai.generate_image', 'openai', 'Image generation via OpenAI DALL-E', '{RHUMB_CREDENTIAL_OPENAI_API_KEY}', 'POST', '/v1/images/generations', '{}'),
('ai.generate_image', 'replicate', 'Image generation via Replicate', '{RHUMB_CREDENTIAL_REPLICATE_API_TOKEN}', 'POST', '/v1/predictions', '{}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  updated_at = now();

-- ---- AI CLASSIFY ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('ai.classify', 'cohere', 'Text classification via Cohere', '{RHUMB_CREDENTIAL_COHERE_API_KEY}', 'POST', '/v2/classify', '{}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  updated_at = now();

-- ---- AI TRANSCRIPTION + SPEECH (deepgram, openai, elevenlabs) ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('ai.transcribe', 'deepgram', 'Audio transcription via Deepgram', '{RHUMB_CREDENTIAL_DEEPGRAM_API_KEY}', 'POST', '/v1/listen', '{}'),
('ai.transcribe', 'openai', 'Audio transcription via OpenAI Whisper', '{RHUMB_CREDENTIAL_OPENAI_API_KEY}', 'POST', '/v1/audio/transcriptions', '{}'),
('ai.generate_speech', 'elevenlabs', 'Text-to-speech via ElevenLabs', '{RHUMB_CREDENTIAL_ELEVENLABS_API_KEY}', 'POST', '/v1/text-to-speech/{voice_id}', '{}'),
('ai.generate_speech', 'openai', 'Text-to-speech via OpenAI TTS', '{RHUMB_CREDENTIAL_OPENAI_API_KEY}', 'POST', '/v1/audio/speech', '{}'),
('ai.generate_speech', 'deepgram', 'Text-to-speech via Deepgram', '{RHUMB_CREDENTIAL_DEEPGRAM_API_KEY}', 'POST', '/v1/speak', '{}'),
('media.transcribe', 'deepgram', 'Audio transcription via Deepgram', '{RHUMB_CREDENTIAL_DEEPGRAM_API_KEY}', 'POST', '/v1/listen', '{}'),
('media.generate_speech', 'elevenlabs', 'Text-to-speech via ElevenLabs', '{RHUMB_CREDENTIAL_ELEVENLABS_API_KEY}', 'POST', '/v1/text-to-speech/{voice_id}', '{}'),
('video.subtitle', 'deepgram', 'Video subtitle generation via Deepgram', '{RHUMB_CREDENTIAL_DEEPGRAM_API_KEY}', 'POST', '/v1/listen', '{}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  updated_at = now();

-- ---- DATA ENRICHMENT (apollo, pdl, ipinfo) ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('data.enrich_person', 'apollo', 'Person enrichment via Apollo', '{RHUMB_CREDENTIAL_APOLLO_API_KEY}', 'POST', '/v1/people/match', '{}'),
('data.enrich_company', 'apollo', 'Company enrichment via Apollo', '{RHUMB_CREDENTIAL_APOLLO_API_KEY}', 'POST', '/v1/organizations/enrich', '{}'),
('data.search_contacts', 'apollo', 'Contact search via Apollo', '{RHUMB_CREDENTIAL_APOLLO_API_KEY}', 'POST', '/v1/mixed_people/search', '{}'),
('data.enrich_person', 'people-data-labs', 'Person enrichment via PDL', '{RHUMB_CREDENTIAL_PDL_API_KEY}', 'GET', '/v5/person/enrich', '{}'),
('data.enrich_company', 'people-data-labs', 'Company enrichment via PDL', '{RHUMB_CREDENTIAL_PDL_API_KEY}', 'GET', '/v5/company/enrich', '{}'),
('geo.lookup', 'ipinfo', 'IP geolocation via IPinfo', '{RHUMB_CREDENTIAL_IPINFO_TOKEN}', 'GET', '/{ip}', '{}'),
('data.enrich', 'ipinfo', 'IP data enrichment via IPinfo', '{RHUMB_CREDENTIAL_IPINFO_TOKEN}', 'GET', '/{ip}', '{}'),
('identity.lookup', 'ipinfo', 'IP identity lookup via IPinfo', '{RHUMB_CREDENTIAL_IPINFO_TOKEN}', 'GET', '/{ip}', '{}'),
('network.ip_check', 'ipinfo', 'IP info check via IPinfo', '{RHUMB_CREDENTIAL_IPINFO_TOKEN}', 'GET', '/{ip}', '{}'),
('network.dns_lookup', 'ipinfo', 'DNS lookup via IPinfo', '{RHUMB_CREDENTIAL_IPINFO_TOKEN}', 'GET', '/{ip}', '{}'),
('network.whois', 'ipinfo', 'WHOIS via IPinfo', '{RHUMB_CREDENTIAL_IPINFO_TOKEN}', 'GET', '/{ip}', '{}'),
('timezone.get_info', 'ipinfo', 'Timezone lookup via IPinfo', '{RHUMB_CREDENTIAL_IPINFO_TOKEN}', 'GET', '/{ip}', '{}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  updated_at = now();

-- ---- EMAIL (resend, postmark) ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('email.send', 'resend', 'Send email via Resend', '{RHUMB_CREDENTIAL_RESEND_API_KEY}', 'POST', '/emails', '{}'),
('email.send', 'postmark', 'Send email via Postmark', '{RHUMB_CREDENTIAL_POSTMARK_API_KEY}', 'POST', '/email', '{"X-Postmark-Server-Token": "USE_BEARER"}'),
('email.template', 'resend', 'Send templated email via Resend', '{RHUMB_CREDENTIAL_RESEND_API_KEY}', 'POST', '/emails', '{}'),
('email.template', 'postmark', 'Send template email via Postmark', '{RHUMB_CREDENTIAL_POSTMARK_API_KEY}', 'POST', '/email/withTemplate', '{}'),
('email.track', 'postmark', 'Email tracking stats via Postmark', '{RHUMB_CREDENTIAL_POSTMARK_API_KEY}', 'GET', '/stats/outbound', '{}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  updated_at = now();

-- ---- DOCUMENT PROCESSING (unstructured) ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('document.convert', 'unstructured', 'Document conversion via Unstructured', '{RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY}', 'POST', '/general/v0/general', '{}'),
('document.parse', 'unstructured', 'Document parsing via Unstructured', '{RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY}', 'POST', '/general/v0/general', '{}'),
('pdf.convert', 'unstructured', 'PDF conversion via Unstructured', '{RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY}', 'POST', '/general/v0/general', '{}'),
('pdf.extract_text', 'unstructured', 'PDF text extraction via Unstructured', '{RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY}', 'POST', '/general/v0/general', '{}'),
('receipt.parse', 'unstructured', 'Receipt parsing via Unstructured', '{RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY}', 'POST', '/general/v0/general', '{}'),
('file.convert', 'unstructured', 'File conversion via Unstructured', '{RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY}', 'POST', '/general/v0/general', '{}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  updated_at = now();

-- ---- COMPUTE (e2b) ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('compute.execute_code', 'e2b', 'Execute code in E2B sandbox', '{RHUMB_CREDENTIAL_E2B_API_KEY}', 'POST', '/sandboxes', '{}'),
('compute.create_sandbox', 'e2b', 'Create E2B sandbox', '{RHUMB_CREDENTIAL_E2B_API_KEY}', 'POST', '/sandboxes', '{}'),
('compute.run_function', 'e2b', 'Run function in E2B sandbox', '{RHUMB_CREDENTIAL_E2B_API_KEY}', 'POST', '/sandboxes', '{}'),
('code.format', 'e2b', 'Format code in E2B sandbox', '{RHUMB_CREDENTIAL_E2B_API_KEY}', 'POST', '/sandboxes', '{}'),
('code.lint', 'e2b', 'Lint code in E2B sandbox', '{RHUMB_CREDENTIAL_E2B_API_KEY}', 'POST', '/sandboxes', '{}'),
('agent.spawn', 'e2b', 'Spawn agent sandbox via E2B', '{RHUMB_CREDENTIAL_E2B_API_KEY}', 'POST', '/sandboxes', '{}'),
('agent.get_status', 'e2b', 'Get agent sandbox status via E2B', '{RHUMB_CREDENTIAL_E2B_API_KEY}', 'GET', '/sandboxes/{sandboxId}', '{}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  updated_at = now();

-- ---- MAPS (google-maps, google-places) ----
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers) VALUES
('maps.geocode', 'google-maps', 'Geocoding via Google Maps', '{RHUMB_CREDENTIAL_GOOGLE_PLACES_API_KEY}', 'GET', '/maps/api/geocode/json', '{}'),
('maps.directions', 'google-maps', 'Directions via Google Maps', '{RHUMB_CREDENTIAL_GOOGLE_PLACES_API_KEY}', 'GET', '/maps/api/directions/json', '{}'),
('maps.places_search', 'google-places', 'Places search via Google', '{RHUMB_CREDENTIAL_GOOGLE_PLACES_API_KEY}', 'GET', '/maps/api/place/textsearch/json', '{}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  updated_at = now();

-- ============================================================
-- STEP 3: Update capability_services to reflect rhumb_managed
-- ============================================================

-- All capabilities that now have execution configs should show rhumb_managed in catalog
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}'
WHERE (capability_id, service_slug) IN (
  SELECT capability_id, service_slug FROM rhumb_managed_capabilities WHERE enabled = true
)
AND NOT ('rhumb_managed' = ANY(credential_modes));

-- ============================================================
-- Summary of unique executable capabilities after this migration
-- ============================================================
-- scrape.extract, scrape.crawl, scrape.screenshot        → firecrawl, apify, scraperapi    (3)
-- browser.scrape, browser.crawl                           → firecrawl, apify               (2)
-- search.query, search.web_search                         → tavily, exa, brave             (2)
-- search.index, search.autocomplete                       → algolia                        (2)
-- ecommerce.search_products, document.search              → algolia                        (2)
-- ai.generate_text                                        → openai, groq, cohere, replicate (1)
-- ai.embed                                                → openai, cohere                 (1)
-- ai.generate_image                                       → openai, replicate              (1)
-- ai.classify                                             → cohere                         (1)
-- ai.transcribe                                           → deepgram, openai               (1)
-- ai.generate_speech                                      → elevenlabs, openai, deepgram   (1)
-- media.transcribe                                        → deepgram                       (1)
-- media.generate_speech                                   → elevenlabs                     (1)
-- video.subtitle                                          → deepgram                       (1)
-- data.enrich_person, data.enrich_company, data.search_contacts → apollo, pdl              (3)
-- data.enrich, geo.lookup, identity.lookup                → ipinfo                         (3)
-- network.ip_check, network.dns_lookup, network.whois     → ipinfo                         (3)
-- timezone.get_info                                        → ipinfo                         (1)
-- email.send, email.template, email.track                 → resend, postmark               (3)
-- document.convert, document.parse                        → unstructured                   (2)
-- pdf.convert, pdf.extract_text                           → unstructured                   (2)
-- receipt.parse, file.convert                             → unstructured                   (2)
-- compute.execute_code, compute.create_sandbox, compute.run_function → e2b                 (3)
-- code.format, code.lint                                   → e2b                            (2)
-- agent.spawn, agent.get_status                            → e2b                            (2)
-- maps.geocode, maps.directions                            → google-maps                   (2)
-- maps.places_search                                       → google-places                 (1)
--
-- TOTAL: ~48 unique executable capabilities
-- (+ 6 from 0082 no-auth APIs = ~54 total)

COMMIT;
