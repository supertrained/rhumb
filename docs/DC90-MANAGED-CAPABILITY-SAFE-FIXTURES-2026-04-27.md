# DC90 Managed-Capability Safe Fixtures

Date: 2026-04-27
Owner: Pedro
Scope: fixtures for the next trusted-user managed-capability proof wave. This is an internal operator artifact, not public launch copy.

## Purpose

Fresh hosted proof now exists for the first safe managed rails:

- `ai.embed` via `google-ai`
- `document.search`, `search.autocomplete`, `ecommerce.search_products`, and disposable `search.index` via `algolia`
- `scrape.extract` via `scraperapi`
- `data.enrich` via `ipinfo`
- `ai.generate_text` via `replicate`, `google-ai`, and `perplexity`
- IPinfo aliases: `geo.lookup`, `identity.lookup`, and `timezone.get_info`
- `media.transcribe` and `video.subtitle` via `deepgram` on a tiny Rhumb-generated audio fixture

This file defines the next safe fixture set for managed capabilities that were skipped because they can create side effects, touch customer resources, burn unbounded cost, or require tenant-owned files/indexes/channels/sandboxes. Do **not** run these until the fixture’s gate is satisfied.

## Follow-up classification from the 2026-04-27 matrix

- **Replicate `ai.generate_text`: real fixture gap, now safe to retry after code deploy.** The failing smoke sent only `input.prompt` to `POST /v1/predictions`; Replicate requires an immutable `version`. The managed executor now defaults bare `ai.generate_text` smokes to the same low-cost text model version used by prior runtime-review harnesses, while preserving explicit caller versions. Fresh hosted proof exists at `artifacts/dc90-replicate-ai-generate-text-smoke-20260427T223542Z.json`: Rhumb returned HTTP 200, Replicate accepted the prediction with upstream 201, and receipt `rcpt_eb888ecd4fd24df49f3ea77e` was emitted. Treat this as async prediction-acceptance proof, not completed text-output proof.
- **E2B fake `agent.get_status`: expected negative, not provider failure.** `sandboxId=sbx_rhumb_smoke_missing` correctly reached E2B and returned upstream `400 Invalid sandbox ID`. A real pass requires creating a short-lived sandbox, reading its status, and deleting it in `finally`; do not classify a missing sandbox as a managed-execution failure.
- **E2B lifecycle is now proved with a short-TTL cleanup fixture.** `scripts/dc90_e2b_lifecycle_smoke.py` created exactly one `base` sandbox through Rhumb-managed `agent.spawn`, read status once through Rhumb-managed `agent.get_status`, attempted direct E2B cleanup, and verified the sandbox was gone through a final Rhumb-managed status check. Artifact: `artifacts/dc90-e2b-lifecycle-smoke-20260428T043835Z.json`; receipts: create `rcpt_47d1279339aa40c2a28c5f32`, status `rcpt_df30f498545645329354f0ad`, cleanup verification `rcpt_a30566b1c9a64f63a7bb2c3a`.
- **PDL `data.enrich_person`: expected negative no-match, not provider failure.** `not-a-real-person@rhumb.dev` reached People Data Labs and returned upstream `404 No records were found matching your request` after debiting about `$0.12`. It proves Rhumb credits/auth/path work, but it is not a green positive-match fixture and should not be rerun casually.
- **Known PDL match caveat:** older runtime-review scripts use `https://www.linkedin.com/in/satyanadella/` as a known public match. That is an existing documented fixture, but it is not a Rhumb-owned/consented internal person. For pilot-safe positive proof, use a consented internal test person already visible to PDL, or get explicit approval for a public-person lookup before spending more PDL credits.

## Safety classes

| Class | Meaning | Run posture |
| --- | --- | --- |
| `green` | Read-only or bounded compute against public/synthetic data. | May run with dogfood governed key after estimate. |
| `amber` | Bounded side effect in Rhumb-owned sandbox/test resource. | Run only after named sandbox/resource is confirmed. |
| `red` | External recipient/user impact, unbounded crawl/agent spawn, production write, or sensitive upload. | Do not run until Tom approves the exact target and payload. |

## Required preflight for every fixture

1. `GET /v1/capabilities/{capability_id}/resolve?credential_mode=rhumb_managed`
2. `GET /v1/capabilities/{capability_id}/execute/estimate?provider={provider}&credential_mode=rhumb_managed`
3. Confirm estimate is within the dogfood budget and the selected provider matches the fixture.
4. Execute once with `X-Rhumb-Key` from the funded dogfood org.
5. Store request/response JSON in `artifacts/` with timestamp, receipt id, upstream status, and redacted payload.

## Green fixtures — safe next candidates

These are the next lowest-risk managed rails because they use public/synthetic inputs and avoid writes to external recipients.

### Gemini 2.0 text model caveat

`gemini-2.0-flash` now returns upstream `404 NOT_FOUND` for the hosted managed credential. Use `gemini-2.5-flash` plus `generationConfig.thinkingConfig.thinkingBudget=0` for tiny deterministic smokes; otherwise Gemini 2.5 can spend a low output cap on thinking tokens and return `MAX_TOKENS` without text.

### Perplexity text generation

- Capability/provider: `ai.generate_text` / `perplexity`
- Safety class: `green`
- Gate: estimate returns HTTP 200 and selected provider `perplexity`.
- Status: fresh hosted proof exists at `artifacts/dc90-perplexity-ai-generate-text-smoke-20260428T013346Z.json` with receipt `rcpt_dc93ef3e731042d5815e9e5a`.
- Payload:

```json
{
  "body": {
    "model": "sonar",
    "messages": [
      {"role": "system", "content": "Answer in one sentence."},
      {"role": "user", "content": "What is Rhumb in this test context?"}
    ],
    "max_tokens": 60,
    "temperature": 0
  }
}
```

- Pass condition: HTTP 200, `provider_used=perplexity`, non-empty text response, receipt id present.
- Stop condition: provider unavailable, auth failure, estimated cost missing, or response lacks usage/receipt.

### Google AI text generation

- Capability/provider: `ai.generate_text` / `google-ai`
- Safety class: `green`
- Gate: estimate returns HTTP 200 and selected provider `google-ai`.
- Payload:

```json
{
  "body": {
    "model": "gemini-2.5-flash",
    "contents": [
      {
        "role": "user",
        "parts": [{"text": "Return exactly: dc90-google-ai-text-ok"}]
      }
    ],
    "generationConfig": {
      "temperature": 0,
      "maxOutputTokens": 64,
      "thinkingConfig": {"thinkingBudget": 0}
    }
  }
}
```

- Pass condition: HTTP 200, upstream 200, response contains `dc90-google-ai-text-ok`, receipt id present. Fresh hosted proof exists at `artifacts/dc90-google-ai-generate-text-smoke-gemini-25-flash-final-20260427T223651Z.json` with receipt `rcpt_1374ba9b2b6d486695e2da7b`.
- Stop condition: model/path mismatch, provider unavailable, or response omits generated text.

### Emailable single-email verification

- Capability/provider: `email.verify` / `emailable`
- Safety class: `green`
- Gate: use only non-deliverable documentation domains; do not verify real user addresses.
- Status: still blocked on hosted managed-catalog visibility as of the 2026-04-28 `scripts/dc90_managed_fixture_smoke.py` rerun. Resolve returned HTTP 200 with no `rhumb_managed` providers and estimate returned HTTP 503 `provider_not_available`; no execute was run. Latest artifact: `artifacts/dc90-managed-fixture-smoke-20260428T033602Z.json`. Migration `0164_emailable_managed_visibility_repair.sql` re-asserts the Emailable managed rows; rerun this fixture only after deploy/migration convergence.
- Payload:

```json
{
  "body": {
    "email": "pilot-fixture@example.com"
  }
}
```

- Pass condition: HTTP 200 or provider-level validation result, no outbound email sent, receipt id present.
- Stop condition: provider attempts a send, asks for mailbox ownership, or reports unexpected billing tier.

### IPinfo alternate lookup aliases

- Capability/providers: `geo.lookup`, `identity.lookup`, `network.ip_check`, `timezone.get_info` / `ipinfo`
- Safety class: `green`
- Gate: reuse public resolver IP `8.8.8.8`; do not use real user IPs.
- Status: `geo.lookup`, `identity.lookup`, and `timezone.get_info` all have fresh hosted proof from 2026-04-28 with receipts `rcpt_03cc9528eab942d38546d146`, `rcpt_943805616c38406eb0b6f46a`, and `rcpt_70b5a400a1f9473690225863`. `network.ip_check` already passed in the broader 2026-04-27 matrix.
- Payload:

```json
{
  "body": {
    "ip": "8.8.8.8"
  }
}
```

- Pass condition: HTTP 200, `provider_used=ipinfo`, response includes `ip=8.8.8.8`, receipt id present.
- Stop condition: output differs materially from already-proven `data.enrich` behavior or reveals request-origin IP.

## Amber fixtures — require named sandbox/resource first

### Algolia autocomplete / product search / disposable index write

- Capability/providers: `search.autocomplete`, `ecommerce.search_products`, `search.index` / `algolia`
- Safety class: `amber`
- Required sandbox: Rhumb-owned read-only index with stable fixture records. Current proven index: `rhumb_test`; do not mutate stable fixture records. (`document.search` also normalizes the placeholder `services` to `rhumb_test`, but autocomplete/product search fixtures should name `rhumb_test` directly.)
- Status: fresh hosted proof exists for both read-only amber fixtures and one disposable write fixture. `search.autocomplete` passed at `artifacts/dc90-algolia-search-autocomplete-smoke-20260428T023421Z.json` with receipt `rcpt_2a697ac7913b478884ca1acd`; `ecommerce.search_products` passed at `artifacts/dc90-algolia-ecommerce-search_products-smoke-20260428T023421Z.json` with receipt `rcpt_67a673c149274a3699470fd9`; `search.index` passed via `scripts/dc90_managed_fixture_smoke.py` at `artifacts/dc90-managed-fixture-smoke-20260428T033602Z.json` with receipt `rcpt_ba598de8c9ec4cdd9dc045f3`, direct readback of object `dc90-smoke-20260428t033602z`, direct delete, and cleanup verification HTTP 404.
- Payload template:

```json
{
  "body": {
    "index": "rhumb_test",
    "query": "rh",
    "hitsPerPage": 1
  }
}
```

- Pass condition for read fixtures: HTTP 200, one or more fixture hits, receipt id present.
- Pass condition for `search.index`: estimate HTTP 200; Rhumb execute HTTP 200 with receipt; direct Algolia readback returns the disposable `objectID`; direct delete succeeds; cleanup verification returns HTTP 404.
- `search.index` is now proved only through `scripts/dc90_managed_fixture_smoke.py`; do not run arbitrary index writes or mutate stable fixture records.

### Firecrawl scrape / screenshot

- Capability/providers: `scrape.extract`, `scrape.screenshot`, `browser.scrape` / `firecrawl`
- Safety class: `amber`
- Required sandbox: public static URL with no login and no robots/policy ambiguity. Default candidate: `https://example.com`.
- Payload template:

```json
{
  "body": {
    "url": "https://example.com",
    "formats": ["markdown"]
  }
}
```

- Pass condition: HTTP 200, upstream 200, bounded content/screenshot artifact, receipt id present.
- Do not run crawl variants until `limit` / depth / page cap is confirmed in the provider payload.

### Unstructured document parse/extract

- Capability/providers: `document.parse`, `document.convert`, `pdf.extract_text`, `file.convert` / `unstructured`
- Safety class: `amber`
- Required sandbox: tiny Rhumb-owned fixture file committed under `fixtures/dc90/` or generated in-memory; no customer documents.
- Status: `document.parse` is now freshly proved via `scripts/dc90_unstructured_document_parse_smoke.py`. Artifact `artifacts/dc90-unstructured-document-parse-smoke-20260428T044349Z.json` shows estimate HTTP 200, execute HTTP 200 / upstream 200, receipt `rcpt_d03450f4ff5349798ad073e5`, one upstream `NarrativeText` element, and fixture token `dc90-unstructured-parse-ok` returned from the synthetic 96-byte text file.
- Payload template for the proved `document.parse` fixture:

```json
{
  "body": {
    "files": {
      "filename": "dc90-unstructured-smoke.txt",
      "content_base64": "<base64 synthetic text fixture>",
      "content_type": "text/plain"
    },
    "strategy": "fast",
    "languages": ["eng"]
  }
}
```

- Pass condition: HTTP 200, `provider_used=unstructured`, upstream 200, parsed fixture text includes only the synthetic token, receipt id present.
- Stop condition: route cannot attach file safely, provider requires public document URL, or output includes anything beyond the synthetic fixture content. `pdf.extract_text`, `file.convert`, and other document variants still need separate fixture-specific proof before pilot positioning.

### Mindee financial document extraction

- Capability/providers: `document.extract_fields`, `invoice.extract` / `mindee`
- Safety class: `amber`
- Required sandbox: synthetic invoice/receipt PDF with fake company/person data; no real financial documents.
- Payload template: TBD after confirming multipart adapter expectations.
- Pass condition: HTTP 200, extracted fake fields only, receipt id present.
- Stop condition: provider stores documents longer than expected or fixture cannot be marked synthetic.

### E2B code/sandbox rails

- Capability/providers: `agent.spawn`, `agent.get_status` / `e2b` for the next lifecycle proof; `compute.execute_code`, `code.format`, and `code.lint` remain later because the current managed configs map through sandbox creation rather than a proven code-exec adapter.
- Safety class: `amber`
- Required sandbox: hard cost ceiling, short TTL, cleanup verification, and no network/file side effects.
- Status: lifecycle proof is now fresh. `scripts/dc90_e2b_lifecycle_smoke.py` passed at `artifacts/dc90-e2b-lifecycle-smoke-20260428T043835Z.json`: `agent.spawn` returned Rhumb HTTP 200 / upstream 201 with receipt `rcpt_47d1279339aa40c2a28c5f32`; `agent.get_status` returned Rhumb HTTP 200 / upstream 200 with receipt `rcpt_df30f498545645329354f0ad`; the direct E2B delete attempt returned the provider's ambiguous 404/no-access response, and the helper then verified through Rhumb-managed status that the 10-second sandbox TTL had removed the sandbox (`upstream_status=404`, receipt `rcpt_a30566b1c9a64f63a7bb2c3a`). Treat this as lifecycle/TTL cleanup proof, not proof that the local direct E2B key can delete hosted-managed sandboxes.
- Proposed short-TTL helper flow:

1. Estimate `agent.spawn` with provider `e2b` and `credential_mode=rhumb_managed`.
2. Execute `agent.spawn` once with a tiny base template body:

```json
{
  "body": {
    "templateID": "base",
    "timeout": 10
  }
}
```

3. Extract `sandboxID` from the upstream response.
4. Execute `agent.get_status` once with that `sandboxID`.
5. In a `finally` block, attempt `DELETE https://api.e2b.app/sandboxes/{sandboxID}` directly with the E2B key. Record the delete status in the artifact.
6. Verify cleanup through Rhumb-managed `agent.get_status` until the provider returns `upstream_status=404`, because the local direct E2B key can return an ambiguous 404/no-access response for hosted-managed sandboxes.
7. Stop immediately if create fails or no `sandboxID` is returned; never create a second sandbox in the same run.

- Existing cleanup pattern: `scripts/runtime_review_e2b_depth11_20260403.py` already creates, status-checks, and directly deletes Rhumb/direct E2B sandboxes. The DC90 helper intentionally avoids direct-control duplication and uses a 10-second TTL plus managed cleanup verification for the hosted dogfood path.
- Future code-exec payload, after lifecycle cleanup is proven:

```json
{
  "body": {
    "code": "print('dc90-e2b-ok')",
    "language": "python",
    "timeout_ms": 3000
  }
}
```

- Pass condition: create returns upstream 201, status returns upstream 200, receipt ids are present for both Rhumb calls, and cleanup is verified by either direct delete success or final Rhumb-managed status returning upstream 404.
- Do not run arbitrary code execution or long-lived agent variants until the lifecycle helper has a fresh cleanup artifact.

## Side-effect/resource fixture inventory

| Surface | Can test with existing owned fixture now? | Minimal safe fixture / blocker |
| --- | --- | --- |
| `email.send`, `email.template` / Resend or Postmark | **No.** Keys are configured and `email.track` passed, but no committed owned recipient/template fixture is documented here. | Named Rhumb-owned recipient inbox, verified sender/domain, exact subject/body, idempotency key, and one-message cap. |
| `communication.send_message` / Slack | **Not yet.** Prior Slack runtime reviews prove `auth.test`; no dedicated channel ID is documented for managed send. | Rhumb-owned smoke channel, bot membership, explicit channel ID, single `[dc90-smoke]` message, delete/update cleanup if supported. |
| `search.index` / Algolia | **Yes, through helper only.** The owned `rhumb_test` index exists; read fixtures and one disposable write/read/delete pass are proven. | Use `scripts/dc90_managed_fixture_smoke.py` to write objectID `dc90-smoke-{timestamp}` into `rhumb_test`, read it back, delete it, and verify cleanup. Do not mutate existing fixture records. |
| `document.parse` / Unstructured | **Yes, through helper only.** The helper generates a 96-byte synthetic text fixture in-memory and verifies the returned text token. | Use `scripts/dc90_unstructured_document_parse_smoke.py`; do not upload customer documents. `pdf.extract_text`, `file.convert`, and other document variants still need separate tiny fixtures. |
| `media.transcribe`, `video.subtitle` / Deepgram | **Yes, through helpers only.** The Rhumb-generated 2.45s WAV fixture is committed at `packages/astro-web/public/fixtures/dc90/dc90-deepgram-transcribe-ok.wav`; both helpers default to the raw GitHub URL while static-site deploy convergence can lag. | For `media.transcribe`, use `scripts/dc90_deepgram_media_transcribe_smoke.py`; pass condition is upstream 200, receipt id present, and transcript contains `deepgram` + `transcribe`. For `video.subtitle`, use `scripts/dc90_deepgram_video_subtitle_smoke.py`; pass condition is upstream 200, receipt id present, transcript contains `deepgram` + `transcribe`, and the response includes word-level start/end timings that can form a VTT cue. |
| `media.generate_speech` / ElevenLabs/OpenAI/Deepgram | **Partially.** ElevenLabs tiny TTS has fresh proof; broader speech rails still need provider-specific caps. | Tiny text (`"OK"`), fixed low-cost voice/model, max one generation, artifact retention/deletion policy. |
| `ai.generate_image`, `ai.edit_image` / OpenAI, Google AI, Replicate | **No.** No low-cost image prompt/reference/storage policy is committed. | One 512/1024px safe prompt, one image max, explicit budget ceiling, artifact storage/deletion plan, and no external publication. |
| PDL/Apollo person/contact enrichment | **No positive consented fixture.** Synthetic PDL no-match is expected negative; public Satya Nadella fixture exists in runtime scripts but is not consented/internal. | Consented internal test person with known match, or explicit approval for a named public-person lookup; no private prospect search by default. |

### Deepgram video subtitles

- Capability/provider: `video.subtitle` / `deepgram`
- Safety class: `amber`
- Required sandbox: the same tiny Rhumb-generated audio fixture used for `media.transcribe`; no customer media.
- Status: fresh hosted proof exists at `artifacts/dc90-deepgram-video-subtitle-smoke-20260428T064106Z.json` with receipt `rcpt_629073223cf14f3096166635`. The response included five word-level timing entries and the helper generated a VTT-shaped preview: `00:00:00.118 --> 00:00:02.243` / `dc ninety deepgram transcribe okay`.
- Helper: `scripts/dc90_deepgram_video_subtitle_smoke.py`
- Pass condition: HTTP 200, `provider_used=deepgram`, upstream 200, receipt id present, transcript contains `deepgram` + `transcribe`, and at least two words include monotonic `start` / `end` timestamps.
- Boundary: this proves subtitle-shaped timing output from a tiny audio fixture only. It is not proof of video container ingest, SRT/VTT file export, long-media readiness, diarization quality, or customer media readiness.

## Red fixtures — do not run without exact approval

These can notify real users, mutate external systems, create durable resources, or incur unbounded cost. They remain skipped until Tom approves exact target resources and payloads.

| Capability/provider | Risk | Required approval artifact |
| --- | --- | --- |
| `email.send`, `email.template` / Resend or Postmark | Sends external email. | Named Rhumb-owned recipient, subject/body, and send window. |
| `push_notification.send`, `push_notification.send_to_user`, `push_topic.publish` / Airship | Sends push notifications or touches messaging audiences. | Rhumb-owned app/channel, test audience/tag, validation-only flag or explicit send approval. |
| `search.index` / Algolia | Writes to an index. | Use the amber `rhumb_test` disposable object fixture above; no production/customer indexes. |
| `scrape.crawl`, `browser.crawl` / Firecrawl, Apify, ScraperAPI | Multi-page crawl/spend risk. | Domain allowlist, max pages/depth, robots/policy check, spend ceiling. |
| `ai.generate_image`, `ai.edit_image`, speech rails | Media generation/upload and cost/safety risk. | Prompt/file fixture, content policy check, max tokens/duration/size. |
| Apollo/PDL person/company/contact search | Personal/company data enrichment. | Synthetic or explicitly approved lookup target; no private person lookup by default. |
| Google Maps/Places directions/search | External quota and location sensitivity. | Public fixture addresses, max result count, no real user addresses. |
| Long-lived E2B agent/sandbox rails | Durable compute/resource leak. | Lifecycle proof now exists for 10-second sandbox create/status/cleanup; arbitrary code execution and long-lived variants still need a separate spend/cleanup gate. |

## Expansion sequence recommendation

1. Rerun Emailable `email.verify` after the 0164 managed-visibility repair deploys; the 2026-04-28 recheck still showed no managed providers on resolve and `provider_not_available` on estimate, so do not count it as proof.
2. Add successful receipts/artifacts back to the pilot readiness packet.
3. The disposable Algolia `search.index` write/read/delete fixture, E2B short-TTL create/status/cleanup lifecycle fixture, Unstructured `document.parse` tiny synthetic-file fixture, Deepgram `media.transcribe` tiny audio fixture, and Deepgram `video.subtitle` subtitle-shaped timing fixture are now proved. Next amber target should be a consented side-effect fixture only if exact target/resource/cleanup controls exist; do not run uncontrolled external sends, arbitrary code execution, customer documents, or long-lived compute.
4. Keep red fixtures skipped until there is a named human-approved target and payload.

## Claim guardrail

Even after all green fixtures pass, the public claim remains:

> Rhumb has fresh first-wave hosted proof for selected managed capabilities, and trusted users can start with a governed key on the proven rails.

Do not claim:

- all 68 managed configs work;
- side-effect rails are safe by default;
- anonymous managed execution;
- public launch readiness;
- `rhumb-mcp@2.0.0` is public on npm.
