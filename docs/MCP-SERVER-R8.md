# Round 8: MCP Server Directory Surface — Kickoff Artifact

> **Machine ID:** cb-r008  
> **Type:** feature  
> **Goal:** Rhumb as a deployable MCP server agents can install and call.  
> **Owner:** Codex sub-agent (implementation) + Pedro (spec/review)  
> **Depends on:** WU 1.1 (AN Score Engine), WU 1.4 (CLI `rhumb find` pattern)  

---

## Why This Round

Agents already call `rhumb find` via CLI. The next-highest leverage is to make **Rhumb itself an installable tool** agents register once and call many times without subprocess overhead. MCP is the canonical protocol for agent-callable tools.

Key insight from panels: agents want "decision-making primitives at the moment of need" (Felix). MCP server removes procurement friction — agents install, then ask tool discovery questions inline with their actual work.

---

## Acceptance Criteria

By end of Round 8, acceptance is:

1. ✅ MCP server scaffold in `/packages/mcp` (TypeScript, Vitest, type-safe)
2. ✅ Tools implemented:
   - `find_tools` — semantic search + AN Score ranking
   - `get_score` — detailed breakdown for one service
   - `get_alternatives` — related services ranked by score
   - `get_failure_modes` — known failure patterns for a service
3. ✅ Contract tests for all tool I/O signatures
4. ✅ Installation docs for major frameworks (Claude SDK, LangChain, Crew, AutoGen)
5. ✅ End-to-end integration test (real agent call via stdio)
6. ✅ Diff artifact + PR merge to main

---

## Thin-Slice Decomposition

### Slice A: MCP Scaffold + Types (Codex sub-agent)

**Branch:** `feat/r8-slice-a-mcp-scaffold`

**Deliverable:**
- `/packages/mcp/` monorepo layout
  - `src/index.ts` — MCP server entry point (stdio transport)
  - `src/types.ts` — Tool I/O contracts (JSON Schema, type-safe)
  - `src/server.ts` — Server handler initialization + tool registration
  - `package.json` — dependencies (Node MCP SDK, TypeScript 5.3+, Vitest)
  - `vitest.config.ts` — test runner config matching web package
  - `README.md` — basic usage + framework links (stub)

**Tests:**
- `tests/types.contract.test.ts` — validate all tool schemas are JSON-Schema-valid and export TS types
- `tests/server.init.test.ts` — MCP server boots and registers all 4 tools

**Acceptance:**
- ✅ Zero linting errors
- ✅ Type-check passes
- ✅ All tests pass (3/3)

---

### Slice B: Core Tools — `find_tools` + `get_score` (Codex sub-agent)

**Branch:** `feat/r8-slice-b-core-tools`

**Deliverable:**
- `src/tools/find.ts` — search handler
  - input: `{ query: string; limit?: number }`
  - output: `{ tools: Array<{ name, slug, aggregateScore, executionScore, accessScore, explanation }> }`
  - calls `/v1/services` with query param + returns top N by aggregateScore
  - fallback: empty array on API error (resilient)

- `src/tools/score.ts` — detailed score handler
  - input: `{ slug: string }`
  - output: `{ slug, aggregateScore, executionScore, accessScore, confidence, tier, explanation, freshness }`
  - calls `/v1/services/{slug}/score`
  - fallback: error response with message on API error

- Server updates:
  - register both tools with MCP server
  - wire API client instance (reuse from web package or API package)

**Tests:**
- `tests/tools/find.tool.test.ts` — mock API, verify search results ranked by score, empty query fallback
- `tests/tools/score.tool.test.ts` — mock API, verify score breakdown, 404 handling

**Acceptance:**
- ✅ All tests pass (5/5)
- ✅ Type-check passes
- ✅ No regressions in Slice A tests

---

### Slice C: Related Tools — `get_alternatives` + `get_failure_modes` (Codex sub-agent)

**Branch:** `feat/r8-slice-c-related-tools`

**Deliverable:**
- `src/tools/alternatives.ts` — related services handler
  - input: `{ slug: string }`
  - output: `{ alternatives: Array<{ name, slug, aggregateScore, reason }> }`
  - extracts failure-mode tags from service score response → finds peers with same tags but higher scores
  - fallback: empty array on API error

- `src/tools/failures.ts` — failure modes handler
  - input: `{ slug: string }`
  - output: `{ failures: Array<{ pattern, impact, frequency, workaround }> }`
  - calls `/v1/services/{slug}/score` and extracts `failure_modes` array
  - fallback: empty array on API error

- Server updates:
  - register both tools with MCP server

**Tests:**
- `tests/tools/alternatives.tool.test.ts` — verify peer ranking by score, fallback on API error
- `tests/tools/failures.tool.test.ts` — verify failure array extraction, empty fallback

**Acceptance:**
- ✅ All tests pass (7/7 cumulative)
- ✅ Type-check passes
- ✅ All tools callable (end-to-end manual validation)

---

### Slice D: Framework Integration Docs + E2E Test (Codex sub-agent)

**Branch:** `feat/r8-slice-d-integration-docs`

**Deliverable:**
- `docs/FRAMEWORK-INSTALL.md` — step-by-step installation for:
  - Anthropic Claude SDK (JavaScript + Python)
  - LangChain (JavaScript + Python)
  - CrewAI
  - AutoGen
  - Each includes: `npm install rhumb-mcp`, configuration snippet, usage example

- `README.md` updates:
  - clarify MCP server vs. CLI vs. API layer differences
  - link to FRAMEWORK-INSTALL.md
  - dev run instructions (`npm run dev`)
  - publish/deploy notes (if applicable)

- `tests/e2e.mcp.test.ts` — end-to-end test
  - spawn MCP server via stdio
  - call all 4 tools with mock API data
  - verify responses match contract
  - cleanup (close server process)

**Tests:**
- ✅ E2E test passes (1 new, 7/7 existing)
- ✅ Type-check passes
- ✅ All docs render (no broken links)

**Acceptance:**
- ✅ All tests pass (8/8)
- ✅ Framework integration docs are copy-paste ready
- ✅ PR ready to merge with full coverage

---

## API Dependencies

**Required from `/packages/api`:**
- `GET /v1/services` — list with semantic search
- `GET /v1/services/{slug}/score` — full score + breakdown

**Mocking strategy:**
- Mock fixture at `tests/fixtures/services.ts` matching web package patterns
- Stub API calls in tool tests
- E2E test uses real HTTP mock server (if API is running) or test fixtures

---

## Type Safety & Contracts

All tool I/O will be defined as **JSON Schema** + exported as **TypeScript types**:

```typescript
// src/types.ts
export const FindToolInputSchema = {
  type: "object",
  properties: {
    query: { type: "string" },
    limit: { type: "number", minimum: 1, maximum: 50 }
  },
  required: ["query"]
};

export type FindToolInput = {
  query: string;
  limit?: number;
};

export type FindToolOutput = {
  tools: Array<{
    name: string;
    slug: string;
    aggregateScore: number | null;
    executionScore: number | null;
    accessScore: number | null;
    explanation: string;
  }>;
};
```

**Contract tests** validate schema compliance before any tool test runs.

---

## Dependencies & Blocking

- ❌ Blocked on: nothing (WU 1.1 and WU 1.4 are already complete/merged)
- ✅ Ready to proceed: all slices are independent of web surface changes

---

## Agent Assignment & Model Routing

| Slice | Task | Agent | Model | Why |
|-------|------|-------|-------|-----|
| A | MCP scaffold + types | Codex | Codex 5.3 xhigh | TypeScript monorepo setup |
| B | `find_tools` + `get_score` | Codex | Codex 5.3 xhigh | Core logic + API integration |
| C | `get_alternatives` + `get_failure_modes` | Codex | Codex 5.3 xhigh | Derived data + fallback patterns |
| D | Integration docs + E2E test | Codex | Codex 5.3 xhigh | Full-stack verification |

---

## Success Metrics

- ✅ MCP server boots in <500ms
- ✅ Tool calls return in <1000ms (including API latency)
- ✅ 100% test coverage on tool handlers
- ✅ 4 tools, 4 frameworks, full install docs
- ✅ Zero linting/type/test errors
- ✅ Diff artifact generated and merged to main

---

## Post-Round Continuity

When Round 8 is complete:
1. Commit final state to `.compound-beads/context.md`
2. Update QUICKSTART.md with Round 8 completion
3. Determine if next round is:
   - Round 9: Tester fleet integration (validating MCP tools automatically)
   - Round 9: Leaderboard dataset expansion (score more services)
   - Next WU from BUILD-PLAN (context-driven)

---

## Next Round Preview (Round 9)

Round 9 will likely integrate MCP tools into the **Tester Fleet** — agents can use `rhumb find` + `rhumb get-alternatives` to autonomously discover and test related services, feeding back discovery signals into the scoring model.

Timeline: ~3 days (if slices ship on 1-day cadence).
