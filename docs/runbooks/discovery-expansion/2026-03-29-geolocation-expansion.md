# Discovery expansion — geolocation

Date: 2026-03-29
Owner: Pedro / Keel runtime review loop

## Why this category

Geolocation is still underrepresented relative to how often agents need it.

Current live depth before this batch was only **5** providers:
- `ipinfo`
- `maxmind`
- `radar`
- `here-api`
- `ipstack`

That is too thin for a category agents regularly use for:
- IP-to-location enrichment
- timezone-aware scheduling and routing
- support localization
- fraud / risk / compliance checks
- region-aware personalization
- ASN / carrier / network context in operations workflows

## Added services

### 1. IPregistry
- Slug: `ipregistry`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **8.05**
- Why it made the cut:
  - broad IP intelligence surface beyond just country/city lookup
  - strong ASN, company, and threat-context follow-on potential
  - best immediate normalization target in the batch

### 2. IP2Location
- Slug: `ip2location`
- Score: **8.05**
- Execution: **8.20**
- Access readiness: **7.90**
- Why it made the cut:
  - practical country / city / timezone / ASN enrichment surface
  - strong fit for agent workflows that need deterministic geo and network context

### 3. ipapi
- Slug: `ipapi`
- Score: **8.00**
- Execution: **8.10**
- Access readiness: **7.90**
- Why it made the cut:
  - low-friction IP lookup path with useful timezone and localization data
  - especially good for fast read-first agent integrations

### 4. BigDataCloud
- Slug: `bigdatacloud`
- Score: **7.95**
- Execution: **8.05**
- Access readiness: **7.85**
- Why it made the cut:
  - useful geo-context and locality data around simple IP lookups
  - credible complement to the more network-centric vendors in the batch

### 5. DB-IP
- Slug: `db-ip`
- Score: **7.85**
- Execution: **7.95**
- Access readiness: **7.75**
- Why it made the cut:
  - practical ISP / ASN / city-country enrichment utility
  - improves category depth for support, fraud, and localization workflows

## Phase 0 capability assessment

### Services with accessible APIs
All five added services expose accessible APIs.

Strongest early Resolve targets:
1. **IPregistry**
2. **IP2Location**
3. **ipapi**
4. **BigDataCloud**

### Candidate capability shapes
- `network.ip_geolocate`
- `timezone.lookup`
- `network.asn_lookup`
- `network.company_lookup`

### Best initial Phase 0 wedge
The cleanest first move is:
- `network.ip_geolocate`
- `timezone.lookup`

Why:
- both are read-first and broadly reusable across support, fraud, routing, and personalization
- they normalize cleanly across the added providers
- they create a natural follow-on path into ASN, company, and threat-intelligence enrichments
- **IPregistry** is the best first provider target because it exposes a strong structured IP lookup surface with the richest follow-on metadata in the batch

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0118_geolocation_expansion.sql`

## Verdict

Geolocation depth was thinner than the demand pattern warrants. This batch materially improves Rhumb’s discovery surface for geo-aware agent workflows, and **IPregistry is now the clearest next Phase 0 target** when the geolocation capability lane opens.
