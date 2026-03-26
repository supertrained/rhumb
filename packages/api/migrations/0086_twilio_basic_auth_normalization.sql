-- Migration 0086: normalize Twilio capability auth metadata
-- Twilio uses account SID + auth token (basic auth), not bearer/api key auth.
-- Some legacy capability_services rows still advertise api_key, which makes
-- credential-modes lie about setup status and env var naming.

begin;

update capability_services
set auth_method = 'basic_auth'
where service_slug = 'twilio'
  and coalesce(auth_method, '') <> 'basic_auth';

commit;
