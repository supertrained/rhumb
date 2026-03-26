-- Fix: Algolia api_domain was null, causing managed execution to crash with 503.
-- The domain includes the application ID as a subdomain.
UPDATE services
SET api_domain = '80LYFTF37Y-dsn.algolia.net'
WHERE slug = 'algolia' AND (api_domain IS NULL OR api_domain = '');
