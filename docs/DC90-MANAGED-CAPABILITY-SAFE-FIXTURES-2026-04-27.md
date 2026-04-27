# DC90 Managed-Capability Safe Fixtures

Date: 2026-04-27
Owner: Pedro
Scope: fixtures for the next trusted-user managed-capability proof wave. This is an internal operator artifact, not public launch copy.

## Purpose

Fresh hosted proof now exists for the first safe managed rails:

- `ai.embed` via `google-ai`
- `document.search` via `algolia`
- `scrape.extract` via `scraperapi`
- `data.enrich` via `ipinfo`

This file defines the next safe fixture set for managed capabilities that were skipped because they can create side effects, touch customer resources, burn unbounded cost, or require tenant-owned files/indexes/channels/sandboxes. Do **not** run these until the fixture’s gate is satisfied.

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

### Perplexity text generation

- Capability/provider: `ai.generate_text` / `perplexity`
- Safety class: `green`
- Gate: estimate returns HTTP 200 and selected provider `perplexity`.
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
    "model": "gemini-2.0-flash",
    "contents": [
      {
        "role": "user",
        "parts": [{"text": "Return exactly: dc90-google-ai-text-ok"}]
      }
    ],
    "generationConfig": {
      "temperature": 0,
      "maxOutputTokens": 16
    }
  }
}
```

- Pass condition: HTTP 200, upstream 200, response contains `dc90-google-ai-text-ok`, receipt id present.
- Stop condition: model/path mismatch, provider unavailable, or response omits generated text.

### Emailable single-email verification

- Capability/provider: `email.verify` / `emailable`
- Safety class: `green`
- Gate: use only non-deliverable documentation domains; do not verify real user addresses.
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

### Algolia autocomplete / product search

- Capability/providers: `search.autocomplete`, `ecommerce.search_products` / `algolia`
- Safety class: `amber`
- Required sandbox: Rhumb-owned read-only index with stable fixture records. Current proven index: `services`; do not mutate it.
- Payload template:

```json
{
  "body": {
    "index": "services",
    "query": "rh",
    "hitsPerPage": 1
  }
}
```

- Pass condition: HTTP 200, one or more fixture hits, receipt id present.
- Do not run `search.index` until a disposable index name and cleanup step are defined.

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
- Payload template: TBD after confirming the route’s multipart/body adapter expectations.
- Pass condition: HTTP 200, parsed fixture text only, receipt id present.
- Stop condition: route cannot attach file safely or provider requires public document URL.

### Mindee financial document extraction

- Capability/providers: `document.extract_fields`, `invoice.extract` / `mindee`
- Safety class: `amber`
- Required sandbox: synthetic invoice/receipt PDF with fake company/person data; no real financial documents.
- Payload template: TBD after confirming multipart adapter expectations.
- Pass condition: HTTP 200, extracted fake fields only, receipt id present.
- Stop condition: provider stores documents longer than expected or fixture cannot be marked synthetic.

### E2B code/sandbox rails

- Capability/providers: `compute.execute_code`, `code.format`, `code.lint` / `e2b`
- Safety class: `amber`
- Required sandbox: hard cost ceiling and no network/file side effects.
- Payload template:

```json
{
  "body": {
    "code": "print('dc90-e2b-ok')",
    "language": "python",
    "timeout_ms": 3000
  }
}
```

- Pass condition: HTTP 200, output contains `dc90-e2b-ok`, receipt id present, sandbox terminates.
- Do not run `compute.create_sandbox`, `agent.spawn`, or long-lived status checks until lifecycle cleanup is proven.

## Red fixtures — do not run without exact approval

These can notify real users, mutate external systems, create durable resources, or incur unbounded cost. They remain skipped until Tom approves exact target resources and payloads.

| Capability/provider | Risk | Required approval artifact |
| --- | --- | --- |
| `email.send`, `email.template` / Resend or Postmark | Sends external email. | Named Rhumb-owned recipient, subject/body, and send window. |
| `push_notification.send`, `push_notification.send_to_user`, `push_topic.publish` / Airship | Sends push notifications or touches messaging audiences. | Rhumb-owned app/channel, test audience/tag, validation-only flag or explicit send approval. |
| `search.index` / Algolia | Writes to an index. | Disposable index name, fixture object, cleanup command, max writes. |
| `scrape.crawl`, `browser.crawl` / Firecrawl, Apify, ScraperAPI | Multi-page crawl/spend risk. | Domain allowlist, max pages/depth, robots/policy check, spend ceiling. |
| `ai.generate_image`, `ai.edit_image`, speech/transcription rails | Media generation/upload and cost/safety risk. | Prompt/file fixture, content policy check, max tokens/duration/size. |
| Apollo/PDL person/company/contact search | Personal/company data enrichment. | Synthetic or explicitly approved lookup target; no private person lookup by default. |
| Google Maps/Places directions/search | External quota and location sensitivity. | Public fixture addresses, max result count, no real user addresses. |
| Long-lived E2B agent/sandbox rails | Durable compute/resource leak. | Sandbox lifecycle cleanup proof and spend ceiling. |

## Expansion sequence recommendation

1. Run green fixtures one at a time, with estimate before each execute.
2. Add successful green receipts/artifacts back to the pilot readiness packet.
3. Define and commit the missing amber fixtures before running amber smokes.
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
