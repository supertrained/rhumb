# WU-28.2: Billing Fail-Closed (CRIT-02)

## Context
Currently, Rhumb's capability execution path is FAIL-OPEN for billing: if the Supabase credit check fails (connection timeout, 500, etc.), execution proceeds without billing. This is a company-killer — an attacker who can cause brief Supabase instability gets free executions.

## Current Code
The execution flow is in `packages/api/routes/capability_execute.py` in the `execute_capability` function.

Look at how billing/budget checks are currently done:
1. `check_agent_exec_rate_limit()` — in-memory, not Supabase-dependent
2. `check_managed_daily_limit()` — in-memory, not Supabase-dependent  
3. `check_wallet_rate_limit()` — in-memory, not Supabase-dependent
4. The actual credit deduction happens... somewhere (find it)

## Requirements

### 1. Identify the billing gate
Find where credit balance is checked and deducted. It might be in:
- `capability_execute.py` directly
- A billing service/module
- The `AgentIdentityStore`
- A Supabase RPC call

### 2. Make it fail-closed
Every execution that costs money MUST verify the credit balance BEFORE executing. If the balance check fails for ANY reason (timeout, 500, connection refused, malformed response):
- Return HTTP 503 with body:
```json
{
  "error": "billing_unavailable",
  "message": "Billing system temporarily unavailable. Execution blocked for safety.",
  "resolution": "Retry in 30 seconds. If persistent, check https://rhumb.dev/status",
  "request_id": "<request_id>"
}
```
- Do NOT proceed with execution
- Log the failure for alerting

### 3. Exemptions
- x402 on-chain payments: these are verified against the blockchain, not Supabase. They can proceed even if Supabase billing is down (the payment proof is on-chain).
- Free/rate-limited-only calls (if any exist): document clearly.

### 4. Add a billing health check function
```python
async def check_billing_health() -> tuple[bool, str]:
    """Returns (healthy, reason). Used by execute gate and /v1/status."""
```
This should:
- Attempt a lightweight Supabase query (e.g., `SELECT 1`)
- Timeout after 2 seconds
- Return (False, "timeout") or (False, "connection_error") on failure

### 5. Tests
Write tests in the appropriate test file:
- Test: billing check succeeds → execution proceeds
- Test: billing check fails (timeout) → 503 returned, NO execution
- Test: billing check fails (connection error) → 503 returned, NO execution
- Test: x402 payment → execution proceeds even if billing is down

## Files to modify
- `packages/api/routes/capability_execute.py` — main execution flow
- Potentially `packages/api/routes/billing.py` — health check
- Test files in `packages/api/tests/` or wherever tests live

## Anti-patterns to avoid
- Don't add a try/except that swallows billing errors silently
- Don't add a "maintenance mode" flag that someone has to manually toggle
- Don't make this configurable — fail-closed is not optional

When completely finished, run this command to notify me:
openclaw system event --text "Done: WU-28.2 billing fail-closed implemented and tested" --mode now
