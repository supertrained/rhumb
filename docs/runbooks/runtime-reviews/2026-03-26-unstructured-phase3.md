# Runtime Review: Unstructured Phase 3

**Date:** 2026-03-26
**Reviewer:** Pedro (build loop)
**Status:** ✅ VERIFIED

## Summary
Unstructured managed execution verified end-to-end in production via Rhumb Resolve.

## Tests Run

### 1. document.convert (rhumb_managed)
- **Request:** `POST /v1/capabilities/document.convert/execute` with `provider=unstructured`, `credential_mode=rhumb_managed`
- **Payload:** Base64-encoded text file via JSON file descriptor
- **Result:** 200 OK, 376.8ms
- **Output:** Single `NarrativeText` element correctly parsed

### 2. document.parse (rhumb_managed)
- **Request:** `POST /v1/capabilities/document.parse/execute` with same pattern
- **Payload:** Multi-paragraph text file
- **Result:** 200 OK, 363.4ms
- **Output:** Two `NarrativeText` elements correctly parsed

### 3. Direct Unstructured API (parity check)
- **Request:** `POST https://api.unstructuredapp.io/general/v0/general` with multipart file upload
- **Result:** 200 OK
- **Output:** Same two `NarrativeText` elements — exact structural parity with Rhumb proxy

## Bugs Found & Fixed

### Bug 1: httpx AsyncClient multipart sync/async conflict
- **Symptom:** 500 Internal Server Error when executing Unstructured via managed path
- **Root cause:** `httpx.AsyncClient.request()` with both `data` and `files` parameters triggers a synchronous multipart encoder that raises `RuntimeError: Attempted to send an sync request with an AsyncClient instance`
- **Fix:** Merged form-data fields into the `files` list as `(field_name, (None, value_bytes, "text/plain"))` tuples
- **Commit:** `6446d80`

### Bug 2: document.parse missing from capability_services
- **Symptom:** Estimate endpoint returns 503 "No providers configured for capability 'document.parse'"
- **Root cause:** `document.parse` existed in `rhumb_managed_capabilities` but not in `capability_services`. The execution code path queries `capability_services` first.
- **Fix:** Migration 0099 syncs both tables. Also added `document.extract` to `rhumb_managed_capabilities` and ensured all Unstructured entries include `rhumb_managed` credential mode.
- **Commit:** `6446d80`

## Coverage
- **16/16 callable providers now Phase-3-verified** (Unstructured was the last holdout)
- All 7 Unstructured capabilities accessible via Rhumb-managed execution
- Evidence: `ev_6d9917b1ca2b`
- Review: `rev_45d3309e103a`
