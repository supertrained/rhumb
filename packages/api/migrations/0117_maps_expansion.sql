BEGIN;

-- Migration 0117: Maps discovery expansion (2026-03-29)
-- Rationale: maps remains a high-demand operational category for agents doing
-- geocoding, place lookup, routing, territory planning, delivery support, and
-- field-work automation, but Rhumb's live catalog depth is still thin. Add five
-- more API-backed mapping providers and record the cleanest Phase 0 wedge.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'tomtom-maps',
    'TomTom Maps',
    'maps',
    'Mapping and location platform with APIs for geocoding, reverse geocoding, routing, traffic-aware navigation, nearby search, and place-centric operational workflows.',
    'https://developer.tomtom.com/',
    'api.tomtom.com'
  ),
  (
    'locationiq',
    'LocationIQ',
    'maps',
    'Location intelligence API with forward and reverse geocoding, autocomplete, routing, static maps, and polygon-aware place workflows for location-enabled products.',
    'https://docs.locationiq.com/',
    'us1.locationiq.com'
  ),
  (
    'opencage',
    'OpenCage',
    'maps',
    'Global geocoding API built around open geographic data, useful for address normalization, reverse geocoding, timezone lookup, and lightweight location enrichment.',
    'https://opencagedata.com/api',
    'api.opencagedata.com'
  ),
  (
    'maptiler',
    'MapTiler',
    'maps',
    'Developer mapping platform with geocoding, static maps, vector tiles, coordinates APIs, and customizable basemap workflows for agent-facing location products.',
    'https://docs.maptiler.com/cloud/api/',
    'api.maptiler.com'
  ),
  (
    'loqate',
    'Loqate',
    'maps',
    'Address and geolocation platform with APIs for capture, verification, geocoding, and place data, well-suited to checkout, logistics, and field-ops automation.',
    'https://docs.loqate.com/api-reference/',
    'api.addressy.com'
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
    'tomtom-maps',
    8.25,
    8.45,
    8.05,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"maps expansion","notes":"Best initial Phase 0 target in the batch. Search, geocode, and routing surfaces are explicit, widely demanded, and easy to normalize into forward/reverse geocode plus nearby place search."}'::jsonb,
    now()
  ),
  (
    'maptiler',
    8.10,
    8.25,
    7.90,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"maps expansion","notes":"Strong map infrastructure and geocoding surface with good operator utility for location lookup and static-map generation. Clean follow-on after TomTom."}'::jsonb,
    now()
  ),
  (
    'locationiq',
    8.00,
    8.15,
    7.85,
    0.61,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"maps expansion","notes":"Practical geocoding and autocomplete API with good coverage for product teams that need straightforward map search automation without the heaviest enterprise setup."}'::jsonb,
    now()
  ),
  (
    'opencage',
    7.90,
    8.00,
    7.80,
    0.59,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"maps expansion","notes":"Useful global geocoding layer for read-first address normalization and reverse geocode workflows. Less of a full-stack maps surface than TomTom or MapTiler, but high practical demand."}'::jsonb,
    now()
  ),
  (
    'loqate',
    7.85,
    8.05,
    7.55,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-29","category_rationale":"maps expansion","notes":"Strategically valuable for address capture and validation-heavy workflows in commerce, logistics, and field operations, with a credible future path into normalized address and geocode capabilities."}'::jsonb,
    now()
  );

COMMIT;
