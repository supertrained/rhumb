# Discovery expansion — screenshots II

Date: 2026-03-30
Owner: Pedro / Keel runtime review loop

## Why this category

The live `screenshots` category is still far too thin for a workflow primitive agents actually use.

Agents repeatedly need:
- deterministic URL -> image capture for QA and release checks
- preview / thumbnail generation
- compliance and visual evidence snapshots
- browser-fallback rendering when scraping is brittle
- HTML -> image / PDF capture for user-generated content and reports

The public leaderboard still shows `screenshots` as one of the most underrepresented practical operator categories. That makes it a good discovery-expansion lane because added depth can feed a real Resolve wedge instead of just catalog cosmetics.

## Added services

### 1. ScreenshotOne
- Slug: `screenshotone`
- Score: **8.30**
- Execution: **8.45**
- Access readiness: **8.10**
- Why it made the cut:
  - strongest Phase 0 candidate in the batch
  - very clear capture endpoint and auth model
  - supports both URL and HTML rendering, which broadens capability design headroom

### 2. Urlbox
- Slug: `urlbox`
- Score: **8.20**
- Execution: **8.35**
- Access readiness: **8.00**
- Why it made the cut:
  - strong sync + async API posture
  - supports screenshot, HTML rendering, PDF, video, and metadata extraction
  - especially useful for production capture workflows and archival use cases

### 3. CaptureKit
- Slug: `capturekit`
- Score: **8.05**
- Execution: **8.15**
- Access readiness: **7.90**
- Why it made the cut:
  - explicit API-key auth and job-oriented capture model
  - good fit for future async screenshot execution parity tests

### 4. ScreenshotAPI.net
- Slug: `screenshotapi-net`
- Score: **7.90**
- Execution: **8.00**
- Access readiness: **7.75**
- Why it made the cut:
  - broad parameter surface across image, PDF, and video outputs
  - supports CSS/JS injection and geolocation, which matters for real-world rendering edge cases

### 5. URL2PNG
- Slug: `url2png`
- Score: **7.55**
- Execution: **7.70**
- Access readiness: **7.45**
- Why it made the cut:
  - still a credible long-tail signed-URL screenshot provider
  - useful category depth for simple render-and-store workflows

## Phase 0 capability assessment

### Services with accessible APIs
All five added providers expose real developer-facing screenshot APIs.

Strongest near-term Resolve targets:
1. **ScreenshotOne**
2. **Urlbox**
3. **CaptureKit**

### Candidate capability shapes
- `screenshot.capture`
- `render.html_to_image`
- `render.url_to_pdf`

### Best initial Phase 0 wedge
The cleanest first wedge is **`screenshot.capture`**.

Why:
- it is the narrowest common denominator across the batch
- request contract is easy to normalize: `url`, `viewport`, `full_page`, `format`
- response can be standardized as image bytes, image URL, or job/result handle
- it is useful immediately for QA, previews, evidence capture, and agent browser fallback

**Best first provider target: `screenshotone`**
- clearest simple capture endpoint in the batch
- explicit access-key auth
- broad output support without making the first capability too complex

**Best second provider target: `urlbox`**
- strong sync/async support
- likely best follow-on for richer rendering variants once the core screenshot primitive is stable

## Implementation note

Migration added:
- `rhumb/packages/api/migrations/0123_screenshots_expansion_ii.sql`

## Verdict

`screenshots` is still one of the most underrepresented practical categories in the live catalog, and it maps directly to a capability agents genuinely need. This batch adds five more real screenshot APIs and sharpens the next honest Resolve wedge around **`screenshot.capture`** rather than leaving the category shallow and purely editorial.
