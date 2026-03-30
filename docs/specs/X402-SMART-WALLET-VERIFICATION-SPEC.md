# Spec: x402 Smart Wallet Signature Verification

**Status:** Draft  
**Date:** 2026-03-30  
**Source:** [Expert Panel](../panels/X402-SMART-WALLET-SETTLEMENT-PANEL-2026-03-30.md)  
**Owner:** Pedro  
**Scope:** `x402_local_settlement.py` — add ERC-1271 smart wallet signature verification and bytes-variant ABI encoding

---

## Problem

`verify_authorization_signature()` uses `ecrecover`, which only works for 64/65-byte raw ECDSA signatures (EOA wallets). Coinbase Smart Wallet (Awal) produces ~640-byte ERC-1271/EIP-6492 wrapped signatures. These are valid on-chain — the USDC contract calls `isValidSignature` on contract addresses — but Rhumb's off-chain verification rejects them.

**Impact:** Beacon's Awal wallet ($5 USDC on Base) cannot pay Rhumb.

## Solution

Dual-path verification: detect signature type, route to `ecrecover` (EOA) or `eth_call` to `isValidSignature` (smart wallet).

---

## Verification Algorithm

```
async verify_authorization_signature(authorization, signature) -> VerifyResult:
  1. Parse signature bytes from hex
  2. Reject if sig_len > 2048 bytes (payload inflation guard)
  3. Validate timeliness:
     - validBefore == 0 OR now < validBefore
     - validAfter == 0 OR now >= validAfter
  4. Compute EIP-712 digest for TransferWithAuthorization

  5a. IF sig_len in (64, 65):
      - ecrecover(digest, signature) → recovered_address
      - Verify recovered_address == authorization.from
      - Return valid

  5b. ELSE (sig_len > 65):
      - eth_getCode(authorization.from) → code
      - IF code is empty: return invalid ("signature too long for EOA")
      - eth_call: authorization.from.isValidSignature(digest, signature)
        - Timeout: 3 seconds
        - If return != 0x1626ba7e: return invalid
      - eth_call: USDC.balanceOf(authorization.from)
        - Timeout: 3 seconds
        - If balance < authorization.value: return invalid ("insufficient balance")
      - Return valid (signer = authorization.from)
```

### Key Design Decisions

1. **Signature length is the dispatch signal.** 64/65 bytes → EOA path. >65 bytes → smart wallet path. This avoids an RPC call for the common (EOA) case.

2. **`eth_getCode` confirms contract existence.** If someone sends a >65-byte signature from an EOA address (no contract code), it's definitively invalid.

3. **Balance check is mandatory for smart wallets.** A malicious contract can return `0x1626ba7e` from `isValidSignature` without holding any USDC. The balance check catches this.

4. **3-second timeout on all RPC calls.** Prevents a malicious `isValidSignature` implementation from delaying responses. The existing 15-second httpx timeout is too generous for this path.

5. **Function is now `async`.** Smart wallet verification requires network calls. All callers must be updated.

---

## ABI Encoding: Bytes-Variant Settlement

### Current (EOA only)
```
transferWithAuthorization(address,address,uint256,uint256,uint256,bytes32,uint8,bytes32,bytes32)
Selector: 0xe3ee160e
```
Encodes `v`, `r`, `s` as discrete parameters. Requires splitting the signature.

### New (Smart Wallet)
```
transferWithAuthorization(address,address,uint256,uint256,uint256,bytes32,bytes)
Selector: 0xe3e3bdb1
```
Passes raw signature bytes. Required because smart wallet signatures can't be split into `v/r/s`.

### Encoding Logic
```python
TRANSFER_WITH_AUTH_BYTES_SELECTOR = "e3e3bdb1"

def abi_encode_transfer_with_authorization_bytes(
    from_addr, to_addr, value, valid_after, valid_before, nonce, signature_bytes
) -> str:
    # Standard ABI encoding with dynamic bytes parameter
    # Fixed params at positions 0-5 (6 × 32 bytes)
    # Offset pointer to bytes at position 6 (= 0xe0 = 224)
    # Bytes length + padded data after fixed section
```

### Dispatch in `verify_and_settle()`
```python
sig_bytes = _signature_bytes(signature)
if len(sig_bytes) in (64, 65):
    v, r, s = _split_signature(signature)
    call_data = abi_encode_transfer_with_authorization(...)  # existing v/r/s
else:
    call_data = abi_encode_transfer_with_authorization_bytes(
        ..., signature_bytes=sig_bytes
    )  # new bytes variant
```

---

## RPC Call Specifications

### `eth_getCode(address)`
- **Purpose:** Determine if `from` is a contract
- **Caching:** In-memory, 1-hour TTL, keyed by `address.lower()`
- **Failure mode:** If RPC fails, treat as EOA (fail safely to the `ecrecover` path, which will reject the long signature)

### `isValidSignature(bytes32 hash, bytes signature)`
- **Target:** `authorization.from` address
- **Selector:** `0x1626ba7e`
- **Input ABI:** `abi.encode(bytes32, bytes)`
  - `hash`: the EIP-712 typed data hash
  - `signature`: raw signature bytes from the payment payload
- **Expected return:** `0x1626ba7e` (left-padded to 32 bytes)
- **Timeout:** 3 seconds
- **Failure mode:** Any revert, timeout, or non-magic return → verification fails

### `balanceOf(address)`
- **Target:** USDC contract (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
- **Selector:** `0x70a08231`
- **Input ABI:** `abi.encode(address)`
- **Return:** `uint256` balance in atomic USDC (6 decimals)
- **Timeout:** 3 seconds
- **Failure mode:** If RPC fails, reject the payment (fail closed)

---

## Error Responses

### New error codes (added to existing set)

| `error_code` | Meaning | `retryable_with_facilitator` |
|---|---|---|
| `smart_wallet_not_contract` | `from` address has no code but signature is >65 bytes | `false` |
| `smart_wallet_signature_invalid` | `isValidSignature` returned non-magic value | `false` |
| `smart_wallet_signature_timeout` | `isValidSignature` call timed out | `true` |
| `smart_wallet_insufficient_balance` | USDC balance < authorized value | `false` |
| `smart_wallet_rpc_error` | RPC call failed (network issue) | `true` |
| `signature_too_large` | Signature exceeds 2048 bytes | `false` |

---

## Changes to Existing Code

### `x402_local_settlement.py`

1. **`verify_authorization_signature()`** → becomes `async`, adds smart wallet path
2. **New: `abi_encode_transfer_with_authorization_bytes()`** — bytes-variant encoder
3. **New: `_check_is_contract(address)`** — cached `eth_getCode` wrapper
4. **New: `_check_usdc_balance(address)`** — `balanceOf` call
5. **New: `_call_is_valid_signature(address, digest, signature)`** — `isValidSignature` call
6. **`LocalX402Settlement.verify_and_settle()`** — dispatch to bytes-variant encoding for smart wallet signatures; `await` the now-async verification

### `x402_settlement.py`

7. **`X402SettlementService.verify_and_settle()`** — `await` the inner local settlement call (already async; no change needed if the inner call is awaited correctly)

### `capability_execute.py`

8. No changes required — the route calls `_x402_settlement.verify_and_settle()` which is already async.

---

## Security Invariants

1. **EOA path is unchanged.** All existing 64/65-byte signature flows must produce identical results. Zero regressions.
2. **Smart wallet path requires all three checks.** Signature verification AND balance check AND contract existence. Skipping any one opens an attack vector.
3. **Fail closed on RPC errors for balance.** If we can't verify the balance, reject the payment. Lost sale is better than free API access.
4. **Fail open on RPC errors for `eth_getCode`.** If we can't determine contract status, try `ecrecover` (which will fail for smart wallet signatures) → return the existing `unsupported_local_signature_format` error with `retryable_with_facilitator: true`.
5. **No new trust assumptions.** We trust the Base RPC endpoint (already trusted for settlement). We trust the USDC contract (already trusted). We do NOT trust the `from` address's `isValidSignature` implementation — the balance check compensates.

---

## Testing Plan

### Unit Tests
- EOA 65-byte signature: passes (existing, unchanged)
- EOA 64-byte signature: passes (existing, unchanged)
- Smart wallet 640-byte signature from deployed contract with balance: passes
- Smart wallet signature from address with no code: fails with `smart_wallet_not_contract`
- Smart wallet signature where `isValidSignature` returns wrong magic: fails
- Smart wallet signature where balance is zero: fails with `smart_wallet_insufficient_balance`
- Signature >2048 bytes: fails with `signature_too_large`
- RPC timeout on `isValidSignature`: fails with `smart_wallet_signature_timeout`

### Integration Test (Beacon's Awal Wallet)
- Beacon signs EIP-3009 authorization for $0.01 USDC
- Rhumb verifies (off-chain `isValidSignature` call succeeds)
- Rhumb settles (on-chain `transferWithAuthorization` with bytes variant succeeds)
- USDC moves from Beacon's wallet to Rhumb's `payTo` address
- `usdc_receipts` row created, `PAYMENT-RESPONSE` header returned

---

## Implementation Order

1. **WU-1 + WU-4:** Make `verify_authorization_signature` async, add smart wallet path with `isValidSignature` + balance check (single PR)
2. **WU-2:** Add `abi_encode_transfer_with_authorization_bytes()`, wire into `verify_and_settle` (same PR)
3. **WU-3:** `eth_getCode` caching (can be same or follow-up PR)
4. **WU-5:** Integration test with Beacon's wallet (after deploy)

**Estimated effort:** 1-2 days for WU-1+2+4. Half day for WU-3. Half day for WU-5.

---

## Appendix: USDC v2.2 Contract Reference

The USDC contract on Base (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`) implements two variants of `transferWithAuthorization`:

```solidity
// Legacy (v/r/s discrete params)
function transferWithAuthorization(
    address from, address to, uint256 value,
    uint256 validAfter, uint256 validBefore, bytes32 nonce,
    uint8 v, bytes32 r, bytes32 s
) external;

// EIP-3009 v2 (bytes signature)
function transferWithAuthorization(
    address from, address to, uint256 value,
    uint256 validAfter, uint256 validBefore, bytes32 nonce,
    bytes memory signature
) external;
```

Both internally compute the EIP-712 digest and:
- For EOA (`from` has no code): `ecrecover` with the signature
- For contract (`from` has code): `IERC1271(from).isValidSignature(digest, signature)`

The `bytes` variant is the forward-compatible choice for smart wallets.

### ERC-1271 Interface
```solidity
interface IERC1271 {
    function isValidSignature(bytes32 hash, bytes memory signature)
        external view returns (bytes4 magicValue);
    // magicValue must be 0x1626ba7e for valid signatures
}
```
