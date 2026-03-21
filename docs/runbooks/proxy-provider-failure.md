# Runbook: Proxy Provider Failure

**Severity:** P1
**Last updated:** 2026-03-21

## Detection

- Execution endpoint returns provider-specific errors (429, 500, 502, 503)
- Execution success rate drops below 90% for a specific provider
- User reports execution failure for a specific capability

## Impact

- **Scoped**: Only executions routed to the failing provider are affected
- **Other providers**: Continue operating normally
- **Discovery/scoring**: Unaffected (no provider dependency)
- **Cost routing**: May route to suboptimal provider if cheapest is down

## Immediate Actions (T0 — Automated)

1. Cost-optimal routing skips failing provider if alternatives exist
2. Execution returns error with provider attribution in response body
3. No retry logic — agents handle their own retry strategy

## Diagnosis (T1 — Pedro)

```bash
# Check which provider is failing
curl -s "https://api.rhumb.dev/v1/capabilities/{capability_id}/execute" \
  -H "X-Rhumb-API-Key: $API_KEY" \
  -X POST -d '{}' | python3 -m json.tool

# Check provider status page (find URL in services table)
# Common status pages:
# Resend: https://status.resend.com
# Slack: https://status.slack.com

# Check if credential is expired/revoked
# Look up credential in 1Password via sop
sop item get "{Provider Name}" --vault "OpenClaw Agents" --fields credential --reveal
```

## Mitigation

### If provider is rate-limited (429):
1. Check daily cap in `rhumb_managed.py` — are we hitting our own limits?
2. If so, reduce cap or wait for reset
3. If provider-side: nothing to do, routing will skip

### If provider credential expired:
1. Rotate credential in 1Password
2. Restart Railway deployment to pick up new credential
3. Verify: test execution against the capability

### If provider is fully down:
1. Check provider status page
2. If alternative providers exist for the capability: no action (routing handles it)
3. If single-provider capability: update capability status to `degraded`
4. Communicate to users via status endpoint

## Resolution

1. Provider recovers (check their status page)
2. Test execution: `curl -X POST https://api.rhumb.dev/v1/capabilities/{id}/execute`
3. Verify success in response
4. No cache invalidation needed — executions are not cached

## Escalation to Tom (T2)

Escalate if:
- Provider requires account-level action (billing, ToS acceptance)
- Credential rotation requires human verification (OAuth re-auth)
- Provider is permanently shutting down a feature we depend on

## Post-Incident

- Log in `memory/incidents/`
- If credential-related: update credential rotation schedule
- If provider instability is recurring: evaluate alternatives, update AN Score
