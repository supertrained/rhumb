# WU-28.3: x402 Multi-Event Transaction Fix (CRIT-03)

## Context
The x402 USDC payment verification in Rhumb has a vulnerability: a crafted transaction with multiple Transfer events can trick the verifier. Single-tx replay is already fixed (commit `5fb71c9`), but multi-event exploitation is not.

## Current Code
The USDC verification logic is in `packages/api/services/usdc_verifier.py` (or similar — find it).

The `verify_usdc_payment()` function:
1. Takes a transaction hash
2. Fetches the transaction receipt from Base (L2)
3. Scans Transfer event logs
4. Checks: to_address matches Rhumb wallet, amount matches expected

## Vulnerability
A transaction can contain multiple ERC-20 Transfer events. An attacker can construct a tx that:
1. Transfers 1 cent USDC to Rhumb's wallet (matches address check)
2. Transfers $100 USDC to their own address (the real value)
3. The scanner finds event #1 first, amount matches the 1-cent expected amount → passes

More critically: the payment amount is estimated BEFORE execution using `min(cost_per_call)` from capability_services. If a capability has multiple providers at different prices, the 402 response quotes the cheapest, but execution might route to the expensive one.

## Requirements

### 1. Strict single-transfer validation
The verification function MUST:
- Count ALL Transfer events in the transaction that have `to_address == rhumb_wallet`
- If there is exactly 1 such transfer → validate its amount
- If there are 0 → reject ("no payment found")
- If there are >1 → reject ("ambiguous transaction: multiple transfers to Rhumb detected")
- The amount check must use the ACTUAL selected provider's cost, not the estimate

### 2. Amount re-verification
After provider selection but before returning success:
- Recalculate the billed cost based on the ACTUAL provider selected (not the pre-execution estimate)
- If payment amount < actual billed cost → reject with underpayment error
- If payment amount > actual billed cost by >20% → log as suspicious but allow (overpayment is the user's loss)

### 3. Hardening
- Verify the Transfer event's `from_address` matches the agent's declared wallet
- Verify the token contract address is the canonical USDC contract on Base (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
- Reject if transaction is not yet finalized (block confirmations < 1)

### 4. Tests
- Test: single valid transfer → passes
- Test: multiple transfers to Rhumb in same tx → rejected
- Test: transfer to Rhumb but wrong amount → rejected
- Test: transfer to Rhumb but wrong token contract → rejected
- Test: transaction with 0 transfers to Rhumb → rejected
- Test: amount check uses actual provider cost, not estimate

## Files
- `packages/api/services/usdc_verifier.py` (or find the actual location)
- `packages/api/routes/capability_execute.py` (where verify is called)
- Test files

When completely finished, run this command to notify me:
openclaw system event --text "Done: WU-28.3 x402 multi-event transaction fix with tests" --mode now
