# Runbook: Recover a Stuck Awal Buyer Wallet Without Wiping State

**Owner:** Pedro  
**Last updated:** 2026-03-28  
**Scope:** x402 dogfood / live buyer-wallet recovery for Awal (Coinbase Payments MCP)

## Why This Exists

The current x402 live rerun blocker is no longer Rhumb discovery, settlement, or seller-side gas. It is **buyer wallet recovery**:

- the originally funded Awal wallet on Base was `0x43Ab546B202033e4680aEB0923140Bc4105Edfed`
- a later re-auth reopened a different zero-balance wallet: `0x059952Cea0613DB7837f782E3702c8674779E3DB`
- the Electron daemon (`payments-mcp-server`) can remain alive but unresponsive, which makes `npx awal status` misleadingly look like total state loss

The critical operational rule is: **do not wipe Electron app data before checking whether the funded wallet identity still exists on disk.**

## Read-Only Recovery Signal

On 2026-03-28, a read-only inspection of the Awal Electron IndexedDB store found **both** wallet identities still present in the local LevelDB store:

- `0x43Ab546B202033e4680aEB0923140Bc4105Edfed` (the funded wallet)
- `0x059952Cea0613DB7837f782E3702c8674779E3DB` (the later zero-balance wallet)

This changes the posture from “wallet may be lost” to **“wallet state still exists locally; recovery should prefer account-selection or controlled restart over destructive reset.”**

## Safe Inspection Command

```bash
python3 rhumb/scripts/inspect_awal_wallet_state.py
```

What it does:
- scans `~/Library/Application Support/Electron/IndexedDB/https_payments-mcp.coinbase.com_0.indexeddb.leveldb`
- extracts wallet-address evidence and email strings from local files
- captures a lightweight `ps aux` snapshot for `payments-mcp-server` / `awal`
- **does not mutate anything**

## Expected Good Signal

You want to see one of these:

1. **The funded wallet address appears in the local store**
   - This means the identity still exists on disk.
   - Next action: recover via the correct account / wallet selection path.

2. **Both the funded wallet and the replacement wallet appear**
   - This means multiple wallet identities are cached locally.
   - Next action: prefer account selection or a controlled restart of the stuck daemon, not an app-data wipe.

## Recovery Ladder

### 1) Prove the wallet still exists locally

Run the inspector first:

```bash
python3 rhumb/scripts/inspect_awal_wallet_state.py
```

If the funded wallet is present, stop treating this as a data-loss problem.

### 2) Prefer the correct account before any reset

Known lead from local memory/logs:
- funded wallet recovery likely wants `tommeredith@supertrained.ai`, not `tom.d.meredith@gmail.com`

Non-destructive next try:
- bring the companion back into focus with `npx awal show`
- re-auth with the correct email/account path
- verify the returned address before funding or paying again

### 3) Only then consider a controlled daemon restart

If the process is clearly wedged and UI/account selection cannot recover the right wallet, escalate to a **controlled restart** of the stuck `payments-mcp-server` daemon.

Why this is lower risk than a wipe:
- the state already appears to exist on disk
- restart can clear a dead IPC/UI path without deleting evidence or cached identities

### 4) Do **not** lead with an app-data wipe

Avoid deleting any of these as a first move:

- `~/Library/Application Support/Electron`
- `~/Library/Application Support/awal-nodejs`

That would destroy the best local evidence about which wallet identities are still recoverable.

## After Recovery

Once the funded wallet is active again:

1. confirm address = `0x43Ab546B202033e4680aEB0923140Bc4105Edfed`
2. confirm Base balance is still present
3. rerun live x402 buyer flow
4. capture evidence for:
   - buyer discovery
   - signed payment / settlement
   - paid execute success

## Outcome This Runbook Unlocked

This runbook turns the blocker from vague (“Awal lost the wallet”) into concrete truth:

- **seller side is ready**
- **wallet state still exists locally**
- the remaining work is **interactive buyer recovery**, not more backend implementation theater
