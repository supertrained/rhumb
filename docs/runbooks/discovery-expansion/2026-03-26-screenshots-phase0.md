# Discovery Expansion — Screenshots Category

Date: 2026-03-26
Operator: Pedro / Keel runtime loop
Status: completed

## Why this category

`screenshots` was underrepresented in the live catalog despite being a practical agent workflow primitive. Agents regularly need URL → image capture for QA, preview generation, monitoring, compliance evidence, and browser fallback workflows, but the category only had four services before this pass.

## Services added

| Service | Slug | Score | Tier | Notes |
|---|---|---:|---|---|
| ApiFlash | `apiflash` | 7.4 | Ready | Chrome-based screenshot API with full-page, mobile, ad blocking, cookie-banner handling |
| Screenshot Machine | `screenshotmachine` | 6.8 | Ready | Straightforward screenshot API with device selection and full-page support |
| screenshotlayer | `screenshotlayer` | 6.5 | Ready | Mature screenshot API with viewport/full-height parameters and HTTPS |
| URL2PNG | `url2png` | 6.9 | Ready | Screenshot-as-a-service with viewport control, UA overrides, and CSS injection |

## Scoring approach

These additions were scored from documentation, auth surface, pricing posture, and integration shape using the current catalog scoring lane. Probe metadata was recorded as:
- runner: `pedro-manual-docs`
- evidence types: docs / pricing / auth
- freshness: 24 hours

## Phase 0 Resolve assessment

This category is a clean candidate for a future Resolve capability such as:
- `screenshot.capture`
- logical params: `url`, `full_page`, `viewport`, `format`
- output: image URL or binary image payload

Strong Phase 0 candidates from this batch:
1. **ApiFlash** — simple screenshot primitive, modern positioning, good fit for `url -> image` capability
2. **screenshotlayer** — direct capture endpoint and parameterized GET flow
3. **URL2PNG** — also fits the same capability shape with a narrow parameter surface

## Operator view

This is a good category to expand because it is:
- operationally useful for agents
- easy to normalize behind one capability contract
- distinct from generic scraping providers
- likely to benefit from direct runtime comparisons once screenshot execution is added to Resolve
