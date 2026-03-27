# Runtime Review: Unstructured Phase 3 rerun — 2026-03-26

Date: 2026-03-26
Operator: Pedro / Keel runtime loop
Status: ✅ VERIFIED

## Why Unstructured was selected

Current callable-inventory review coverage check showed Unstructured with the weakest visible runtime-backed coverage on the public review surface, so it was the right Mission 1 target even though an earlier verification run existed in internal notes.

## Tests run

### 1. Rhumb Resolve estimate
- **Request:** `GET /v1/capabilities/document.parse/execute/estimate?provider=unstructured&credential_mode=rhumb_managed`
- **Result:** 200 OK

### 2. Rhumb Resolve execute
- **Request:** `POST /v1/capabilities/document.parse/execute`
- **Provider:** `unstructured`
- **Credential mode:** `rhumb_managed`
- **Payload:** base64-encoded `.txt` file via managed multipart JSON descriptor
- **Result:** 200 OK
- **Upstream status:** 200
- **Execution id:** `exec_30363e5389c34076be501e2aa58e1b0c`
- **Output shape:** 2 parsed elements (`Title`, `NarrativeText`)

### 3. Direct control
- **Request:** `POST https://api.unstructuredapp.io/general/v0/general`
- **Transport:** direct multipart file upload
- **Result:** 200 OK
- **Output shape:** 2 parsed elements (`Title`, `NarrativeText`)

## Parity read

Resolve and direct control returned the same element count and element-type shape for the same input file:
- Rhumb: `Title`, `NarrativeText`
- Direct: `Title`, `NarrativeText`

That is sufficient parity for this Phase 3 spot check.

## Investigation outcome

No new execution bug surfaced on this rerun. The managed multipart bridge and `capability_services` sync fixes shipped earlier in `6446d80` are still holding in production.

## Conclusion

Unstructured is confirmed live in production through Rhumb Resolve on `document.parse`, with direct-provider parity revalidated.