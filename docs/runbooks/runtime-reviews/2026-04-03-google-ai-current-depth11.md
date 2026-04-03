# Google AI runtime review — depth 11 (2026-04-03 PT)

## What this pass did
- Re-ran live callable-review coverage first and checked the real freshness order instead of trusting stale fallback wording.
- Confirmed the callable floor was still depth **10** across all 16 callable providers.
- Confirmed **Google AI** was the oldest non-PDL member of the depth-10 bucket on the fresh coverage pull (`2026-03-31T15:28:29Z`), so it was the honest next target.
- Added `scripts/runtime_review_google_ai_depth11_20260403.py` for a reusable production parity pass.
- Ran the pass through Railway production context against Rhumb Resolve and direct Google AI control.

## Production result
- Capability: `ai.generate_text`
- Provider route: `google-ai`
- Model: `gemini-2.5-flash`
- Estimate: `200` (attempt **1**)
- Rhumb execute: `200`
- Direct Google AI control: `200`
- Execution ID: `exec_abab9c99e2c3411dace3d7c8166f46ca`

## Parity checked
- provider used
- upstream status
- model version
- exact generated text
- exact sentinel match

## Observed parity
- Rhumb and direct control both returned:
  - model version = `gemini-2.5-flash`
  - exact text = `RHUMB_GOOGLE_AI_20260403_DEPTH11`
- Published trust rows:
  - evidence `10453582-0657-4007-aee3-70146766ecbf`
  - review `a0c7e9d0-e4d6-44a7-91f5-c3d1b66ec819`

## Harness note worth preserving
- The new reusable helper includes the now-standard post-grant delay plus bounded invalid-key estimate retry guard, but this pass did **not** need the retry path.
- Estimate succeeded on the first attempt and the pass stayed clean end-to-end.

## Coverage impact
- **Google AI moved from 10 → 11 claim-safe runtime-backed reviews.**
- The callable floor stays **10**.
- Providers now above the floor:
  - `e2b` at 11
  - `brave-search` at 11
  - `google-ai` at 11
- The new weakest callable bucket remains depth **10**, now without Google AI.
- Freshness-ordered next honest non-PDL target is now **Tavily**.

## Artifacts
- `artifacts/callable-review-coverage-2026-04-03-pre-google-ai-depth11.json`
- `artifacts/runtime-review-pass-20260403T144821Z-google-ai-depth11.json`
- `artifacts/runtime-review-publication-2026-04-03-google-ai-depth11.json`
- `artifacts/callable-review-coverage-2026-04-03-post-google-ai-depth11.json`
