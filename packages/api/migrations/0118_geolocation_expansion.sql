BEGIN;

-- Migration 0118: Geolocation discovery expansion (2026-03-29)
-- Rationale: geolocation is still a thin but high-demand operational category
-- for agents doing IP enrichment, fraud/risk checks, support localization,
-- timezone routing, and geo-aware personalization. Add five API-backed
-- providers with clear Phase 0 normalization potential around IP lookup.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'ipregistry',
    'IPregistry',
    'geolocation',
    'IP intelligence API covering geolocation, ASN, company, threat, and network metadata for fraud checks, localization, routing, and compliance-aware automation.',
    'https://ipregistry.co/docs/',
    'api.ipregistry.co'
  ),
  (
    'ip2location',
    'IP2Location',
    'geolocation',
    'IP geolocation and network intelligence platform with country, region, ASN, proxy, and company data suitable for routing, geo-enrichment, and trust decisions.',
    'https://www.ip2location.io/ip2location-documentation',
    'api.ip2location.io'
  ),
  (
    'ipapi',
    'ipapi',
    'geolocation',
    'Simple IP address intelligence API for country, city, timezone, currency, and carrier lookup with a low-friction read path for support and personalization workflows.',
    'https://ipapi.com/documentation',
    'api.ipapi.com'
  ),
  (
    'bigdatacloud',
    'BigDataCloud',
    'geolocation',
    'Geolocation and reverse-geocode API set with timezone, locality, and network-aware lookup surfaces useful for region routing, localization, and geo-context automation.',
    'https://www.bigdatacloud.com/docs/api',
    'api.bigdatacloud.net'
  ),
  (
    'db-ip',
    'DB-IP',
    'geolocation',
    'IP geolocation API focused on country, city, ASN, and ISP metadata for lookup-heavy support, fraud screening, and geo-aware product logic.',
    'https://db-ip.com/api/',
    'api.db-ip.com'
  )
ON CONFLICT (slug) DO NOTHING;

INSERT INTO scores (
  service_slug,
  aggregate_recommendation_score,
  execution_score,
  access_readiness_score,
  confidence,
  tier,
  tier_label,
  probe_metadata,
  calculated_at
)
VALUES
  (
    'ipregistry',
    8.20,
    8.35,
    8.05,
    0.65,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"geolocation expansion","notes":"Best first Phase 0 target in the batch. Clean IP lookup surface plus richer ASN/company/threat metadata creates a strong normalization path from simple geolocation into deeper network intelligence."}'::jsonb,
    now()
  ),
  (
    'ip2location',
    8.05,
    8.20,
    7.90,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"geolocation expansion","notes":"Strong operator utility for country/city/timezone/ASN enrichment with a clear read-first Phase 0 wedge. Good second provider after IPregistry."}'::jsonb,
    now()
  ),
  (
    'ipapi',
    8.00,
    8.10,
    7.90,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"geolocation expansion","notes":"Low-friction IP lookup surface with practical timezone and localization fields. Especially useful for fast Phase 0 read-path coverage."}'::jsonb,
    now()
  ),
  (
    'bigdatacloud',
    7.95,
    8.05,
    7.85,
    0.59,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"geolocation expansion","notes":"Good geo-context provider with locality and timezone depth that complements pure IP lookup vendors. Credible fit for geo-aware support and routing workflows."}'::jsonb,
    now()
  ),
  (
    'db-ip',
    7.85,
    7.95,
    7.75,
    0.57,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"geolocation expansion","notes":"Useful read-first IP enrichment option with practical ISP and ASN metadata. Slightly less differentiated than the leaders but still meaningful category depth."}'::jsonb,
    now()
  );

COMMIT;
