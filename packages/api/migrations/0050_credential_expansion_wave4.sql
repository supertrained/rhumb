-- Migration 0050: Credential expansion wave 4
-- New signup: Fal.ai (AI model inference — requires balance top-up, key stored)
-- Note: Fal.ai is pay-per-use, no free tier. Key created but not yet executable.
-- This migration adds the mapping for when balance is funded.

BEGIN;

-- ============================================================
-- 1. Fal.ai → ai.generate_image (pending funding)
-- ============================================================
INSERT INTO proxy_services (id, name, domain, auth_type, credential_status, last_verified)
VALUES ('fal-ai', 'Fal.ai', 'queue.fal.run', 'api_key', 'pending_funding', NOW())
ON CONFLICT (id) DO UPDATE
  SET last_verified = NOW();

-- Note: Not marking rhumb_managed until balance is funded
-- Mapping exists from earlier migrations; leave as-is

-- ============================================================
-- Summary: wave 4
-- ============================================================
-- fal-ai: Key stored in 1Password, needs balance top-up ($10 min)
-- deepgram: Already shipped in wave 3 (migration 0049)
-- No new executable capabilities in this wave (fal-ai pending funding)

COMMIT;
