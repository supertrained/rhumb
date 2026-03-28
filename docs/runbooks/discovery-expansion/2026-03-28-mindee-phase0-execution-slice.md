# Mindee Phase 0 execution slice — 2026-03-28

Owner: Pedro
Status: shipped in product main as the next honest unblocked execution wedge

## Why this lane now

The original telemetry → dogfood → Google AI → callable-review chain is done:
- telemetry MVP is live
- the repeatable dogfood harness is shipped
- Google AI managed wiring is live and rerun-verified
- the callable-review floor is now 2 runtime-backed reviews across all 16 callable providers

That means the old chain is no longer the active build choice.

From the current priority stack:
- **x402 live buyer proof** is still blocked outside code by recovery of the funded Awal buyer wallet identity
- **Airship live proof** still depends on the credential / audience lane being available honestly
- **Emailable runtime proof** remains credential-gated in this environment

So the correct move was to take the next clean document-processing bridge that was already called out in the discovery notes: **Mindee**.

## Why Mindee specifically

The document-processing expansion work already established three truths:
1. document processing is underweight relative to demand
2. Mindee is the strongest immediate execution candidate in the category
3. the cleanest honest wedge is structured extraction, not a fake universal workflow layer

Mindee is a good first bridge because it offers:
- explicit document extraction endpoints
- simple token auth
- a concrete multipart upload contract
- provider-native structured outputs that are useful immediately without pretending Rhumb already has a universal document schema

## What shipped

### Managed execution wiring
- `document.extract_fields` → `POST /v1/products/mindee/financial_document/v1/predict`
- `invoice.extract` → `POST /v1/products/mindee/financial_document/v1/predict`

### Capability truth
This is a **Phase 0 provider-backed extraction slice**.

It does **not** claim:
- universal document extraction across every document type
- normalized invoice outputs beyond what Mindee actually returns
- asynchronous job orchestration or polling semantics

It **does** claim:
- if the caller uploads a document and a valid Mindee credential exists,
  Rhumb can forward the file to Mindee's financial-document parser and return
  Mindee's real extraction payload

### Input contract
The Rhumb-managed executor now accepts JSON-native multipart descriptors and translates them into Mindee's provider-native multipart upload shape.

Accepted caller aliases:
- `document`
- `file`
- `files`

Normalized upstream field:
- `document`

Auth contract:
- `Authorization: Token <api_key>`

## Why this slice is honest

The key design choice was to avoid inventing a fake generic IDP abstraction.

Instead:
- the capability names are useful and legible to agent callers
- the execution contract stays narrow and concrete
- the return payload remains provider-native for now

That preserves truth while still making the provider executable through Resolve.

## What did not ship

- no runtime-backed public review yet
- no broader receipt / ID / passport surface yet
- no universal field normalization layer
- no async polling abstraction for Mindee v2 job flows

Those are later slices, not prerequisites for this one.

## Recommended next move from here

1. If a Mindee credential is available, run a controlled proof on `invoice.extract` first using a low-risk sample invoice.
2. Confirm the provider response shape is stable enough to publish a runtime-backed evidence / review pair.
3. If the proof is clean, add the next narrow document-processing wedge rather than broad category sprawl.

## Net

**The old sequence is complete, so this loop advanced the next real unblocked item instead of replaying already-shipped work.**

Mindee is now executable through Rhumb on a tight, honest Phase 0 contract:
- upload a document
- route it through Resolve
- get Mindee's structured extraction payload back
