# Terminology Sprint — Phase 1: API + MCP Field Renames

## Context
We're implementing a terminology audit. The database column `aggregate_recommendation_score` stays as-is in Supabase. But all API RESPONSES should return `an_score` instead of `aggregate_recommendation_score`. Also, the `score` alias that already exists in some responses should be kept (it maps to the same value).

## Changes Required

### 1. API Response Field: `aggregate_recommendation_score` → `an_score`

**Schema (`packages/api/schemas/score.py`):**
- Rename `aggregate_recommendation_score` field to `an_score` in the Pydantic model
- Keep `score` alias if it exists

**Routes (all files in `packages/api/routes/`):**
- In every response dict where we build JSON, change the key from `"aggregate_recommendation_score"` to `"an_score"`
- Keep `"score"` as a top-level alias where it already exists
- DO NOT change the Supabase query strings — those reference the DB column which is still `aggregate_recommendation_score`
- The pattern is: fetch from DB using old name, return to client using new name

Example transform:
```python
# Before:
"aggregate_recommendation_score": sc.get("aggregate_recommendation_score"),
# After:
"an_score": sc.get("aggregate_recommendation_score"),
```

**Tests (all test files):**
- Update response assertions to check for `an_score` instead of `aggregate_recommendation_score`
- Mock data can keep `aggregate_recommendation_score` in DB-level mocks (that's the column name)
- Response-level assertions should use `an_score`

### 2. MCP Tool: `find_tools` → `find_services`

**`packages/mcp/src/server.ts`:**
- Rename tool registration from `find_tools` to `find_services`
- Update tool description to reference "services" not "tools"

**`packages/mcp/src/tools/` (any file defining find_tools):**
- Rename function/handler

**`packages/mcp/src/types.ts`:**
- Update any type that references find_tools

### 3. Tier Labels

Find any hardcoded tier label strings in API responses or MCP descriptions:
- "Limited" → "Emerging" (for L1)
- "Opaque" → "Emerging" (for L1)
- Keep "Developing" (L2), "Ready" (L3), "Native" (L4) as-is

### 4. Evidence Tier Labels

Find any hardcoded evidence tier strings:
- "Pending" → "Unscored"
- "Assessed" → "Docs-backed"  
- "Tested" → "Test-backed"
- "Verified" → "Runtime-verified"

### 5. MCP Description Refresh

In all MCP tool descriptions (`packages/mcp/src/server.ts` and tools files):
- Replace "managed execution" with "Rhumb Resolve"
- Replace "tools" with "services" when referring to indexed services
- Replace "execution" with "call" when referring to billing/usage units
- Make sure tool descriptions use canonical vocabulary: Service, Capability, AN Score, Rhumb Resolve, BYOK

## Rules
- ALL existing tests must pass after changes
- Do NOT rename the Supabase database column — only the API response field names
- Do NOT break the `score` alias in responses (keep both `score` and `an_score` where `score` already exists)
- Run `PYTHONPATH=packages/api python3 -m pytest packages/api/tests/ -q` to verify
