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

## Framework Integration

- [Anthropic Claude SDK](https://docs.anthropic.com/en/docs/agents-and-tools/mcp)
- [LangChain MCP Adapters](https://github.com/langchain-ai/langchain-mcp-adapters)
- [CrewAI](https://docs.crewai.com/)
- [AutoGen](https://microsoft.github.io/autogen/)

> Full installation guides: see `docs/FRAMEWORK-INSTALL.md` (Slice D).

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
- `tests/` — Contract and initialization tests
