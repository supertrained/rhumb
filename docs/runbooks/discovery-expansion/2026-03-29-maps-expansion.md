# Discovery expansion — maps

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop

## Why this category

Maps is still underrepresented in the live catalog relative to how often agents need it.

Current live depth is only **5** providers:
- `geoapify`
- `google-maps`
- `google-places`
- `here-maps`
- `mapbox`

That is thin for a category agents routinely need for:
- forward and reverse geocoding
- nearby place search
- address normalization
- routing and ETA-aware planning
- delivery, field-work, and territory workflows
- local search enrichment for support and operations

## Added services

### 1. TomTom Maps
- Slug: `tomtom-maps`
- Score: **8.25**
- Execution: **8.45**
- Access readiness: **8.05**
- Why it made the cut:
  - broad, explicit Search + Routing + Geocoding API surface
  - strongest immediate normalization target in the batch
  - high operator value for delivery, dispatch, and location-aware automation

### 2. MapTiler
- Slug: `maptiler`
- Score: **8.10**
- Execution: **8.25**
- Access readiness: **7.90**
- Why it made the cut:
  - credible modern geocoding and map infrastructure surface
  - useful follow-on provider after TomTom for map lookup and static-map workflows

### 3. LocationIQ
- Slug: `locationiq`
- Score: **8.00**
- Execution: **8.15**
- Access readiness: **7.85**
- Why it made the cut:
  - practical geocoding, autocomplete, and routing APIs
  - good fit for product teams that need lightweight map automation fast

### 4. OpenCage
- Slug: `opencage`
- Score: **7.90**
- Execution: **8.00**
- Access readiness: **7.80**
- Why it made the cut:
  - strong global geocoding utility on top of open geographic data
  - especially useful for address normalization and reverse-geocode workflows

### 5. Loqate
- Slug: `loqate`
- Score: **7.85**
- Execution: **8.05**
- Access readiness: **7.55**
- Why it made the cut:
  - meaningful address capture and validation depth for commerce and logistics flows
  - expands Rhumb beyond generic map tiles into real operational address intelligence

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose documented, accessible APIs.

Strongest early Resolve targets:
1. **TomTom Maps**
2. **MapTiler**
3. **LocationIQ**
4. **OpenCage**

Loqate is strategically useful, but it is slightly more address-validation shaped than the cleanest first normalized maps wedge.

### Candidate capability shapes
- `maps.geocode_forward`
- `maps.geocode_reverse`
- `places.search_text`
- `route.compute`
- `map.static_image`

### Best initial Phase 0 wedge
The cleanest first move is:
- `maps.geocode_forward`
- `maps.geocode_reverse`
- `places.search_text`

Why:
- they are read-first and broadly reusable across support, field ops, and product workflows
- they normalize cleanly across the added providers
- they create a natural follow-on path into routing and ETA-aware planning
- **TomTom Maps** is the best first provider target because its search, geocode, and routing surfaces are explicit and operator-relevant

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0117_maps_expansion.sql`

## Verdict

Maps depth was too thin for the level of real-world demand. This batch materially improves Rhumb’s discovery surface, and **TomTom Maps is now the clearest next Phase 0 candidate** when the maps capability lane opens.
