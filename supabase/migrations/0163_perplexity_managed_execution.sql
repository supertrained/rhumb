-- Migration 0163: Perplexity managed execution wiring
--
-- Goal:
--   Ship the narrowest honest managed Perplexity wedge so Resolve can execute
--   Perplexity-backed text generation without requiring BYOK.
--
-- Notes:
--   - This slice intentionally starts with ai.generate_text only. Perplexity
--     exposes additional surfaces (including Search and Sonar variants), but
--     this migration does not claim those until the current runtime and public
--     contract are reviewed end-to-end.
--   - Resolve already exposes Perplexity as a BYOK provider for
--     POST /chat/completions. Perplexity's docs currently describe that route
--     as the OpenAI-compatible alias for Sonar; we keep the existing contract
--     rather than silently shifting callers to a broader or different surface.
--
-- Verified credential context:
--   - Shared managed key verified externally on 2026-04-23.

BEGIN;

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES (
  'perplexity',
  'Perplexity',
  'ai',
  'Web-grounded AI API with OpenAI-compatible chat completions and a separate Search API.',
  'https://docs.perplexity.ai/',
  'api.perplexity.ai'
)
ON CONFLICT (slug) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  official_docs = EXCLUDED.official_docs,
  api_domain = EXCLUDED.api_domain,
  updated_at = now();

INSERT INTO capability_services (
  capability_id,
  service_slug,
  credential_modes,
  auth_method,
  endpoint_pattern,
  notes,
  is_primary
)
VALUES (
  'ai.generate_text',
  'perplexity',
  '{byo,rhumb_managed}',
  'api_key',
  'POST /chat/completions',
  'PROXY-CALLABLE - Perplexity Sonar text generation via the OpenAI-compatible chat-completions alias and a shared Rhumb-managed credential. Phase 0 is intentionally narrow: managed execution covers ai.generate_text only and returns Perplexity''s provider-native response payload.',
  false
)
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_modes = EXCLUDED.credential_modes,
  auth_method = EXCLUDED.auth_method,
  endpoint_pattern = EXCLUDED.endpoint_pattern,
  notes = EXCLUDED.notes,
  is_primary = capability_services.is_primary,
  updated_at = now();

INSERT INTO rhumb_managed_capabilities (
  capability_id,
  service_slug,
  description,
  credential_env_keys,
  default_method,
  default_path,
  default_headers
)
VALUES (
  'ai.generate_text',
  'perplexity',
  'Text generation via Perplexity Sonar chat completions',
  '{RHUMB_CREDENTIAL_PERPLEXITY_API_KEY}',
  'POST',
  '/chat/completions',
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
