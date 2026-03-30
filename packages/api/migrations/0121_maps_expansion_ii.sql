BEGIN;

-- Migration 0121: Maps discovery expansion II (2026-03-30)
-- Rationale: live maps coverage is still thin relative to how often agents need
-- geocoding, routing, ETA, isochrone, territory planning, and delivery-aware
-- place search. Add five more API-backed mapping vendors with strong route,
-- matrix, and travel-time surfaces plus a clear Phase 0 read-first wedge.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'nextbillion',
    'NextBillion.ai',
    'maps',
    'Location and mobility API platform with geocoding, routing, distance matrix, optimization, navigation, and fleet-oriented mapping primitives suitable for logistics, dispatch, and field-ops automation.',
    'https://docs.nextbillion.ai/',
    'api.nextbillion.io'
  ),
  (
    'traveltime',
    'TravelTime',
    'maps',
    'Travel-time intelligence API focused on isochrones, route-time search, time-filter queries, and commute-aware location analysis for planning and geo-decision workflows.',
    'https://docs.traveltime.com/api/reference/',
    'api.traveltimeapp.com'
  ),
  (
    'graphhopper',
    'GraphHopper',
    'maps',
    'Routing and geocoding platform with directions, matrix, optimization, map-matching, and geocoding APIs that fit delivery, routing, and navigation-heavy agent workflows.',
    'https://docs.graphhopper.com/',
    'graphhopper.com'
  ),
  (
    'openrouteservice',
    'OpenRouteService',
    'maps',
    'OpenStreetMap-based routing platform with directions, matrix, isochrones, geocoding, and elevation APIs for route planning, accessibility, and spatial decision automation.',
    'https://giscience.github.io/openrouteservice/api-reference/',
    'api.openrouteservice.org'
  ),
  (
    'woosmap',
    'Woosmap',
    'maps',
    'Location-search and store-locator platform with search, distance, geofencing, and journey APIs that support nearby-place lookup, retail ops, and geo-aware customer experiences.',
    'https://developers.woosmap.com/products/',
    'api.woosmap.com'
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
    'nextbillion',
    8.30,
    8.50,
    8.10,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"maps expansion ii","notes":"Best Phase 0 candidate in the batch. NextBillion exposes clean geocode, directions, matrix, optimization, and nearby-search style surfaces that map well to future route.calculate, geocode.forward, geocode.reverse, and places.nearby contracts."}'::jsonb,
    now()
  ),
  (
    'graphhopper',
    8.20,
    8.35,
    8.00,
    0.64,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"maps expansion ii","notes":"Strong operator utility across directions, matrix, optimization, and geocoding with straightforward HTTP surfaces. Good second Phase 0 lane after NextBillion for route and matrix primitives."}'::jsonb,
    now()
  ),
  (
    'traveltime',
    8.10,
    8.20,
    7.95,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"maps expansion ii","notes":"Distinctive travel-time and isochrone API surface gives Rhumb better coverage for commute-aware search and territory planning. Excellent candidate for future isochrone and time-filter capabilities even if it is less general-purpose than the route leaders."}'::jsonb,
    now()
  ),
  (
    'openrouteservice',
    7.95,
    8.10,
    7.80,
    0.60,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"maps expansion ii","notes":"Valuable open-data routing and isochrone coverage with practical agent utility for route planning, accessibility, and map-based workflow automation. Slightly lower access readiness than the leaders but still strong catalog depth."}'::jsonb,
    now()
  ),
  (
    'woosmap',
    7.85,
    7.95,
    7.75,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-03-30","category_rationale":"maps expansion ii","notes":"Strong retail and store-locator oriented location surface with search, distance, and journey APIs. Useful category breadth for nearby-place lookup and geo-aware customer experience workflows even if less universal than the route-first providers."}'::jsonb,
    now()
  )
ON CONFLICT (service_slug) DO UPDATE SET
  aggregate_recommendation_score = EXCLUDED.aggregate_recommendation_score,
  execution_score = EXCLUDED.execution_score,
  access_readiness_score = EXCLUDED.access_readiness_score,
  confidence = EXCLUDED.confidence,
  tier = EXCLUDED.tier,
  tier_label = EXCLUDED.tier_label,
  probe_metadata = EXCLUDED.probe_metadata,
  calculated_at = EXCLUDED.calculated_at;

COMMIT;
