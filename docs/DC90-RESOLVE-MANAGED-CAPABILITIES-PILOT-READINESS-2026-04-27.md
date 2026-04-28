# DC90 Resolve Managed-Capabilities Pilot Readiness

Date: 2026-04-27
Owner: Pedro
Scope: trusted-user pilot for Resolve **Rhumb-managed capabilities**, not public launch and not broad unmanaged system-of-record rails.

## Verdict

**Small-group ready, narrowly scoped.**

Rhumb is ready for a controlled trusted-user pilot where the first task is a Rhumb-managed `search.query` call through the governed `X-Rhumb-Key` rail. This should be a **2-5 trusted-user / friend-agent pilot**, not a public launch and not a claim that all managed capabilities are equally pilot-ready.

The pilot should start with:

1. open preflight: `resolve`;
2. open preflight: `estimate`;
3. governed execution with a capped key;
4. receipt / error inspection;
5. short feedback capture on where the agent got stuck.

## Why this is ready

Live no-spend checks on 2026-04-27 show the public hosted surface still supports the managed-capability story:

- `GET /v1/capabilities/search.query/resolve` returns HTTP 200.
- `search.query` currently exposes 7 provider paths.
- Managed-capable providers surfaced for `search.query`: `exa`, `tavily`, and `brave-search-api`.
- `GET /v1/capabilities/search.query/credential-modes` returns configured `rhumb_managed` modes for `exa`, `tavily`, and `brave-search-api`.
- `GET /v1/capabilities/search.query/execute/estimate` returns HTTP 200 with concrete managed execution rail:
  - provider: `brave-search-api`
  - `credential_mode`: `rhumb_managed`
  - circuit: `closed`
  - estimated cost: `$0.003`
- `POST /v1/capabilities/search.query/execute` without auth returns HTTP 402 with machine-readable payment/auth handoff, not anonymous execution.
- `GET /v1/capabilities/rhumb-managed` returns HTTP 200 and currently lists 68 managed capability configs.

Existing Helm validation from 2026-04-25 already proved the governed-key execute path for the same pilot snippet: `search.query` executed via `brave-search-api` in `rhumb_managed` mode with upstream 200. Treat that as still useful but not a substitute for a fresh smoke immediately before sending keys.

## Fresh managed execute proof — first wave

Fresh hosted dogfood smokes on 2026-04-27 and 2026-04-28 expanded the readiness proof beyond the original `search.query` pilot rail. These were authorized `rhumb_managed` executions using tight, safe payloads and stored artifacts:

| Capability | Provider | Result | Receipt | Artifact |
| --- | --- | --- | --- | --- |
| `ai.embed` | `google-ai` | HTTP 200, upstream 200, 64-dim embedding returned | `rcpt_87fc313e37ea426c970a14a8` | `artifacts/dc90-google-ai-embed-smoke-20260427T213328Z.json` |
| `document.search` | `algolia` | HTTP 200, upstream 200, one `services` index hit returned | `rcpt_9eee236d3706468fbe566407` | `artifacts/dc90-algolia-document-search-smoke-20260427T213807Z.json` |
| `search.autocomplete` | `algolia` | HTTP 200, upstream 200, read-only `rhumb_test` autocomplete fixture returned | `rcpt_2a697ac7913b478884ca1acd` | `artifacts/dc90-algolia-search-autocomplete-smoke-20260428T023421Z.json` |
| `ecommerce.search_products` | `algolia` | HTTP 200, upstream 200, read-only `rhumb_test` product-search fixture returned | `rcpt_67a673c149274a3699470fd9` | `artifacts/dc90-algolia-ecommerce-search_products-smoke-20260428T023421Z.json` |
| `search.index` | `algolia` | HTTP 200, upstream 201, disposable `rhumb_test` object written, read back directly, deleted, and cleanup-verified 404 | `rcpt_ba598de8c9ec4cdd9dc045f3` | `artifacts/dc90-managed-fixture-smoke-20260428T033602Z.json` |
| `scrape.extract` | `scraperapi` | HTTP 200, upstream 200, `https://example.com` HTML returned | `rcpt_7cdb0b94414e47739742e1df` | `artifacts/dc90-scraperapi-scrape-extract-smoke-post-4a6aefb-20260427T214448Z.json` |
| `scrape.screenshot` | `firecrawl` | HTTP 200, upstream 200, `https://example.com` screenshot URL evidence returned | `rcpt_ed702a3ba70a47859966254a` | `artifacts/dc90-firecrawl-screenshot-smoke-20260428T074045Z.json` |
| `data.enrich` | `ipinfo` | HTTP 200, upstream 200, `8.8.8.8` enrichment returned | `rcpt_29b420541d5f492f9f28a980` | `artifacts/dc90-ipinfo-data-enrich-smoke-post-4a6aefb-20260427T214448Z.json` |
| `ai.generate_text` | `replicate` | HTTP 200, upstream 201, async prediction accepted after default-version normalization | `rcpt_eb888ecd4fd24df49f3ea77e` | `artifacts/dc90-replicate-ai-generate-text-smoke-20260427T223542Z.json` |
| `ai.generate_text` | `google-ai` | HTTP 200, upstream 200, `dc90-google-ai-text-ok` returned using `gemini-2.5-flash` | `rcpt_1374ba9b2b6d486695e2da7b` | `artifacts/dc90-google-ai-generate-text-smoke-gemini-25-flash-final-20260427T223651Z.json` |
| `ai.generate_text` | `perplexity` | HTTP 200, upstream 200, non-empty Sonar response returned | `rcpt_dc93ef3e731042d5815e9e5a` | `artifacts/dc90-perplexity-ai-generate-text-smoke-20260428T013346Z.json` |
| `geo.lookup` | `ipinfo` | HTTP 200, upstream 200, `8.8.8.8` geo response returned | `rcpt_03cc9528eab942d38546d146` | `artifacts/dc90-ipinfo-geo-lookup-smoke-20260428T013346Z.json` |
| `identity.lookup` | `ipinfo` | HTTP 200, upstream 200, `8.8.8.8` identity response returned | `rcpt_943805616c38406eb0b6f46a` | `artifacts/dc90-ipinfo-identity-lookup-smoke-20260428T013346Z.json` |
| `timezone.get_info` | `ipinfo` | HTTP 200, upstream 200, `8.8.8.8` timezone response returned | `rcpt_70b5a400a1f9473690225863` | `artifacts/dc90-ipinfo-timezone-get-info-smoke-20260428T013346Z.json` |
| `agent.spawn` + `agent.get_status` | `e2b` | HTTP 200 / upstream 201 sandbox create, HTTP 200 / upstream 200 status read, then 10-second TTL cleanup verified through managed status upstream 404 | create `rcpt_47d1279339aa40c2a28c5f32`; status `rcpt_df30f498545645329354f0ad`; cleanup verify `rcpt_a30566b1c9a64f63a7bb2c3a` | `artifacts/dc90-e2b-lifecycle-smoke-20260428T043835Z.json` |
| `document.parse` | `unstructured` | HTTP 200, upstream 200, 96-byte synthetic text fixture parsed into one `NarrativeText` element containing `dc90-unstructured-parse-ok` | `rcpt_d03450f4ff5349798ad073e5` | `artifacts/dc90-unstructured-document-parse-smoke-20260428T044349Z.json` |
| `media.transcribe` | `deepgram` | HTTP 200, upstream 200, Rhumb-generated 2.45s WAV fixture transcribed as `dc ninety deepgram transcribe okay` | `rcpt_e8987476659846739937146e` | `artifacts/dc90-deepgram-media-transcribe-smoke-20260428T053852Z.json` |
| `video.subtitle` | `deepgram` | HTTP 200, upstream 200, same tiny WAV fixture returned five word-level timing entries and a VTT-shaped cue preview | `rcpt_629073223cf14f3096166635` | `artifacts/dc90-deepgram-video-subtitle-smoke-20260428T064106Z.json` |

Emailable `email.verify` was attempted as a green fixture on 2026-04-28, but estimate returned HTTP 503 `provider_not_available` before execution because the hosted managed catalog did not expose `email.verify` / `emailable`. A later recheck after `0164` had been pushed, and the latest gated `scripts/dc90_managed_fixture_smoke.py --skip-algolia` rerun at `artifacts/dc90-emailable-recheck-20260428T064102Z.json`, still showed no `rhumb_managed` Emailable provider on resolve; the helper skipped estimate/execute to avoid repeatedly rediscovering `provider_not_available`, so Emailable remains pending until deploy/migration convergence exposes the rows.

Interpretation: the trusted-user pilot can honestly say that Rhumb-managed execution has fresh hosted proof across search-adjacent, embedding, Algolia read-only search/autocomplete/product-search plus one disposable index-write fixture, scraping, screenshot capture, IP enrichment, IP lookup aliases, text-generation rails, one short-TTL E2B sandbox lifecycle, one tiny synthetic document-parse fixture, one tiny Rhumb-generated media transcription fixture, and one subtitle-shaped Deepgram timing fixture. This is still **first-wave proof**, not a universal claim that all managed configs work.

## Pilot boundary

This is **not** ready as an unrestricted “try any managed capability” launch.

Use this exact promise:

> Resolve can give your agent a governed, capped key for supported Rhumb-managed capabilities. Start with web search: resolve the capability, estimate the active execution rail before spend, then execute with a capped governed key.

Do not promise:

- anonymous execution;
- universal managed execution across all indexed services;
- that every one of the 68 managed configs is equally polished;
- that Resolve always chooses the highest AN Score provider;
- public MEO / retrieval / citation improvement;
- `rhumb-mcp@2.0.0` availability on npm.

## Pilot cohort shape

Recommended first cohort:

- 2-5 trusted users or friend agents.
- Each gets a capped governed key, not provider credentials.
- Suggested initial cap: `$5-$10/month`, `60 qpm`.
- Start with `search.query` only for the first invite unless the user has an explicit need for one of the freshly proven rails (`ai.embed`, `ai.generate_text`, `document.search`, `search.autocomplete`, `ecommerce.search_products`, disposable `search.index`, `scrape.extract`, one-page `scrape.screenshot`, `data.enrich`, `geo.lookup`, `identity.lookup`, `timezone.get_info`, short-TTL `agent.spawn` / `agent.get_status`, synthetic-file `document.parse`, tiny-fixture `media.transcribe`, or subtitle-shaped `video.subtitle`).
- Expand only after at least one complete run includes: resolve artifact, estimate artifact, execution result, receipt/error, and user friction notes.
- Keep side-effect/resource/cost-bearing managed surfaces skipped until safe recipients, channels, indexes, sandboxes, or spend ceilings are explicitly defined.

## Operator flow

Use `docs/ONBOARD-A-FRIEND-AGENT.md` for key issuance.

For each trusted user:

1. Mint a governed key with `scripts/issue_friend_key.py`.
2. Set a low monthly budget and sane rate limit.
3. Send only:
   - `RHUMB_API_KEY=...`
   - quickstart snippet
   - the pilot boundary above
4. Ask them to paste back:
   - the resolve response if confusing;
   - the estimate response;
   - the execution status;
   - any receipt/error id;
   - the exact point their agent got stuck.

## Fresh smoke required before sending keys

Before issuing real pilot keys, run one final governed-key smoke:

```bash
API="https://api.rhumb.dev/v1"

curl "${API}/capabilities/search.query/resolve"
curl "${API}/capabilities/search.query/execute/estimate"
curl -X POST "${API}/capabilities/search.query/execute" \
  -H "X-Rhumb-Key: $RHUMB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"body":{"query":"best tools for agent web search","max_results":3}}'
```

The execute call is a paid/authorized managed execution. Run it with a dogfood governed key immediately before issuing pilot keys; store the result as the fresh readiness artifact.

## Current go / no-go

- **Go:** controlled trusted-user pilot for `search.query` managed execution through governed keys.
- **No-go:** public launch, broad unmanaged system-of-record pilot, or “all managed capabilities are ready” claim.
- **Remaining action before invites:** run a final `search.query` governed execute smoke immediately before issuing keys, then mint capped keys for named trusted users. The broader managed-capability proof above is sufficient to update pilot positioning, but it does not remove the final per-invite smoke requirement. Google AI text should use `gemini-2.5-flash` rather than stale `gemini-2.0-flash`; Replicate text proof is async prediction-acceptance proof.
- **Next expansion action:** after `0164_emailable_managed_visibility_repair.sql` deploys, rerun Emailable `email.verify`. If that remains blocked, move only to a consented side-effect fixture with exact target/resource/cleanup controls. E2B create/status/cleanup lifecycle, Unstructured `document.parse`, Deepgram `media.transcribe`, Deepgram `video.subtitle`, and Firecrawl `scrape.screenshot` are now proved, but arbitrary E2B code execution, long-lived sandboxes, customer documents, broader document variants, multi-page crawls, video-container subtitle export, and uncontrolled external sends remain out of scope until separate fixture/spend/cleanup gates exist.
