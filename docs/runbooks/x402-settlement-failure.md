# Runbook: x402 Settlement Failure

**Severity:** P1
**Last updated:** 2026-03-21

## Detection

- Execution returns `payment_verification_failed` after user submits tx hash
- USDC transfer verification rejects valid-looking transactions
- Base network RPC endpoint is slow or unreachable

## Impact

- **x402 executions blocked**: Agents cannot pay-per-call
- **API-key executions unaffected**: Standard billing path works independently
- **No financial risk**: Failed verification = no execution = no cost exposure
- **User frustration**: Agent already sent USDC but execution didn't proceed

## Immediate Actions (T0 — Automated)

1. Verification returns specific error code explaining why verification failed
2. Agent can retry with the same tx hash (idempotent)
3. No automatic refund — USDC is on-chain and non-reversible

## Diagnosis (T1 — Pedro)

```bash
# Check Base network status
curl -s https://base.blockscout.com/api/v2/stats | python3 -m json.tool

# Verify a specific transaction
curl -s "https://base.blockscout.com/api/v2/transactions/{tx_hash}" | python3 -m json.tool

# Check our USDC verifier
# File: packages/api/services/usdc_verifier.py
# Key checks:
# 1. Single transfer to Rhumb wallet
# 2. Token contract = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
# 3. Payer wallet matches X-Payment header
# 4. Amount >= required (15% markup on provider cost)
```

## Common Failure Modes

### 1. Multiple transfers in one transaction
- **Cause**: Agent batched payments or used a router contract
- **Fix**: Agent must send a clean single-transfer transaction
- **Our stance**: Strict single-transfer validation is by design (anti-manipulation)

### 2. Wrong token contract
- **Cause**: Agent sent a different token or USDC on wrong network
- **Fix**: Must be USDC on Base (contract `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
- **Our stance**: Only USDC on Base is supported

### 3. Payer wallet mismatch
- **Cause**: Agent used a different wallet than declared in X-Payment header
- **Fix**: `wallet_address` in header must match `from_address` in transaction

### 4. Insufficient amount
- **Cause**: Agent paid exact provider cost without the 15% markup
- **Fix**: Use `/capabilities/{id}/execute/estimate` endpoint first to get exact amount

### 5. Base network congestion
- **Cause**: RPC endpoint is slow, transaction not yet confirmed
- **Fix**: Wait for confirmation, retry verification with same tx hash

## Mitigation

### If Base RPC is down:
1. Check https://status.base.org or https://base.blockscout.com
2. x402 path is unusable until Base RPC recovers
3. API-key billing continues working — agents should fall back
4. No Rhumb-side fix possible — external dependency

### If our verification logic has a bug:
1. Check recent commits to `usdc_verifier.py`
2. Roll back if needed
3. Any transactions that were correctly paid but incorrectly rejected need manual review

## Resolution

1. Root cause resolved (Base RPC up, verification logic fixed)
2. Agents can retry failed transactions — verification is idempotent
3. No refund mechanism needed — failed verification = no execution = no cost to Rhumb

## Escalation to Tom (T2)

Escalate if:
- Agent claims valid payment was rejected and tx hash checks out on Basescan
- Need to evaluate adding fallback RPC endpoints
- Legal question about holding USDC from failed verification scenarios
