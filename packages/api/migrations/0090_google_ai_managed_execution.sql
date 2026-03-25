-- Migration 0090: Google AI managed execution wiring
--
-- Goal:
--   Turn Google AI (Gemini) from directory-only/BYO-only into a real
--   Rhumb-managed callable provider using the existing shared credential.
--
-- What this does:
--   1. Sets the Google AI API domain
--   2. Registers ai.edit_image in the capability registry
--   3. Adds/updates Google AI capability_services mappings so they advertise
--      rhumb_managed where appropriate
--   4. Inserts managed execution configs for text, embeddings, image gen,
--      image edit, TTS, and text-model aliases that share generateContent
--
-- Notes:
--   - chat.stream is intentionally excluded here because RhumbManagedExecutor
--     is request/response today; streamGenerateContent needs separate runtime work.
--   - Video/music/computer-use/research stay index-only per Phase 0.

BEGIN;

-- ============================================================
-- STEP 1: Ensure Google AI has a concrete API domain
-- ============================================================

UPDATE services
SET api_domain = 'generativelanguage.googleapis.com',
    updated_at = now()
WHERE slug = 'google-ai'
  AND (api_domain IS DISTINCT FROM 'generativelanguage.googleapis.com');

-- ============================================================
-- STEP 2: Register new capability from Google AI Phase 0
-- ============================================================

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome)
VALUES (
  'ai.edit_image',
  'ai',
  'edit_image',
  'Edit an existing image using text instructions',
  'prompt, image or images, model (optional)',
  'Edited image URL or binary'
)
ON CONFLICT (id) DO UPDATE SET
  domain = EXCLUDED.domain,
  action = EXCLUDED.action,
  description = EXCLUDED.description,
  input_hint = EXCLUDED.input_hint,
  outcome = EXCLUDED.outcome,
  updated_at = now();

-- ============================================================
-- STEP 3: Google AI capability mappings (catalog + billing surface)
-- ============================================================

-- Existing mappings: widen to rhumb_managed and normalize endpoint patterns.
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    endpoint_pattern = CASE
      WHEN capability_id IN ('ai.generate_text', 'ai.classify') THEN 'POST /v1beta/models/{model}:generateContent'
      WHEN capability_id IN ('ai.embed', 'embed.text') THEN 'POST /v1beta/models/{model}:embedContent'
      ELSE endpoint_pattern
    END,
    notes = CASE
      WHEN capability_id = 'ai.generate_text' THEN 'PROXY-CALLABLE — Google AI text generation via managed Gemini credential.'
      WHEN capability_id = 'ai.classify' THEN 'PROXY-CALLABLE — Google AI classification via managed Gemini credential.'
      WHEN capability_id = 'ai.embed' THEN 'PROXY-CALLABLE — Google AI embeddings via managed Gemini credential.'
      WHEN capability_id = 'embed.text' THEN 'PROXY-CALLABLE — Google AI text embeddings via managed Gemini credential.'
      ELSE notes
    END,
    updated_at = now()
WHERE service_slug = 'google-ai'
  AND capability_id IN ('ai.generate_text', 'ai.classify', 'ai.embed', 'embed.text');

-- New Google AI mappings unlocked by the same credential.
INSERT INTO capability_services (
  capability_id,
  service_slug,
  credential_modes,
  auth_method,
  endpoint_pattern,
  notes,
  is_primary
) VALUES
  (
    'ai.generate_image',
    'google-ai',
    '{byo,rhumb_managed}',
    'api_key',
    'POST /v1beta/models/{model}:generateContent',
    'ENHANCED — Google AI native image generation (Nano Banana / Gemini image models).',
    false
  ),
  (
    'media.generate_speech',
    'google-ai',
    '{byo,rhumb_managed}',
    'api_key',
    'POST /v1beta/models/{model}:generateContent',
    'ENHANCED — Google AI text-to-speech via Gemini TTS models.',
    false
  ),
  (
    'chat.complete',
    'google-ai',
    '{byo,rhumb_managed}',
    'api_key',
    'POST /v1beta/models/{model}:generateContent',
    'PROXY-CALLABLE — Google AI chat completion via managed Gemini credential.',
    false
  ),
  (
    'chat.function_call',
    'google-ai',
    '{byo,rhumb_managed}',
    'api_key',
    'POST /v1beta/models/{model}:generateContent',
    'PROXY-CALLABLE — Google AI tool/function calling via managed Gemini credential.',
    false
  ),
  (
    'nlp.summarize',
    'google-ai',
    '{byo,rhumb_managed}',
    'api_key',
    'POST /v1beta/models/{model}:generateContent',
    'PROXY-CALLABLE — Google AI summarization via managed Gemini credential.',
    false
  ),
  (
    'ai.edit_image',
    'google-ai',
    '{byo,rhumb_managed}',
    'api_key',
    'POST /v1beta/models/{model}:generateContent',
    'ENHANCED — Google AI text-and-image editing via Gemini image models.',
    false
  )
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_modes = EXCLUDED.credential_modes,
  auth_method = EXCLUDED.auth_method,
  endpoint_pattern = EXCLUDED.endpoint_pattern,
  notes = EXCLUDED.notes,
  is_primary = COALESCE(capability_services.is_primary, EXCLUDED.is_primary),
  updated_at = now();

-- ============================================================
-- STEP 4: Managed execution configs (the actual zero-config unlock)
-- ============================================================

INSERT INTO rhumb_managed_capabilities (
  capability_id,
  service_slug,
  description,
  credential_env_keys,
  default_method,
  default_path,
  default_headers
) VALUES
  (
    'ai.generate_text',
    'google-ai',
    'Text generation via Google AI Gemini models',
    '{RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY}',
    'POST',
    '/v1beta/models/{model}:generateContent',
    '{"Content-Type": "application/json"}'
  ),
  (
    'ai.classify',
    'google-ai',
    'Classification via Google AI Gemini models',
    '{RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY}',
    'POST',
    '/v1beta/models/{model}:generateContent',
    '{"Content-Type": "application/json"}'
  ),
  (
    'ai.embed',
    'google-ai',
    'Embeddings via Google AI Gemini embedding models',
    '{RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY}',
    'POST',
    '/v1beta/models/{model}:embedContent',
    '{"Content-Type": "application/json"}'
  ),
  (
    'embed.text',
    'google-ai',
    'Text embeddings via Google AI Gemini embedding models',
    '{RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY}',
    'POST',
    '/v1beta/models/{model}:embedContent',
    '{"Content-Type": "application/json"}'
  ),
  (
    'ai.generate_image',
    'google-ai',
    'Image generation via Google AI Gemini image models',
    '{RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY}',
    'POST',
    '/v1beta/models/{model}:generateContent',
    '{"Content-Type": "application/json"}'
  ),
  (
    'media.generate_speech',
    'google-ai',
    'Text-to-speech via Google AI Gemini TTS models',
    '{RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY}',
    'POST',
    '/v1beta/models/{model}:generateContent',
    '{"Content-Type": "application/json"}'
  ),
  (
    'chat.complete',
    'google-ai',
    'Chat completion via Google AI Gemini models',
    '{RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY}',
    'POST',
    '/v1beta/models/{model}:generateContent',
    '{"Content-Type": "application/json"}'
  ),
  (
    'chat.function_call',
    'google-ai',
    'Tool/function calling via Google AI Gemini models',
    '{RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY}',
    'POST',
    '/v1beta/models/{model}:generateContent',
    '{"Content-Type": "application/json"}'
  ),
  (
    'nlp.summarize',
    'google-ai',
    'Summarization via Google AI Gemini models',
    '{RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY}',
    'POST',
    '/v1beta/models/{model}:generateContent',
    '{"Content-Type": "application/json"}'
  ),
  (
    'ai.edit_image',
    'google-ai',
    'Image editing via Google AI Gemini image models',
    '{RHUMB_CREDENTIAL_GOOGLE_AI_API_KEY}',
    'POST',
    '/v1beta/models/{model}:generateContent',
    '{"Content-Type": "application/json"}'
  )
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  description = EXCLUDED.description,
  credential_env_keys = EXCLUDED.credential_env_keys,
  default_method = EXCLUDED.default_method,
  default_path = EXCLUDED.default_path,
  default_headers = EXCLUDED.default_headers,
  updated_at = now();

COMMIT;
