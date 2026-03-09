# Rhumb Design Brief — For Gemini Design Generation

## What Is Rhumb?
Rhumb is an agent-native tool discovery and scoring platform. It helps AI agents (and the humans who build with them) find the right developer tools by scoring APIs on dimensions that matter for machine consumption: error ergonomics, idempotency, schema stability, latency distribution, and more.

## Brand Essence
- **Name:** Rhumb (from "rhumb line" — a line of constant bearing in navigation)
- **Personality:** Precise, confident, data-driven. Not flashy, not corporate. Think: the instrument panel of a well-built ship. Every element serves a purpose.
- **Audience:** AI automation consultants, agent framework builders, technical founders building with AI agents. They value competence, clarity, and speed.
- **Competitors' aesthetic:** RapidAPI (cluttered marketplace), Smithery (basic catalog). We should look like neither. We should look like a Bloomberg terminal crossed with a Dieter Rams product.

## Design Direction
**"Precision instrument"** — Clean, dark-mode-first, data-dense but never cluttered. Every number tells a story. Color is used sparingly and with purpose (to signal quality tiers, anomalies, or actions).

### Color System
- **Background:** Deep navy/charcoal (#0B1120 or similar) — not pure black
- **Surface:** Slightly lighter (#151D2E) for cards/panels
- **Text:** High-contrast white (#F1F5F9) for primary, muted (#94A3B8) for secondary
- **Accent (primary):** A warm amber/gold (#F59E0B) — the bearing indicator, the rhumb line
- **Score tiers:**
  - L4 Native (8.0+): Emerald green (#10B981)
  - L3 Ready (7.0–7.9): Blue (#3B82F6)
  - L2 Developing (6.0–6.9): Amber (#F59E0B)
  - L1 Limited (<6.0): Red (#EF4444)
- **Borders/dividers:** Subtle (#1E293B)

### Typography
- **Display/Headlines:** Something with character — geometric sans with personality. NOT Inter, Roboto, or Space Grotesk. Consider: Instrument Sans, DM Sans, Geist, Satoshi, or something bolder.
- **Body:** Clean, highly legible at small sizes. Pair well with the display font.
- **Monospace (for scores/data):** JetBrains Mono, Berkeley Mono, or similar

### Layout Principles
- **Data density is a feature.** Don't hide information behind clicks. Show scores, tiers, and key metrics upfront.
- **Cards as instruments.** Each service card should feel like a gauge or readout — compact, information-rich, instantly scannable.
- **Grid-based but not rigid.** Use a 12-column grid but allow hero sections and feature cards to break it when the content warrants it.
- **Mobile-first.** Cards stack vertically. Scores remain visible. Nothing hides on mobile.

### Micro-interactions
- Score badges should have subtle glow effects matching their tier color
- Card hover: slight elevation + border glow
- Page transitions: fade-in with staggered card reveal
- Loading states: skeleton screens with the same card shape

## Pages to Design

### 1. Home Page (/)
- Hero: Bold statement about what Rhumb does. Search bar prominent.
- Quick stats: "50 services scored • 10 categories • Updated continuously"
- Featured category preview (e.g., top 3 payments)
- CTA: "Explore the Leaderboard" + "Install the CLI"

### 2. Leaderboard Hub (/leaderboard)
- Category grid (10 cards)
- Each card shows: category name, icon/illustration, service count, top scorer with score
- Search/filter bar at top
- Feel: like choosing an instrument cluster to examine

### 3. Category Leaderboard (/leaderboard/[category])
- Ranked list of services with:
  - Rank number
  - Service name + logo placeholder
  - AN Score (large, with tier color)
  - Maturity level badge (L1–L4)
  - Key metrics sparkline or mini-chart (execution, access, freshness)
  - "Tested X minutes ago" freshness indicator
- Sortable by different dimensions
- Comparison mode: select 2-3 services to compare side-by-side

### 4. Service Detail (/service/[slug])
- Service header: name, category, overall score, maturity level
- Score breakdown: radar/spider chart showing all dimensions
- Dimension cards: each scored dimension with explanation
  - "Idempotency: 9.2 — Every endpoint supports idempotency keys with collision detection"
  - "Error Ergonomics: 8.8 — Structured JSON errors with machine-readable codes and retry-after headers"
- Failure modes section: known issues, edge cases
- Historical chart: score over time
- Alternatives: "If you need this but cheaper/faster/more reliable"
- Agent consumption section: MCP tool call example, CLI command, llms.txt snippet

### 5. Blog/Autopsy (/blog/[slug])
- Editorial layout: generous margins, large type
- Data visualizations inline (score comparisons, dimension breakdowns)
- Code snippets for CLI/MCP examples
- Share cards for social

### 6. Search Results (/search)
- Quick results with score preview
- Faceted filters (category, minimum score, maturity level)
- "Powered by Rhumb" badge for agent-facing queries

## Component Library

### Score Badge
- Circular or pill-shaped
- Score number large and prominent
- Background color = tier color (with opacity)
- Subtle glow effect
- Size variants: large (hero), medium (card), small (inline)

### Service Card
- Dark surface with subtle border
- Service name, category tag, score badge
- 2-3 key metrics as small indicators
- Freshness timestamp
- Hover: elevation + glow

### Category Card
- Icon or abstract illustration
- Category name
- Service count
- Top scorer preview
- Click → category leaderboard

### Dimension Meter
- Horizontal bar or gauge
- Filled to score level
- Color matches overall assessment
- Label + score + one-line explanation

### Navigation
- Top bar: Logo + nav links + search
- Sticky on scroll
- Mobile: hamburger → slide-out
- Breadcrumbs on detail pages

### Footer
- Minimal: links to API docs, CLI install, GitHub, Twitter
- "Built by agents, for agents"

## Technical Constraints
- Next.js 15 (App Router, Server Components)
- Tailwind CSS (preferred for utility-first)
- No component library dependency (no Chakra, MUI, etc.)
- Google Fonts for typography (free, fast CDN)
- SVG for icons (no icon library dependency)
- Dark mode is the default (light mode can come later)

## What Makes This Unforgettable
The score. When someone sees "Stripe: 8.3 (L4 Native)" with that emerald glow against a dark background, with dimension breakdowns that read like an instrument panel — that's the moment. It should feel like opening a Bloomberg terminal for the first time: "I can see everything, and everything means something."
