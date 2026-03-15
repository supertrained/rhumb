# Agent Accessibility Guidelines (AAG) v0.3

> **"ADA made the web usable for every human. AAG makes it usable for every agent."**

## Why This Exists

The Americans with Disabilities Act (ADA) and WCAG created a framework for making websites accessible to humans with diverse abilities. Screen readers, keyboard navigation, color contrast, alt text — all emerged from asking: "What if the user can't interact the way we assumed?"

AI agents face the same problem. They interact with websites through fundamentally different modalities than humans, and most sites are accidentally hostile to all of them. This document defines **Agent Accessibility** — a set of guidelines for making web interfaces usable by AI agents across every interaction mode.

This isn't theoretical. We build agents. We watch them fail. These guidelines come from real failures.

---

## How Agents Actually Interact with Websites

Unlike humans (who have one primary mode: eyes + hands), agents use **multiple interaction channels simultaneously**, falling back between them when one fails. Understanding all channels is prerequisite to designing for them.

### Channel 1: DOM / Accessibility Tree (Primary)

**How it works:** Agent reads the page's accessibility tree — the same tree screen readers use. Elements with roles, names, labels, and states become the agent's "vision" of the page.

**Tools:** Playwright `page.accessibility.snapshot()`, CDP `Accessibility.getFullAXTree`, browser tool snapshots (OpenClaw, Stagehand, etc.)

**What agents see:**
```
- navigation "Main"
  - link "Home" [href="/"]
  - link "Leaderboard" [href="/leaderboard"]
  - link "Search" [href="/search"]
- heading "Find agent-native services" [level=1]
- search
  - textbox "Search services" [placeholder]
  - button "Search"
- list "Top Services"
  - listitem
    - link "Stripe" [href="/service/stripe"]
    - text "8.3 · L4 Native"
```

**When it fails:**
- Elements rendered via `<canvas>` or WebGL (invisible to a11y tree)
- Custom components without ARIA roles (`<div onclick>` instead of `<button>`)
- Dynamic content loaded after snapshot (race conditions)
- Shadow DOM that doesn't expose its internals
- CSS-in-JS with hashed class names (no stable selectors)

### Channel 2: Visual / Screenshot (Fallback)

**How it works:** Agent takes a screenshot and uses vision models (GPT-4o, Claude, Gemini) to understand the page visually. Some agents use OCR for text extraction.

**Tools:** Playwright `page.screenshot()`, CDP `Page.captureScreenshot`, browser tool screenshots

**What agents see:** A pixel image. They identify elements by visual position, text content, color, and spatial relationships.

**When it fails:**
- Low contrast text (same problem as human accessibility)
- Text baked into images without alt text
- Overlapping elements or z-index issues
- Animations or transitions mid-capture (blurred states)
- Responsive layouts that shift elements unexpectedly
- Modals/overlays that obscure the target content
- Infinite scroll with no visual pagination cues

### Channel 3: CDP (Chrome DevTools Protocol)

**How it works:** Agent connects to a running Chrome instance via WebSocket. Can execute JavaScript, intercept network requests, manipulate DOM directly, and monitor events.

**Tools:** Playwright `connectOverCDP()`, Puppeteer, direct CDP clients

**What agents see:** Full programmatic access to the browser. Can query selectors, execute JS, read network traffic.

**When it fails:**
- Sites that detect automation (`navigator.webdriver`, CDP detection)
- Sites that block CDP connections or specific User-Agents
- Heavy client-side rendering that races with CDP commands
- Service workers that intercept/modify requests
- WebSocket connections that require specific handshakes

### Channel 4: Raw HTML Parsing

**How it works:** Agent fetches page HTML and parses it directly. Cheapest and fastest channel — no browser needed.

**Tools:** `fetch` + cheerio/BeautifulSoup, `curl`, web scraping libraries

**What agents see:** Raw HTML structure, text content, links, forms.

**When it fails:**
- Single Page Applications (empty `<div id="root">` in source)
- Content behind authentication
- JavaScript-rendered content
- Anti-scraping measures (Cloudflare challenges, rate limits)
- Dynamic content that requires user interaction to appear

### Channel 5: Structured Data Endpoints

**How it works:** Agent accesses machine-readable data through documented APIs, JSON-LD, microdata, RSS, sitemaps, `llms.txt`, or `robots.txt`.

**Tools:** HTTP clients, JSON parsers, schema.org validators

**What agents see:** Clean, typed, structured data. The ideal interaction mode.

**When it fails:**
- No API exists (UI-only product)
- API docs are outdated or wrong
- Rate limits without clear documentation
- Authentication complexity (OAuth flows requiring browser redirects)
- No `llms.txt` or structured data markup

### Channel 6: Keyboard / Action Simulation

**How it works:** Agent simulates keyboard and mouse events. Types into fields, clicks buttons, navigates via Tab key.

**Tools:** Playwright actions (`click`, `fill`, `press`), CDP `Input.dispatchKeyEvent`, browser tool `act`

**What agents see:** Interactive elements they can target by selector, ARIA ref, or coordinates.

**When it fails:**
- Custom input components that don't respond to standard events
- Drag-and-drop interfaces
- Canvas-based interactions
- Time-dependent interactions (hold to activate, double-click required)
- Focus traps (modals that don't release focus)
- Custom keyboards on mobile web

---

## The AAG Levels

Modeled after WCAG's A/AA/AAA structure. Each level builds on the previous.

### Level A: Agent Parseable
*Minimum bar. An agent can understand what's on the page.*

| # | Guideline | Rationale |
|---|-----------|-----------|
| A.1 | **Semantic HTML for all interactive elements** — Use `<button>`, `<a>`, `<input>`, `<select>`, `<form>` instead of styled `<div>`s with click handlers | Agents identify interactive elements by role. A `<div onclick>` is invisible to the accessibility tree. |
| A.2 | **All images have descriptive alt text** | Vision models can read images, but alt text is faster, cheaper, and more reliable than OCR. |
| A.3 | **Page has a single `<h1>` and logical heading hierarchy** | Agents use headings to understand page structure and navigate to relevant sections. |
| A.4 | **All form inputs have associated `<label>` elements** | Agents need to know what a text field is for. Placeholder text disappears on focus. |
| A.5 | **Links have descriptive text** (not "click here") | Agents extract link text to understand navigation options without visual context. |
| A.6 | **No content locked behind hover-only interactions** | Agents can hover, but it's unreliable. Critical content must be accessible without hover state. |
| A.7 | **Error messages appear in the DOM** (not just toast notifications) | Toast notifications disappear. Agents need errors to persist until acknowledged. |
| A.8 | **Loading states are detectable** — Skeleton screens, `aria-busy`, or `data-loading` attributes | Agents need to know when to wait. An empty div is ambiguous — is it loading or empty? |
| A.9 | **No `noindex` on agent-facing pages** — Remove `<meta name="robots" content="noindex">` from any page agents need to discover | A page for agents that tells machines to ignore it is self-defeating. `noindex` blocks crawlers, LLM training, and agent discovery. If it's public and for agents, it must be indexable. |
| A.10 | **Content extraction yields ≥ 100 words** — Server HTML must contain meaningful text content extractable without JavaScript | If `curl yourpage.com \| wc -w` returns < 100 words, the page is functionally invisible to agents. 3 words from a full product page (the Ramp Agent Cards case) means 99.7% of the content is locked behind JS. |
| A.11 | **Meta descriptions describe actual functionality** — `<meta name="description">` should be a complete sentence explaining what the page offers | "Cards built for agents" (4 words) tells an agent almost nothing. A good meta description acts as a fallback summary when content extraction fails. Aim for 50–160 characters of actual description. |
| A.12 | **Icons always paired with text** — Never use icon-only buttons or links. SVG icons are invisible to agents; an icon-only action is a blank action. | Agents can't see SVGs. A hamburger menu icon without `aria-label` or visible text is a `<button>` with no name. At minimum, `aria-label`; prefer visible text alongside the icon. |
| A.13 | **Headings are descriptive, not clever** — Use headings that describe content ("Stripe Agent-Native Score: 8.1/10") not headings that require visual context ("The Verdict") | Agents use heading text to navigate documents and understand section content. A clever heading requires surrounding context to interpret — agents parse headings in isolation. |

### Level AA: Agent Navigable
*An agent can reliably interact with the page and extract structured data.*

| # | Guideline | Rationale |
|---|-----------|-----------|
| AA.1 | **Stable selectors on key interactive elements** — `data-testid`, meaningful `id`, or stable `aria-label` | CSS-in-JS hashes change on rebuild. Agents need selectors that survive deploys. |
| AA.2 | **Predictable URL structure** — `/resource/[id]`, not `/app?view=detail&resource=abc123` | Agents construct URLs programmatically. Predictable patterns = reliable navigation. |
| AA.3 | **Machine-readable dates and numbers** — ISO 8601 dates, `datetime` attributes, `data-value` for formatted numbers | "2 hours ago" requires inference. `2026-03-09T12:00:00Z` is unambiguous. |
| AA.4 | **Server-side rendered content in initial HTML** | Client-side-only rendering means raw HTML parsing returns nothing. SSR ensures content is accessible to all channels. |
| AA.5 | **No CAPTCHAs or bot detection on read-only pages** | Agents are bots. If the content is public, bot detection is a barrier, not a security measure. |
| AA.6 | **Structured data markup** (JSON-LD, Schema.org) on key pages | Gives agents typed, structured access to page content without parsing HTML. |
| AA.7 | **Consistent page layout across routes** — Navigation, content area, and footer in the same DOM positions | Agents learn page structure. Inconsistent layouts mean re-learning on every page. |
| AA.8 | **Modals and overlays are dismissible and don't trap focus** | Cookie consent banners, newsletter popups, and onboarding modals block agent interaction. They must be dismissible or not block the main content. |
| AA.9 | **Pagination over infinite scroll** — Or provide `?page=N` parameter | Agents can't "scroll." Infinite scroll requires simulating scroll events and waiting for load. Pagination is reliable. |
| AA.10 | **Tables use `<th>` headers and `scope` attributes** | Agents extract tabular data frequently. Proper table markup makes extraction trivial. |
| AA.11 | **Discovery files return 200** — `robots.txt`, `sitemap.xml`, and `llms.txt` must exist and return valid responses, not 404 | Agents check these files to understand site structure and permissions. A 404 on `robots.txt` means the agent has no signal about what's allowed. A 404 on `sitemap.xml` means no page discovery. These are the agent's front door — keep it open. |
| AA.12 | **No script loaders that defer all content** — Avoid Cloudflare Rocket Loader, lazy-load-everything patterns, or deferred rendering that empties the initial HTML | Script loaders that move all content to deferred JS execution make pages invisible to any non-browser consumer. If you use a CDN-level script loader, ensure critical content is excluded or pre-rendered. |
| AA.13 | **Navigation links rendered in static HTML** — All nav links must be in the initial document, not behind a JS toggle. Mobile hamburger menus are a progressive enhancement over a fully-rendered `<nav>` | Agents parse `<nav>` tags from raw HTML. A nav that requires JS to expand doesn't exist to non-browser agents. Render all links statically; use JS only to show/hide on small screens. |
| AA.14 | **Search available at a server-rendered URL** — Provide `/search?q=term` that returns results in HTML, not just a JS-dependent search widget | Agents need a URL they can GET. A search box that requires JS event handling is unusable via raw HTML or API channels. The pretty UI is for humans; the URL endpoint is for agents. |
| AA.15 | **Use native HTML disclosure over JS tabs** — Use `<details>`/`<summary>` for show/hide content, not JS-toggled tab panels that hide content from the DOM | Content inside an inactive JS tab is invisible when agents parse HTML. Native `<details>` elements are parseable even when collapsed. If tabs are essential, ensure all tab content is in the DOM (not lazy-loaded on click). |
| AA.16 | **Tabular data uses `<table>`, not card layouts** — When data is structurally tabular (rankings, scores, comparisons), render it in `<table>` elements with proper `<th>` and `scope` | Cards are visually appealing for humans but lose structure when extracted. Agents extract tables trivially. Use cards for browsing/discovery, tables for structured data. Both can coexist. |
| AA.17 | **Every content piece reachable at a direct URL** — No information should only be accessible via modal, popup, or overlay | If a key feature or detail lives only in a modal triggered by a click, it has no URL and cannot be linked, crawled, or fetched. Every meaningful content piece needs a permalink. |

### Level AAA: Agent Native
*The site is designed with agents as a first-class audience.*

| # | Guideline | Rationale |
|---|-----------|-----------|
| AAA.1 | **API parity** — Everything visible in the UI is available via API | The UI is an interface for humans. Agents prefer APIs. Full parity means agents never need to scrape. |
| AAA.2 | **`llms.txt` at site root** — Machine-readable description of site capabilities, API endpoints, and data models | Emerging standard. Gives agents a "README" for your site. |
| AAA.3 | **Stable `data-testid` attributes on ALL interactive elements** | Not just key elements (AA.1) — every button, link, input, and toggle. |
| AAA.4 | **Event-driven state** — DOM reflects application state in real-time via `aria-` attributes or `data-` attributes | Agents monitor state changes to verify their actions worked. `data-state="submitted"` beats checking if a success message appeared. |
| AAA.5 | **Webhook/SSE support for state changes** | Beyond scraping for updates — push-based notifications for agents monitoring your app. |
| AAA.6 | **Multi-modal content** — Text alternatives for all visual-only information (charts, graphs, diagrams) | A chart is pixels. Its `data-values` attribute or underlying data table is information. |
| AAA.7 | **Token-efficient pages** — Minimal DOM nesting, no wrapper div soup, clean structure | Every DOM node costs tokens when agents snapshot the page. Deeply nested `<div>` wrappers waste agent compute. |
| AAA.8 | **Documented interaction patterns** — A machine-readable file describing how to complete key flows (login, purchase, submit) | Agents shouldn't have to figure out multi-step flows by trial and error. `agent-flows.json` at site root. |
| AAA.9 | **Graceful degradation without JavaScript** | Content accessible even with JS disabled = maximum compatibility across all agent channels. |
| AAA.10 | **No anti-automation measures on legitimate use paths** | If an agent is using your product legitimately (paying customer, API access), don't block automation. Rate limit, don't ban. |
| AAA.11 | **Three-level degradation** — Every UI element works at three levels: (1) Full JS — rich human experience, (2) HTML only — what agents/curl/screen readers see, (3) Structured data — JSON-LD, meta tags, semantic markup | If your element only works at level 1, you've failed agent-native design. Server-side rendering makes level 2 the default. Structured data (level 3) lets agents skip HTML parsing entirely. |

---

## Agent-Hostile Patterns (Anti-Patterns)

These patterns make websites actively difficult for agents. Avoid them.

| Pattern | Why It's Hostile | Fix |
|---------|-----------------|-----|
| **`<div>` with click handlers instead of `<button>`** | Invisible to accessibility tree | Use semantic HTML elements |
| **Hashed CSS class names** (`.css-1a2b3c`) | Unstable selectors, change on every build | Add `data-testid` or meaningful classes alongside |
| **Canvas-rendered UI** | No DOM representation at all | Provide text alternatives or overlay DOM elements |
| **Infinite scroll without API** | Agents can't scroll | Add `?page=N` pagination parameter |
| **Shadow DOM without `delegatesFocus`** | Blocks accessibility tree traversal | Expose key elements to the light DOM or use open shadow roots |
| **Aggressive bot detection on public pages** | Blocks all agent channels | Allow read access, rate limit writes |
| **Dynamic IDs** (`element-a7f3b2c`) | Can't build reliable selectors | Use stable IDs or `data-testid` |
| **Toast-only notifications** | Disappear before agents can read them | Persist state in DOM, use `role="alert"` + keep in DOM |
| **Required hover/drag interactions** | Unreliable across agent channels | Provide click/keyboard alternatives |
| **iframes for core content** | Cross-origin iframes block DOM access | Use same-origin or provide API access to iframe content |
| **Client-side only rendering** | Raw HTML parsing returns nothing | SSR or SSG for content pages |
| **Unstructured dates** ("last Tuesday") | Requires NLU to parse | ISO 8601 in `datetime` attribute |
| **`noindex` on agent-facing pages** | Tells machines to ignore a page built for machines | Remove `noindex` from any public, agent-facing page |
| **CDN script loaders (Rocket Loader, etc.)** | Moves all content to deferred JS, emptying initial HTML | Exclude critical content from script deferral, or pre-render |
| **"Agent" branding with no agent access** | Markets to agents but serves empty HTML to them | Verify your page works without JS before branding it "for agents" |
| **4-word meta descriptions** | Useless as fallback context for agents | Write real descriptions: what the page does, who it's for, what data it contains |
| **Icon-only buttons** | Agents see a nameless `<button>` | Always pair icons with visible text or at minimum `aria-label` |
| **Clever headings** ("The Verdict", "What We Think") | Agents can't infer meaning from context | Use descriptive headings that work in isolation |
| **JS-toggled tab panels** | Inactive tab content isn't in the DOM for many implementations | Use `<details>`/`<summary>` or ensure all tab content is always in DOM |
| **Infinite scroll without `?page=N`** | Agents can't simulate scrolling reliably | Provide URL-based pagination parameters |
| **Modal-only content** | No URL, no crawl, no fetch | Every meaningful content piece needs a permalink |
| **Hamburger-only navigation** | Nav links hidden behind JS toggle don't exist to agents | Render full `<nav>` in HTML; hamburger is progressive enhancement |

---

## Real-World Case Study: Ramp Agent Cards

*Added in v0.2 based on the March 2026 audit published at rhumb.dev/blog/agent-cards-invisible*

Ramp launched "Agent Cards" at `agents.ramp.com/cards` — a product explicitly designed for AI agents. We tested it the way every agent framework accesses web content: HTTP GET + readability extraction.

**Results:**
- Content extraction: **3 words** ("Agent Cards", "Interest", "Help")
- `robots.txt`: 404
- `llms.txt`: 404
- `sitemap.xml`: 404
- JSON-LD: None
- Meta description: "Cards built for agents" (4 words)
- `<meta name="robots" content="noindex">` set in HTML

**What went wrong:** The page is a Next.js SPA with Cloudflare Rocket Loader. All content is client-rendered. The server HTML is an empty shell. Combined with `noindex`, the page actively tells agents to ignore it.

**AAG violations:** A.9 (noindex on agent page), A.10 (< 100 extractable words), A.11 (insufficient meta description), AA.4 (no SSR), AA.11 (discovery files 404), AA.12 (Rocket Loader defers all content).

**The lesson:** If your audience is agents, your architecture must serve agents. Client-side-only rendering + `noindex` + no discovery files = invisible to every agent channel except browser automation (the most expensive and least reliable channel). Six of the new guidelines added in v0.2 were directly inspired by this case.

---

## Agent-Native UI Element Reference

*Added in v0.3. How every major UI element changes when you design for agents as a first-class audience.*

Every UI element should work at **three levels**:

1. **Full JS** — the rich human experience (animations, hover states, transitions)
2. **HTML only** — what an agent, `curl`, or screen reader sees
3. **Structured data** — JSON-LD, meta tags, semantic markup for machine understanding

If your element only works at level 1, you've failed agent-native design.

### Navigation

| | Human | Agent |
|---|-------|-------|
| **Interaction** | Hamburger menus, dropdowns, hover states | Parses `<nav>` and `<a>` tags from raw HTML |
| **Failure mode** | — | Nav behind JS toggle doesn't exist |

**The fix:** Render all nav links in static HTML. The mobile hamburger is a **progressive enhancement** (React island for humans), but the `<nav>` element with every link is always in the document. Astro does this by default — the nav is an `.astro` component, zero JS.

```html
<!-- ✅ Correct: Full nav always in DOM -->
<nav>
  <a href="/">Home</a>
  <a href="/leaderboard">Leaderboard</a>
  <a href="/search">Search</a>
  <a href="/docs">Docs</a>
</nav>
<!-- Mobile toggle is JS enhancement, not gatekeeper -->
<button class="mobile-toggle" aria-label="Toggle menu">☰</button>
```

### Search

| | Human | Agent |
|---|-------|-------|
| **Interaction** | Type in a box, see filtered results | Needs a URL: `GET /search?q=stripe` |
| **Failure mode** | — | JS-dependent search widget is unusable via raw HTML or API channels |

**The fix:** Keep the pretty search UI for humans, but also expose a **server-rendered `/search?q=`** that returns results in the HTML. Plus the API endpoint.

```
# Agent can GET this URL and parse results from HTML
https://site.com/search?q=stripe

# Even better: API endpoint with structured response
https://site.com/api/search?q=stripe → JSON
```

### Tables vs Cards

| | Human | Agent |
|---|-------|-------|
| **Interaction** | Cards are prettier for browsing | Cards lose structure when parsed |
| **Failure mode** | — | Card grid becomes a blob of text with lost relationships |

**The fix:** Use semantic `<table>` for data that **is** tabular (leaderboards, score breakdowns, comparisons). Cards are fine for discovery browsing, but use proper heading hierarchy + microdata inside them so structure survives extraction.

```html
<!-- ✅ Leaderboard: tabular data gets a table -->
<table>
  <thead>
    <tr><th scope="col">Rank</th><th scope="col">Service</th><th scope="col">Score</th></tr>
  </thead>
  <tbody>
    <tr><td>1</td><td>Stripe</td><td>8.3</td></tr>
  </tbody>
</table>

<!-- ✅ Discovery cards: structured with headings + microdata -->
<article itemscope itemtype="https://schema.org/SoftwareApplication">
  <h3 itemprop="name">Stripe</h3>
  <span itemprop="aggregateRating">8.3/10</span>
</article>
```

### Tabs / Accordions

| | Human | Agent |
|---|-------|-------|
| **Interaction** | Click tab to reveal content | Content behind inactive JS tab is invisible |
| **Failure mode** | — | This is exactly what killed Ramp's Agent Cards page |

**The fix:** Use `<details>`/`<summary>` (native HTML, parseable even when collapsed) instead of JS-toggled tabs. Or just... show everything. Sections with headings. The page can be longer — agents don't care about scroll length, they care about content being **in the document**.

```html
<!-- ✅ Native HTML: content parseable even when collapsed -->
<details>
  <summary>Authentication Methods</summary>
  <p>Supports OAuth 2.0, API keys, and JWT bearer tokens...</p>
</details>

<!-- ❌ JS tabs: inactive content often not in DOM -->
<div role="tabpanel" hidden>Content agent never sees</div>
```

### Pagination

| | Human | Agent |
|---|-------|-------|
| **Interaction** | Scroll for more, or click page numbers | Can't scroll. Needs `rel="next"` links or `?page=N` params |
| **Failure mode** | — | Infinite scroll = agent sees only the first viewport |

**The fix:** Real pagination with `<link rel="next">` / `<link rel="prev">` in `<head>`. Agents can crawl the full set.

```html
<head>
  <link rel="next" href="/leaderboard?page=2">
  <link rel="prev" href="/leaderboard?page=1">
</head>

<!-- Pagination controls with real links -->
<nav aria-label="Pagination">
  <a href="/leaderboard?page=1">1</a>
  <a href="/leaderboard?page=2" aria-current="page">2</a>
  <a href="/leaderboard?page=3">3</a>
</nav>
```

### Modals / Overlays

| | Human | Agent |
|---|-------|-------|
| **Interaction** | Click to open, click/Esc to close | Completely invisible — no URL, no DOM presence until triggered |
| **Failure mode** | — | If key content is modal-only, it doesn't exist to agents |

**The fix:** Every piece of information should be reachable at a **direct URL**, not trapped in a popup. Modals are a UI convenience for humans, not a content container.

### Loading States / Skeletons

| | Human | Agent |
|---|-------|-------|
| **Interaction** | See skeleton, wait for content to fill in | Fetches HTML and sees whatever arrived — if skeleton, that's what they get |
| **Failure mode** | — | Agent sees a page full of empty placeholder boxes |

**The fix:** Server-render the content. This is the entire point of SSR frameworks — the HTML arrives **complete**. No loading states needed for the initial render. Use `aria-busy="true"` on dynamic sections that update after load so agents know to wait.

### Headings

| | Human | Agent |
|---|-------|-------|
| **Interaction** | Scan visually, headings are style emphasis | Use heading hierarchy as primary document navigation |
| **Failure mode** | — | Clever headings ("The Verdict") require visual context to interpret |

**The fix:** Strict hierarchy. One `<h1>` per page. Headings should be descriptive ("Stripe Agent-Native Score: 8.1/10") not clever ("The Verdict"). Agents parse headings in isolation — they should make sense without the surrounding content.

### Icons

| | Human | Agent |
|---|-------|-------|
| **Interaction** | Recognize visual glyph (hamburger, search, settings) | See nothing — SVGs are invisible to the accessibility tree |
| **Failure mode** | — | Icon-only button is a blank `<button>` with no name |

**The fix:** Always pair icons with text. `aria-label` minimum, visible text preferred.

```html
<!-- ❌ Agent sees: button (no name) -->
<button><svg>...</svg></button>

<!-- ⚠️ Minimum: agent sees "Search" -->
<button aria-label="Search"><svg>...</svg></button>

<!-- ✅ Best: agent AND human see "Search" -->
<button><svg>...</svg> Search</button>
```

---

## Testing Agent Accessibility

### Automated Checks

```bash
# Level A: Accessibility tree has all interactive elements
npx playwright test --project=accessibility

# Level A: Content extraction yields ≥ 100 words (A.10)
curl -s https://site.com | sed 's/<[^>]*>//g' | wc -w  # Should be > 100

# Level A: No noindex on agent-facing pages (A.9)
curl -s https://site.com | grep -i 'noindex'  # Should return nothing

# Level A: Meta description is substantive (A.11)
curl -s https://site.com | grep -oP '(?<=<meta name="description" content=")[^"]+' | wc -w  # Aim for > 8 words

# Level AA: Structured data present
curl -s https://site.com | grep 'application/ld+json'

# Level AA: SSR content present
curl -s https://site.com | grep '<h1>'  # Content in source, not just JS

# Level AA: Discovery files return 200 (AA.11)
curl -s -o /dev/null -w "%{http_code}" https://site.com/robots.txt    # Should be 200
curl -s -o /dev/null -w "%{http_code}" https://site.com/sitemap.xml   # Should be 200
curl -s -o /dev/null -w "%{http_code}" https://site.com/llms.txt      # Should be 200

# Level AAA: llms.txt exists and is substantial
curl -s https://site.com/llms.txt | wc -w  # More than a stub

# Visual regression: screenshot comparison
npx playwright screenshot https://site.com --full-page
```

### Manual Agent Testing Protocol

1. **DOM Channel Test:** Take accessibility snapshot. Can you identify all interactive elements and their purposes?
2. **Visual Channel Test:** Take screenshot. Can a vision model describe every actionable element?
3. **HTML Channel Test:** Fetch raw HTML. Is the content present without JavaScript?
4. **Selector Stability Test:** Deploy a code change. Do your selectors still work?
5. **Flow Completion Test:** Can an agent complete a key flow (search, navigate, submit) using only the accessibility tree?

### Scoring (for AN Score integration)

Each AAG level maps to a score component:

| Level | Score Range | Label |
|-------|------------|-------|
| Fails Level A | 0–3 | Agent Hostile |
| Level A | 4–5 | Agent Parseable |
| Level AA | 6–7 | Agent Navigable |
| Level AAA | 8–10 | Agent Native |

---

## The Intersection: ADA Compliance ∩ Agent Accessibility

Here's the insight that ties it together: **Most ADA best practices are also agent accessibility best practices.** Semantic HTML, ARIA labels, keyboard navigability, alt text, heading hierarchy — all of these serve both screen readers AND agents.

This means:
- Sites that are ADA compliant are already partially agent-accessible
- Agent accessibility testing can piggyback on existing a11y testing tools
- Improving agent accessibility often improves human accessibility too
- The divergence is in AAA: API parity, `llms.txt`, `agent-flows.json`, and token efficiency are agent-specific

**The metaphor:** ADA compliance assumes the user is human but may have different abilities. AAG assumes the user may not be human at all.

---

## Applying AAG to Rhumb

Rhumb itself should be Level AAA compliant — we're literally building for agents.

### Current Status (self-audit)

| Guideline | Status | Notes |
|-----------|--------|-------|
| A.1 Semantic HTML | ✅ | All buttons are `<button>`, links are `<a>` |
| A.2 Alt text | ⚠️ | OG images lack alt text in some routes |
| A.3 Heading hierarchy | ✅ | Single `<h1>` per page, logical h2/h3 |
| A.4 Form labels | ✅ | Search input has `aria-label` |
| A.5 Link text | ✅ | No "click here" — all links are descriptive |
| A.6 No hover-only content | ✅ | All content visible without hover |
| A.7 Error messages in DOM | ⚠️ | Need to verify error states |
| A.8 Loading states | ⚠️ | Need `aria-busy` on dynamic content |
| A.9 No noindex | ✅ | No `noindex` on any page |
| A.10 Content ≥ 100 words | ✅ | Homepage ~1,100 words, service pages ~2,700 words server-rendered |
| A.11 Substantive meta descriptions | ✅ | All pages have descriptive meta tags (30-160 chars) |
| A.12 Icons paired with text | ✅ | All buttons have visible text or `aria-label` |
| A.13 Descriptive headings | ✅ | Headings describe content, not just styling |
| AA.1 Stable selectors | ⚠️ | Need `data-testid` on key elements |
| AA.2 Predictable URLs | ✅ | `/service/[slug]`, `/leaderboard/[category]` |
| AA.3 Machine-readable dates | ⚠️ | "12 minutes ago" lacks `datetime` attr |
| AA.4 SSR | ✅ | Astro SSR on all dynamic routes, SSG on static pages |
| AA.5 No CAPTCHA | ✅ | Public read, no bot detection |
| AA.6 Structured data | ⚠️ | Need JSON-LD on service pages |
| AA.7 Consistent layout | ✅ | Same nav/content/footer on all pages |
| AA.8 Dismissible modals | ✅ | No modals currently |
| AA.9 Pagination | ✅ | Leaderboard uses categories, not infinite scroll |
| AA.10 Table headers | ⚠️ | Leaderboard is cards, not tables — need scope if we add tables |
| AA.11 Discovery files 200 | ✅ | `robots.txt`, `sitemap.xml`, `llms.txt` all return 200 |
| AA.12 No script loaders | ✅ | No Rocket Loader or deferred-all-content patterns |
| AA.13 Static nav links | ✅ | Full `<nav>` rendered in Astro; hamburger is React island enhancement |
| AA.14 Server-rendered search URL | ✅ | `/search?q=` returns SSR results |
| AA.15 Native HTML disclosure | ⚠️ | Service pages use sections, not tabs — but no `<details>` yet |
| AA.16 Tabular data uses `<table>` | ⚠️ | Leaderboard is cards — could add `<table>` alongside |
| AA.17 Direct URL for all content | ✅ | No modal-only content anywhere |
| AAA.1 API parity | ✅ | MCP + CLI cover everything web shows |
| AAA.2 llms.txt | ✅ | Already at `/llms.txt` |
| AAA.3 data-testid everywhere | ❌ | Not yet implemented |
| AAA.4 Event-driven state | ❌ | No `data-state` attributes |
| AAA.5 Webhooks/SSE | ❌ | Not yet implemented |
| AAA.6 Multi-modal content | ⚠️ | Score badges use color — need text fallback |
| AAA.7 Token-efficient | ✅ | Clean structure, minimal nesting |
| AAA.8 agent-flows.json | ❌ | Not yet implemented |
| AAA.9 No-JS graceful degradation | ✅ | Astro serves complete HTML; JS islands enhance, not gate |
| AAA.10 No anti-automation | ✅ | No bot detection |
| AAA.11 Three-level degradation | ✅ | Astro default = level 2 (HTML only); JSON-LD + meta = level 3 |

### Priority Fixes for Rhumb
1. Add `data-testid` attributes to all interactive elements
2. Add JSON-LD structured data on service and leaderboard pages
3. Add `datetime` attributes to all relative time displays
4. Create `agent-flows.json` describing search and navigation flows
5. Add `data-state` attributes to track UI state for monitoring agents

---

## Future: AAG as an AN Score Dimension

This framework becomes a new dimension in the AN Score — **Web Agent Accessibility**. For services that have web interfaces (dashboards, admin panels, signup flows), we can score:

- Can an agent navigate the dashboard?
- Can an agent complete setup/onboarding?
- Can an agent extract data from the UI when the API is down?
- How many interaction channels does the site support?

This is especially relevant for the **Access layer** — when Rhumb needs to provision an account, the signup flow's agent accessibility directly impacts provisioning reliability.

---

*Version 0.3 — Pedro Nunes, Rhumb — 2026-03-14*
*Inspired by WCAG 2.1, ADA Section 508, and real-world agent failures.*
*v0.2: 6 new guidelines (A.9–A.11, AA.11–AA.12) and 4 anti-patterns from the Ramp Agent Cards audit.*
*v0.3: Agent-Native UI Element Reference — 8 new guidelines (A.12–A.13, AA.13–AA.17, AAA.11), 7 new anti-patterns, and a complete reference for how every major UI element changes for agent-native design.*
