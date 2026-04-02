BEGIN;

-- Migration 0150: Maps discovery expansion II (2026-04-02)
-- Rationale: live production still shows maps as an underrepresented,
-- high-demand category even though agents routinely need place search,
-- address normalization, reverse geocoding, route estimation, and
-- travel-time context before taking real-world actions.
-- Add five more API-backed mapping/location surfaces and note the
-- cleanest Phase 0 Resolve wedge.

INSERT INTO services (slug, name, category, description, official_docs, api_domain)
VALUES
  (
    'tomtom',
    'TomTom',
    'maps',
    'Mapping and search platform with APIs for place search, forward and reverse geocoding, routing, traffic-aware navigation, and mobility workflows across consumer and operational applications.',
    'https://developer.tomtom.com/search-api/documentation/search-service/fuzzy-search',
    'api.tomtom.com'
  ),
  (
    'geocodio',
    'Geocodio',
    'maps',
    'Geocoding API for U.S. and Canadian addresses with forward and reverse geocoding, rooftop-accuracy normalization, congressional districts, time zones, and location enrichment workflows.',
    'https://www.geocod.io/docs/',
    'api.geocod.io'
  ),
  (
    'openrouteservice',
    'OpenRouteService',
    'maps',
    'Open routing and geospatial API with endpoints for directions, isochrones, matrices, geocoding, optimization, and map-oriented planning workflows.',
    'https://giscience.github.io/openrouteservice/api-reference/endpoints/',
    'api.openrouteservice.org'
  ),
  (
    'traveltime',
    'TravelTime',
    'maps',
    'Travel-time and routing API for journey-time calculation, isochrones, time-filter search, and location-decision workflows across logistics, commerce, and real-world planning.',
    'https://docs.traveltime.com/api/reference/',
    'api.traveltimeapp.com'
  ),
  (
    'positionstack',
    'Positionstack',
    'maps',
    'REST geocoding service for forward and reverse address lookup, coordinate normalization, batch geocoding, and lightweight map/search enrichment workflows.',
    'https://positionstack.com/documentation',
    'api.positionstack.com'
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
    'tomtom',
    8.55,
    8.70,
    8.25,
    0.69,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"maps expansion ii","phase0_assessment":"Best immediate Resolve candidate in the batch because TomTom Search API covers forward geocoding, reverse geocoding, and place search on a clean REST surface with high real-world demand.","notes":"Strong market presence, broad map/search coverage, and a practical read-first path for normalized geocode.forward / geocode.reverse / place.search capabilities."}'::jsonb,
    now()
  ),
  (
    'geocodio',
    8.35,
    8.35,
    8.30,
    0.66,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"maps expansion ii","phase0_assessment":"Excellent follow-on Phase 0 target for address normalization and geocode.forward where U.S./Canada coverage matters more than broad global mapping.","notes":"Very clean developer ergonomics and strong operational usefulness for CRM cleanup, enrichment, logistics prep, and location-aware support workflows."}'::jsonb,
    now()
  ),
  (
    'openrouteservice',
    8.20,
    8.35,
    8.00,
    0.63,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"maps expansion ii","phase0_assessment":"Strong later Resolve candidate once the base geocoding lane is live, especially for route.matrix / route.directions / isochrone-style planning workflows.","notes":"Important open geospatial surface with practical routing and geocoding APIs for infrastructure-heavy or cost-sensitive teams."}'::jsonb,
    now()
  ),
  (
    'traveltime',
    8.15,
    8.40,
    7.80,
    0.62,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"maps expansion ii","phase0_assessment":"High-value second-wave Resolve target for route.travel_time and catchment analysis once the simpler geocode/place-search lane is normalized.","notes":"Distinctive travel-time primitives make it strategically useful for real-world planning, territory analysis, delivery windows, and location intelligence."}'::jsonb,
    now()
  ),
  (
    'positionstack',
    7.95,
    8.00,
    7.90,
    0.58,
    'L3',
    'Ready',
    '{"source":"pedro-keel-discovery-2026-04-02","category_rationale":"maps expansion ii","phase0_assessment":"Credible lightweight Phase 0 candidate for forward/reverse geocoding where teams want a simpler standalone geocoder rather than a full mapping platform.","notes":"Useful catalog-depth addition with straightforward REST semantics, even if it is not as strategically broad as TomTom or as differentiated as TravelTime."}'::jsonb,
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
