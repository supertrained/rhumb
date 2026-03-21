# Runbook: Billing System Failure

**Severity:** P0
**Last updated:** 2026-03-21

## Detection

- `check_billing_health()` returns `(False, reason)` — 2-second timeout
- Execution endpoint returns 503 `billing_unavailable`
- Status endpoint shows `payments: degraded`

## Impact

- **All managed executions blocked**: Fail-closed billing means zero billable executions proceed
- **x402 payments continue**: Blockchain receipt IS proof of payment — exempt from billing health
- **Free tier read endpoints**: Unaffected (discovery, scoring, search)
- **BYOK executions**: Blocked if billing tracking is required, unblocked if passthrough-only

## Immediate Actions (T0 — Automated)

1. Billing health check fails → managed execution gate blocks all billable calls
2. Response includes: `{"error": "billing_unavailable", "resolution": "Check /status"}`
3. x402 path continues operating independently

## Diagnosis (T1 — Pedro)

```bash
# Check billing health directly
curl -s https://api.rhumb.dev/v1/status | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Payments:', data.get('payments', {}).get('status', 'unknown'))
print('Database:', data.get('database', {}).get('status', 'unknown'))
"

# If Supabase is up but billing RPC fails, check the function
# Look for errors in Railway logs mentioning billing/payment/credit

# Check if it's a Supabase RPC issue vs our code
curl -s "https://pmmkyseluruksppnejxh.supabase.co/rest/v1/rpc/check_billing_health" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY"
```

## Mitigation

### If Supabase is down (root cause):
- Follow [Supabase Outage runbook](./supabase-outage.md)
- Billing will auto-recover when Supabase recovers

### If billing-specific RPC/table issue:
1. Check if recent migration broke billing tables
2. Roll back migration if needed (see [Deployment Rollback](./deployment-rollback.md))
3. Verify `capability_executions` and `org_members` tables are accessible

### If timeout-related (slow but not down):
1. Increase billing health check timeout: `BILLING_HEALTH_TIMEOUT=5` in Railway env
2. Monitor — if consistently slow, investigate Supabase query performance
3. Check for missing indexes on billing-related tables

## Resolution

1. Root cause resolved (Supabase up, RPC working, tables accessible)
2. `check_billing_health()` returns `(True, "ok")`
3. Managed executions auto-resume — no manual intervention needed
4. Verify: execute a test capability and confirm billing record created

## Critical Design Decision

**Billing is fail-closed by design.** This is intentional and non-negotiable:
- If we can't verify billing state, we don't execute
- This prevents unbounded cost exposure
- x402 is the only exception (blockchain receipt is self-proving)
- Do NOT add a bypass or fail-open mode

## Escalation to Tom (T2)

Escalate if:
- Billing data integrity concern (missing or duplicate charges)
- Stripe integration issues requiring account access
- Need to issue refunds for failed-but-charged executions
