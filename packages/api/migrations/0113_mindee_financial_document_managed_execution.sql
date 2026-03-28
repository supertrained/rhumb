-- Migration 0113: Mindee financial-document managed execution wiring
--
-- Goal:
--   Ship the next honest document-processing execution wedge now that the
--   telemetry → dogfood → Google AI → callable-review sequence is complete and
--   the current top execution lanes remain blocked outside code.
--
-- Notes:
--   - This slice intentionally starts with Mindee's legacy financial-document
--     predict endpoint because it provides a concrete, synchronous extraction
--     contract without inventing asynchronous job semantics.
--   - Managed execution expects a multipart `document` upload. The executor
--     accepts logical aliases like `file`/`files` but normalizes them to the
--     provider-native `document` field.
--   - Success means Mindee accepted and processed the uploaded document through
--     the financial-document model. It does not claim universal document-model
--     coverage beyond what Mindee actually returns.

BEGIN;

UPDATE services
SET api_domain = 'api.mindee.net',
    updated_at = now()
WHERE slug = 'mindee'
  AND api_domain IS DISTINCT FROM 'api.mindee.net';

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome)
VALUES
  (
    'document.extract_fields',
    'document',
    'extract_fields',
    'Extract structured fields from a business document using Mindee financial-document parsing',
    'document/file upload descriptor plus optional provider flags like include_mvision',
    'Structured provider extraction payload for the uploaded financial document'
  ),
  (
    'invoice.extract',
    'invoice',
    'extract',
    'Extract invoice-style fields from an uploaded document using Mindee financial-document parsing',
    'document/file upload descriptor plus optional provider flags like include_mvision',
    'Structured provider extraction payload for the uploaded invoice or financial document'
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
    'document.extract_fields',
    'mindee',
    '{byo,rhumb_managed}',
    'api_key',
    'POST /v1/products/mindee/financial_document/v1/predict',
    'PROXY-CALLABLE — Mindee financial-document parsing via multipart `document` upload and Token auth. Phase 0 intentionally returns Mindee''s provider-native extraction payload rather than pretending to normalize every extracted field.',
    true
  ),
  (
    'invoice.extract',
    'mindee',
    '{byo,rhumb_managed}',
    'api_key',
    'POST /v1/products/mindee/financial_document/v1/predict',
    'PROXY-CALLABLE — Mindee financial-document parsing for invoice-style extraction via multipart `document` upload and Token auth. Phase 0 keeps provider-native output truth instead of flattening it into a fake universal invoice schema.',
    true
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
    'document.extract_fields',
    'mindee',
    'Mindee financial-document extraction via multipart document upload',
    '{RHUMB_CREDENTIAL_MINDEE_API_KEY}',
    'POST',
    '/v1/products/mindee/financial_document/v1/predict',
    '{}'
  ),
  (
    'invoice.extract',
    'mindee',
    'Mindee invoice extraction via multipart document upload',
    '{RHUMB_CREDENTIAL_MINDEE_API_KEY}',
    'POST',
    '/v1/products/mindee/financial_document/v1/predict',
    '{}'
  )
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  description = EXCLUDED.description,
  credential_env_keys = EXCLUDED.credential_env_keys,
  default_method = EXCLUDED.default_method,
  default_path = EXCLUDED.default_path,
  default_headers = EXCLUDED.default_headers,
  updated_at = now();

COMMIT;
