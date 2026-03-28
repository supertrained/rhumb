-- Migration 0111: Emailable managed execution wiring
--
-- Goal:
--   Ship the next clean blocked-safe execution wedge while Airship proof remains
--   credential/audience blocked: Emailable single-email verification plus honest
--   batch creation wiring.
--
-- Notes:
--   - email.verify maps to GET /v1/verify and returns Emailable's structured
--     verification payload.
--   - email.batch_verify maps to POST /v1/batch and honestly returns batch
--     creation / job-state primitives. It does NOT pretend batch results are
--     immediately available without a follow-up status read.

BEGIN;

UPDATE services
SET api_domain = 'api.emailable.com',
    updated_at = now()
WHERE slug = 'emailable'
  AND api_domain IS DISTINCT FROM 'api.emailable.com';

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
  default_headers
)
VALUES
  (
    'email.verify',
    'emailable',
    'Single-email verification via Emailable',
    '{RHUMB_CREDENTIAL_EMAILABLE_API_KEY}',
    'GET',
    '/v1/verify',
    '{}'
  ),
  (
    'email.batch_verify',
    'emailable',
    'Batch email verification job creation via Emailable',
    '{RHUMB_CREDENTIAL_EMAILABLE_API_KEY}',
    'POST',
    '/v1/batch',
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
