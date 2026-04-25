# DC90 Month 1 Run Notes

Run window: 2026-04-25T15:07:03Z–2026-04-25T15:16:08Z; preflight plus Gemini CLI diagnostic capture only. Exact browser answer-surface capture is still pending.
Runner: Pedro preflight scaffold + Beacon capture pass.
Keel reviewer: not required yet; no Rhumb-mentioned rows in completed diagnostic rows.

## Pre-run drift checks

Preflight artifacts:

- `docs/dc90-measurement/month1-2026-04/preflight/preflight-20260425T150703Z.json`
- `docs/dc90-measurement/month1-2026-04/preflight/preflight-20260425T151608Z.json`

Helper: `python3 scripts/dc90_month1_measurement.py --preflight`

- [x] `https://rhumb.dev/llms.txt` is reachable.
- [x] `https://rhumb.dev/llms-full.txt` is reachable.
- [x] `https://rhumb.dev/sitemap.xml` is reachable.
- [x] `https://rhumb.dev/.well-known/agent-capabilities.json` is reachable.
- [x] `https://rhumb.dev/logo.svg` and `https://rhumb.dev/logo.png` are reachable.
- [x] Official MCP Registry listing still points to public npm `rhumb-mcp@0.8.2` unless a separate npm release has been verified.
- [x] Public callable-provider count is source-read before interpreting rows: `packages/astro-web/src/lib/public-truth.ts` has `callableProviders: 28`, `agent-capabilities.json` has `coverage.providers_with_execution: 28`, and live `/v2/providers?status=callable&limit=200` returned `28`.

Latest validation/preflight command:

```bash
python3 scripts/dc90_month1_measurement.py --validate && python3 scripts/dc90_month1_measurement.py --preflight
```

Latest result: validator passed with `15` completed rows, `60` pending rows, `15` existing artifacts, `0` Rhumb mentions; preflight passed with all public URLs OK, MCP Registry `0.8.2`, callable-provider count `28`.

## Surface notes

| Surface | Mode used | Account / region notes | Deviation from Month 0? |
|---|---|---|---|
| GPT-4 | blocked: no ChatGPT/GPT-4 web answer-surface capture tool in this session | none available | yes — not captured |
| Claude | blocked: no Claude web answer-surface capture tool in this session | none available | yes — not captured |
| Perplexity | blocked: no Perplexity answer-surface capture tool in this session | none available | yes — not captured |
| Gemini | Gemini CLI 0.36.0; default main model `gemini-3-flash-preview` via CLI router; wrapped benchmark prompt; no tools invoked; no Google-grounded web retrieval/citation cards; empty temp cwd | cached local Gemini CLI credentials | yes — diagnostic CLI capture, not Gemini web UI with Google-grounded citations |
| Copilot | blocked: no Microsoft Copilot web answer-surface capture tool in this session | none available | yes — not captured |

## Review status

- Rows collected: 15/75
- Rows with Rhumb mention: 0/15 completed rows
- Rows reviewed by Keel: 0/0 required so far
- Public claim approved: no

## Completed diagnostic rows

Beacon captured all 15 Gemini CLI rows under `docs/dc90-measurement/month1-2026-04/raw-artifacts/` and updated the Gemini rows in `scorecard.csv`.

Diagnostic result from this mode:

- Rhumb mentioned: 0/15
- Resolve mentioned: 0/5 Resolve-cluster rows
- Citation cards: none returned by this mode; one plain surfaced URL appeared in Q4 (`https://smithery.ai/`).
- Composio present: 2/15 completed rows (`Q1`, `Q10`)

These rows are useful internal diagnostics, but they should not be treated as strict Month-0-comparable Gemini web results.

## Exact blocker

The remaining 60 scorecard rows, plus a strict Gemini web UI row set if required for Month-0 comparability, need first-party/browser capture access to the exact target answer surfaces. The current Beacon toolset has Gemini CLI and xAI-backed `web_search`, but not authenticated/browser-equivalent capture for ChatGPT/GPT-4, Claude, Perplexity, Gemini web, or Copilot. `web_search` cannot substitute because it is a Grok search surface, not one of the five selected labels.

Runnable capture procedure: `docs/dc90-measurement/month1-2026-04/CAPTURE-PROCEDURE.md`.

## Follow-up actions

- Use `CAPTURE-PROCEDURE.md` to collect exact browser/UI artifacts for GPT-4, Claude, Perplexity, Gemini web, and Copilot.
- Keep every partial result internal until Keel reviews all Rhumb-mentioned rows.
- Re-run `python3 scripts/dc90_month1_measurement.py --validate` after every scorecard edit and `python3 scripts/dc90_month1_measurement.py --preflight` before interpreting a completed run.
