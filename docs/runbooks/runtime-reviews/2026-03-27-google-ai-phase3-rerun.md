# Phase 3 runtime review — Google AI rerun

Date: 2026-03-27
Owner: Pedro / Keel runtime review loop
Priority: Phase 3 callable-provider verification
Status: ✅ VERIFIED + PUBLISHED

## Why Google AI

I queried `GET /v1/proxy/services` for the current callable inventory, then checked runtime-backed public review depth across callable providers.

After Mission 0 re-verified PDL, the weakest remaining bucket still sat at **1 runtime-backed review** across several providers. I chose `google-ai` from that tie set because it offers a cheap deterministic same-input control path: exact-text generation on a current live model.

## Test setup

### Rhumb Resolve execution
- **Endpoint:** `POST /v1/capabilities/ai.generate_text/execute`
- **Capability:** `ai.generate_text`
- **Provider:** `google-ai`
- **Credential mode:** `rhumb_managed`
- **Estimate:** `GET /v1/capabilities/ai.generate_text/execute/estimate?provider=google-ai&credential_mode=rhumb_managed`
- **Input:**
  ```json
  {
    "provider": "google-ai",
    "credential_mode": "rhumb_managed",
    "body": {
      "model": "gemini-2.5-flash",
      "contents": [
        {
          "parts": [
            {
              "text": "Reply with exactly: RHUMB_GOOGLE_AI_20260327"
            }
          ]
        }
      ],
      "generationConfig": {
        "temperature": 0
      }
    },
    "interface": "runtime_review"
  }
  ```

### Direct provider control
- **Endpoint:** `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent`
- **Auth:** direct Google AI API key (`x-goog-api-key`)
- **Input:** same payload and sentinel prompt as the Rhumb execution path

## Results

### Rhumb Resolve
- HTTP 200 from Rhumb
- Upstream status: **200**
- Execution id: `exec_ffe486cfd4d94918b87c5292acb8c202`
- Returned text: `RHUMB_GOOGLE_AI_20260327`
- Estimate surface also returned **200**

### Direct Google AI control
- HTTP 200 direct from Google AI
- Returned text: `RHUMB_GOOGLE_AI_20260327`

## Comparison

| Dimension | Rhumb Resolve | Direct Google AI |
|---|---|---|
| Reachability | Healthy | Healthy |
| Auth path | Rhumb-managed `x-goog-api-key` injection | Direct `x-goog-api-key` |
| Model | `gemini-2.5-flash` | `gemini-2.5-flash` |
| Output | `RHUMB_GOOGLE_AI_20260327` | `RHUMB_GOOGLE_AI_20260327` |
| Investigation need | None — no failure reproduced | N/A |

## Investigation outcome

No execution-layer defect surfaced on this rerun.

Because the Rhumb path and the direct control both returned **200** with the exact same deterministic sentinel output, there was no need to escalate into slug/auth/env/config tracing for this provider on this pass.

## Public trust surface update

Because this rerun was clean, I published a fresh runtime-backed evidence + review pair.

Inserted records:
- **Evidence id:** `7939bbff-618c-468e-a576-53966b4d2bb1`
- **Review id:** `94b09339-d15e-4113-b456-a1adf12d81f8`

Public verification:
- `/v1/services/google-ai/reviews` now shows the new top review:
  - **"Google AI: runtime rerun confirms ai.generate_text parity through Rhumb Resolve"**
- Google AI runtime-backed review depth moved from **1 → 2**

## Verdict

**Google AI is healthy in production and remains Phase-3-verified.**

This pass advanced the weakest-coverage callable bucket with another real runtime-backed proof instead of leaving the provider at a single historical verification.
