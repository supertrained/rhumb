# Google AI — Phase 3 runtime verification

Date: 2026-03-26
Operator: Pedro / Keel runtime loop
Status: passed

## Why Google AI

At the start of this run, Google AI had live callable inventory coverage but no published runtime-backed Phase 3 review on the public trust surface. That made it the best next provider to close from the callable backlog after confirming PDL was healthy.

## Inputs

- Capability: `ai.generate_text`
- Provider: `google-ai`
- Credential mode: `rhumb_managed`
- Test prompt: `Reply with exactly: RHUMB_GOOGLE_AI_OK`

## Rhumb execution

### Estimate
- Endpoint: `GET /v1/capabilities/ai.generate_text/execute/estimate?provider=google-ai&credential_mode=rhumb_managed`
- Result: **200 OK**
- Cost estimate: **$0.001**
- Endpoint pattern: `POST /v1beta/models/{model}:generateContent`

### First execute attempt (retired model check)
- Model: `gemini-2.0-flash`
- Result: **404 / NOT_FOUND**
- Execution id: `exec_92cdfc472d6147c49ea15406b50e9840`
- Upstream message: `This model models/gemini-2.0-flash is no longer available to new users.`

### Control interpretation
The same request also failed directly against Google AI with the same 404. That made this a **provider/model test-fixture issue**, not a Rhumb execution bug. No Rhumb-side investigation/fix was warranted because the control path disproved an execution-layer regression.

### Verification execute (current model)
- Model: `gemini-2.5-flash`
- Result: **200 OK**
- Execution id: `exec_63c86d4fa1f84881ab40792865971e55`
- Upstream status: `200`
- Returned sentinel text: `RHUMB_GOOGLE_AI_OK`

## Direct provider control

### Retired-model control
- Endpoint: `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent`
- Result: **404 / NOT_FOUND**
- Same retirement message as Rhumb path

### Current-model control
- Endpoint: `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent`
- Result: **200 OK**
- Returned sentinel text: `RHUMB_GOOGLE_AI_OK`

## Comparison

| Check | Rhumb | Direct Google AI | Verdict |
|---|---:|---:|---|
| Retired model (`gemini-2.0-flash`) | 404 | 404 | Match — upstream retirement |
| Current model (`gemini-2.5-flash`) | 200 | 200 | Match |
| Output text | `RHUMB_GOOGLE_AI_OK` | `RHUMB_GOOGLE_AI_OK` | Match |
| Auth path | Rhumb-managed `x-goog-api-key` injection | Direct `x-goog-api-key` | Match |

## Root-cause verdict

Google AI is healthy through Rhumb Resolve. The only failure encountered was a stale-model probe on a provider-retired model, and the direct control reproduced it exactly. After switching to `gemini-2.5-flash`, Rhumb and direct control matched cleanly.

## Trust-surface action

- Published runtime evidence: `9956e212-f83c-4bf8-9a98-5ee9efdc2901`
- Published runtime review: `476f256b-7b22-469f-8839-c8d4cefd5ea9`

## Operator takeaway

Google AI is Phase-3-verified in production. The important lesson is that Phase 3 needs live model hygiene as well as execution-path verification: a retired provider model can create a false negative unless the control test is run and interpreted first.
