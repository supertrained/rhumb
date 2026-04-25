# DC90 Month 1 Capture Procedure

This file is the runnable procedure for finishing the Month 1 scorecard without publishing externally.

## Current blocker

Beacon can access Gemini through the local Gemini CLI, but this session does **not** have first-party capture access for the exact Month-0-comparable answer surfaces:

- ChatGPT / GPT-4 answer surface with web retrieval
- Claude answer surface with web search / citations
- Perplexity default answer surface
- Microsoft Copilot default answer surface
- Gemini web answer surface with Google-grounded retrieval

The available Gemini CLI capture is useful internal diagnostics, but it is not equivalent to a browser-visible Gemini web UI capture with citation cards. Keep that deviation in `surface_mode` and do not use partial rows for public improvement claims.

## Preflight commands

Run before interpreting rows:

```bash
python3 scripts/dc90_month1_measurement.py --validate
python3 scripts/dc90_month1_measurement.py --preflight
```

Expected preflight facts as of 2026-04-25:

- Public URLs reachable: `llms.txt`, `llms-full.txt`, `sitemap.xml`, `.well-known/agent-capabilities.json`, `logo.svg`, `logo.png`.
- MCP Registry latest: `io.github.supertrained/rhumb-mcp@0.8.2`.
- Source callable-provider count: `packages/astro-web/src/lib/public-truth.ts` has `callableProviders: 28`; `agent-capabilities.json` has `coverage.providers_with_execution: 28`.
- Live callable-provider count: `https://api.rhumb.dev/v2/providers?status=callable&limit=200` returns `28` providers.

## Manual/browser capture loop

For each pending row in `scorecard.csv`:

1. Use a clean capture context for the target surface/account.
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

Month 1 is not complete until all 75 rows have raw artifacts and Keel has reviewed every Rhumb-mentioned row. Partial CLI or non-equivalent UI rows are internal diagnostics only.
