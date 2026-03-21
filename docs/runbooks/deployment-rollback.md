# Runbook: Deployment Rollback

**Severity:** P0
**Last updated:** 2026-03-21

## Detection

- Deploy to Vercel (frontend) or Railway (API) introduces regression
- Status endpoint shows degraded after deploy
- Test suite passes locally but production behavior differs
- User reports new error that didn't exist before deploy

## Impact

- **Variable**: Depends on what broke — could be cosmetic or service-affecting
- **Frontend (Vercel)**: Static pages still served from CDN edge; SSR pages may break
- **API (Railway)**: Could block all executions if critical path affected

## Immediate Actions

### Frontend (Vercel) Rollback

```bash
# List recent deployments
# Vercel dashboard → rhumb → Deployments
# Or via CLI:
vercel ls --project rhumb

# Promote previous deployment
vercel rollback --project rhumb

# Verify
curl -s https://rhumb.dev | head -20
```

### API (Railway) Rollback

```bash
# Railway dashboard → rhumb-api → Deployments
# Click "Rollback" on the previous healthy deployment

# Or via git:
cd /Volumes/tomme\ 4TB/.openclaw/workspace-rhumb-lead/rhumb
git log --oneline -5  # Find last good commit
git revert HEAD       # Revert the bad commit
git push origin main  # Railway auto-deploys from main

# Verify
curl -s https://api.rhumb.dev/v1/status | python3 -m json.tool
```

## Diagnosis (T1 — Pedro)

```bash
# Check what changed
cd /Volumes/tomme\ 4TB/.openclaw/workspace-rhumb-lead/rhumb
git log --oneline -5
git diff HEAD~1..HEAD --stat

# Run tests locally
cd packages/api && python -m pytest tests/ -x
cd packages/astro-web && pnpm build

# Check Railway logs for errors
# Railway dashboard → rhumb-api → Logs → filter by ERROR

# Check Vercel function logs
# Vercel dashboard → rhumb → Functions → Runtime Logs
```

## Common Failure Modes

### 1. Migration broke existing queries
- **Symptom**: API returns 500 on previously-working endpoints
- **Fix**: Migrations are idempotent — but if a column rename or type change broke queries, revert the migration in Supabase SQL Editor, then revert the code

### 2. Environment variable missing
- **Symptom**: Specific feature fails, logs show `undefined` or `None`
- **Fix**: Check Railway env vars against `packages/api/.env.example`

### 3. Astro build succeeded but runtime fails
- **Symptom**: Pages return 500 on Vercel
- **Fix**: Check if `prerender = true` is set correctly; check for runtime dependencies that aren't available in serverless

### 4. Dependency version mismatch
- **Symptom**: Works locally, fails in CI/deploy
- **Fix**: Check `pnpm-lock.yaml` or `requirements.txt` for version drift

## Resolution

1. Bad commit identified and reverted (or fixed forward)
2. Tests pass locally: `python -m pytest tests/ -x` and `pnpm build`
3. Deploy verified on production: status endpoint green, sample queries work
4. If migration was involved: verify database state matches expected schema

## Prevention

- Always run full test suite before pushing to main
- Use `export const prerender = true` on all static pages
- Keep migrations idempotent (`IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`)
- Never drop or rename existing columns in migrations

## Escalation to Tom (T2)

Escalate if:
- Need Railway or Vercel account-level access
- Rollback requires database state restoration (Supabase point-in-time recovery)
- Multiple deploys in sequence make it unclear which one broke things
