# Discovery expansion — design

Date: 2026-04-03
Owner: Pedro / Keel runtime review loop

## Why this category

Live production category counts show **`design`** at only **4** providers:
- `framer`
- `lunacy`
- `penpot`
- `sketch-api`

That is too thin for a category agents increasingly need for:
- template-driven image generation for email, social, and reporting
- automated product photo enhancement and background removal
- brand-consistent asset creation at scale
- document and PDF export from design templates
- visual workflow output without human designer involvement

The existing four providers are all UI-first or self-hosted design tools. None of them expose a clean read-first or generate-first API surface suitable for a first Resolve wedge. This batch targets accessible API-backed image and template generation platforms instead.

## Added services

### 1. Bannerbear
- Slug: `bannerbear`
- Score: **8.55**
- Execution: **8.70**
- Access readiness: **8.35**
- Why it made the cut:
  - explicit synchronous image generation API with template + layer override semantics
  - best immediate Phase 0 candidate in the batch
  - API key only, no OAuth friction
  - directly maps to `design.template.render` without normalization gymnastics

### 2. Placid
- Slug: `placid`
- Score: **8.45**
- Execution: **8.55**
- Access readiness: **8.25**
- Why it made the cut:
  - template-driven image AND PDF generation from a single REST API
  - similar layer override model to Bannerbear
  - adds PDF output shape that is absent from Bannerbear
  - strong fit for document generation alongside social/email use cases

### 3. Canva
- Slug: `canva`
- Score: **8.35**
- Execution: **8.45**
- Access readiness: **8.15**
- Why it made the cut:
  - category-defining platform with a real developer API
  - design, brand kit, and export surfaces are all present
  - OAuth 2.0 user consent makes it heavier than Bannerbear as a first managed provider
  - important catalog inclusion for discovery regardless

### 4. PhotoRoom
- Slug: `photoroom`
- Score: **8.25**
- Execution: **8.40**
- Access readiness: **8.05**
- Why it made the cut:
  - AI background removal and product photo editing via a single POST endpoint
  - API key only, extremely accessible
  - orthogonal to template rendering — covers a distinct and high-demand image editing lane
  - best non-template design primitive for ecommerce and content automation

### 5. Frontify
- Slug: `frontify`
- Score: **8.10**
- Execution: **8.20**
- Access readiness: **7.90**
- Why it made the cut:
  - enterprise brand asset management via GraphQL API
  - useful for brand-consistent asset retrieval and design library inspection
  - GraphQL adds normalization complexity versus REST-first providers
  - valuable enterprise catalog depth; better as a later-wave Resolve target

## Phase 0 capability assessment

### Services with accessible APIs
All five expose accessible developer APIs. Bannerbear, Placid, and PhotoRoom use API keys only. Canva requires OAuth. Frontify uses GraphQL with API keys.

### Candidate capability shapes
- `design.template.render` — primary wedge (Bannerbear, Placid)
- `image.edit.background_remove` — orthogonal wedge (PhotoRoom)
- `design.template.list` — read-first enumeration (Bannerbear, Placid, Canva)
- `design.export` — download-first output (Canva)
- `design.asset.list` — brand kit enumeration (Frontify, Canva)

### Best initial Phase 0 wedge
The cleanest first move is:
- `design.template.render` via **Bannerbear** (`POST https://sync.api.bannerbear.com/v2/images`)

Why:
- API key auth, no OAuth, no per-user session
- explicit template UID + modifications array input
- returns rendered image URL or base64 directly
- all layer override semantics (text, image, color) are fully documented
- useful immediately for email personalization, social cards, and report header images

The second wedge is:
- `image.edit.background_remove` via **PhotoRoom** (`POST https://sdk.photoroom.com/v1/segment`)

Why:
- single POST, multipart file upload, base64 or URL output
- no OAuth, immediate commercial utility for product photo workflows

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0153_design_expansion.sql`

## Verdict

Design is an underrepresented and growing agent-demand category. This batch adds five real API-backed providers and sharpens the next honest Resolve wedge around **`design.template.render`** via **Bannerbear**, with **PhotoRoom** as the cleanest orthogonal background-removal addition for the next capability pass.
