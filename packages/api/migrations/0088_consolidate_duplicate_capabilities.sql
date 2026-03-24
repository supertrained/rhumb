-- Migration 0088: Consolidate duplicate capabilities
-- 
-- The SOP audit (2026-03-24) identified capabilities that are semantically
-- identical but registered under different domains. This migration merges
-- provider mappings and removes the duplicate capabilities.
--
-- Merge plan:
--   ai.generate_speech → media.generate_speech (keep media.*)
--   ai.transcribe → media.transcribe (keep media.*)
--   search.web_search → search.query (keep search.query — more providers)
--   browser.crawl → scrape.crawl (keep scrape.crawl — more providers)  
--   browser.scrape → scrape.extract (keep scrape.extract — more providers)
--
-- For each merge:
-- 1. Move provider mappings from deprecated cap to surviving cap (skip if already exists)
-- 2. Move execution configs (rhumb_managed_capabilities) from deprecated to surviving
-- 3. Delete deprecated capability_services rows
-- 4. Delete deprecated capability

-- ═══════════════════════════════════════════════════════════════
-- 1. ai.generate_speech → media.generate_speech
-- ═══════════════════════════════════════════════════════════════

-- Move provider mappings that don't already exist on the target
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, created_at)
SELECT 'media.generate_speech', cs.service_slug, cs.credential_modes, cs.auth_method, cs.endpoint_pattern, now()
FROM capability_services cs
WHERE cs.capability_id = 'ai.generate_speech'
  AND NOT EXISTS (
    SELECT 1 FROM capability_services existing
    WHERE existing.capability_id = 'media.generate_speech'
      AND existing.service_slug = cs.service_slug
  );

-- Move execution configs
UPDATE rhumb_managed_capabilities
SET capability_id = 'media.generate_speech'
WHERE capability_id = 'ai.generate_speech'
  AND NOT EXISTS (
    SELECT 1 FROM rhumb_managed_capabilities existing
    WHERE existing.capability_id = 'media.generate_speech'
      AND existing.service_slug = rhumb_managed_capabilities.service_slug
  );

-- Clean up deprecated
DELETE FROM rhumb_managed_capabilities WHERE capability_id = 'ai.generate_speech';
DELETE FROM capability_services WHERE capability_id = 'ai.generate_speech';
DELETE FROM capabilities WHERE id = 'ai.generate_speech';

-- ═══════════════════════════════════════════════════════════════
-- 2. ai.transcribe → media.transcribe
-- ═══════════════════════════════════════════════════════════════

INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, created_at)
SELECT 'media.transcribe', cs.service_slug, cs.credential_modes, cs.auth_method, cs.endpoint_pattern, now()
FROM capability_services cs
WHERE cs.capability_id = 'ai.transcribe'
  AND NOT EXISTS (
    SELECT 1 FROM capability_services existing
    WHERE existing.capability_id = 'media.transcribe'
      AND existing.service_slug = cs.service_slug
  );

UPDATE rhumb_managed_capabilities
SET capability_id = 'media.transcribe'
WHERE capability_id = 'ai.transcribe'
  AND NOT EXISTS (
    SELECT 1 FROM rhumb_managed_capabilities existing
    WHERE existing.capability_id = 'media.transcribe'
      AND existing.service_slug = rhumb_managed_capabilities.service_slug
  );

DELETE FROM rhumb_managed_capabilities WHERE capability_id = 'ai.transcribe';
DELETE FROM capability_services WHERE capability_id = 'ai.transcribe';
DELETE FROM capabilities WHERE id = 'ai.transcribe';

-- ═══════════════════════════════════════════════════════════════
-- 3. search.web_search → search.query  
-- ═══════════════════════════════════════════════════════════════

INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, created_at)
SELECT 'search.query', cs.service_slug, cs.credential_modes, cs.auth_method, cs.endpoint_pattern, now()
FROM capability_services cs
WHERE cs.capability_id = 'search.web_search'
  AND NOT EXISTS (
    SELECT 1 FROM capability_services existing
    WHERE existing.capability_id = 'search.query'
      AND existing.service_slug = cs.service_slug
  );

UPDATE rhumb_managed_capabilities
SET capability_id = 'search.query'
WHERE capability_id = 'search.web_search'
  AND NOT EXISTS (
    SELECT 1 FROM rhumb_managed_capabilities existing
    WHERE existing.capability_id = 'search.query'
      AND existing.service_slug = rhumb_managed_capabilities.service_slug
  );

DELETE FROM rhumb_managed_capabilities WHERE capability_id = 'search.web_search';
DELETE FROM capability_services WHERE capability_id = 'search.web_search';
DELETE FROM capabilities WHERE id = 'search.web_search';

-- ═══════════════════════════════════════════════════════════════
-- 4. browser.crawl → scrape.crawl
-- ═══════════════════════════════════════════════════════════════

INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, created_at)
SELECT 'scrape.crawl', cs.service_slug, cs.credential_modes, cs.auth_method, cs.endpoint_pattern, now()
FROM capability_services cs
WHERE cs.capability_id = 'browser.crawl'
  AND NOT EXISTS (
    SELECT 1 FROM capability_services existing
    WHERE existing.capability_id = 'scrape.crawl'
      AND existing.service_slug = cs.service_slug
  );

UPDATE rhumb_managed_capabilities
SET capability_id = 'scrape.crawl'
WHERE capability_id = 'browser.crawl'
  AND NOT EXISTS (
    SELECT 1 FROM rhumb_managed_capabilities existing
    WHERE existing.capability_id = 'scrape.crawl'
      AND existing.service_slug = rhumb_managed_capabilities.service_slug
  );

DELETE FROM rhumb_managed_capabilities WHERE capability_id = 'browser.crawl';
DELETE FROM capability_services WHERE capability_id = 'browser.crawl';
DELETE FROM capabilities WHERE id = 'browser.crawl';

-- ═══════════════════════════════════════════════════════════════
-- 5. browser.scrape → scrape.extract
-- ═══════════════════════════════════════════════════════════════

INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, created_at)
SELECT 'scrape.extract', cs.service_slug, cs.credential_modes, cs.auth_method, cs.endpoint_pattern, now()
FROM capability_services cs
WHERE cs.capability_id = 'browser.scrape'
  AND NOT EXISTS (
    SELECT 1 FROM capability_services existing
    WHERE existing.capability_id = 'scrape.extract'
      AND existing.service_slug = cs.service_slug
  );

UPDATE rhumb_managed_capabilities
SET capability_id = 'scrape.extract'
WHERE capability_id = 'browser.scrape'
  AND NOT EXISTS (
    SELECT 1 FROM rhumb_managed_capabilities existing
    WHERE existing.capability_id = 'scrape.extract'
      AND existing.service_slug = rhumb_managed_capabilities.service_slug
  );

DELETE FROM rhumb_managed_capabilities WHERE capability_id = 'browser.scrape';
DELETE FROM capability_services WHERE capability_id = 'browser.scrape';
DELETE FROM capabilities WHERE id = 'browser.scrape';
