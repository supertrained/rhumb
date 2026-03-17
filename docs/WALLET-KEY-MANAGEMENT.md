# Wallet Key Management — Rhumb

> Last updated: 2026-03-17

## Phase 1: EOA Receive Wallet

**Address:** `0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623`  
**Network:** Base (Mainnet + Sepolia — same address on both)  
**Type:** EOA (Externally Owned Account) — not a smart contract wallet  
**Purpose:** Receive USDC payments from x402-capable agents  

### Key Storage
- **Primary:** 1Password vault `OpenClaw Agents`, item `Rhumb USDC Receive Wallet`
- **Fields:** `credential` (private key), `address`, `network`, `notes`
- **Access:** Pedro (via `sop`) — never expose in code, logs, or env vars

### Environment Variables (Railway)
| Variable | Value | Environment |
|---|---|---|
| `RHUMB_USDC_WALLET_ADDRESS` | `0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623` | production |

The private key is **NOT** in Railway. Only the public address is set as an env var.

### Key Operations
This wallet is **receive-only** in Phase 1:
- ✅ Receive USDC from agents paying for capability execution
- ❌ Does NOT initiate transactions
- ❌ Does NOT need ETH for gas (receive-only)
- ❌ Does NOT hold or manage tokens beyond received USDC

### Settlement
In Phase 1, USDC settlement (conversion to USD) is a manual process:
1. Transfer USDC from this wallet to Coinbase exchange
2. Convert USDC → USD
3. Track in `settlement_batches` table

Phase 2 will automate settlement via Coinbase Commerce API.

### Recovery
If the 1Password item is lost:
1. The wallet is permanently inaccessible
2. Any USDC in the wallet is permanently lost
3. Generate a new wallet and update `RHUMB_USDC_WALLET_ADDRESS` in Railway

### Phase 2 Upgrade Path
Phase 2 will move to Coinbase Agentic Wallets (MPC-based):
- No single private key — key shares distributed across Coinbase infrastructure
- Programmable spending policies
- Automated settlement
- The Phase 1 EOA wallet will be deprecated and any remaining balance swept to the new wallet
