-- Migration 0096: refresh Twilio Lookup endpoint metadata
-- Twilio Lookup v2 no longer accepts Fields=carrier. The current supported
-- line-type enrichment field is line_type_intelligence.

BEGIN;

UPDATE capability_services
SET endpoint_pattern = 'GET /v2/PhoneNumbers/{number}?Fields=line_type_intelligence'
WHERE service_slug = 'twilio'
  AND capability_id = 'phone.lookup';

COMMIT;
