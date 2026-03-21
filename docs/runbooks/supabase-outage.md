# Runbook: Supabase Outage

**Severity:** P0
**Last updated:** 2026-03-21

## Detection

- `/v1/status` returns `database: degraded` or `database: down`
- API routes return 503 with `billing_unavailable` error
- Circuit breaker trips (5 consecutive failures within 30s)
- Supabase status page: https://status.supabase.com

## Impact

- **All read endpoints degraded**: Service discovery, scores, reviews return stale cache or 503
- **All write endpoints blocked**: No new executions, no billing records, no auth
- **x402 payments exempt**: On-chain verification doesn't depend on Supabase
- **Free tier unaffected**: Read-only endpoints served from cache if available

## Immediate Actions (T0 — Automated)

1. Circuit breaker opens → read endpoints serve cached responses (TTL cache)
2. Billing health check fails → all managed executions blocked (fail-closed)
3. x402 continues operating (blockchain is the source of truth)

## Diagnosis (T1 — Pedro)

```bash
# Check Supabase status
curl -s https://status.supabase.com/api/v2/status.json | python3 -m json.tool

# Check our status endpoint
curl -s https://api.rhumb.dev/v1/status | python3 -m json.tool

# Check Supabase directly
curl -s "https://pmmkyseluruksppnejxh.supabase.co/rest/v1/services?select=count&limit=1" \
  -H "apikey: $SUPABASE_ANON_KEY" \
  -H "Authorization: Bearer $SUPABASE_ANON_KEY"

# Check Railway logs for error patterns
# (Railway dashboard → rhumb-api → Logs)
```

## Mitigation

### If partial outage (some queries slow):
1. Increase cache TTL to 300s: set `CACHE_DEFAULT_TTL=300` in Railway env
2. Monitor cache hit rate in logs
3. No user communication needed unless >5 minutes

### If full outage:
1. Confirm via Supabase status page
2. Cache continues serving stale reads — no action needed for discovery
3. Post status update: update `/v1/status` to reflect degraded state
4. All managed executions will auto-block (fail-closed billing)

## Resolution

1. Supabase confirms recovery on status page
2. Circuit breaker enters HALF_OPEN → tests with 2 successful queries
3. Circuit breaker closes → full service restored
4. Verify: `curl https://api.rhumb.dev/v1/status` shows all `operational`
5. Cache naturally refreshes on TTL expiry — no manual invalidation needed

## Escalation to Tom (T2)

Escalate if:
- Outage exceeds 2 hours
- Supabase has no ETA on status page
- Data integrity concern (missing records after recovery)
- Need to evaluate alternative database provider

## Post-Incident

- Log incident in `memory/incidents/YYYY-MM-DD-supabase-outage.md`
- Review: was cache TTL sufficient? Should circuit breaker thresholds change?
- Update this runbook with any new learnings
