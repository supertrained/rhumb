# WU-B3: Dashboard First-Run — Usage Display + Billing Status

## Context
The Rhumb dashboard at `/dashboard` (in `packages/astro-web/src/pages/dashboard.astro`) currently shows:
- Welcome header with name/email
- API key display/rotation
- Quick Start checklist
- Resource links

It's missing **usage display** and **billing status**, which are needed for WU-B3 completion.

## What to Build

### 1. Backend: Session-authenticated dashboard endpoints

Add to `packages/api/routes/auth.py` (or create `packages/api/routes/dashboard_api.py` and register it in `app.py`):

**`GET /v1/auth/me/usage`** — returns usage stats for the logged-in user
- Authenticate via `rhumb_session` cookie (same pattern as `/v1/auth/me`)
- Get `agent_id` from JWT claims
- Query the `query_logs` table in Supabase (if it exists) or aggregate from billing ledger
- Return:
```json
{
  "total_calls": 142,
  "calls_this_month": 42,
  "calls_today": 7,
  "recent_calls": [
    {"service": "stripe", "endpoint": "score", "timestamp": "...", "status": "success"},
    ...
  ],
  "calls_by_service": {"stripe": 23, "github": 15, "twilio": 4}
}
```
- If no usage data exists yet, return zeros gracefully (this is a dashboard for new users too)

**`GET /v1/auth/me/billing`** — returns billing status
- Authenticate via `rhumb_session` cookie
- Get `organization_id` from the user record
- Reuse logic from `routes/billing.py`'s `_require_org` but using cookie auth
- Call the existing billing balance/ledger logic
- Return:
```json
{
  "balance_usd": 10.00,
  "plan": "prepaid",
  "has_payment_method": false,
  "recent_transactions": [
    {"type": "deposit", "amount_usd": 10.00, "timestamp": "...", "description": "Stripe checkout"},
    ...
  ]
}
```
- If no billing record exists, return `{"balance_usd": 0, "plan": "free", "has_payment_method": false, "recent_transactions": []}`

### 2. Frontend: Dashboard UI updates

Update `packages/astro-web/src/pages/dashboard.astro`:

Add two new cards between the API Key card and Quick Start checklist:

**Usage card:**
- Title: "Usage"
- Show: total calls this month, calls today
- Small bar chart or list showing top services called
- "No usage yet" state for new users
- Fetches from `/v1/auth/me/usage` on load

**Billing card:**
- Title: "Billing"
- Show: current balance, plan type
- "Add funds" button linking to checkout (POST to `/v1/billing/checkout`)
- Recent transactions list (last 5)
- "No billing activity" state for new users
- Fetches from `/v1/auth/me/billing` on load

### Design Constraints
- Match existing dashboard style: `bg-slate-800/50 border border-slate-700/50 rounded-lg p-5`
- Text colors: `text-white` for headings, `text-slate-400` for secondary, `text-score-native` for accent
- Keep it minimal — this is a developer dashboard, not a analytics product
- All API calls use `credentials: "include"` for cookie auth
- Handle errors gracefully — show "Unable to load" instead of crashing

### Key Files
- Backend auth: `packages/api/routes/auth.py`
- Frontend dashboard: `packages/astro-web/src/pages/dashboard.astro`  
- Billing routes (reference): `packages/api/routes/billing.py`
- Budget routes (reference): `packages/api/routes/budget.py`
- App registration: `packages/api/app.py`
- Supabase client: `packages/api/db/client.py`
- User store: check for `get_user_store` import pattern in `routes/auth.py`

### Testing
- Run existing tests to make sure nothing breaks: `cd packages/api && source .venv/bin/activate && python -m pytest tests/ -x -q`
- The new endpoints should handle gracefully when Supabase has no data (return zeros/empty arrays)

### Commit
Commit with message: `WU-B3: Dashboard first-run — usage display + billing status`
