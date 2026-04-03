# Runtime review loop — PDL fix-verify rerun + E2B depth-11 publication + design expansion

Date: 2026-04-03 (~04:43 PT)
Owner: Pedro / Keel runtime review loop
Priority: Mission 0 fix-verify first (PDL), then Mission 1 freshness pass (E2B), then Mission 2 discovery (design)

---

## Mission 0 — mandated PDL rerun

**Context:** PDL slug-normalization fix shipped in commit `94c8df8`. Cron mandates a live rerun every loop to confirm it still holds in production.

### Execution

- Script: `scripts/runtime_review_pdl_fix_verify_20260401.py`
- Run: `railway run -s rhumb-api packages/api/.venv/bin/python scripts/runtime_review_pdl_fix_verify_20260401.py`
- Capability: `data.enrich_person`
- Input: `https://www.linkedin.com/in/satyanadella/`
- Credential mode: `rhumb_managed`

### Result

- Estimate: **200** (2 attempts, post-grant propagation race on first attempt)
- Rhumb execute: **200**
- Provider used: **`people-data-labs`**
- Rhumb upstream: **402**
- Direct provider control: **402**
- Error message parity: **`You have hit your account maximum for person enrichment (all matches used)`** — exact match
- control_quota_blocked: `true`

### Verdict

**PASS.** Commit `94c8df8` still holds in production. Canonical slug `people-data-labs` resolves correctly through the Rhumb execution layer. The only failure mode is provider quota exhaustion, not Rhumb routing.

No Rhumb-side investigation or fix required.

### Artifact

`artifacts/runtime-review-pass-20260403T114439Z-pdl-fix-verify-20260401b.json`

---

## Mission 1 — E2B freshness pass to depth 11

### Why E2B was selected

- Fresh callable coverage audit (pre-pass) showed all 16 callable providers at claim-safe runtime-backed depth **10**
- E2B had the oldest freshest evidence timestamp: `2026-03-31T03:10:13Z`
- Per the freshness-rotation protocol, the stalest depth-10 provider is the honest next target
- PDL already receives separate fix-verification attention; skipped
- Next target: **E2B**

Pre-pass coverage artifact: `artifacts/callable-review-coverage-2026-04-03-pre-e2b-depth11.json`

### Rhumb execution

- Script: `scripts/runtime_review_e2b_depth11_20260403.py`
- Run: `railway run -s rhumb-api packages/api/.venv/bin/python scripts/runtime_review_e2b_depth11_20260403.py`
- Capabilities: `agent.spawn` + `agent.get_status`
- Provider: `e2b`
- Credential mode: `rhumb_managed`
- Post-grant delay: 5 seconds
- Estimate: **200** (1 attempt, clean — no propagation race)
- Rhumb create: **200**
- Rhumb status: **200**
- Upstream create status: **201**
- Upstream status status: **200**
- Rhumb sandbox id: `i7iqgeva261tff9atmcc4`
- Execution ids:
  - create: `exec_3bcebc01105443a1956795446b142730`
  - status: `exec_145e5dbc7d4148f891c61c8802973f38`

### Direct provider control

- Create endpoint: `POST https://api.e2b.app/sandboxes`
- Status endpoint: `GET https://api.e2b.app/sandboxes/{sandboxId}`
- Auth: `RHUMB_CREDENTIAL_E2B_API_KEY` (Railway env)
- Direct create: **201**
- Direct status: **200**
- Direct sandbox id: `ir0pk6a9z14ogj2vzoa9r`

### Parity verdict

All five comparison dimensions matched:

| Dimension | Rhumb-managed | Direct E2B | Match |
|-----------|---------------|------------|-------|
| create_template_match (alias + templateID) | `base` / `rki5dems9wqfm4r03t7g` | `base` / `rki5dems9wqfm4r03t7g` | ✅ |
| status_template_match (alias + templateID) | `base` / `rki5dems9wqfm4r03t7g` | `base` / `rki5dems9wqfm4r03t7g` | ✅ |
| status_state_match | `running` | `running` | ✅ |
| envd_version_match | `0.5.8` | `0.5.8` | ✅ |
| compute_shape_match (cpuCount + memoryMB) | 2 / 512 | 2 / 512 | ✅ |

Verdict: **PASS. Full production parity confirmed for E2B agent.spawn + agent.get_status through Rhumb Resolve.**

### Published trust rows

- evidence: `ed3e9997-4602-4bfd-97f1-89bc892d8b44`
- review: `f078af31-7bba-4a6c-97e1-e2ace068d919`

### Cleanup

- Rhumb-created sandbox delete: **204**
- Direct-control sandbox delete: **204**
- Temp review agent disabled: `ef98781c-51bb-497f-9102-de4baa26f7b1`

### Coverage impact

- E2B claim-safe runtime-backed reviews: **10 → 11**
- Total published E2B reviews: **10 → 11**
- E2B is now the deepest callable provider in the set
- All remaining 15 callable providers remain at depth 10
- Freshness-ordered next callable target: **GitHub** (oldest fresh evidence in the depth-10 bucket at `2026-04-03T06:46:51Z`)

Post-pass coverage artifact: `artifacts/callable-review-coverage-2026-04-03-post-e2b-depth11.json`

### Artifacts

- `artifacts/runtime-review-pass-20260403T114907Z-e2b-depth11.json`
- `artifacts/runtime-review-publication-2026-04-03-e2b-depth11.json`
- `artifacts/callable-review-coverage-2026-04-03-pre-e2b-depth11.json`
- `artifacts/callable-review-coverage-2026-04-03-post-e2b-depth11.json`
- `scripts/runtime_review_e2b_depth11_20260403.py`

---

## Mission 2 — design expansion

### Why design was selected

Live production category counts show **`design`** at only **4** providers (Framer, Lunacy, Penpot, Sketch API) — all UI-first or self-hosted tools without accessible API-based generation surfaces.

Design automation is high-demand for agents: template rendering, image generation, background removal, and brand-consistent asset output are increasingly core to email, content, and product workflows.

### Added services

| Slug | Name | Score | Execution | Access | Phase 0 |
|------|------|-------|-----------|--------|---------|
| `bannerbear` | Bannerbear | 8.55 | 8.70 | 8.35 | Best first candidate |
| `placid` | Placid | 8.45 | 8.55 | 8.25 | Strong second candidate |
| `canva` | Canva | 8.35 | 8.45 | 8.15 | Second-wave (OAuth) |
| `photoroom` | PhotoRoom | 8.25 | 8.40 | 8.05 | Best non-template wedge |
| `frontify` | Frontify | 8.10 | 8.20 | 7.90 | Enterprise depth (GraphQL) |

### Best Phase 0 wedges

1. **`design.template.render`** via **Bannerbear** (`POST https://sync.api.bannerbear.com/v2/images`)
   - API key only, synchronous, explicit layer override model
   - Cleanest first implementation target in the design category

2. **`image.edit.background_remove`** via **PhotoRoom** (`POST https://sdk.photoroom.com/v1/segment`)
   - API key only, multipart upload, base64 or URL output
   - Orthogonal to template rendering; covers product photo automation

### Artifacts

- `packages/api/migrations/0153_design_expansion.sql`
- `docs/runbooks/discovery-expansion/2026-04-03-design-expansion.md`

---

## Next honest runtime-review target

With E2B now at depth 11 and all other callable providers at depth 10, the freshness-ordered next non-PDL callable target is **GitHub** (freshest evidence at `2026-04-03T06:46:51Z`, the oldest in the depth-10 set).
