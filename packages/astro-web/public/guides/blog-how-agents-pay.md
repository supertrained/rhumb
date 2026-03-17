# How AI Agents Get Wallets and Pay for Things

AI agents need to pay for API calls, compute, and data — but they can't enter a credit card number or complete a checkout flow. The payment infrastructure that works for humans doesn't work for autonomous software. This guide covers the three ways agents acquire wallets and pay for services today, with working code for each path.

## The Problem: Agents Can't Click "Buy Now"

Every payment system built before 2025 assumed a human at the keyboard. Credit card forms, 3D Secure challenges, CAPTCHA gates, redirect-based OAuth — all designed for browsers with human operators. When an AI agent needs to call a paid API mid-task, it hits a wall.

The cost of this wall is measurable. An agent that needs to pause execution, surface a payment prompt to its operator, wait for human approval, then resume loses minutes on every paid interaction. At scale — thousands of API calls per day — human-gated payments become the bottleneck that limits what agents can do autonomously.

Three solutions have emerged, each with different tradeoffs in autonomy, security, and complexity.

## Path 1: Prepaid Credit Wallets (Simplest)

**How it works:** A human pre-funds a credit balance. The agent spends from that balance via API calls. When the balance gets low, it auto-reloads from a saved payment method.

**Who it's for:** Developers who want agents to operate autonomously within a budget, without touching crypto or managing keys.

**Setup time:** Under 5 minutes.

### How an Agent Gets a Wallet

The developer (human) creates an account, tops up credits via Stripe Checkout, and hands the agent an API key. The agent never sees a payment form — it just uses the key, and costs are deducted from the credit balance automatically.

```bash
# Developer: top up credits (opens Stripe Checkout)
curl -X POST https://api.example.com/v1/billing/checkout \
  -H "X-Api-Key: rhumb_live_abc123" \
  -H "Content-Type: application/json" \
  -d '{"amount_usd": 25}'

# Agent: just call APIs — billing is invisible
curl https://api.example.com/v1/capability/execute \
  -H "X-Api-Key: rhumb_live_abc123" \
  -H "Content-Type: application/json" \
  -d '{"capability": "web.scrape", "params": {"url": "https://example.com"}}'

# Agent: check remaining balance
curl https://api.example.com/v1/billing/balance \
  -H "X-Api-Key: rhumb_live_abc123"
```

### How Payment Happens

1. Agent makes an API call
2. System checks credit balance
3. If sufficient: deduct cost, execute request, return result
4. If insufficient: return HTTP 402 with the exact amount needed
5. Auto-reload triggers if configured (saved payment method, no human required)

### Tradeoffs

- **Autonomy:** High within budget limits. Agent never waits for human approval.
- **Security:** Budget caps prevent runaway spending. Immutable ledger tracks every cent.
- **Complexity:** Near zero for the agent. The developer handles billing setup once.
- **Limitation:** Requires a human to initially fund the account and set up auto-reload.

## Path 2: x402 Protocol — Pay-Per-Request with USDC (Most Agent-Native)

**How it works:** When an API returns HTTP 402 (Payment Required), the response includes machine-readable payment instructions. The agent reads the instructions, signs a USDC transfer on Base, and retries with a payment proof header. No accounts, no sessions, no human in the loop.

**Who it's for:** Agents operating with their own crypto wallets, paying for exactly what they use at the moment they use it.

**Setup time:** Under 10 minutes (wallet creation + funding).

### How an Agent Gets a Wallet

Three sub-paths, from easiest to most flexible:

**Option A: Coinbase Agentic Wallets (recommended)**

Purpose-built for AI agents. The agent authenticates via email OTP (no private keys exposed), gets a gasless USDC wallet on Base, and can pay for services immediately.

```bash
# Create an agentic wallet (agent or developer runs this once)
npx awal status
# Follow email OTP prompt → wallet created on Base

# Fund the wallet
npx awal fund
# Opens Coinbase Onramp → select amount → USDC deposited

# The wallet now has a Base address and USDC balance
# Agent can pay for x402-enabled services automatically
```

Built-in skills handle the entire x402 flow:
- `search-for-service` — discover paid APIs
- `pay-for-service` — handle 402 → sign → retry automatically
- `send-usdc` — direct USDC transfers

**Option B: Coinbase AgentKit Server Wallets**

The developer provisions wallets programmatically via the CDP API. Better for managing fleets of agents where each needs its own wallet.

```typescript
import { AgentKit, CdpV2WalletProvider } from "@coinbase/agentkit";

const walletProvider = await CdpV2WalletProvider.configureWithWallet({
  apiKeyId: process.env.CDP_API_KEY_ID,
  apiKeySecret: process.env.CDP_API_KEY_SECRET,
  walletSecret: process.env.CDP_WALLET_SECRET,
  networkId: "base",
  idempotencyKey: "agent-007-wallet",
});

const agentkit = await AgentKit.from({ walletProvider });
const details = await agentkit.getWalletDetails();
// → { address: "0x...", network: "base", balance: "25.00 USDC" }
```

Developer signs up at [portal.cdp.coinbase.com](https://portal.cdp.coinbase.com) (free). First 5,000 wallet operations per month are free, then $0.005 per operation.

**Option C: Self-Custody EOA**

The developer generates a standard Ethereum wallet and funds it with USDC on Base. Maximum control, maximum responsibility.

```bash
# Generate a wallet (keep the private key secure!)
cast wallet new
# → Address: 0xABC...
# → Private Key: 0x123...

# Fund with USDC on Base via any exchange or bridge
# Agent signs x402 payments using the private key
```

### The x402 Payment Flow

```
Agent                          Paid API
  |                               |
  |  GET /v1/premium-data         |
  |------------------------------>|
  |                               |
  |  402 Payment Required         |
  |  {                            |
  |    "x402Version": 1,          |
  |    "accepts": [{              |
  |      "scheme": "exact",       |
  |      "network": "base",       |
  |      "asset": "USDC",         |
  |      "amount": "0.01",        |
  |      "payTo": "0xDEF..."      |
  |    }]                         |
  |  }                            |
  |<------------------------------|
  |                               |
  |  [Agent signs USDC transfer]  |
  |                               |
  |  GET /v1/premium-data         |
  |  X-Payment: {tx_hash, proof}  |
  |------------------------------>|
  |                               |
  |  200 OK + data                |
  |  X-Payment-Response: receipt  |
  |<------------------------------|
```

### Tradeoffs

- **Autonomy:** Maximum. Agent pays and proceeds without any human involvement.
- **Security:** On-chain verification. Replay protection via unique transaction hashes. Spending limits configurable per wallet.
- **Complexity:** Medium. Requires wallet setup and USDC funding. Agent needs signing capability.
- **Limitation:** Requires USDC on Base. Settlement happens on-chain (transparent but irreversible).

## Path 3: Enterprise Agent Cards (Highest Control)

**How it works:** The organization issues virtual cards (via Ramp, Brex, or similar) with agent-specific spending rules. The agent uses the card number programmatically for services that accept card payments.

**Who it's for:** Enterprises managing dozens of agents with strict compliance, audit, and approval requirements.

**Setup time:** Varies by provider (Ramp: ~30 minutes for card issuance).

### How an Agent Gets a Card

```
1. Admin creates a virtual card in Ramp/Brex dashboard
2. Sets per-transaction limit ($5), monthly limit ($500), merchant category restrictions
3. Card details (number, expiry, CVC) stored in a secrets manager
4. Agent retrieves card details at runtime for payment
```

### Tradeoffs

- **Autonomy:** Moderate. Agent can pay independently within card limits, but card setup requires human admin.
- **Security:** Highest. Real-time spend controls, merchant restrictions, instant freeze capability, full audit trail via card provider.
- **Complexity:** High. Requires enterprise card provider account, card issuance workflow, secrets management.
- **Limitation:** Only works for services that accept card payments via API. Many API providers don't support programmatic card entry — they require Stripe Checkout or similar human flows.

## Which Path Should You Use?

| Factor | Prepaid Credits | x402 USDC | Enterprise Cards |
|--------|----------------|-----------|-----------------|
| Setup time | 5 min | 10 min | 30+ min |
| Human involvement | Initial funding only | None after setup | Card issuance |
| Agent autonomy | High (within budget) | Maximum | Moderate |
| Cost visibility | Per-execution ledger | On-chain receipts | Card statement |
| Best for | Individual developers | Agent-to-agent commerce | Enterprise compliance |
| Works with | Any API key service | x402-enabled services | Card-accepting services |

**Start with prepaid credits** if you want the fastest path to an agent that can pay for things. **Move to x402** when your agents need to pay other agents or services without any human in the loop. **Use enterprise cards** when compliance and audit requirements demand it.

## The Convergence: All Three at Once

The most robust agent payment architecture supports all three paths simultaneously. When an agent hits a paid service:

1. **Check credit balance first** (fastest, cheapest)
2. **Fall back to x402 USDC** if credits are exhausted (no human needed)
3. **Fall back to enterprise card** for services that only accept cards

This is the x402 protocol in action: the 402 response includes multiple payment options, and the agent picks the best one based on what it has available.

```json
{
  "x402Version": 1,
  "accepts": [
    {
      "scheme": "exact",
      "network": "base",
      "asset": "USDC",
      "amount": "0.01",
      "payTo": "0xDEF..."
    },
    {
      "scheme": "stripe",
      "checkoutUrl": "https://checkout.stripe.com/c/pay/cs_test_..."
    }
  ],
  "balanceRequired": 1,
  "balanceRequiredUsd": "0.01"
}
```

## What Services Need to Do

If you run an API and want agents to pay you, you need two things:

1. **A wallet to receive USDC** (for x402 payments) — a standard Ethereum address on Base
2. **A Stripe account** (for credit-based payments) — your existing account works

Your API returns 402 with payment instructions when an unauthenticated or underfunded request arrives. The agent handles the rest. No checkout pages, no redirect flows, no human intervention.

## Further Reading

- [x402 Protocol Specification](https://www.x402.org/x402-whitepaper.pdf) — the HTTP-native payment standard
- [Coinbase AgentKit Documentation](https://docs.cdp.coinbase.com/agent-kit/welcome) — agent wallet SDK
- [Coinbase Agentic Wallets](https://docs.cdp.coinbase.com/agentic-wallet/welcome) — purpose-built agent wallets
- [Rhumb Pricing](/pricing) — how Rhumb implements all three payment paths
