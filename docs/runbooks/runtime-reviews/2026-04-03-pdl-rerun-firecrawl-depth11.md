# Runtime review loop — PDL fix-verify rerun + Firecrawl depth-11 publication + secrets expansion

Date: 2026-04-03 (~15:52 PT)
Owner: Pedro / Keel runtime review loop
Priority: Mission 0 fix-verify first (PDL), then Mission 1 freshness pass (Firecrawl), then Mission 2 discovery (secrets)

---

## Mission 0 — mandated PDL rerun

**Context:** PDL slug-normalization fix shipped in commit `94c8df8`. This run explicitly required a live rerun first.

### Execution

- Script: `scripts/runtime_review_pdl_fix_verify_20260401.py`
- Run: `railway run -s rhumb-api packages/api/.venv/bin/python scripts/runtime_review_pdl_fix_verify_20260401.py`
- Capability: `data.enrich_person`
- Input: `https://www.linkedin.com/in/satyanadella/`
- Credential mode: `rhumb_managed`

### Result

- Estimate: **200** (attempt `1`)
- Rhumb execute: **200**
- Provider used: **`people-data-labs`**
- Rhumb upstream: **402**
- Direct provider control: **402**
- Error message parity: **exact match**
  - `You have hit your account maximum for person enrichment (all matches used)`
- Execution ID: `exec_41c18f8c98cf42b99043f381d33bc54b`
- control_quota_blocked: `true`

### Verdict

**PASS.** Commit `94c8df8` still holds in production. Canonical slug `people-data-labs` resolves correctly through Rhumb Resolve. The only blocker is provider quota exhaustion, not a Rhumb execution-layer regression.

No Rhumb-side investigation or fix was required in this run.

### Artifact

`artifacts/runtime-review-pass-20260403T225345Z-pdl-fix-verify-20260401b.json`

---

## Mission 1 — Firecrawl freshness pass to depth 11

### Why Firecrawl was selected

- Fresh callable inventory query (`GET /v1/proxy/services`) still showed **16 callable providers**.
- Pre-pass callable coverage audit showed the weakest claim-safe bucket at depth **10**.
- PDL was already handled under Mission 0, so it was skipped for Mission 1 selection.
- After skipping PDL, **Firecrawl** was the freshness-ordered oldest remaining provider in the weakest bucket:
  - `firecrawl` — freshest evidence `2026-03-31T20:12:37Z`
- Therefore Firecrawl was the honest next Mission 1 target.

Pre-pass coverage artifact: `artifacts/callable-review-coverage-2026-04-03-pre-current-pass-from-cron-1552.json`

### Rhumb execution

- Script: `scripts/runtime_review_firecrawl_depth11_20260403.py`
- Run:
  - `packages/api/.venv/bin/python -m py_compile scripts/runtime_review_firecrawl_depth11_20260403.py`
  - `railway run -s rhumb-api packages/api/.venv/bin/python scripts/runtime_review_firecrawl_depth11_20260403.py`
- Capability: `scrape.extract`
- Provider: `firecrawl`
- Target URL: `https://example.com`
- Formats: `markdown`
- Credential mode: `rhumb_managed`
- Post-grant delay: `5` seconds
- Estimate: **200**
- Rhumb execute: **200**
- Execution ID: `exec_b51f19a3a1be4df6b3c6fb713223708c`

### Direct provider control

- Endpoint: `POST https://api.firecrawl.dev/v1/scrape`
- Auth: `RHUMB_CREDENTIAL_FIRECRAWL_API_KEY`
- Direct Firecrawl control: **200**

### Parity checked

- provider used
- upstream status
- scrape success
- metadata title
- metadata source URL
- markdown presence
- markdown prefix content

### Observed parity

Rhumb and direct control matched exactly on:
- provider used: `firecrawl`
- upstream status: `200`
- success: `true`
- title: `Example Domain`
- source URL: `https://example.com`
- markdown presence: `true`
- markdown prefix content: **matched**

### Verdict

**PASS. Full production parity confirmed for Firecrawl `scrape.extract` through Rhumb Resolve.**

Published trust rows:
- evidence `3bed0f06-d0ab-4d88-83a0-4fc06abe07f1`
- review `8cdcdece-1287-4994-8165-cfb9be0f13bb`

### Coverage impact

- Firecrawl moved **10 → 11** claim-safe runtime-backed reviews.
- Callable floor stays **10**.
- Providers now above the floor include:
  - `e2b`
  - `brave-search`
  - `google-ai`
  - `tavily`
  - `firecrawl`
- The weakest depth-10 bucket now starts with:
  - `people-data-labs`
  - `apollo`
  - `exa`
  - `unstructured`
  - `apify`
- Freshness-ordered next honest non-PDL target is now **Apollo**.

Post-pass coverage artifact: `artifacts/callable-review-coverage-2026-04-03-post-firecrawl-depth11.json`

### Artifacts

- `artifacts/runtime-review-pass-20260403T225620Z-firecrawl-depth11.json`
- `artifacts/runtime-review-publication-2026-04-03-firecrawl-depth11.json`
- `artifacts/callable-review-coverage-2026-04-03-pre-current-pass-from-cron-1552.json`
- `artifacts/callable-review-coverage-2026-04-03-post-firecrawl-depth11.json`
- `scripts/runtime_review_firecrawl_depth11_20260403.py`

---

## Mission 2 — secrets expansion

### Why secrets was selected

Live production category counts still show **`secrets`** at only **5** providers:
- `aws-secrets-manager`
- `bitwarden-secrets`
- `doppler`
- `hashicorp-vault`
- `infisical`

That is too thin for a category agents increasingly need for governed runtime credential retrieval, machine-to-machine secret access, and read-first vault inspection.

### Added services

| Slug | Name | Score | Execution | Access | Phase 0 |
|------|------|-------|-----------|--------|---------|
| `akeyless` | Akeyless | 8.55 | 8.65 | 8.25 | Best first candidate |
| `onepassword-secrets` | 1Password Secrets Automation | 8.45 | 8.50 | 8.20 | Strong second-wave candidate |
| `google-secret-manager` | Google Secret Manager | 8.40 | 8.55 | 8.05 | Strong cloud-native wedge |
| `azure-key-vault` | Azure Key Vault | 8.30 | 8.45 | 8.00 | Enterprise cloud depth |
| `cyberark-conjur` | CyberArk Conjur | 8.10 | 8.25 | 7.85 | Enterprise governance depth |

### Best Phase 0 wedge

The cleanest first move is read-first secret access:
- `secret.get`
- `secret.version.get`
- `secret.list`

**Best first provider:** **Akeyless**

Why:
- explicit secret retrieval + metadata APIs
- cloud-agnostic normalization surface
- strong fit for agent runtime execution
- cleaner first managed wedge than cloud-IAM-specific vaults or bridge-based connector setups

### Artifacts

- `packages/api/migrations/0155_secrets_expansion_iii.sql`
- `docs/runbooks/discovery-expansion/2026-04-03-secrets-expansion-iii.md`

---

## Next honest runtime-review target

With Firecrawl lifted to depth 11, the freshness-ordered next non-PDL callable target is now **Apollo**.
