-- Migration 0099: Sync Unstructured capability_services with rhumb_managed_capabilities
-- Bug: document.parse existed in rhumb_managed_capabilities but not capability_services,
-- causing _get_capability_services() to return empty → 503 "No providers configured".
-- Also syncs document.extract (in capability_services but not managed).

-- Add document.parse to capability_services (was missing → 503 on estimate/execute)
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern)
VALUES ('document.parse', 'unstructured', '{byo,rhumb_managed}', 'api_key', 'POST /general/v0/general')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_modes = EXCLUDED.credential_modes,
  endpoint_pattern = EXCLUDED.endpoint_pattern,
  updated_at = now();

-- Ensure all existing Unstructured capability_services entries include rhumb_managed
UPDATE capability_services
SET credential_modes = '{byo,rhumb_managed}',
    endpoint_pattern = COALESCE(endpoint_pattern, 'POST /general/v0/general'),
    updated_at = now()
WHERE service_slug = 'unstructured'
  AND NOT (credential_modes @> '{rhumb_managed}');

-- Add document.extract to rhumb_managed_capabilities (was missing from managed side)
INSERT INTO rhumb_managed_capabilities (capability_id, service_slug, description, credential_env_keys, default_method, default_path, default_headers)
VALUES ('document.extract', 'unstructured', 'Document extraction via Unstructured', '{RHUMB_CREDENTIAL_UNSTRUCTURED_API_KEY}', 'POST', '/general/v0/general', '{}')
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  credential_env_keys = EXCLUDED.credential_env_keys,
  updated_at = now();
