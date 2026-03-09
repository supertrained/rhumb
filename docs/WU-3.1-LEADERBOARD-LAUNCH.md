# WU 3.1 — Pre-Launch Leaderboard
## Phase 3: GTM & Launch

**Objective:** Polish leaderboard for public launch. Add category discovery, social sharing, and canonical URLs.

**Acceptance Criteria:**
- ✅ `/leaderboard` landing shows 10 category cards (clickable, with description)
- ✅ `/leaderboard/[category]` has OG image generation (title, top 3 services, score)
- ✅ `/service/[slug]` has OG image (tool name, score, execution/access/tier)
- ✅ Each URL is canonical and shareable (no query params, clean slug)
- ✅ 25+ tests passing (social card tests, route tests)
- ✅ Categories sorted by prevalence in dataset (payments first, then rest alphabetically)

**Dependencies:** None (Supabase + Vercel already live)

**Timeline:** 2-3 hours (thin-slice execution)

---

## Thin-Slice Execution Plan

### Slice A: Category Landing Page
**Goal:** Build `/leaderboard` hub showing all 10 categories

**Deliverables:**
- New file: `packages/web/app/leaderboard/page.tsx` (category grid)
- 10 category cards with:
  - Category name (capitalized)
  - Category description (1 sentence)
  - Service count per category
  - Link to `/leaderboard/[category]`
- Card styling: rounded, hover effect, clean typography
- Responsive grid (3 cols on desktop, 1-2 on mobile)

**Tests:**
- Route renders without error
- All 10 categories present
- Links resolve correctly

**Acceptance:** Category grid complete, visually polished, all links working

---

### Slice B: OG Image Generation (Leaderboard)
**Goal:** Add dynamic OG images for category leaderboards

**Deliverables:**
- New file: `packages/web/app/leaderboard/[category]/og/route.ts` (API route for OG image)
- Uses next/og `ImageResponse` with:
  - Category name (large, bold)
  - Top 3 services in category (name + score)
  - "Agent-native tool ranking" tagline
  - Rhumb logo/branding
- Size: 1200×630px (standard OG size)
- Format: PNG (Vercel default)
- Cache: 24h (Vercel CDN)

**Metadata:** Update `generateMetadata` in `[category]/page.tsx` to:
```
og: { image: `/leaderboard/${category}/og` }
```

**Tests:**
- Route responds with image/png
- Image renders without errors
- Metadata injection works

**Acceptance:** OG images generated on-demand, cacheable, correct dimensions

---

### Slice C: OG Image Generation (Service Pages)
**Goal:** Add dynamic OG images for individual service pages

**Deliverables:**
- New file: `packages/web/app/service/[slug]/og/route.ts` (API route for OG image)
- Uses next/og `ImageResponse` with:
  - Service name (large, bold)
  - Aggregate score (large, colored by tier)
  - Execution + Access scores (small)
  - Tier badge (L1/L2/L3/L4)
  - Rhumb branding
- Size: 1200×630px
- Cache: 24h

**Metadata:** Update `generateMetadata` in `[slug]/page.tsx` to:
```
og: { image: `/service/${slug}/og` }
```

**Tests:**
- Route responds with image/png
- All tiers render correctly
- Handles missing services gracefully

**Acceptance:** OG images for services working, cacheable

---

### Slice D: URL Polish & Testing
**Goal:** Ensure all URLs are canonical and shareable

**Deliverables:**
- Verify canonical tags on all pages (meta rel="canonical")
- Verify no query parameters leak into social shares
- Add E2E tests:
  - Homepage → Leaderboard → Category → Service (full flow)
  - OG image presence for 3 random categories + 3 random services
  - Link clicks navigate correctly
- Update README with shareable URL patterns
  - `rhumb.dev/leaderboard/payments` → top payment tools
  - `rhumb.dev/service/stripe` → Stripe score details

**Tests:**
- 10+ integration tests (category cards, social cards, canonical URLs)
- Snapshot tests for OG images (skip image rendering, test metadata)

**Acceptance:** All URLs clean, shareable, tested

---

## Success Metrics

- Category landing page complete + styled
- OG images rendering for all leaderboard routes
- OG images rendering for all service routes
- 25+ tests passing
- Ready for DNS + public launch

---

## Post-Execution

If complete: Commit to `feat/wu3.1-leaderboard-launch`, create PR, merge to main, deploy to Vercel.

Next: WU 3.2 (Tool Autopsy Content)
