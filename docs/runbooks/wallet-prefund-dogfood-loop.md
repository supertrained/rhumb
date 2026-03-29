# Runbook: wallet-prefund dogfood loop

**Last updated:** 2026-03-29
**Owner:** Pedro

## Purpose

Prove the honest repeatable payments rail that works today:

1. wallet challenge
2. wallet verify
3. wallet-prefund top-up request
4. standard x402 authorization proof submit
5. credited balance
6. optional paid execute via `X-Rhumb-Key`

This is the dogfood rail to use while wrapped / smart-wallet x402 remains compatibility-bound on production facilitator wiring.

## Honest boundary

This runbook is for:
- **EOAs / exportable private keys** on Base
- a wallet that already holds enough **USDC on Base** for the top-up
- proving the **wallet-prefund / spend-from-balance** rail

This runbook is **not** for:
- Awal wrapped / smart-wallet proof debugging
- proving generic smart-wallet interoperability
- pretending facilitator-backed wrapped-signature settlement is already solved

If you want to test the Awal smart-wallet path, use the facilitator lane. If you want the repeatable public rail that works now, use this runbook.

## Script

Operator harness:
- `scripts/wallet_prefund_dogfood.py`

What it does:
- requests a wallet auth challenge
- signs it locally with the wallet private key
- verifies into a wallet session
- requests a prefund payment envelope
- builds a standard USDC EIP-3009 authorization proof
- verifies the top-up into `org_credits`
- optionally executes a capability via `X-Rhumb-Key`

## Prerequisites

### 1) Fund the wallet first

The wallet must already hold enough **USDC on Base** to cover the top-up amount.

Minimum top-up is `$0.25`.

### 2) Export the private key into an env var

```bash
export RHUMB_DOGFOOD_WALLET_PRIVATE_KEY=0x...
```

Do **not** hardcode the key into the repo or shell history.

### 3) Use the repo Python env

Recommended:

```bash
cd rhumb
packages/api/.venv/bin/python scripts/wallet_prefund_dogfood.py --help
```

## Default proof pass

This proves:
- wallet auth
- prefund crediting
- optional paid execute on `search.query` via `brave-search-api`

```bash
cd rhumb
export RHUMB_DOGFOOD_WALLET_PRIVATE_KEY=0x...
packages/api/.venv/bin/python scripts/wallet_prefund_dogfood.py --json
```

Default execute payload:
- capability: `search.query`
- provider: `brave-search-api`
- credential mode: `rhumb_managed`
- params: `{"query":"rhumb wallet prefund dogfood smoke test","numResults":3}`

## If verify does not return a plaintext API key

Repeat wallet verifies only return `api_key_prefix`, not the full key.

If this is a dedicated dogfood wallet and rotating the key is acceptable:

```bash
cd rhumb
export RHUMB_DOGFOOD_WALLET_PRIVATE_KEY=0x...
packages/api/.venv/bin/python scripts/wallet_prefund_dogfood.py \
  --rotate-key-if-missing \
  --json
```

Use this only when key rotation will not break another live consumer.

## Top-up only

If you want to prove the credited-balance rail without execute:

```bash
cd rhumb
export RHUMB_DOGFOOD_WALLET_PRIVATE_KEY=0x...
packages/api/.venv/bin/python scripts/wallet_prefund_dogfood.py \
  --skip-execute \
  --topup-cents 25 \
  --json
```

## Success evidence to capture

A clean pass should give you:
- wallet address
- `payment_request_id`
- top-up `transaction`
- credited balance before/after
- if execute enabled:
  - capability id
  - provider
  - `execution_id`
  - remaining `org_credits`

## Failure triage

### `wallet challenge failed`
- API/base URL wrong
- auth route unhealthy
- malformed chain or address

### `wallet verify failed`
- wrong private key for the challenge address
- stale/expired challenge
- chain/address mismatch

### `top-up verify failed`
Common causes:
- wallet lacks enough USDC on Base
- wrong network
- wrong token
- settlement wallet gas issue
- invalid EIP-3009 proof shape

### `capability execute failed`
Common causes:
- no plaintext API key available and rotation not enabled
- provider/credential-mode mismatch
- managed provider unhealthy
- balance credited, but execute payload invalid

## Operational meaning

When this runbook passes, Rhumb has fresh evidence that:
- wallet auth works
- wallet-prefund credits work
- spend-from-balance works on the standard `X-Rhumb-Key` rail

That is the honest repeatable dogfood loop for payments until wrapped smart-wallet x402 is cleared end to end.
