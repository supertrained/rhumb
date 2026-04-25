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

- `packages/mcp/server.json` — MCP Registry manifest now advertises the latest published `rhumb-mcp` package version (`0.8.2`) instead of stale registry version `0.8.1`, while the repo package can continue carrying unreleased `2.0.0` source metadata until an npm publish is intentional.
- Official MCP Registry latest version — published `io.github.supertrained/rhumb-mcp` `0.8.2` through the registry API; `/v0.1/servers/io.github.supertrained%2Frhumb-mcp/versions/latest` now returns the canonical agent-gateway / Index / Resolve description.
- `README.md` — GitHub repository README now opens with the Index/Resolve agent-gateway framing, includes an explicit repository visibility map, and avoids stale generic `best provider` / broad cost-aware routing shorthand.
- `packages/mcp/README.md` — GitHub/npm MCP README now uses `999` services, `435` capability definitions, and `28` callable providers instead of stale `1,038` / `415` / `16` copy, and describes Layer 2 as best-fit supported routing rather than generic best-provider selection.
- `agent-capabilities.json` and `.well-known/agent-capabilities.json` — regenerated from shared public truth and kept in sync.
- `packages/astro-web/public/guides/blog-api-failure-modes-engineering.md` — stale public guide count changed from `1,038` to `999` scored services.

## Guard added

`packages/mcp/tests/types.contract.test.ts` now freezes:

- MCP Registry manifest package version is pinned to the latest published npm version (`0.8.2`) so official registry validation can pass.
- Built MCP server bundle and API client user-agent still report the repo package version for local unreleased `2.0.0` source builds.
- Root README opens with Index/Resolve agent-gateway framing, contains the repository visibility map, and rejects stale generic best-provider routing shorthand.
- MCP README contains `999` / `435` / `28`, best-fit supported routing copy, and rejects stale `1,038 services`, `415 capability definitions`, `16 callable providers`, and generic best-provider copy.

## Verification

- `python3 scripts/generate_agent_capabilities.py --check`
- `npm test -- --run tests/types.contract.test.ts` from `packages/mcp`
- `gh repo view supertrained/rhumb --json description,repositoryTopics,homepageUrl,url,visibility` after the GitHub metadata update confirmed the public repo description, homepage, and topics carry the agent-gateway / Index / Resolve / MCP framing.
- `POST /v0.1/publish` to the Official MCP Registry returned HTTP 200 for `io.github.supertrained/rhumb-mcp` version `0.8.2`; `GET /v0.1/servers/io.github.supertrained%2Frhumb-mcp/versions/latest` confirmed `isLatest: true`.

## Boundary

This pass aligns distribution metadata, GitHub-facing source copy, GitHub repository metadata, and the Official MCP Registry latest listing. It does not publish a new npm package; the registry listing intentionally points at the currently published npm package `rhumb-mcp@0.8.2` until an npm `2.0.0` release is intentional.
