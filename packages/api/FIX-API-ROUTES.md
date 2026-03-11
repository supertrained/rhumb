# FIX: Wire API Routes to Supabase

## Problem
The Python API routes in `routes/services.py`, `routes/leaderboard.py`, and `routes/search.py` are either stubs (returning empty arrays) or read from filesystem paths that don't exist in the Railway Docker container. This makes the MCP server return empty results.

## Solution
Rewrite these three files to query Supabase REST API directly using `httpx` (async HTTP client). The web app (`packages/web/lib/api.ts`) already has working Supabase queries — port the same logic to Python.

## Architecture
- Supabase URL and anon key come from `config.py` settings: `settings.supabase_url` and `settings.supabase_service_role_key`
- Use `httpx.AsyncClient` to call Supabase REST API (PostgREST format)
- Base URL pattern: `{supabase_url}/rest/v1/{table}?{postgrest_params}`
- Headers: `apikey: {key}`, `Authorization: Bearer {key}`

## Supabase Tables (already populated with data)
- `services` — columns: slug, name, category, description
- `scores` — columns: service_slug, aggregate_recommendation_score, execution_score, access_readiness_score, confidence, tier, tier_label, probe_metadata (JSON), calculated_at, payment_autonomy, governance_readiness, web_accessibility, payment_autonomy_rationale, governance_readiness_rationale, web_accessibility_rationale, autonomy_score

## Files to Rewrite

### 1. `routes/services.py` — Currently returns empty arrays
Port from web app's `getServicesFromSupabase()` and `getServiceScoreFromSupabase()`:

**GET /services** → Query: `services?select=slug,name,category,description&order=name.asc`
Return format: `{"data": {"items": [...], "limit": N, "offset": N}, "error": null}`

**GET /services/{slug}** → Query: `services?slug=eq.{slug}&select=slug,name,category,description&limit=1`
Join with latest score: `scores?service_slug=eq.{slug}&order=calculated_at.desc&limit=1`
Return format: `{"data": {service details + score}, "error": null}`

**GET /services/{slug}/failures** → Keep as-is for now (empty array is OK, we'll populate later)

**GET /services/{slug}/history** → Query: `scores?service_slug=eq.{slug}&order=calculated_at.desc&limit=20`

### 2. `routes/leaderboard.py` — Currently reads from filesystem (fails in Docker)
Port from web app's `getLeaderboardFromSupabase()`:

**GET /leaderboard/{category}** → 
1. Get services: `services?category=eq.{category}&select=slug,name`
2. Get scores: `scores?service_slug=in.({slugs})&order=aggregate_recommendation_score.desc.nullslast&limit={limit}`
3. Deduplicate by slug, sort by score desc

**GET /leaderboard** →
Query: `services?select=category`
Aggregate counts per category

### 3. `routes/search.py` — Currently reads from filesystem (fails in Docker)
Rewrite to use Supabase text search:

**GET /search?q=X** →
1. Query: `services?or=(slug.ilike.*{q}*,name.ilike.*{q}*,category.ilike.*{q}*,description.ilike.*{q}*)&select=slug,name,category,description`
2. For matching services, get scores: `scores?service_slug=in.({slugs})&order=aggregate_recommendation_score.desc.nullslast`
3. Join and return

## Shared Supabase Helper
Create `routes/_supabase.py`:
```python
import httpx
from config import settings

async def supabase_fetch(path: str) -> list | dict | None:
    """Fetch from Supabase REST API."""
    url = f"{settings.supabase_url}/rest/v1/{path}"
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=10.0)
        if resp.status_code != 200:
            return None
        return resp.json()
```

## Testing
After changes, verify:
1. `curl https://rhumb-api-production-f173.up.railway.app/v1/services` returns real services
2. `curl https://rhumb-api-production-f173.up.railway.app/v1/leaderboard/payments` returns ranked services
3. `curl https://rhumb-api-production-f173.up.railway.app/v1/search?q=stripe` returns Stripe
4. `curl https://rhumb-api-production-f173.up.railway.app/v1/services/stripe/score` returns score data

## Dependencies
Add `httpx` to requirements if not already present. Check `requirements.txt` or `pyproject.toml`.

## DO NOT modify
- `routes/scores.py` (already has working SQLAlchemy implementation)
- `routes/proxy.py` 
- `routes/admin_*.py`
- `app.py`
- Any test files
