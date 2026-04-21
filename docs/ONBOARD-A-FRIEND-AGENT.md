# Onboard a friend’s agent (operator-minted key)

This is the fastest path for a **small controlled cohort**: mint a governed key for a new agent, set a spend limit, and hand them a copy/paste snippet.

## Prereqs

- You have the Rhumb admin key (`X-Rhumb-Admin-Key`) for the hosted environment.
- You know which organization you want the agent created under (if you don’t, the script will infer it from existing agents).

## Issue a key + set budget

```bash
export RHUMB_ADMIN_KEY="…"   # do not commit

python3 rhumb/scripts/issue_friend_key.py \
  --name "Alice Agent" \
  --budget-usd 10 \
  --budget-period monthly \
  --rate-limit-qpm 60
```

The script prints:
- `agent_id`
- `organization_id`
- the **API key** (shown once)
- a ready-to-run `curl` example

## What this key is

- This is a **governed** Rhumb execution key used via the repeat-traffic `X-Rhumb-Key` rail.
- It is **not** a provider API key.

## What to send the friend

Send them only:
- the `RHUMB_API_KEY=...` value
- the quickstart snippet

Do not send:
- admin keys
- any provider credentials
