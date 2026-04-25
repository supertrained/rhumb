# Public Distribution Surface Parity — DC90-5 / DC90-6

Date: 2026-04-25

Purpose: keep the MCP Registry and GitHub-facing discovery surfaces aligned with the live DC90 public truth before wider distribution.

## Current live truth used

- 999 scored services
- 435 capability definitions
- 28 callable providers
- 21 MCP tools
- Best current fit: research, extraction, generation, and narrow enrichment
- Execution rails: governed API key, wallet-prefund, and x402 / USDC
- Operator-controlled credential modes where supported: BYOK and Agent Vault

## Surfaces aligned

- `packages/mcp/server.json` — MCP Registry manifest now advertises `rhumb-mcp` version `2.0.0`, matching the npm package metadata.
- `packages/mcp/package-lock.json` — lockfile now matches package version `2.0.0` so package metadata and registry metadata do not drift.
- `packages/mcp/src/server.ts` — MCP server self-reported version now matches `2.0.0`.
- `packages/mcp/src/api-client.ts` — outbound MCP `User-Agent` now reports `rhumb-mcp/2.0.0`.
- `packages/mcp/README.md` — GitHub/npm MCP README now uses `999` services, `435` capability definitions, and `28` callable providers instead of stale `1,038` / `415` / `16` copy.
- `agent-capabilities.json` and `.well-known/agent-capabilities.json` — regenerated from shared public truth and kept in sync.
- `packages/astro-web/public/guides/blog-api-failure-modes-engineering.md` — stale public guide count changed from `1,038` to `999` scored services.

## Guard added

`packages/mcp/tests/types.contract.test.ts` now freezes:

- MCP Registry manifest version equals `packages/mcp/package.json` version.
- Manifest npm package version equals `packages/mcp/package.json` version.
- Built MCP server bundle reports the package version.
- Built API client user-agent reports the package version.
- MCP README contains `999` / `435` / `28` and rejects stale `1,038 services`, `415 capability definitions`, and `16 callable providers` copy.

## Verification

- `python3 scripts/generate_agent_capabilities.py --check`
- `npm test -- --run tests/types.contract.test.ts` from `packages/mcp`

## Boundary

This pass only aligns distribution metadata and public discovery copy. It does not publish a new npm package or submit an external registry update from this cron run.
