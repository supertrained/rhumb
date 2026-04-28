# DC90 Month 1 Run Notes

Current state as of 2026-04-28T12:46:41Z: exact browser/UI capture is complete for Perplexity and Gemini web, and still pending for GPT-4, Claude, and Copilot.

Runner: Pedro browser/UI capture through the `rhumb` Chrome profile (CDP 18805), plus earlier Beacon/Pedro diagnostic scaffolding.
Keel reviewer: not required for completed exact rows so far; no completed exact row mentions Rhumb or Resolve.

## Pre-run drift checks

Preflight artifacts include:

- `docs/dc90-measurement/month1-2026-04/preflight/preflight-20260425T150703Z.json`
- `docs/dc90-measurement/month1-2026-04/preflight/preflight-20260425T151608Z.json`

Helper: `python3 scripts/dc90_month1_measurement.py --preflight`

Expected facts before interpreting completed rows:

- `https://rhumb.dev/llms.txt` is reachable.
- `https://rhumb.dev/llms-full.txt` is reachable.
- `https://rhumb.dev/sitemap.xml` is reachable.
- `https://rhumb.dev/.well-known/agent-capabilities.json` is reachable.
- `https://rhumb.dev/logo.svg` and `https://rhumb.dev/logo.png` are reachable.
- Official MCP Registry listing still points to public npm `rhumb-mcp@0.8.2` unless a separate npm release has been verified.
- Public callable-provider count is source-read before interpreting rows: `packages/astro-web/src/lib/public-truth.ts` has `callableProviders: 28`, `agent-capabilities.json` has `coverage.providers_with_execution: 28`, and live `/v2/providers?status=callable&limit=200` should return `28`.

Latest validation command during the 2026-04-28 capture pass:

```bash
python3 scripts/dc90_month1_measurement.py --validate
```

Latest result: validator passed with `30` completed rows, `45` pending rows, `30` existing scorecard artifacts, `0` Rhumb mentions, and `0` Resolve mentions.

## Surface notes

| Surface | Current mode/status | Account / region notes | Deviation from Month 0? |
|---|---|---|---|
| GPT-4 | blocked: ChatGPT is logged out in the Pedro `rhumb` Chrome profile | no logged-in GPT-4/web-retrieval surface available | yes — not captured |
| Claude | blocked: Claude is logged out in the Pedro `rhumb` Chrome profile | no logged-in Claude/web-search surface available | yes — not captured |
| Perplexity | Perplexity web UI exact browser capture complete, 15/15 rows | accessible from profile | no known material deviation |
| Gemini | Gemini web UI exact browser capture complete, 15/15 rows; signed-out/free Tools/Fast mode recorded in artifacts | signed-out/free Gemini web UI | captured as visible web UI; mode is explicitly recorded |
| Copilot | blocked: exact Q1 prompt submission hit Cloudflare human verification before any answer rendered | no answer content available past verification interstitial | yes — not captured |

## Completed exact browser/UI rows

- Perplexity web UI: 15/15 rows captured under `docs/dc90-measurement/month1-2026-04/raw-artifacts/` and committed in `cccc569`.
- Gemini web UI: 15/15 rows captured under `docs/dc90-measurement/month1-2026-04/raw-artifacts/` and committed in `e5539be`.

Exact-row result so far:

- Rows collected: 30/75
- Rows pending: 45/75
- Rhumb mentioned: 0/30 completed exact rows
- Resolve mentioned: 0/30 completed exact rows
- Rows reviewed by Keel: 0/0 required so far
- Public claim approved: no

## Superseded diagnostic rows

The 2026-04-25 Gemini CLI rows remain useful internal diagnostics but are superseded by the 2026-04-28 Gemini web UI rows. Do not treat Gemini CLI output as current scorecard evidence or use it for Month-1 visibility/retrieval claims.

## Latest blocked-surface probe

Probe artifact: `docs/dc90-measurement/month1-2026-04/blocked-surfaces-2026-04-28T124641Z.md`.

Associated capture-access screenshots/text notes:

- `docs/dc90-measurement/month1-2026-04/raw-artifacts/BLOCKED__GPT-4__20260428T124641Z.md`
- `docs/dc90-measurement/month1-2026-04/raw-artifacts/BLOCKED__GPT-4__20260428T124641Z.png`
- `docs/dc90-measurement/month1-2026-04/raw-artifacts/BLOCKED__Claude__20260428T124641Z.md`
- `docs/dc90-measurement/month1-2026-04/raw-artifacts/BLOCKED__Claude__20260428T124641Z.png`
- `docs/dc90-measurement/month1-2026-04/raw-artifacts/BLOCKED__Copilot__20260428T124641Z.md`
- `docs/dc90-measurement/month1-2026-04/raw-artifacts/BLOCKED__Copilot__20260428T124641Z.png`

These artifacts do not count as scorecard rows. They only document why remaining exact capture could not proceed from the active browser context.

## Follow-up actions

- Continue exact browser/UI capture for GPT-4, Claude, and Copilot as soon as the approved capture context has logged-in/non-verification access.
- Keep every partial or blocker result internal until all 75 rows are captured and Keel reviews all Rhumb-mentioned rows.
- Re-run `python3 scripts/dc90_month1_measurement.py --validate` after every scorecard edit and `python3 scripts/dc90_month1_measurement.py --preflight` before interpreting a completed run.
