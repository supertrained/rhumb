-- Migration 0110: Airship managed execution wiring
--
-- Goal:
--   Ship validation-first Airship execution for Rhumb-managed push sends.
--
-- Notes:
--   - Managed execution defaults to POST /api/push; runtime may swap to
--     /api/push/validate when the caller sets validate_only=true.
--   - Airship acceptance means the request was accepted for validation or
--     processing. It does not imply delivery to a device.
--   - push_topic.publish currently maps logical topic/tag plus
--     tag_group/group/topic_group onto Airship audience.tag + audience.group.

BEGIN;

UPDATE services
SET api_domain = 'go.urbanairship.com',
    updated_at = now()
WHERE slug = 'airship'
  AND api_domain IS DISTINCT FROM 'go.urbanairship.com';

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome)
VALUES
  (
    'push_notification.send',
    'push_notification',
    'send',
    'Send a push notification to an explicit Airship audience',
    'notification or message/alert, audience or channel targeting, device_types, validate_only (optional)',
    'Airship accepts or rejects the push request'
  ),
  (
    'push_notification.send_to_user',
    'push_notification',
    'send_to_user',
    'Send a push notification to an Airship named user',
    'named_user_id, notification or message/alert, device_types, validate_only (optional)',
    'Airship accepts or rejects the user-targeted push request'
  ),
  (
    'push_topic.publish',
    'push_topic',
    'publish',
    'Publish a push notification to an Airship tag group audience',
    'topic/tag, tag_group/group/topic_group, notification or message/alert, device_types, validate_only (optional)',
    'Airship accepts or rejects the tag-group push request'
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
    'push_notification.send',
    'airship',
    '{byo,rhumb_managed}',
    'basic_auth',
    'POST /api/push',
    'VALIDATION-FIRST - Rhumb-managed Airship wiring targets POST /api/push by default and may switch to /api/push/validate when validate_only=true. A 2xx/202 response means Airship accepted the request, not that any device received it.',
    true
  ),
  (
    'push_notification.send_to_user',
    'airship',
    '{byo,rhumb_managed}',
    'basic_auth',
    'POST /api/push',
    'VALIDATION-FIRST - Rhumb-managed Airship wiring maps named_user_id to audience.named_user and uses Airship acceptance semantics only. A successful response means Airship accepted the request for processing or validation.',
    true
  ),
  (
    'push_topic.publish',
    'airship',
    '{byo,rhumb_managed}',
    'basic_auth',
    'POST /api/push',
    'VALIDATION-FIRST - Rhumb-managed Airship wiring maps topic/tag plus tag_group/group/topic_group to audience.tag + audience.group. A successful response means Airship accepted the request; delivery remains downstream of acceptance.',
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
    'push_notification.send',
    'airship',
    'Validation-first push send via Airship push API',
    '{RHUMB_CREDENTIAL_AIRSHIP_BASIC_AUTH}',
    'POST',
    '/api/push',
    '{"Accept": "application/vnd.urbanairship+json; version=3", "Content-Type": "application/json"}'
  ),
  (
    'push_notification.send_to_user',
    'airship',
    'Validation-first named-user push send via Airship push API',
    '{RHUMB_CREDENTIAL_AIRSHIP_BASIC_AUTH}',
    'POST',
    '/api/push',
    '{"Accept": "application/vnd.urbanairship+json; version=3", "Content-Type": "application/json"}'
  ),
  (
    'push_topic.publish',
    'airship',
    'Validation-first tag-group push publish via Airship push API',
    '{RHUMB_CREDENTIAL_AIRSHIP_BASIC_AUTH}',
    'POST',
    '/api/push',
    '{"Accept": "application/vnd.urbanairship+json; version=3", "Content-Type": "application/json"}'
  )
ON CONFLICT (capability_id, service_slug) DO UPDATE SET
  description = EXCLUDED.description,
  credential_env_keys = EXCLUDED.credential_env_keys,
  default_method = EXCLUDED.default_method,
  default_path = EXCLUDED.default_path,
  default_headers = EXCLUDED.default_headers,
  updated_at = now();

COMMIT;
