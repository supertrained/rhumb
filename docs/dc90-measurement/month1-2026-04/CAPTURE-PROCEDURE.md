# DC90 Month 1 Capture Procedure

This file is the runnable procedure for finishing the Month 1 scorecard without publishing externally.

## Current status

As of 2026-04-28T12:46:41Z, exact browser/UI evidence is complete for:

- Perplexity web UI: 15/15 rows captured in `cccc569`; no Rhumb or Resolve mentions.
- Gemini web UI: 15/15 rows captured in `e5539be`; no Rhumb or Resolve mentions.

The older Gemini CLI rows from 2026-04-25 are superseded/internal diagnostics only. They are not current scorecard evidence.

Remaining exact browser/UI surfaces are still pending:

- GPT-4 / ChatGPT web answer surface with web retrieval: blocked because the Pedro `rhumb` Chrome profile is logged out of ChatGPT.
- Claude answer surface with web/search citations: blocked because the Pedro `rhumb` Chrome profile is logged out of Claude.
- Microsoft Copilot default answer surface: blocked by a Cloudflare human-verification interstitial after submitting the exact Q1 prompt.

Latest blocker probe note: `docs/dc90-measurement/month1-2026-04/blocked-surfaces-2026-04-28T124641Z.md`.

## Non-substitutes

Do not substitute API/CLI/model-router captures for the selected Month 1 browser/UI surfaces:

- Gemini CLI is useful internal diagnostics, but not Gemini web UI evidence.
- xAI-backed `web_search` is a Grok search surface, not GPT-4, Claude, Perplexity, Gemini web, or Copilot.
- Signed-out/free surfaces must be clearly labeled in `surface_mode` and cannot be upgraded into paid/authenticated-surface claims.
- Blocker screenshots do not count as scorecard artifacts.

## Preflight commands

Run before interpreting rows:

```bash
python3 scripts/dc90_month1_measurement.py --validate
python3 scripts/dc90_month1_measurement.py --preflight
```

Expected preflight facts remain:

- Public URLs reachable: `llms.txt`, `llms-full.txt`, `sitemap.xml`, `.well-known/agent-capabilities.json`, `logo.svg`, `logo.png`.
- MCP Registry latest: `io.github.supertrained/rhumb-mcp@0.8.2` until a separate npm release is verified.
- Source callable-provider count: `packages/astro-web/src/lib/public-truth.ts` has `callableProviders: 28`; `agent-capabilities.json` has `coverage.providers_with_execution: 28`.
- Live callable-provider count: `https://api.rhumb.dev/v2/providers?status=callable&limit=200` returns `28` providers.

## Manual/browser capture loop

For each pending row in `scorecard.csv`:

1. Use the Pedro `rhumb` Chrome profile only (CDP 18805) unless Tom explicitly provides a different approved capture context.
2. Record exact `surface_mode` before asking the query: model label, web/search/citation mode, UI or API path, account/region if visible.
3. Ask the row's `query_text` exactly. Do not add Rhumb hints.
4. Save the raw transcript/export/screenshot under:

   ```text
   docs/dc90-measurement/month1-2026-04/raw-artifacts/<query_id>__<surface>__YYYYMMDDTHHMMSSZ.<ext>
   ```

5. Update the row:
   - `run_at_utc`: capture timestamp
   - `artifact_path`: saved artifact path
   - `rhumb_mentioned`: `yes` only if Rhumb is named
   - `resolve_mentioned`: `yes` only if Rhumb Resolve is named or clearly described as Rhumb's Resolve product
   - `citation_url` / `citation_type`: preserve the surfaced URL exactly; use `none` if no URL/citation exists
   - `entity_accuracy`: 0–3; if Rhumb is not mentioned, use `0` and exclude from mention-only rollups
   - `claim_accuracy`: 0–3; if Rhumb is not mentioned, use `0` and exclude from mention-only rollups
   - `competitors_named`: comma-separated names from the answer
   - `composio_present`: `yes` if Composio is named
   - `actionability`: 0–3 based on whether a developer gets a concrete next step
   - `keel_review_status`: `pending` for every Rhumb-mentioned row; `not_required` otherwise
   - `notes`: exact quote or concise artifact pointer
6. Re-run validator:

   ```bash
   python3 scripts/dc90_month1_measurement.py --validate
   ```

## Completion boundary

Month 1 is not complete until all 75 rows have raw artifacts and Keel has reviewed every Rhumb-mentioned row. Partial CLI, API, non-equivalent UI rows, or blocker screenshots are internal diagnostics only.
