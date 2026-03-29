# Runbook: Controlled Restart for a Wedged Awal / payments-mcp-server Daemon

**Owner:** Pedro  
**Last updated:** 2026-03-28  
**Scope:** x402 buyer-wallet recovery when the local Awal companion opens but the CLI still hangs

## Why This Exists

We now know two important truths at the same time:

1. **The funded buyer wallet identity still exists on disk** in the Awal Electron IndexedDB store.
2. **The daemon can still be wedged** even when `npx awal show` says the wallet window opened.

That means a restart is sometimes the right next move — but it should be **controlled, inspect-first, and bounded**, not a blind kill and definitely not an app-data wipe.

## Use This When

Use this runbook only after all three are true:

- `python3 rhumb/scripts/inspect_awal_wallet_state.py` confirms the funded wallet is still present locally
- `npx awal show` opens or claims to open the companion window
- bounded CLI probes like `npx awal status`, `npx awal address`, or `npx awal balance --json` still hang or time out

## Do NOT Use This For

- first-touch wallet debugging before local-state inspection
- funding problems
- missing on-disk wallet evidence
- cases where the CLI is already healthy again

And especially:

- **do not wipe** `~/Library/Application Support/Electron`
- **do not wipe** `~/Library/Application Support/awal-nodejs`

## Helper Script

A purpose-built helper now exists:

```bash
python3 rhumb/scripts/restart_awal_payments_daemon.py
```

Default behavior is **dry run** only. It will:

1. run the read-only wallet-state inspector
2. locate `payments-mcp-server`
3. run a bounded `npx awal status` probe
4. print exactly what it would do next

### Dry Run

```bash
python3 rhumb/scripts/restart_awal_payments_daemon.py
python3 rhumb/scripts/restart_awal_payments_daemon.py --json
```

Expected good dry-run signal:

- detects `payments-mcp-server` PID
- shows wallet-state summary confirming local recovery evidence
- shows `npx awal status` timing out
- recommends controlled restart rather than wipe

### Execute the Controlled Restart

```bash
python3 rhumb/scripts/restart_awal_payments_daemon.py --execute
```

What execution does:

1. sends **SIGTERM** to the detected `payments-mcp-server` PID
2. waits up to 15 seconds for clean exit
3. reopens the companion via `npx awal show`
4. runs bounded post-restart probes:
   - `npx awal status`
   - `npx awal address`
   - `npx awal balance --json`

## Guardrails

- This helper uses **SIGTERM only**. It does **not** escalate to SIGKILL.
- If the daemon does not exit cleanly, stop there and inspect; do not improvise a wipe.
- The success condition is **CLI recovery + funded wallet confirmation**, not merely “window opened.”

## Success Criteria

After the controlled restart, you want to see all of these:

1. `npx awal status` returns without hanging
2. `npx awal address` returns the funded EVM wallet:
   - `0x43Ab546B202033e4680aEB0923140Bc4105Edfed`
3. `npx awal balance --json` shows the expected Base-side wallet state
4. then rerun live x402 buyer → settle → execute proof

## Failure Interpretation

If the controlled restart completes but probes still fail:

- the issue is still in the local companion/runtime path
- it is **not** evidence that the wallet was lost
- do not revert to destructive storage deletion as a first response

## Relationship to the Earlier Recovery Runbook

Use these together, in order:

1. `rhumb/docs/runbooks/x402-awal-wallet-recovery.md` — prove local wallet identity still exists
2. `rhumb/docs/runbooks/x402-awal-controlled-restart.md` — perform the bounded restart only if UI wake attempts still leave the CLI wedged
