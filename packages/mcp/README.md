# Rhumb MCP Server

Agent-native tool discovery via the [Model Context Protocol](https://modelcontextprotocol.io/).

## Overview

The Rhumb MCP server exposes tool discovery and scoring as MCP tools that any agent framework can call. Agents register the server once and get inline access to:

- **`find_tools`** — Semantic search for agent tools, ranked by AN Score
- **`get_score`** — Detailed AN Score breakdown for a service
- **`get_alternatives`** — Related services ranked by score
- **`get_failure_modes`** — Known failure patterns for a service

## Quick Start

```bash
# Development
cd packages/mcp
npm install
npx tsx src/index.ts
```

## Claude Desktop

Get started with Claude Desktop in under 5 minutes:

1. Build the server: `cd packages/mcp && npm run build`
2. Add the server to `claude_desktop_config.json`
3. Restart Claude Desktop

📖 **Full guide:** [docs/CLAUDE-DEV.md](docs/CLAUDE-DEV.md)

## Integration

For architecture details, tool contracts, handler development, testing patterns, and deployment options:

📖 **[MCP Integration Guide](docs/MCP-INTEGRATION.md)**

### Framework links

- [Anthropic Claude SDK](https://docs.anthropic.com/en/docs/agents-and-tools/mcp)
- [LangChain MCP Adapters](https://github.com/langchain-ai/langchain-mcp-adapters)
- [CrewAI](https://docs.crewai.com/)
- [AutoGen](https://microsoft.github.io/autogen/)

## Testing

The test suite is organized into three layers:

| Layer | Files | What it covers |
|-------|-------|----------------|
| **Contract** | `tests/types.contract.test.ts` | JSON Schema validity, TypeScript type compliance |
| **Unit** | `tests/server.init.test.ts`, `tests/tools/*.test.ts` | Server init, individual handler logic with mock API clients |
| **E2E** | `tests/e2e.server.test.ts` | Full server instance → tool call → response via MCP protocol |

```bash
# Run all tests
npm run test

# Run specific test file
npx vitest run tests/e2e.server.test.ts

# Run with verbose output
npx vitest run --reporter=verbose
```

## Development

```bash
# Run tests
npm run test

# Type-check
npm run type-check

# Build
npm run build
```

## Architecture

- `src/index.ts` — Entry point, stdio transport
- `src/types.ts` — Tool I/O contracts (JSON Schema + TypeScript types)
- `src/server.ts` — Server initialization + tool registration
- `src/api-client.ts` — Rhumb API client (DI-compatible interface)
- `src/tools/` — Tool handler implementations
- `tests/` — Contract, unit, and end-to-end tests
- `docs/` — Integration and framework guides
