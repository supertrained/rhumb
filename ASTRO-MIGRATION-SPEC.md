# Astro Migration Spec — rhumb.dev

## Mission
Rebuild rhumb.dev from Next.js App Router to Astro + React islands. Practice what we preach: the most agent-native frontend framework, with a design that's the best-looking agent-native site on the internet.

## Current State
- **Framework:** Next.js 15 (App Router, React Server Components)
- **Styling:** Tailwind CSS 4.2 with custom theme
- **Data:** Supabase direct (scores, services, evidence, failure_modes tables)
- **Deployment:** Vercel
- **Pages:** 27+ routes (see inventory below)
- **Components:** 10 shared components
- **Static files:** 66 files in public/ (guides, security.txt, favicon, etc.)

## Design System (PRESERVE)
The current brand is excellent. Keep it.

### Colors
```
Navy (bg):        #0B1120
Surface:          #151D2E
Elevated:         #1C2640
Amber (accent):   #F59E0B
Amber dark:       #D97706
Score Native:     #10B981 (green)
Score Ready:      #3B82F6 (blue)
Score Developing: #F59E0B (amber)
Score Limited:    #EF4444 (red)
```

### Typography
- **Display:** DM Sans (300-700)
- **Mono:** JetBrains Mono (400-700)

### Patterns
- Dark mode only (color-scheme: dark)
- Glass-morphism nav (bg-navy/85 backdrop-blur-md)
- Grid background pattern (bg-grid class)
- Amber radial glow on hero sections
- Score badges with tier-colored glow effects
- Staggered fade-up animations on page load
- Amber selection color
- Border-slate-800 card style with hover elevation

## Architecture

### Astro Setup
- Astro 5.x with React integration for interactive islands
- Tailwind CSS 4.x (same config)
- SSG for static pages (blog, about, trust, methodology, privacy, terms, changelog)
- SSR for dynamic pages (homepage, leaderboard, service pages, search) via Vercel adapter
- Content Collections for blog posts (MDX or Astro components)

### Interactive Islands (React)
Only these need client-side JS:
1. **Navigation** — mobile hamburger toggle, active path highlighting
2. **Search** — client-side search with typeahead
3. **CopyInstall** — clipboard copy button
4. **DimensionChart** — score visualization (if interactive)

Everything else is static Astro components.

### Data Layer
Keep the existing Supabase client (`lib/api.ts`) — it works server-side and Astro can call it in frontmatter/server endpoints.

### API Routes → Astro Endpoints
- `app/api/og/route.tsx` → `src/pages/api/og.ts` (OG image generation)
- `app/llms.txt/route.ts` → `src/pages/llms.txt.ts`
- `app/llms-full.txt/route.ts` → `src/pages/llms-full.txt.ts`
- `app/go/route.ts` → `src/pages/go.ts` (redirect handler)
- `app/indexnow/route.ts` → `src/pages/indexnow.ts`

### Deployment
Vercel with `@astrojs/vercel` adapter. Same domain, same env vars.

## Page Inventory

### Static Pages (SSG)
| Current Route | Astro File | Notes |
|---|---|---|
| `/about` | `src/pages/about.astro` | |
| `/blog` | `src/pages/blog.astro` | Blog index |
| `/blog/[slug]` | `src/pages/blog/[slug].astro` | Use Content Collections |
| `/changelog` | `src/pages/changelog.astro` | |
| `/docs` | `src/pages/docs.astro` | |
| `/methodology` | `src/pages/methodology.astro` | |
| `/pricing` | `src/pages/pricing.astro` | |
| `/privacy` | `src/pages/privacy.astro` | |
| `/providers` | `src/pages/providers.astro` | |
| `/terms` | `src/pages/terms.astro` | |
| `/trust` | `src/pages/trust.astro` | |

### Dynamic Pages (SSR)
| Current Route | Astro File | Notes |
|---|---|---|
| `/` | `src/pages/index.astro` | Fetches featured leaderboard + count |
| `/leaderboard` | `src/pages/leaderboard.astro` | Category hub |
| `/leaderboard/[category]` | `src/pages/leaderboard/[category].astro` | Category leaderboard |
| `/search` | `src/pages/search.astro` | Search page |
| `/service/[slug]` | `src/pages/service/[slug].astro` | Service detail |
| `/internal/launch` | `src/pages/internal/launch.astro` | Admin dashboard |

### Redirects
| Source | Destination |
|---|---|
| `/services` | `/leaderboard` |
| `/services/[slug]` | `/service/[slug]` |
| `/services/[slug]/failures` | `/service/[slug]` |
| `/services/[slug]/history` | `/service/[slug]` |

### API Endpoints
| Current Route | Astro File |
|---|---|
| `/api/og` | `src/pages/api/og.ts` |
| `/llms.txt` | `src/pages/llms.txt.ts` |
| `/llms-full.txt` | `src/pages/llms-full.txt.ts` |
| `/go` | `src/pages/go.ts` |
| `/indexnow` | `src/pages/indexnow.ts` |

## Components

### Astro Components (static)
- `Layout.astro` — base layout with nav, footer, meta
- `Navigation.astro` + `MobileNav.tsx` (island) — sticky nav
- `ScoreDisplay.astro` — AN Score badge
- `TierBadge.astro` — inline tier pill
- `ServiceCard.astro` — leaderboard row
- `FailureModeTags.astro` — failure mode display
- `AutonomySection.astro` — P1/G1/W1 breakdown
- `GuideSection.astro` — markdown guide renderer

### React Islands (interactive)
- `Search.tsx` — typeahead search
- `CopyInstall.tsx` — clipboard copy
- `MobileNav.tsx` — hamburger menu toggle

## Discovery Files (MUST PRESERVE)
- `robots.txt` — in public/
- `sitemap.xml` — Astro built-in (@astrojs/sitemap)
- `llms.txt` — dynamic endpoint
- `llms-full.txt` — dynamic endpoint
- `.well-known/security.txt` — in public/
- `google5f0d824854111d38.html` — Google verification

## Agent-Native Requirements
1. Every page SSR/SSG — zero client-only content
2. JSON-LD on every page
3. Semantic HTML (h1-h6, tables, lists, nav, article, section)
4. Meta descriptions on every page
5. OG images for every page
6. No noindex anywhere (except internal/launch)
7. Content ≥ 100 words extractable on every public page
8. Clean URLs (Astro default)
9. All discovery files return 200

## Environment Variables (from Vercel)
```
NEXT_PUBLIC_SUPABASE_URL → PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY → PUBLIC_SUPABASE_ANON_KEY
NEXT_PUBLIC_GA_ID → PUBLIC_GA_ID
NEXT_PUBLIC_CLARITY_ID → PUBLIC_CLARITY_ID
RHUMB_ADMIN_SECRET → RHUMB_ADMIN_SECRET (server-only)
RHUMB_LAUNCH_DASHBOARD_KEY → RHUMB_LAUNCH_DASHBOARD_KEY (server-only)
```

## Tests
Existing Vitest test suite should be adapted. Key tests:
- Homepage renders headline, stats, featured services
- Service page renders scores, failure modes
- Leaderboard renders ranked items
- Blog pages render content
- Discovery files return 200

## What NOT to Change
1. Supabase schema — zero database changes
2. Domain/DNS — same rhumb.dev
3. Public files — same guides/, security.txt, etc.
4. Brand colors, typography, design language
5. Functionality — every feature that exists today must exist after migration
