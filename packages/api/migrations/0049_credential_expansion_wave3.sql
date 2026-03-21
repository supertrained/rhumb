-- Migration 0049: Credential expansion wave 3
-- New signup: Deepgram ($200 free credits, speech-to-text, text-to-speech, voice agents)
-- Also: recognize existing Railway-deployed proxy services as rhumb_managed capabilities

BEGIN;

-- ============================================================
-- 1. Deepgram → ai.transcribe, ai.generate_speech
-- ============================================================
INSERT INTO proxy_services (id, name, domain, auth_type, credential_status, last_verified)
VALUES ('deepgram', 'Deepgram', 'api.deepgram.com', 'api_key', 'rhumb_managed', NOW())
ON CONFLICT (id) DO UPDATE
  SET credential_status = 'rhumb_managed',
      last_verified = NOW();

INSERT INTO provider_capability_mappings
  (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes)
VALUES
  ('ai.transcribe', 'deepgram', '{byo,rhumb_managed}', 'api_key',
   'POST /v1/listen',
   'PROXY-CALLABLE — live Deepgram credential. $200 free credits. Nova 3 model, 50+ languages.'),
  ('ai.generate_speech', 'deepgram', '{byo,rhumb_managed}', 'api_key',
   'POST /v1/speak',
   'PROXY-CALLABLE — live Deepgram credential. Text-to-speech, multiple voices.')
ON CONFLICT (capability_id, provider_id) DO UPDATE
  SET credential_mode = EXCLUDED.credential_mode,
      notes = EXCLUDED.notes;

-- ============================================================
-- 2. Existing Railway-deployed services → rhumb_managed
-- These services already have live credentials on Railway production.
-- They were previously only used as proxy pass-through services.
-- Now we also recognize them as capability-level rhumb_managed.
-- ============================================================

-- Resend (email.send) — already has RHUMB_CREDENTIAL_RESEND_API_KEY on Railway
UPDATE provider_capability_mappings
SET credential_mode = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Resend credential on Railway. 100 emails/day free.'
WHERE provider_id = 'resend'
  AND capability_id = 'email.send';

-- GitHub (code.search, code.review) — already has RHUMB_CREDENTIAL_GITHUB_API_TOKEN on Railway
UPDATE provider_capability_mappings
SET credential_mode = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live GitHub credential on Railway. Fine-grained PAT.'
WHERE provider_id = 'github'
  AND capability_id IN ('code.search', 'code.review', 'devops.trigger_build');

-- Twilio (communication.send_sms) — credential wired to Railway
UPDATE provider_capability_mappings
SET credential_mode = '{byo,rhumb_managed}',
    notes = 'PROXY-CALLABLE — live Twilio credential on Railway.'
WHERE provider_id = 'twilio'
  AND capability_id IN ('communication.send_sms', 'communication.send_push');

-- ============================================================
-- Summary: wave 3 additions
-- ============================================================
-- deepgram:  ai.transcribe, ai.generate_speech (+2 new unique capabilities)
-- resend:    email.send (upgraded to rhumb_managed, +1 unique)
-- github:    code.search, code.review, devops.trigger_build (upgraded, +3 unique)
-- twilio:    communication.send_sms, communication.send_push (upgraded, +2 unique)
--
-- Running total: ~25 unique rhumb_managed capabilities
-- Running total: ~41 rhumb_managed provider-capability mappings
-- Providers: 14 (tavily, exa, brave-search, e2b, replicate, algolia, unstructured,
--                firecrawl, apify, ipinfo, scraperapi, deepgram, resend, github, twilio)

COMMIT;
