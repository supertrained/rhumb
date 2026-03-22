-- Migration 0059: Capability expansion Day 15
-- 8 new capabilities across 2 new domains: cache, network
-- cache: stateless key-value store ops (upstash, redis cloud, momento)
-- network: utility lookups (whois, dns, ip-check) — stateless, no auth context needed

BEGIN;

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================
INSERT INTO capabilities (id, domain, description, status) VALUES
  -- Cache (3)
  ('cache.get',         'cache',   'Read a value from a key-value cache',                'active'),
  ('cache.set',         'cache',   'Write a key-value pair to a cache with optional TTL','active'),
  ('cache.delete',      'cache',   'Delete one or more keys from a cache',               'active'),
  -- Network utilities (5)
  ('network.whois',     'network', 'Look up WHOIS registration data for a domain or IP', 'active'),
  ('network.dns_lookup','network', 'Resolve DNS records for a domain',                   'active'),
  ('network.ip_check',  'network', 'Validate and classify an IP address',                'active'),
  ('network.ping',      'network', 'Check reachability / uptime of a host or URL',       'active'),
  ('network.ssl_check', 'network', 'Inspect TLS/SSL certificate details for a domain',   'active')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- PROVIDER MAPPINGS
-- ============================================================

-- cache.get
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('cache.get', 'upstash',     '{byo,rhumb_managed}', 'api_key', 'GET /get/{key}',            'PROXY-CALLABLE — live Upstash credential (Tester vault). Serverless Redis. Free: 10K commands/day.'),
  ('cache.get', 'redis-cloud', '{byo}',               'api_key', 'GET /get/{key}',            'Redis Cloud REST API. 30 MB free database.'),
  ('cache.get', 'momento',     '{byo}',               'api_key', 'GET /cache/{cacheName}/{key}', 'Serverless cache. 5 GB transfer/mo free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- cache.set
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('cache.set', 'upstash',     '{byo,rhumb_managed}', 'api_key', 'POST /set/{key}/{value}',        'PROXY-CALLABLE — live Upstash credential.'),
  ('cache.set', 'redis-cloud', '{byo}',               'api_key', 'POST /set',                      'Redis Cloud REST API.'),
  ('cache.set', 'momento',     '{byo}',               'api_key', 'PUT /cache/{cacheName}/{key}',   'Serverless cache, TTL supported.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- cache.delete
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('cache.delete', 'upstash',     '{byo,rhumb_managed}', 'api_key', 'POST /del/{key}',              'PROXY-CALLABLE — live Upstash credential.'),
  ('cache.delete', 'redis-cloud', '{byo}',               'api_key', 'POST /del',                    'Redis Cloud REST API.'),
  ('cache.delete', 'momento',     '{byo}',               'api_key', 'DELETE /cache/{cacheName}/{key}', 'Serverless cache.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- network.whois
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('network.whois', 'whoisxml',  '{byo}', 'api_key', 'GET /whoisserver/WhoisService',  'WhoisXML API. 500 queries/mo free.'),
  ('network.whois', 'ipwhois',   '{byo}', 'api_key', 'GET /json/{ip}',                 'IP WHOIS via ipwhois.io. Free tier available.'),
  ('network.whois', 'abstractapi','{byo}','api_key', 'GET /whois',                     'Abstract API WHOIS. 1K requests/mo free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- network.dns_lookup
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('network.dns_lookup', 'whoisxml',   '{byo}', 'api_key', 'GET /dns-lookup',                  'DNS record lookup. 500 queries/mo free.'),
  ('network.dns_lookup', 'cloudflare', '{byo}', 'api_key', 'GET /dns-query?name={d}&type={t}', 'Cloudflare DNS-over-HTTPS. No key required for public DNS.'),
  ('network.dns_lookup', 'google-dns', '{byo}', 'api_key', 'GET /resolve?name={d}&type={t}',   'Google DNS-over-HTTPS. Public, no key required.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- network.ip_check
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('network.ip_check', 'ipinfo',     '{byo,rhumb_managed}', 'bearer_token', 'GET /lite/{ip}',    'PROXY-CALLABLE — live IPinfo credential. Validates + classifies IP.'),
  ('network.ip_check', 'abstractapi','{byo}',               'api_key',      'GET /check',        'IP validation + geolocation.'),
  ('network.ip_check', 'ipqualityscore','{byo}',            'api_key',      'GET /json/{key}/{ip}','Fraud score + proxy/VPN detection. 5K lookups/mo free.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- network.ping
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('network.ping', 'freshping',   '{byo}', 'api_key', 'POST /checks',              'Freshping uptime checks. 50 checks free.'),
  ('network.ping', 'statuscake',  '{byo}', 'api_key', 'POST /v1/uptime',           'StatusCake uptime monitoring. 10 checks free.'),
  ('network.ping', 'hyperping',   '{byo}', 'api_key', 'POST /monitors',            'Hyperping. Free tier available.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- network.ssl_check
INSERT INTO provider_capability_mappings (capability_id, provider_id, credential_mode, auth_type, endpoint_pattern, notes) VALUES
  ('network.ssl_check', 'sslmate',    '{byo}', 'api_key', 'GET /api/v1/cert/issuance',    'SSLMate cert search. Free tier.'),
  ('network.ssl_check', 'whoisxml',   '{byo}', 'api_key', 'GET /ssl-certificates/v1',     'WhoisXML SSL lookup.'),
  ('network.ssl_check', 'ssllabs',    '{byo}', 'none',    'GET /analyze?host={domain}',   'Qualys SSL Labs public API. No key required.')
ON CONFLICT (capability_id, provider_id) DO NOTHING;

-- ============================================================
-- Note: cache.get/set/delete mapped to upstash as rhumb_managed
-- Upstash credential exists in 1Password (Tester - Upstash)
-- network.ip_check also mapped to ipinfo as rhumb_managed (live credential)
-- ============================================================

-- Running total: ~219 capabilities, ~697 mappings
COMMIT;
