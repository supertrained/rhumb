# MCP Server Integration Guide

Technical guide for integrating with, extending, and deploying the Rhumb MCP server.

## Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                    MCP Client                        │
│  (Claude Desktop, LangChain, CrewAI, custom agent)   │
└──────────────────────┬───────────────────────────────┘
                       │  stdio / HTTP (JSON-RPC 2.0)
┌──────────────────────▼───────────────────────────────┐
│               Rhumb MCP Server                       │
│  src/server.ts — createServer(apiClient?)             │
│                                                      │
│  ┌────────────┐ ┌───────────┐ ┌─────────────────┐   │
│  │find_services│ │ get_score │ │get_alternatives │   │
│  └─────┬──────┘ └─────┬─────┘ └───────┬─────────┘   │
│  ┌─────▼──────────────▼───────────────▼─────────┐   │
│  │           get_failure_modes                   │   │
│  └─────────────────────┬─────────────────────────┘   │
│                        │                             │
│  ┌─────────────────────▼─────────────────────────┐   │
│  │        RhumbApiClient (DI interface)           │   │
│  │  searchServices(query) → ServiceSearchItem[]   │   │
│  │  getServiceScore(slug) → ServiceScoreItem|null │   │
│  └─────────────────────┬─────────────────────────┘   │
└────────────────────────┼─────────────────────────────┘
                         │  HTTP (fetch)
┌────────────────────────▼─────────────────────────────┐
│                 Rhumb REST API                       │
│  GET /v1/services?query=...                          │
│  GET /v1/services/{slug}/score                       │
└──────────────────────────────────────────────────────┘
```

### Key patterns

- **Tool registration:** Each tool is registered via `server.tool(name, description, zodSchema, handler)` using the MCP SDK's `McpServer` class.
- **Handler pattern:** Tool handlers are pure async functions in `src/tools/*.ts`. They receive validated input and an `RhumbApiClient` instance — no direct SDK coupling.
- **Dependency injection:** `createServer(apiClient?)` accepts an optional `RhumbApiClient`. Production uses the default HTTP client; tests inject mocks.

## Tool Contracts

### `find_services`

Semantic search for agent tools, ranked by AN Score.

**Input:**
```typescript
{
  query: string;    // Search query (required)
  limit?: number;   // Max results, 1–50, default 10
}
```

**Output:**
```typescript
{
  tools: Array<{
    name: string;
    slug: string;
    aggregateScore: number | null;
    executionScore: number | null;
    accessScore: number | null;
    explanation: string;
  }>
}
```

**Error behavior:** Returns `{ tools: [] }` on any API error (resilient fallback).

---

### `get_score`

Detailed AN Score breakdown for a single service.

**Input:**
```typescript
{
  slug: string;  // Service identifier (required)
}
```

**Output:**
```typescript
{
  slug: string;
  aggregateScore: number | null;
  executionScore: number | null;
  accessScore: number | null;
  confidence: number;
  tier: string;
  explanation: string;
  freshness: string;
}
```

**Error behavior:** Returns a valid response with `tier: "unknown"` and descriptive `explanation` on API error or 404. Never throws.

---

### `get_alternatives`

Find alternative services with higher AN Scores, based on shared failure-mode tags.

**Input:**
```typescript
{
  slug: string;  // Service to find alternatives for (required)
}
```

**Output:**
```typescript
{
  alternatives: Array<{
    name: string;
    slug: string;
    aggregateScore: number | null;
    reason: string;
  }>
}
```

**Error behavior:** Returns `{ alternatives: [] }` on any error (resilient fallback).

---

### `get_failure_modes`

Known failure patterns for a service.

**Input:**
```typescript
{
  slug: string;  // Service identifier (required)
}
```

**Output:**
```typescript
{
  failures: Array<{
    pattern: string;
    impact: string;
    frequency: string;
    workaround: string;
  }>
}
```

**Error behavior:** Returns `{ failures: [] }` on any error (resilient fallback).

## Handler Development Guide

To add a new tool to the Rhumb MCP server:

### 1. Define the contract

Add input/output schemas and types to `src/types.ts`:

```typescript
// src/types.ts
export const GetMyToolInputSchema = {
  type: "object" as const,
  properties: {
    param: { type: "string" as const, description: "Parameter description" }
  },
  required: ["param"] as const
};

export type GetMyToolInput = {
  param: string;
};

export type GetMyToolOutput = {
  result: string;
};
```

Update `TOOL_SCHEMAS` and `TOOL_NAMES` in the same file.

### 2. Implement the handler

Create `src/tools/my-tool.ts`:

```typescript
import type { GetMyToolInput, GetMyToolOutput } from "../types.js";
import type { RhumbApiClient } from "../api-client.js";

export async function handleGetMyTool(
  input: GetMyToolInput,
  client: RhumbApiClient
): Promise<GetMyToolOutput> {
  try {
    // Your logic here, using client for API calls
    return { result: "value" };
  } catch {
    // Resilient fallback — never throw
    return { result: "" };
  }
}
```

**Handler rules:**
- Accept `(input, client)` — keep handlers pure and testable
- Always wrap API calls in try/catch — return a valid fallback, never throw
- Return types must match the output contract exactly

### 3. Register the tool

Add registration to `src/server.ts`:

```typescript
import { handleGetMyTool } from "./tools/my-tool.js";

// Inside createServer():
server.tool(
  "my_tool",
  "Description of what the tool does",
  { param: z.string().describe("Parameter description") },
  async ({ param }) => {
    const result = await handleGetMyTool({ param }, client);
    return {
      content: [{ type: "text" as const, text: JSON.stringify(result) }]
    };
  }
);
```

### 4. Add API methods (if needed)

If your tool needs new API endpoints, extend the `RhumbApiClient` interface in `src/api-client.ts` and implement the method in `createApiClient()`.

### 5. Write tests

See [Testing Patterns](#testing-patterns) below.

## Testing Patterns

### Mock client setup

All tool tests use mock `RhumbApiClient` instances:

```typescript
import { vi } from "vitest";
import type { RhumbApiClient } from "../../src/api-client.js";

function createMockClient(): RhumbApiClient {
  return {
    searchServices: vi.fn().mockResolvedValue([
      { name: "Example", slug: "example", aggregateScore: 85,
        executionScore: 90, accessScore: 80, explanation: "Test service" }
    ]),
    getServiceScore: vi.fn().mockResolvedValue({
      slug: "example", aggregateScore: 85, executionScore: 90,
      accessScore: 80, confidence: 0.9, tier: "ready",
      explanation: "Test", freshness: "2026-03-01",
      failureModes: [], tags: []
    })
  };
}

function createErrorClient(): RhumbApiClient {
  return {
    searchServices: vi.fn().mockRejectedValue(new Error("Network failure")),
    getServiceScore: vi.fn().mockRejectedValue(new Error("Network failure"))
  };
}
```

### Test categories

| Category | Location | What it tests |
|----------|----------|---------------|
| Contract tests | `tests/types.contract.test.ts` | Schema validity, type correctness |
| Init tests | `tests/server.init.test.ts` | Server boots, tools registered |
| Tool unit tests | `tests/tools/*.tool.test.ts` | Handler logic with mock API client |
| E2E tests | `tests/e2e.server.test.ts` | Full server → tool call → response flow |

### What to test for each handler

1. **Happy path** — correct output shape with valid input
2. **Required output fields** — all contract fields present
3. **API error resilience** — returns fallback, never throws
4. **Edge cases** — empty results, null scores, missing data
5. **No side effects** — no unintended API calls or mutations

### Running tests

```bash
cd packages/mcp

# Run all tests
npm run test

# Run with verbose output
npx vitest run --reporter=verbose

# Run a specific test file
npx vitest run tests/e2e.server.test.ts
```

## Deployment

### stdio transport (default)

The default transport. The MCP client spawns the server as a child process and communicates over stdin/stdout.

```bash
# Production
node dist/index.js

# Development
npx tsx src/index.ts
```

**Advantages:** Simple, no port management, process-level isolation.
**Use when:** Running locally with Claude Desktop or any stdio-compatible MCP client.

### HTTP transport (SSE)

For remote or multi-client deployments, the MCP SDK supports HTTP with Server-Sent Events:

```typescript
// src/index-http.ts (example — not included in default build)
import express from "express";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import { createServer } from "./server.js";

const app = express();
const mcpServer = createServer();

app.get("/sse", async (req, res) => {
  const transport = new SSEServerTransport("/messages", res);
  await mcpServer.connect(transport);
});

app.post("/messages", async (req, res) => {
  // Handle incoming messages
});

app.listen(3001, () => {
  console.log("Rhumb MCP server (HTTP) listening on :3001");
});
```

**Advantages:** Network-accessible, supports multiple simultaneous clients.
**Use when:** Deploying as a shared service, remote access needed, or multi-agent scenarios.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RHUMB_API_BASE_URL` | `http://localhost:8000/v1` | Base URL for the Rhumb REST API |

### Docker (future)

```dockerfile
FROM node:22-slim
WORKDIR /app
COPY packages/mcp/ .
RUN npm ci && npm run build
CMD ["node", "dist/index.js"]
```

> **Note:** Docker deployment is not yet officially supported but follows standard Node.js container patterns.
