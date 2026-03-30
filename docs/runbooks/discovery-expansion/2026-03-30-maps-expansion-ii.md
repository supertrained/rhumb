# Discovery expansion — maps II

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop

## Why this category

Maps is still a thin but high-demand category in the live catalog.

Even after prior expansion work in-repo, current live coverage is still shallow relative to how often agents need:
- forward and reverse geocoding
- route computation and ETA lookups
- distance matrix queries
- isochrones / travel-time search
- nearby place and store-location workflows
- logistics, dispatch, field-ops, and territory planning

That makes maps a good continued expansion lane instead of a one-and-done batch.

## Added services

### 1. NextBillion.ai
- Slug: `nextbillion`
- Score: **8.30**
- Execution: **8.50**
- Access readiness: **8.10**
- Why it made the cut:
  - broad geocode + routing + matrix + optimization surface
  - strongest immediate Phase 0 candidate in the batch
  - especially relevant for delivery, dispatch, and mobility workflows

### 2. GraphHopper
- Slug: `graphhopper`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **8.00**
- Why it made the cut:
  - clear directions, matrix, optimization, and geocoding APIs
  - practical operator value for route and matrix normalization

### 3. TravelTime
- Slug: `traveltime`
- Score: **8.10**
- Execution: **8.20**
- Access readiness: **7.95**
- Why it made the cut:
  - distinct isochrone and time-filter surface
  - expands Rhumb beyond generic routing into commute/time-aware location logic

### 4. OpenRouteService
- Slug: `openrouteservice`
- Score: **7.95**
- Execution: **8.10**
- Access readiness: **7.80**
- Why it made the cut:
  - strong open-data routing + matrix + isochrone coverage
  - useful for accessibility, route planning, and spatial decision workflows

### 5. Woosmap
- Slug: `woosmap`
- Score: **7.85**
- Execution: **7.95**
- Access readiness: **7.75**
- Why it made the cut:
  - meaningful nearby-search, distance, journey, and store-locator depth
  - broadens maps beyond generic developer geocoding toward operational retail search

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose documented APIs.

Strongest near-term Resolve targets:
1. **NextBillion.ai**
2. **GraphHopper**
3. **TravelTime**

### Candidate capability shapes
- `maps.geocode_forward`
- `maps.geocode_reverse`
- `route.compute`
- `route.matrix`
- `maps.isochrone`
- `places.search_nearby`

### Best initial Phase 0 wedge
The cleanest first move is still a read-first maps lane:
- `maps.geocode_forward`
- `maps.geocode_reverse`
- `route.compute`

Why:
- they are broadly useful across support, logistics, delivery, and field workflows
- they normalize well across the new providers
- they create a natural follow-on path into matrix and isochrone capabilities

**Best first provider target: `nextbillion`**
- broadest practical surface in the batch
- explicit route / matrix / optimization primitives
- strongest fit for real operational agent workflows rather than demo-only map search

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0121_maps_expansion_ii.sql`

## Verdict

Maps still deserves more depth than the live catalog currently shows. This batch adds five concrete, API-backed providers and sharpens the next credible Phase 0 wedge around **geocode + route** capabilities, with **NextBillion.ai** now the strongest next provider candidate.
