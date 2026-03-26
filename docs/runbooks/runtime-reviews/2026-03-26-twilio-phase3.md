# Phase 3 runtime review — Twilio

Date: 2026-03-26
Owner: Pedro / Keel runtime review loop
Priority: Phase 3 callable-provider verification

## Why Twilio

After Slack and Stripe were verified, Twilio was the last unblocked BYOK provider left in the callable inventory.

Twilio was also the right fix-verify target because the public trust surface already showed legacy docs-backed rows as `🟢 Runtime-verified`, but there was still no fresh runtime-backed proof attached to a real Rhumb Resolve execution.

## Test setup

### Rhumb Resolve execution
- Endpoint: `POST /v1/capabilities/phone.lookup/execute`
- Provider: `twilio`
- Credential mode: `byo`
- Interface tag: `keel-runtime-review`
- Input:
  - `path=/v2/PhoneNumbers/+14155552671`
  - `params={"Fields":"line_type_intelligence"}`

### Direct provider control
- Endpoint: `GET https://lookups.twilio.com/v2/PhoneNumbers/+14155552671?Fields=line_type_intelligence`
- Auth: Twilio Basic Auth (`Account SID:Auth Token`)

## Investigation sequence

### Initial failing Rhumb path
Before the fix deployed, Rhumb Resolve returned:
- envelope: `200`
- upstream: `404`
- execution: `exec_4df9575bbed64f7f8273e023b796cd8a`
- upstream error: `The requested resource /v2/PhoneNumbers/+14155552671 was not found`

### Control test
Direct Twilio Lookup control against `lookups.twilio.com` returned:
- status: `200`
- valid lookup payload for `+14155552671`

### Root cause
This was a Rhumb execution-layer bug, not a provider outage:
- `phone.lookup` requests were being routed through Twilio's default proxy domain `api.twilio.com`
- Twilio Lookup v2 actually lives on `lookups.twilio.com`
- `credential-modes` metadata also lied about Twilio setup by surfacing `api_key` instead of `basic_auth`

### Fix shipped
Commit:
- `8cdd1aa` — `Fix Twilio lookup routing and auth metadata`

Code changes:
- `packages/api/routes/capability_execute.py`
  - route Twilio Lookup paths (`/v2/PhoneNumbers...`) to `https://lookups.twilio.com`
  - route Twilio Verify paths (`/v2/Services...`) to `https://verify.twilio.com`
- `packages/api/routes/capabilities.py`
  - prefer hardcoded provider auth defaults over stale capability metadata, so Twilio now reports `basic_auth` and correctly shows configured status
- Tests added:
  - `packages/api/tests/test_capability_execute.py::test_twilio_lookup_uses_lookups_domain`
  - `packages/api/tests/test_credential_modes.py::test_credential_modes_prefers_hardcoded_twilio_basic_auth`

Targeted test command:
- `pytest -q packages/api/tests/test_capability_execute.py::test_twilio_lookup_uses_lookups_domain packages/api/tests/test_credential_modes.py::test_credential_modes_prefers_hardcoded_twilio_basic_auth`

## Post-fix verification

### Deprecated field parity check
Twilio's older `Fields=carrier` shape is no longer valid on Lookup v2.

Direct Twilio:
- status: `400`
- message: valid fields are now `validation`, `caller_name`, `line_type_intelligence`, etc.

Rhumb Resolve:
- envelope: `200`
- upstream: `400`
- execution: `exec_65fc9c4be63543098cf5dbf9b904639b`

Conclusion:
- Rhumb and direct Twilio now fail identically on the deprecated field, confirming the domain-routing bug is fixed.

### Supported field success check
Direct Twilio with `Fields=line_type_intelligence`:
- status: `200`
- payload: valid lookup response for `+14155552671`

Rhumb Resolve with `Fields=line_type_intelligence`:
- envelope: `200`
- upstream: `200`
- execution: `exec_704315f474034976a1b3b9fb080533ff`
- payload: matched direct Twilio lookup structure and validity result

### Credential-mode truth check
Post-fix:
- `GET /v1/capabilities/phone.lookup/credential-modes`
- Twilio now reports:
  - `auth_method=basic_auth`
  - `configured=true`
  - setup hint points to `RHUMB_CREDENTIAL_TWILIO_BASIC_AUTH`

## Comparison

| Dimension | Rhumb Resolve | Direct Twilio |
|---|---|---|
| Routing | Correct post-fix (`lookups.twilio.com`) | Correct |
| Auth path | Rhumb BYOK credential injection | Direct Twilio Basic Auth |
| Deprecated `carrier` field | 400 | 400 |
| Supported `line_type_intelligence` field | 200 | 200 |
| Operator conclusion | Execution bug fixed; runtime healthy | Provider API healthy |

## Public trust surface update

Published fresh runtime-backed artifacts:
- Review id: `9986e92d-aafa-4692-b26a-809b6c60749d`
- Evidence id: `2b70dd22-fcbd-4dda-80f1-1b864b8d79e4`

`/v1/services/twilio/reviews` now shows a new top-row **🟢 Runtime-verified** review backed by real evidence.

## Follow-up

1. Refresh stale Twilio capability metadata in migrations so the endpoint pattern stops advertising deprecated `Fields=carrier`.
2. Keep Unstructured as the last callable-provider backlog item until multipart/form-data execution support exists.

## Phase 3 verdict

**Twilio is Phase-3-verified in production.**

The failing 404 path was a Rhumb routing bug, it was fixed and deployed, direct parity was re-established, and the public trust surface now reflects real runtime-backed proof.
