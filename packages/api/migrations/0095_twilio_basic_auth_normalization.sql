-- Migration 0095: normalize Twilio capability auth metadata
-- Twilio uses account SID + auth token (basic auth), not bearer/api key auth.
-- Some legacy capability_services rows still advertise api_key, which makes
-- credential-modes lie about setup status and env var naming.

BEGIN;

UPDATE capability_services
SET auth_method = 'basic_auth'
WHERE service_slug = 'twilio'
  AND COALESCE(auth_method, '') <> 'basic_auth';

COMMIT;
