-- Migration 0164: Emailable managed visibility repair
--
-- Context: the 2026-04-27 DC90 green-fixture pass found hosted
-- `email.verify` / `emailable` was still absent from the live managed catalog
-- (`provider_not_available`) even though the original 0111 migration defined the
-- managed rail. Re-assert the service, capability-service mapping, and managed
-- config under a fresh migration number so deploy-track migration runners that
-- already skipped/failed older one-off catalog wiring can converge production.

BEGIN;

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES (
  'emailable',
  'Emailable',
  'email-validation',
  'Email verification platform with public API docs for single-address validation, batch processing, webhook-style workflows, and flexible auth via bearer header or API key parameter.',
  'https://emailable.com/docs/api',
  'api.emailable.com'
)
ON CONFLICT (slug) DO UPDATE SET
  name = EXCLUDED.name,
  category = EXCLUDED.category,
  description = EXCLUDED.description,
  official_docs = EXCLUDED.official_docs,
  api_domain = EXCLUDED.api_domain,
  updated_at = now();

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome)
VALUES (
  'email.batch_verify',
  'email',
  'batch_verify',
  'Verify a batch of email addresses and return a provider batch job reference',
  'emails array, optional callback_url/url, optional response_fields, retries',
  'Batch accepted for verification with job or batch identifier'
)
ON CONFLICT (id) DO UPDATE SET
  domain = EXCLUDED.domain,
  action = EXCLUDED.action,
  description = EXCLUDED.description,
  input_hint = EXCLUDED.input_hint,
  outcome = EXCLUDED.outcome,
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
VALUES
  (
    'email.verify',
    'emailable',
    '{byo,rhumb_managed}',
    'api_key',
    'GET /v1/verify',
    'PROXY-CALLABLE — Emailable single-address verification via bearer-auth managed credential. Phase 0 returns provider verification truth directly (deliverable/risky/undeliverable style state, score, and hygiene metadata).',
    false
  ),
  (
    'email.batch_verify',
    'emailable',
    '{byo,rhumb_managed}',
    'api_key',
    'POST /v1/batch',
    'PROXY-CALLABLE — Emailable batch verification job creation. Phase 0 is intentionally honest: success means the batch job was accepted and a batch id was returned, not that results are already available.',
    false
  )
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_modes = EXCLUDED.credential_modes,
  auth_method = EXCLUDED.auth_method,
  endpoint_pattern = EXCLUDED.endpoint_pattern,
  notes = EXCLUDED.notes,
  is_primary = EXCLUDED.is_primary,
  updated_at = now();

INSERT INTO rhumb_managed_capabilities (
  capability_id,
  service_slug,
  description,
  credential_env_keys,
  default_method,
  default_path,
  default_headers,
  enabled
)
VALUES
  (
    'email.verify',
    'emailable',
    'Single-email verification via Emailable',
    '{RHUMB_CREDENTIAL_EMAILABLE_API_KEY}',
    'GET',
    '/v1/verify',
    '{}',
    true
  ),
  (
    'email.batch_verify',
    'emailable',
    'Batch email verification job creation via Emailable',
    '{RHUMB_CREDENTIAL_EMAILABLE_API_KEY}',
    'POST',
    '/v1/batch',
    '{"Content-Type": "application/json"}',
    true
  )
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  description = EXCLUDED.description,
  credential_env_keys = EXCLUDED.credential_env_keys,
  default_method = EXCLUDED.default_method,
  default_path = EXCLUDED.default_path,
  default_headers = EXCLUDED.default_headers,
  enabled = true,
  updated_at = now();

COMMIT;
