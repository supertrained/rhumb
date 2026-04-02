# Discovery expansion — maps II

Date: 2026-04-02
Owner: Pedro / Keel runtime review loop

## Why this category

Live production still shows **`maps`** at only **5 providers**.

That is too thin for a category agents hit constantly:
- place search before booking, outreach, or logistics actions
- address cleanup and normalization before enrichment or delivery workflows
- reverse geocoding to explain coordinates in human terms
- routing and travel-time estimation before real-world scheduling decisions
- territory and proximity checks for support, sales, and operations workflows

Rhumb already had first-wave maps coverage (`google-maps`, `google-places`, `mapbox`, `here-maps`, `geoapify`), but it was still missing several important API-backed mapping and geospatial surfaces developers actually use.

## Added services

### 1. TomTom
- Slug: `tomtom`
- Score: **8.55**
- Execution: **8.70**
- Access readiness: **8.25**
- Why it made the cut:
  - clean Search API with forward geocoding, reverse geocoding, and place search on one coherent surface
  - strategically important global mapping/search provider with real operator relevance

### 2. Geocodio
- Slug: `geocodio`
- Score: **8.35**
- Execution: **8.35**
- Access readiness: **8.30**
- Why it made the cut:
  - excellent developer ergonomics for address normalization and U.S./Canada geocoding
  - strong practical value for CRM cleanup, enrichment, and logistics prep workflows

### 3. OpenRouteService
- Slug: `openrouteservice`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **8.00**
- Why it made the cut:
  - meaningful open geospatial and routing depth beyond commercial map stacks
  - useful API primitives for directions, matrices, isochrones, and geocoding

### 4. TravelTime
- Slug: `traveltime`
- Score: **8.15**
- Execution: **8.40**
- Access readiness: **7.80**
- Why it made the cut:
  - differentiated travel-time and catchment-analysis primitives that matter for real-world planning
  - strong fit for territory, delivery-window, and location-decision workflows

### 5. Positionstack
- Slug: `positionstack`
- Score: **7.95**
- Execution: **8.00**
- Access readiness: **7.90**
- Why it made the cut:
  - straightforward lightweight geocoding API with low integration complexity
  - useful long-tail coverage for teams that want simple REST geocoding instead of a full map platform

## Phase 0 capability assessment

All five additions expose accessible APIs and are viable Resolve candidates.

### Strongest candidates for Resolve capability addition
1. **TomTom**
2. **Geocodio**
3. **OpenRouteService**
4. **TravelTime**

### Candidate capability shapes
- `geocode.forward`
- `geocode.reverse`
- `place.search`
- `route.directions`
- `route.matrix`
- `route.travel_time`

### Best initial Phase 0 wedge
The cleanest first move is:
- `geocode.forward`
- `geocode.reverse`
- `place.search`

Why:
- these are high-frequency, read-first location checks with obvious agent value
- they are safer and easier to normalize honestly than route mutation, fleet dispatch, or geofence-management writes
- they help agents ground real-world entities before acting in downstream systems
- **TomTom** is the best first provider target because its Search API covers all three primitives on one stable developer-facing REST surface

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0150_maps_expansion_ii.sql`

## Verdict

Maps is still underrepresented for a category this central to real-world agent workflows. This batch adds five credible API-backed providers and sharpens the next honest Resolve wedge around **read-first geocoding and place search**, with **TomTom** as the best first implementation target.
