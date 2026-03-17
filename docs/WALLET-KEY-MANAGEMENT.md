# Wallet Key Management — Rhumb

## Phase 1: USDC Receive Wallet (Base)

| Field | Value |
|-------|-------|
| **Address** | `0xA913150269E9FB5Fe3f79e3d8f1E790EC6BA5786` |
| **Network** | Base (mainnet + sepolia — same address works on both) |
| **Type** | EOA (Externally Owned Account) |
| **Purpose** | Receive-only wallet for x402 USDC payments |
| **Private Key** | 1Password: "Rhumb USDC Receive Wallet (Base)" in vault "OpenClaw Agents" |
| **Created** | 2026-03-17 |

## Security Rules

1. **Private key lives ONLY in 1Password.** Never in env vars, code, config files, or logs.
2. **Address** is public and safe to share — it's in the x402 402 responses.
3. **Railway env var:** Only the address goes in Railway: `RHUMB_USDC_WALLET_ADDRESS=0xA913150269E9FB5Fe3f79e3d8f1E790EC6BA5786`
4. **No outbound transactions in Phase 1.** This wallet only receives USDC. Settlement (USDC → USD) is a Phase 2 concern handled by Coinbase Commerce or manual conversion.
5. **If the key is ever compromised:** Rotate immediately (generate new wallet, update Railway env, update 1Password, sweep remaining USDC from old address).

## USDC Contract Addresses

| Network | Contract |
|---------|----------|
| Base Mainnet | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| Base Sepolia | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |

## Phase 2+ Upgrade Path

When volume justifies it, migrate from EOA to:
- **Coinbase Agentic Wallet** (MPC-based, programmatic access, no raw key exposure)
- Or **Safe (Gnosis) multisig** for higher-value operations

The address will change — update Railway env vars and the x402 response builder at that time.
